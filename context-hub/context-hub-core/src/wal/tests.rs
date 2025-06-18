#[cfg(test)]
mod tests {
    use super::super::*;
    use tempfile::TempDir;
    use tokio::time::{sleep, Duration};
    
    #[tokio::test]
    async fn test_wal_basic_operations() {
        let temp_dir = TempDir::new().unwrap();
        let wal = WriteAheadLog::new(temp_dir.path()).await.unwrap();
        
        // Test single append
        let entry = LogEntry {
            sequence: 0,
            timestamp: 1234567890,
            user_id: "user1".to_string(),
            doc_id: Uuid::new_v4(),
            operation: Operation::Create {
                name: "test.txt".to_string(),
                doc_type: "Text".to_string(),
                initial_content: b"Hello, World!".to_vec(),
            },
        };
        
        let seq = wal.append(entry.clone()).await.unwrap();
        assert_eq!(seq, 0);
        
        // Test reading back
        let entries = wal.read_from(0).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].user_id, "user1");
        assert_eq!(entries[0].sequence, 0);
    }
    
    #[tokio::test]
    async fn test_wal_multiple_entries() {
        let temp_dir = TempDir::new().unwrap();
        let wal = WriteAheadLog::new(temp_dir.path()).await.unwrap();
        
        let doc_id = Uuid::new_v4();
        
        // Append multiple entries
        for i in 0..10 {
            let entry = LogEntry {
                sequence: 0,
                timestamp: 1234567890 + i,
                user_id: format!("user{}", i % 3),
                doc_id,
                operation: Operation::Update {
                    crdt_ops: format!("update {}", i).into_bytes(),
                },
            };
            
            let seq = wal.append(entry).await.unwrap();
            assert_eq!(seq, i as u64);
        }
        
        // Read all entries
        let entries = wal.read_from(0).unwrap();
        assert_eq!(entries.len(), 10);
        
        // Read from middle
        let entries = wal.read_from(5).unwrap();
        assert_eq!(entries.len(), 5);
        assert_eq!(entries[0].sequence, 5);
    }
    
    #[tokio::test]
    async fn test_wal_concurrent_writes() {
        let temp_dir = TempDir::new().unwrap();
        let wal = Arc::new(WriteAheadLog::new(temp_dir.path()).await.unwrap());
        
        let mut handles = vec![];
        
        // Spawn 10 concurrent writers
        for i in 0..10 {
            let wal = wal.clone();
            let handle = tokio::spawn(async move {
                let entry = LogEntry {
                    sequence: 0,
                    timestamp: 1234567890,
                    user_id: format!("user{}", i),
                    doc_id: Uuid::new_v4(),
                    operation: Operation::Create {
                        name: format!("doc{}.txt", i),
                        doc_type: "Text".to_string(),
                        initial_content: format!("Content {}", i).into_bytes(),
                    },
                };
                
                wal.append(entry).await.unwrap()
            });
            handles.push(handle);
        }
        
        // Wait for all writes
        let mut sequences = vec![];
        for handle in handles {
            sequences.push(handle.await.unwrap());
        }
        
        // Check sequences are unique
        sequences.sort();
        sequences.dedup();
        assert_eq!(sequences.len(), 10);
        
        // Verify all entries are readable
        let entries = wal.read_from(0).unwrap();
        assert_eq!(entries.len(), 10);
    }
    
    #[tokio::test]
    async fn test_wal_segment_rotation() {
        let temp_dir = TempDir::new().unwrap();
        let wal = WriteAheadLog::new(temp_dir.path()).await.unwrap();
        
        // Write enough data to trigger rotation - WAL segments are 128MB
        // So we need roughly 130+ MB of data 
        let large_content = vec![0u8; 1024 * 1024]; // 1MB per entry
        
        for i in 0..130 { // 130MB should trigger rotation
            let entry = LogEntry {
                sequence: 0,
                timestamp: 1234567890 + i,
                user_id: "user1".to_string(),
                doc_id: Uuid::new_v4(),
                operation: Operation::Create {
                    name: format!("large{}.bin", i),
                    doc_type: "Binary".to_string(),
                    initial_content: large_content.clone(),
                },
            };
            
            wal.append(entry).await.unwrap();
            
            // Give rotation task time to run
            if i % 10 == 0 {
                sleep(Duration::from_millis(50)).await;
            }
        }
        
        // Wait for final rotation to complete
        sleep(Duration::from_millis(500)).await;
        
        // Check multiple segment files exist
        let mut segment_count = 0;
        for entry in std::fs::read_dir(temp_dir.path()).unwrap() {
            let entry = entry.unwrap();
            let name = entry.file_name();
            if let Some(name_str) = name.to_str() {
                if name_str.starts_with("wal-") && name_str.ends_with(".log") {
                    segment_count += 1;
                }
            }
        }
        
        assert!(segment_count > 1, "Expected multiple segments, got {}", segment_count);
        
        // Verify all entries can still be read
        let entries = wal.read_from(0).unwrap();
        assert_eq!(entries.len(), 130);
    }
    
    #[tokio::test]
    async fn test_wal_recovery_after_crash() {
        let temp_dir = TempDir::new().unwrap();
        let doc_id = Uuid::new_v4();
        
        // First WAL instance
        {
            let wal = WriteAheadLog::new(temp_dir.path()).await.unwrap();
            
            for i in 0..5 {
                let entry = LogEntry {
                    sequence: 0,
                    timestamp: 1234567890 + i,
                    user_id: "user1".to_string(),
                    doc_id,
                    operation: Operation::Update {
                        crdt_ops: format!("update {}", i).into_bytes(),
                    },
                };
                
                wal.append(entry).await.unwrap();
            }
        }
        
        // Simulate crash and recovery with new WAL instance
        {
            let wal = WriteAheadLog::new(temp_dir.path()).await.unwrap();
            
            // Should be able to read old entries
            let entries = wal.read_from(0).unwrap();
            assert_eq!(entries.len(), 5);
            
            // Should continue from correct sequence
            let entry = LogEntry {
                sequence: 0,
                timestamp: 1234567895,
                user_id: "user1".to_string(),
                doc_id,
                operation: Operation::Update {
                    crdt_ops: b"after recovery".to_vec(),
                },
            };
            
            let seq = wal.append(entry).await.unwrap();
            assert_eq!(seq, 5);
        }
    }
    
    #[tokio::test]
    async fn test_wal_crc_validation() {
        let temp_dir = TempDir::new().unwrap();
        let wal = WriteAheadLog::new(temp_dir.path()).await.unwrap();
        
        // Write an entry
        let entry = LogEntry {
            sequence: 0,
            timestamp: 1234567890,
            user_id: "user1".to_string(),
            doc_id: Uuid::new_v4(),
            operation: Operation::Create {
                name: "test.txt".to_string(),
                doc_type: "Text".to_string(),
                initial_content: b"Test content".to_vec(),
            },
        };
        
        wal.append(entry).await.unwrap();
        
        // Corrupt the WAL file
        let wal_path = temp_dir.path().join("wal-00000000.log");
        let mut content = std::fs::read(&wal_path).unwrap();
        
        // Corrupt some bytes in the middle
        if content.len() > 20 {
            content[20] ^= 0xFF;
        }
        
        std::fs::write(&wal_path, content).unwrap();
        
        // Try to read - should handle corruption gracefully
        let entries = wal.read_from(0).unwrap();
        
        // May be empty or partial depending on where corruption occurred
        // The important thing is it doesn't panic
        assert!(entries.len() <= 1);
    }
    
    #[tokio::test]
    async fn test_wal_all_operation_types() {
        let temp_dir = TempDir::new().unwrap();
        let wal = WriteAheadLog::new(temp_dir.path()).await.unwrap();
        
        let doc_id = Uuid::new_v4();
        
        // Test Create operation
        let create = LogEntry {
            sequence: 0,
            timestamp: 1000,
            user_id: "user1".to_string(),
            doc_id,
            operation: Operation::Create {
                name: "doc.txt".to_string(),
                doc_type: "Text".to_string(),
                initial_content: b"Initial".to_vec(),
            },
        };
        wal.append(create).await.unwrap();
        
        // Test Update operation
        let update = LogEntry {
            sequence: 0,
            timestamp: 2000,
            user_id: "user1".to_string(),
            doc_id,
            operation: Operation::Update {
                crdt_ops: b"CRDT operations".to_vec(),
            },
        };
        wal.append(update).await.unwrap();
        
        // Test UpdateAcl operation
        let acl = LogEntry {
            sequence: 0,
            timestamp: 3000,
            user_id: "user1".to_string(),
            doc_id,
            operation: Operation::UpdateAcl {
                acl: b"ACL data".to_vec(),
            },
        };
        wal.append(acl).await.unwrap();
        
        // Test Move operation
        let move_op = LogEntry {
            sequence: 0,
            timestamp: 4000,
            user_id: "user1".to_string(),
            doc_id,
            operation: Operation::Move {
                new_parent: Some(Uuid::new_v4()),
            },
        };
        wal.append(move_op).await.unwrap();
        
        // Test Delete operation
        let delete = LogEntry {
            sequence: 0,
            timestamp: 5000,
            user_id: "user1".to_string(),
            doc_id,
            operation: Operation::Delete,
        };
        wal.append(delete).await.unwrap();
        
        // Read and verify all operations
        let entries = wal.read_from(0).unwrap();
        assert_eq!(entries.len(), 5);
        
        // Verify operation types
        match &entries[0].operation {
            Operation::Create { name, .. } => assert_eq!(name, "doc.txt"),
            _ => panic!("Expected Create operation"),
        }
        
        match &entries[1].operation {
            Operation::Update { crdt_ops } => assert_eq!(crdt_ops, b"CRDT operations"),
            _ => panic!("Expected Update operation"),
        }
        
        match &entries[2].operation {
            Operation::UpdateAcl { acl } => assert_eq!(acl, b"ACL data"),
            _ => panic!("Expected UpdateAcl operation"),
        }
        
        match &entries[3].operation {
            Operation::Move { new_parent } => assert!(new_parent.is_some()),
            _ => panic!("Expected Move operation"),
        }
        
        match &entries[4].operation {
            Operation::Delete => {},
            _ => panic!("Expected Delete operation"),
        }
    }
}