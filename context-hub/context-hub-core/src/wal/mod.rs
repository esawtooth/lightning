//! Write-Ahead Log (WAL) for durability
//! 
//! Append-only log that ensures all mutations are persisted before being applied.
//! Supports concurrent writes, automatic rotation, and crash recovery.

use anyhow::{anyhow, Result};
use bytes::{Buf, BufMut, BytesMut};
use crc32fast::Hasher;
use parking_lot::RwLock;
use std::fs::{File, OpenOptions};
use std::io::{BufReader, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use tokio::sync::mpsc;
use uuid::Uuid;

const MAGIC: &[u8] = b"CTXWAL01";
const SEGMENT_SIZE: u64 = 128 * 1024 * 1024; // 128MB segments

/// A single log entry
#[derive(Debug, Clone)]
pub struct LogEntry {
    pub sequence: u64,
    pub timestamp: u64,
    pub user_id: String,
    pub doc_id: Uuid,
    pub operation: Operation,
}

#[derive(Debug, Clone)]
pub enum Operation {
    Create {
        name: String,
        doc_type: String,
        initial_content: Vec<u8>,
    },
    Update {
        crdt_ops: Vec<u8>,
    },
    Delete,
    UpdateAcl {
        acl: Vec<u8>,
    },
    Move {
        new_parent: Option<Uuid>,
    },
}

/// Thread-safe write-ahead log
pub struct WriteAheadLog {
    dir: PathBuf,
    current_segment: Arc<RwLock<Segment>>,
    sequence: Arc<AtomicU64>,
    rotation_tx: mpsc::Sender<()>,
}

struct Segment {
    id: u64,
    file: File,
    size: u64,
    path: PathBuf,
}

impl WriteAheadLog {
    pub async fn new(dir: impl AsRef<Path>) -> Result<Self> {
        let dir = dir.as_ref().to_path_buf();
        std::fs::create_dir_all(&dir)?;
        
        // Find the latest segment or create first one
        let (segment_id, sequence) = Self::find_latest_segment(&dir)?;
        let segment = Segment::create(&dir, segment_id)?;
        
        let (rotation_tx, mut rotation_rx) = mpsc::channel(1);
        let current_segment = Arc::new(RwLock::new(segment));
        let segment_clone = Arc::clone(&current_segment);
        let dir_clone = dir.clone();
        
        // Background rotation task
        tokio::spawn(async move {
            while rotation_rx.recv().await.is_some() {
                let mut segment = segment_clone.write();
                if segment.size >= SEGMENT_SIZE {
                    if let Ok(new_segment) = Segment::create(&dir_clone, segment.id + 1) {
                        *segment = new_segment;
                    }
                }
            }
        });
        
        Ok(Self {
            dir,
            current_segment,
            sequence: Arc::new(AtomicU64::new(sequence)),
            rotation_tx,
        })
    }
    
    /// Append an entry to the log
    pub async fn append(&self, entry: LogEntry) -> Result<u64> {
        let sequence = self.sequence.fetch_add(1, Ordering::SeqCst);
        let mut entry = entry;
        entry.sequence = sequence;
        
        let encoded = Self::encode_entry(&entry)?;
        
        // Write with rotation check
        {
            let mut segment = self.current_segment.write();
            segment.file.write_all(&encoded)?;
            segment.file.sync_data()?;
            segment.size += encoded.len() as u64;
        }
        
        // Check if rotation needed (non-blocking)
        let _ = self.rotation_tx.try_send(());
        
        Ok(sequence)
    }
    
    /// Read entries from a sequence number
    pub fn read_from(&self, start_seq: u64) -> Result<Vec<LogEntry>> {
        let mut entries = Vec::new();
        
        // Read all segments
        for segment_id in 0.. {
            let path = self.segment_path(segment_id);
            if !path.exists() {
                break;
            }
            
            let file = File::open(&path)?;
            let mut reader = BufReader::new(file);
            
            // Verify magic
            let mut magic = [0u8; 8];
            if reader.read_exact(&mut magic).is_err() {
                continue;
            }
            if &magic != MAGIC {
                return Err(anyhow!("Invalid WAL segment"));
            }
            
            // Read entries
            while let Ok(entry) = Self::decode_entry(&mut reader) {
                if entry.sequence >= start_seq {
                    entries.push(entry);
                }
            }
        }
        
        Ok(entries)
    }
    
    /// Compact old segments by removing entries for deleted documents
    /// Returns (segments_processed, entries_removed, bytes_freed)
    pub async fn compact(&self, active_docs: &[Uuid]) -> Result<(usize, usize, u64)> {
        let active_set: std::collections::HashSet<Uuid> = active_docs.iter().cloned().collect();
        let mut segments_processed = 0;
        let mut entries_removed = 0;
        let mut bytes_freed = 0u64;

        // Get all segment files
        let mut segment_files = Vec::new();
        for entry in std::fs::read_dir(&self.dir)? {
            let entry = entry?;
            let name = entry.file_name();
            if let Some(name_str) = name.to_str() {
                if name_str.starts_with("wal-") && name_str.ends_with(".log") {
                    if let Ok(id) = name_str[4..name_str.len()-4].parse::<u64>() {
                        // Don't compact the current segment
                        let current_id = self.current_segment.read().id;
                        if id < current_id {
                            segment_files.push((id, entry.path()));
                        }
                    }
                }
            }
        }

        // Process each segment
        for (_seg_id, path) in segment_files {
            let original_size = std::fs::metadata(&path)?.len();
            
            // Read all entries and filter out deleted documents
            let mut kept_entries = Vec::new();
            let file = File::open(&path)?;
            let mut reader = BufReader::new(file);
            
            // Skip magic
            reader.seek(SeekFrom::Start(8))?;
            
            while let Ok(entry) = Self::decode_entry(&mut reader) {
                // Keep entries for active documents or delete operations
                // (we keep delete operations for audit trail)
                if active_set.contains(&entry.doc_id) || matches!(entry.operation, Operation::Delete) {
                    kept_entries.push(entry);
                } else {
                    entries_removed += 1;
                }
            }

            // If we removed any entries, rewrite the segment
            if entries_removed > 0 {
                let temp_path = path.with_extension("tmp");
                {
                    let mut temp_file = OpenOptions::new()
                        .create(true)
                        .write(true)
                        .truncate(true)
                        .open(&temp_path)?;
                    
                    // Write magic
                    temp_file.write_all(MAGIC)?;
                    
                    // Write kept entries
                    for entry in kept_entries {
                        let encoded = Self::encode_entry(&entry)?;
                        temp_file.write_all(&encoded)?;
                    }
                    
                    temp_file.sync_all()?;
                }
                
                // Calculate freed bytes
                let new_size = std::fs::metadata(&temp_path)?.len();
                bytes_freed += original_size.saturating_sub(new_size);
                
                // Atomically replace the original file
                std::fs::rename(temp_path, path)?;
                segments_processed += 1;
            }
        }

        Ok((segments_processed, entries_removed, bytes_freed))
    }

    /// Remove old WAL segments that have been included in snapshots
    /// Only removes segments older than the given cutoff time
    pub async fn cleanup_old_segments(&self, cutoff_timestamp: u64) -> Result<(usize, u64)> {
        let mut removed_count = 0;
        let mut freed_bytes = 0u64;

        for entry in std::fs::read_dir(&self.dir)? {
            let entry = entry?;
            let name = entry.file_name();
            if let Some(name_str) = name.to_str() {
                if name_str.starts_with("wal-") && name_str.ends_with(".log") {
                    if let Ok(id) = name_str[4..name_str.len()-4].parse::<u64>() {
                        let current_id = self.current_segment.read().id;
                        
                        // Only remove segments older than current and before cutoff
                        if id < current_id {
                            let path = entry.path();
                            
                            // Check if all entries in this segment are before cutoff
                            let mut all_before_cutoff = true;
                            if let Ok(file) = File::open(&path) {
                                let mut reader = BufReader::new(file);
                                reader.seek(SeekFrom::Start(8)).ok();
                                
                                while let Ok(entry) = Self::decode_entry(&mut reader) {
                                    if entry.timestamp > cutoff_timestamp {
                                        all_before_cutoff = false;
                                        break;
                                    }
                                }
                            }
                            
                            if all_before_cutoff {
                                if let Ok(metadata) = entry.metadata() {
                                    freed_bytes += metadata.len();
                                }
                                std::fs::remove_file(path)?;
                                removed_count += 1;
                            }
                        }
                    }
                }
            }
        }

        Ok((removed_count, freed_bytes))
    }
    
    fn find_latest_segment(dir: &Path) -> Result<(u64, u64)> {
        let mut max_id = 0;
        let mut max_seq = 0;
        
        for entry in std::fs::read_dir(dir)? {
            let entry = entry?;
            let name = entry.file_name();
            if let Some(name_str) = name.to_str() {
                if name_str.starts_with("wal-") && name_str.ends_with(".log") {
                    if let Ok(id) = name_str[4..name_str.len()-4].parse::<u64>() {
                        max_id = max_id.max(id);
                        
                        // Find max sequence in this segment
                        if let Ok(seq) = Self::find_max_sequence(&entry.path()) {
                            max_seq = max_seq.max(seq);
                        }
                    }
                }
            }
        }
        
        // For empty directory, start from 0
        let next_seq = if max_seq == 0 && max_id == 0 { 0 } else { max_seq + 1 };
        Ok((max_id, next_seq))
    }
    
    fn find_max_sequence(path: &Path) -> Result<u64> {
        let mut max_seq = 0;
        let file = File::open(path)?;
        let mut reader = BufReader::new(file);
        
        // Skip magic
        reader.seek(SeekFrom::Start(8))?;
        
        while let Ok(entry) = Self::decode_entry(&mut reader) {
            max_seq = max_seq.max(entry.sequence);
        }
        
        Ok(max_seq)
    }
    
    fn segment_path(&self, id: u64) -> PathBuf {
        self.dir.join(format!("wal-{:08}.log", id))
    }
    
    fn encode_entry(entry: &LogEntry) -> Result<Vec<u8>> {
        let mut buf = BytesMut::new();
        
        // Header
        buf.put_u64(entry.sequence);
        buf.put_u64(entry.timestamp);
        buf.put_u32(entry.user_id.len() as u32);
        buf.put(entry.user_id.as_bytes());
        buf.put_slice(entry.doc_id.as_bytes());
        
        // Operation
        match &entry.operation {
            Operation::Create { name, doc_type, initial_content } => {
                buf.put_u8(1);
                buf.put_u32(name.len() as u32);
                buf.put(name.as_bytes());
                buf.put_u32(doc_type.len() as u32);
                buf.put(doc_type.as_bytes());
                buf.put_u32(initial_content.len() as u32);
                buf.put(initial_content.as_slice());
            }
            Operation::Update { crdt_ops } => {
                buf.put_u8(2);
                buf.put_u32(crdt_ops.len() as u32);
                buf.put(crdt_ops.as_slice());
            }
            Operation::Delete => {
                buf.put_u8(3);
            }
            Operation::UpdateAcl { acl } => {
                buf.put_u8(4);
                buf.put_u32(acl.len() as u32);
                buf.put(acl.as_slice());
            }
            Operation::Move { new_parent } => {
                buf.put_u8(5);
                if let Some(parent) = new_parent {
                    buf.put_u8(1);
                    buf.put_slice(parent.as_bytes());
                } else {
                    buf.put_u8(0);
                }
            }
        }
        
        // Length prefix and CRC
        let data = buf.freeze();
        let mut hasher = Hasher::new();
        hasher.update(&data);
        let crc = hasher.finalize();
        
        let mut result = BytesMut::new();
        result.put_u32(data.len() as u32 + 4); // Include CRC in length
        result.put(data);
        result.put_u32(crc);
        
        Ok(result.freeze().to_vec())
    }
    
    fn decode_entry<R: Read>(reader: &mut R) -> Result<LogEntry> {
        // Read length
        let mut len_buf = [0u8; 4];
        reader.read_exact(&mut len_buf)?;
        let len = u32::from_be_bytes(len_buf) as usize;
        
        // Read data + CRC
        let mut buf = vec![0u8; len];
        reader.read_exact(&mut buf)?;
        
        // Verify CRC
        let data_len = len - 4;
        let data = &buf[..data_len];
        let crc = u32::from_be_bytes([buf[data_len], buf[data_len+1], buf[data_len+2], buf[data_len+3]]);
        
        let mut hasher = Hasher::new();
        hasher.update(data);
        if hasher.finalize() != crc {
            return Err(anyhow!("CRC mismatch"));
        }
        
        // Decode entry
        let mut cursor = std::io::Cursor::new(data);
        
        let sequence = cursor.get_u64();
        let timestamp = cursor.get_u64();
        
        let user_len = cursor.get_u32() as usize;
        let mut user_buf = vec![0u8; user_len];
        cursor.read_exact(&mut user_buf)?;
        let user_id = String::from_utf8(user_buf)?;
        
        let mut doc_id_buf = [0u8; 16];
        cursor.read_exact(&mut doc_id_buf)?;
        let doc_id = Uuid::from_bytes(doc_id_buf);
        
        let op_type = cursor.get_u8();
        let operation = match op_type {
            1 => {
                let name_len = cursor.get_u32() as usize;
                let mut name_buf = vec![0u8; name_len];
                cursor.read_exact(&mut name_buf)?;
                let name = String::from_utf8(name_buf)?;
                
                let type_len = cursor.get_u32() as usize;
                let mut type_buf = vec![0u8; type_len];
                cursor.read_exact(&mut type_buf)?;
                let doc_type = String::from_utf8(type_buf)?;
                
                let content_len = cursor.get_u32() as usize;
                let mut initial_content = vec![0u8; content_len];
                cursor.read_exact(&mut initial_content)?;
                
                Operation::Create { name, doc_type, initial_content }
            }
            2 => {
                let ops_len = cursor.get_u32() as usize;
                let mut crdt_ops = vec![0u8; ops_len];
                cursor.read_exact(&mut crdt_ops)?;
                Operation::Update { crdt_ops }
            }
            3 => Operation::Delete,
            4 => {
                let acl_len = cursor.get_u32() as usize;
                let mut acl = vec![0u8; acl_len];
                cursor.read_exact(&mut acl)?;
                Operation::UpdateAcl { acl }
            }
            5 => {
                let has_parent = cursor.get_u8();
                let new_parent = if has_parent == 1 {
                    let mut parent_buf = [0u8; 16];
                    cursor.read_exact(&mut parent_buf)?;
                    Some(Uuid::from_bytes(parent_buf))
                } else {
                    None
                };
                Operation::Move { new_parent }
            }
            _ => return Err(anyhow!("Unknown operation type")),
        };
        
        Ok(LogEntry {
            sequence,
            timestamp,
            user_id,
            doc_id,
            operation,
        })
    }
}

impl Segment {
    fn create(dir: &Path, id: u64) -> Result<Self> {
        let path = dir.join(format!("wal-{:08}.log", id));
        let mut file = OpenOptions::new()
            .create(true)
            .write(true)
            .read(true)
            .open(&path)?;
        
        // Write magic if new file
        if file.metadata()?.len() == 0 {
            file.write_all(MAGIC)?;
            file.sync_data()?;
        }
        
        let size = file.metadata()?.len();
        
        Ok(Self {
            id,
            file,
            size,
            path,
        })
    }
}

#[cfg(test)]
mod tests;

#[cfg(test)]
pub use tests::*;