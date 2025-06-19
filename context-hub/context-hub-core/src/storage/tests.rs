#[cfg(all(test, feature = "distributed"))]
mod tests {
    use crate::storage::distributed::*;
    use crate::shard::{ConsistentHashRouter, ShardId, ShardInfo, ShardStatus};
    use crate::storage::crdt::{AccessLevel, DocumentType};
    use crate::wal::WriteAheadLog;
    use async_trait::async_trait;
    use std::collections::HashMap;
    use std::sync::Arc;
    use tempfile::TempDir;
    use tokio::sync::Mutex;
    
    // Mock implementations for testing
    
    struct MockBlobStorage {
        data: Arc<Mutex<HashMap<String, Vec<u8>>>>,
    }
    
    impl MockBlobStorage {
        fn new() -> Self {
            Self {
                data: Arc::new(Mutex::new(HashMap::new())),
            }
        }
    }
    
    #[async_trait]
    impl BlobStorage for MockBlobStorage {
        async fn put(&self, key: &str, data: &[u8]) -> Result<()> {
            let mut store = self.data.lock().await;
            store.insert(key.to_string(), data.to_vec());
            Ok(())
        }
        
        async fn get(&self, key: &str) -> Result<Vec<u8>> {
            let store = self.data.lock().await;
            store
                .get(key)
                .cloned()
                .ok_or_else(|| anyhow::anyhow!("Key not found"))
        }
        
        async fn delete(&self, key: &str) -> Result<()> {
            let mut store = self.data.lock().await;
            store.remove(key);
            Ok(())
        }
        
        async fn exists(&self, key: &str) -> Result<bool> {
            let store = self.data.lock().await;
            Ok(store.contains_key(key))
        }
    }
    
    struct MockEncryptionProvider;
    
    #[async_trait]
    impl EncryptionProvider for MockEncryptionProvider {
        async fn encrypt(&self, _user_id: &str, data: &[u8]) -> Result<Vec<u8>> {
            // Simple XOR encryption for testing
            Ok(data.iter().map(|b| b ^ 0xAA).collect())
        }
        
        async fn decrypt(&self, _user_id: &str, data: &[u8]) -> Result<Vec<u8>> {
            // XOR is self-inverse
            Ok(data.iter().map(|b| b ^ 0xAA).collect())
        }
    }
    
    async fn setup_test_store() -> (DistributedDocumentStore, TempDir, Arc<ConsistentHashRouter>) {
        let temp_dir = TempDir::new().unwrap();
        let shard_id = ShardId(0);
        
        // Setup router
        let router = Arc::new(ConsistentHashRouter::new());
        let shard_info = ShardInfo {
            id: shard_id,
            address: "localhost:8080".to_string(),
            status: ShardStatus::Active,
            capacity: Default::default(),
            replicas: vec![],
        };
        router.register_shard(shard_info).await.unwrap();
        
        // Setup WAL
        let wal_dir = temp_dir.path().join("wal");
        let wal = Arc::new(WriteAheadLog::new(&wal_dir).await.unwrap());
        
        // Setup mock storage
        let blob_store = Arc::new(MockBlobStorage::new());
        let encryption = Arc::new(MockEncryptionProvider);
        
        // Create test database
        let db_url = "sqlite::memory:";
        
        // For real tests, you'd use a test PostgreSQL instance
        // For now, we'll create a mock store
        let store = DistributedDocumentStore::new(
            shard_id,
            router.clone(),
            wal,
            "redis://localhost:6379", // Would be mocked in real tests
            db_url,
            blob_store,
            encryption,
        )
        .await
        .unwrap();
        
        (store, temp_dir, router)
    }
    
    #[tokio::test]
    async fn test_document_create_and_get() {
        let (store, _temp_dir, _router) = setup_test_store().await;
        
        let user_id = "user0"; // Routes to shard 0
        let doc_name = "test.txt";
        let content = "Hello, World!";
        
        // Create document
        let doc_id = store
            .create(
                user_id,
                doc_name.to_string(),
                content,
                None,
                DocumentType::Text,
            )
            .await
            .unwrap();
        
        // Get document
        let doc = store.get(user_id, doc_id).await.unwrap();
        
        assert_eq!(doc.id(), doc_id);
        assert_eq!(doc.name(), doc_name);
        assert_eq!(doc.text(), content);
        assert_eq!(doc.owner(), user_id);
        assert_eq!(doc.doc_type(), DocumentType::Text);
    }
    
    #[tokio::test]
    async fn test_document_update() {
        let (store, _temp_dir, _router) = setup_test_store().await;
        
        let user_id = "user0";
        
        // Create document
        let doc_id = store
            .create(
                user_id,
                "doc.txt".to_string(),
                "Initial content",
                None,
                DocumentType::Text,
            )
            .await
            .unwrap();
        
        // Update document
        let new_content = "Updated content";
        store.update(user_id, doc_id, new_content).await.unwrap();
        
        // Verify update
        let doc = store.get(user_id, doc_id).await.unwrap();
        assert_eq!(doc.text(), new_content);
    }
    
    #[tokio::test]
    async fn test_document_delete() {
        let (store, _temp_dir, _router) = setup_test_store().await;
        
        let user_id = "user0";
        
        // Create document
        let doc_id = store
            .create(
                user_id,
                "to_delete.txt".to_string(),
                "Delete me",
                None,
                DocumentType::Text,
            )
            .await
            .unwrap();
        
        // Delete document
        store.delete(user_id, doc_id).await.unwrap();
        
        // Try to get deleted document
        let result = store.get(user_id, doc_id).await;
        assert!(result.is_err());
    }
    
    #[tokio::test]
    async fn test_document_acl() {
        let (store, _temp_dir, _router) = setup_test_store().await;
        
        let owner = "user0";
        let other_user = "user1";
        
        // Create document
        let doc_id = store
            .create(
                owner,
                "shared.txt".to_string(),
                "Shared content",
                None,
                DocumentType::Text,
            )
            .await
            .unwrap();
        
        // Other user can't access by default
        let result = store.get(other_user, doc_id).await;
        assert!(result.is_err());
        
        // Grant read access
        store
            .update_acl(owner, doc_id, other_user.to_string(), AccessLevel::Read)
            .await
            .unwrap();
        
        // Now other user can read
        let doc = store.get(other_user, doc_id).await.unwrap();
        assert_eq!(doc.text(), "Shared content");
        
        // But can't write
        let result = store.update(other_user, doc_id, "Hacked!").await;
        assert!(result.is_err());
        
        // Grant write access
        store
            .update_acl(owner, doc_id, other_user.to_string(), AccessLevel::Write)
            .await
            .unwrap();
        
        // Now can write
        store.update(other_user, doc_id, "Collaborative edit").await.unwrap();
    }
    
    #[tokio::test]
    async fn test_folder_hierarchy() {
        let (store, _temp_dir, _router) = setup_test_store().await;
        
        let user_id = "user0";
        
        // Create root folder
        let root_id = store
            .create(
                user_id,
                "My Documents".to_string(),
                "",
                None,
                DocumentType::Folder,
            )
            .await
            .unwrap();
        
        // Create subfolder
        let subfolder_id = store
            .create(
                user_id,
                "Projects".to_string(),
                "",
                Some(root_id),
                DocumentType::Folder,
            )
            .await
            .unwrap();
        
        // Create document in subfolder
        let doc_id = store
            .create(
                user_id,
                "project.txt".to_string(),
                "Project content",
                Some(subfolder_id),
                DocumentType::Text,
            )
            .await
            .unwrap();
        
        // Verify hierarchy
        let doc = store.get(user_id, doc_id).await.unwrap();
        assert_eq!(doc.parent_folder_id(), Some(subfolder_id));
        
        let subfolder = store.get(user_id, subfolder_id).await.unwrap();
        assert_eq!(subfolder.parent_folder_id(), Some(root_id));
        
        let root = store.get(user_id, root_id).await.unwrap();
        assert_eq!(root.parent_folder_id(), None);
    }
    
    #[tokio::test]
    async fn test_encryption() {
        let (store, _temp_dir, _router) = setup_test_store().await;
        
        let user_id = "user0";
        let content = "Sensitive information";
        
        // Create encrypted document
        let doc_id = store
            .create(
                user_id,
                "encrypted.txt".to_string(),
                content,
                None,
                DocumentType::Text,
            )
            .await
            .unwrap();
        
        // Verify content is encrypted in blob storage
        let blob_key = format!("shard-0/docs/{}", doc_id);
        let blob_store = Arc::new(MockBlobStorage::new());
        if let Ok(encrypted_data) = blob_store.get(&blob_key).await {
            // Data should be different from original
            assert_ne!(encrypted_data, content.as_bytes());
        }
        
        // But reading through the store returns decrypted content
        let doc = store.get(user_id, doc_id).await.unwrap();
        assert_eq!(doc.text(), content);
    }
    
    #[tokio::test]
    async fn test_concurrent_operations() {
        let (store, _temp_dir, _router) = setup_test_store().await;
        let store = Arc::new(store);
        
        let user_id = "user0";
        
        // Create multiple documents concurrently
        let mut handles = vec![];
        
        for i in 0..10 {
            let store = store.clone();
            let user_id = user_id.to_string();
            
            let handle = tokio::spawn(async move {
                store
                    .create(
                        &user_id,
                        format!("doc{}.txt", i),
                        format!("Content {}", i),
                        None,
                        DocumentType::Text,
                    )
                    .await
            });
            
            handles.push(handle);
        }
        
        // Wait for all creates
        let mut doc_ids = vec![];
        for handle in handles {
            let doc_id = handle.await.unwrap().unwrap();
            doc_ids.push(doc_id);
        }
        
        // Verify all documents exist
        assert_eq!(doc_ids.len(), 10);
        
        for (i, doc_id) in doc_ids.iter().enumerate() {
            let doc = store.get(user_id, *doc_id).await.unwrap();
            assert_eq!(doc.name(), format!("doc{}.txt", i));
            assert_eq!(doc.text(), format!("Content {}", i));
        }
    }
    
    #[tokio::test]
    async fn test_wrong_shard_rejection() {
        let (store, _temp_dir, router) = setup_test_store().await;
        
        // Add another shard
        let shard_info = ShardInfo {
            id: ShardId(1),
            address: "localhost:8081".to_string(),
            status: ShardStatus::Active,
            capacity: Default::default(),
            replicas: vec![],
        };
        router.register_shard(shard_info).await.unwrap();
        
        // Find a user that routes to shard 1
        let mut user_on_shard_1 = None;
        for i in 0..100 {
            let user = format!("user{}", i);
            if let Ok(shard) = router.route_user(&user).await {
                if shard == ShardId(1) {
                    user_on_shard_1 = Some(user);
                    break;
                }
            }
        }
        
        let user = user_on_shard_1.expect("Should find user for shard 1");
        
        // Try to create document on wrong shard (we're shard 0)
        let result = store
            .create(
                &user,
                "wrong_shard.txt".to_string(),
                "This should fail",
                None,
                DocumentType::Text,
            )
            .await;
        
        assert!(result.is_err());
    }
}