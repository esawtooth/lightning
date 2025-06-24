use fuser::{Filesystem, Request, ReplyEntry, ReplyAttr, ReplyData, ReplyDirectory};
use std::time::{Duration, UNIX_EPOCH};
use std::ffi::OsStr;
use super::*;

pub struct ContextHubFuse {
    storage: Arc<dyn Storage>,
    /// Maps inode numbers to document IDs
    inode_map: RwLock<BiMap<u64, String>>,
    /// Next available inode
    next_inode: AtomicU64,
}

impl ContextHubFuse {
    pub fn new(storage: Arc<dyn Storage>) -> Self {
        Self {
            storage,
            inode_map: RwLock::new(BiMap::new()),
            next_inode: AtomicU64::new(2), // 1 is reserved for root
        }
    }

    async fn document_to_attr(&self, doc: &Document, ino: u64) -> FileAttr {
        let size = match &doc.document_type {
            DocumentType::Text(content) => content.len() as u64,
            DocumentType::Folder => 4096,
            DocumentType::IndexGuide => 0,
        };

        FileAttr {
            ino,
            size,
            blocks: (size + 511) / 512,
            atime: UNIX_EPOCH + Duration::from_secs(doc.created_at as u64),
            mtime: UNIX_EPOCH + Duration::from_secs(doc.updated_at as u64),
            ctime: UNIX_EPOCH + Duration::from_secs(doc.created_at as u64),
            crtime: UNIX_EPOCH + Duration::from_secs(doc.created_at as u64),
            kind: match doc.document_type {
                DocumentType::Folder => FileType::Directory,
                _ => FileType::RegularFile,
            },
            perm: 0o755,
            nlink: 1,
            uid: 501,
            gid: 20,
            rdev: 0,
            flags: 0,
            blksize: 512,
        }
    }
}

impl Filesystem for ContextHubFuse {
    fn lookup(&mut self, _req: &Request, parent: u64, name: &OsStr, reply: ReplyEntry) {
        let runtime = tokio::runtime::Runtime::new().unwrap();
        runtime.block_on(async {
            // Find parent document
            let parent_id = self.inode_map.read().await.get_by_left(&parent).cloned();
            
            if let Some(parent_id) = parent_id {
                // Search for child with matching name
                let children = self.storage.list_children(&parent_id).await;
                
                for child_id in children {
                    if let Ok(doc) = self.storage.get_document(&child_id).await {
                        if doc.name == name.to_str().unwrap() {
                            let ino = self.get_or_create_inode(&child_id).await;
                            let attr = self.document_to_attr(&doc, ino).await;
                            reply.entry(&Duration::from_secs(1), &attr, 0);
                            return;
                        }
                    }
                }
            }
            
            reply.error(libc::ENOENT);
        });
    }

    fn getattr(&mut self, _req: &Request, ino: u64, reply: ReplyAttr) {
        let runtime = tokio::runtime::Runtime::new().unwrap();
        runtime.block_on(async {
            if ino == 1 {
                // Root directory
                let attr = FileAttr {
                    ino: 1,
                    size: 4096,
                    blocks: 8,
                    atime: UNIX_EPOCH,
                    mtime: UNIX_EPOCH,
                    ctime: UNIX_EPOCH,
                    crtime: UNIX_EPOCH,
                    kind: FileType::Directory,
                    perm: 0o755,
                    nlink: 2,
                    uid: 501,
                    gid: 20,
                    rdev: 0,
                    flags: 0,
                    blksize: 512,
                };
                reply.attr(&Duration::from_secs(1), &attr);
            } else {
                let doc_id = self.inode_map.read().await.get_by_left(&ino).cloned();
                
                if let Some(doc_id) = doc_id {
                    if let Ok(doc) = self.storage.get_document(&doc_id).await {
                        let attr = self.document_to_attr(&doc, ino).await;
                        reply.attr(&Duration::from_secs(1), &attr);
                        return;
                    }
                }
                
                reply.error(libc::ENOENT);
            }
        });
    }

    fn read(&mut self, _req: &Request, ino: u64, _fh: u64, offset: i64, size: u32, _flags: i32, _lock: Option<u64>, reply: ReplyData) {
        let runtime = tokio::runtime::Runtime::new().unwrap();
        runtime.block_on(async {
            let doc_id = self.inode_map.read().await.get_by_left(&ino).cloned();
            
            if let Some(doc_id) = doc_id {
                if let Ok(doc) = self.storage.get_document(&doc_id).await {
                    if let DocumentType::Text(content) = &doc.document_type {
                        let data = content.as_bytes();
                        let start = offset as usize;
                        let end = (offset as usize + size as usize).min(data.len());
                        
                        if start < data.len() {
                            reply.data(&data[start..end]);
                        } else {
                            reply.data(&[]);
                        }
                        return;
                    }
                }
            }
            
            reply.error(libc::EIO);
        });
    }

    fn readdir(&mut self, _req: &Request, ino: u64, _fh: u64, offset: i64, mut reply: ReplyDirectory) {
        let runtime = tokio::runtime::Runtime::new().unwrap();
        runtime.block_on(async {
            let mut entries = vec![
                (ino, FileType::Directory, "."),
                (ino, FileType::Directory, ".."),
            ];

            if ino == 1 {
                // List root documents
                let docs = self.storage.list_root_documents().await;
                for doc_id in docs {
                    if let Ok(doc) = self.storage.get_document(&doc_id).await {
                        let child_ino = self.get_or_create_inode(&doc_id).await;
                        let file_type = match doc.document_type {
                            DocumentType::Folder => FileType::Directory,
                            _ => FileType::RegularFile,
                        };
                        entries.push((child_ino, file_type, &doc.name));
                    }
                }
            } else {
                let doc_id = self.inode_map.read().await.get_by_left(&ino).cloned();
                if let Some(doc_id) = doc_id {
                    let children = self.storage.list_children(&doc_id).await;
                    for child_id in children {
                        if let Ok(doc) = self.storage.get_document(&child_id).await {
                            let child_ino = self.get_or_create_inode(&child_id).await;
                            let file_type = match doc.document_type {
                                DocumentType::Folder => FileType::Directory,
                                _ => FileType::RegularFile,
                            };
                            entries.push((child_ino, file_type, &doc.name));
                        }
                    }
                }
            }

            for (i, (ino, file_type, name)) in entries.iter().enumerate().skip(offset as usize) {
                if reply.add(*ino, (i + 1) as i64, *file_type, name) {
                    break;
                }
            }
            reply.ok();
        });
    }
}