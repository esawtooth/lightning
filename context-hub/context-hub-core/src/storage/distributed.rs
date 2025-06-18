//! Distributed storage implementation with caching and sharding
//! 
//! Provides a multi-tier storage system:
//! - Hot tier: In-memory cache (Redis)
//! - Warm tier: PostgreSQL with Citus sharding
//! - Cold tier: S3-compatible object storage

use crate::shard::{ShardId, ShardRouter};
use crate::storage::crdt::{AccessLevel, AclEntry, Document, DocumentType, Pointer};
use crate::wal::{LogEntry, Operation, WriteAheadLog};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use chrono::Utc;
use redis::aio::{ConnectionManager, MultiplexedConnection};
use redis::{AsyncCommands, Client as RedisClient};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Row};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::RwLock;
use uuid::Uuid;

const CACHE_TTL_SECS: u64 = 3600; // 1 hour cache TTL
const BATCH_SIZE: usize = 100;

/// Document metadata stored in PostgreSQL
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentMetadata {
    pub id: Uuid,
    pub owner: String,
    pub name: String,
    pub parent_folder_id: Option<Uuid>,
    pub doc_type: DocumentType,
    pub size_bytes: i64,
    pub created_at: chrono::DateTime<Utc>,
    pub updated_at: chrono::DateTime<Utc>,
    pub version: i64,
    pub shard_id: i32,
    pub encrypted: bool,
}

/// Distributed document store with sharding and caching
pub struct DistributedDocumentStore {
    shard_id: ShardId,
    router: Arc<dyn ShardRouter>,
    wal: Arc<WriteAheadLog>,
    cache: Arc<RedisConnectionPool>,
    db: Arc<PgPool>,
    blob_store: Arc<dyn BlobStorage>,
    encryption: Arc<dyn EncryptionProvider>,
}

/// Redis connection pool for caching
struct RedisConnectionPool {
    client: RedisClient,
    connections: RwLock<Vec<ConnectionManager>>,
}

impl RedisConnectionPool {
    async fn new(url: &str, pool_size: usize) -> Result<Self> {
        let client = RedisClient::open(url)?;
        let mut connections = Vec::with_capacity(pool_size);
        
        for _ in 0..pool_size {
            let conn = client.get_tokio_connection_manager().await?;
            connections.push(conn);
        }
        
        Ok(Self {
            client,
            connections: RwLock::new(connections),
        })
    }
    
    async fn get(&self) -> Result<ConnectionManager> {
        let mut pool = self.connections.write().await;
        if let Some(conn) = pool.pop() {
            Ok(conn)
        } else {
            Ok(self.client.get_tokio_connection_manager().await?)
        }
    }
    
    async fn put(&self, conn: ConnectionManager) {
        let mut pool = self.connections.write().await;
        if pool.len() < pool.capacity() {
            pool.push(conn);
        }
    }
}

/// Trait for blob storage backends
#[async_trait]
pub trait BlobStorage: Send + Sync {
    async fn put(&self, key: &str, data: &[u8]) -> Result<()>;
    async fn get(&self, key: &str) -> Result<Vec<u8>>;
    async fn delete(&self, key: &str) -> Result<()>;
    async fn exists(&self, key: &str) -> Result<bool>;
}

/// Trait for encryption providers
#[async_trait]
pub trait EncryptionProvider: Send + Sync {
    async fn encrypt(&self, user_id: &str, data: &[u8]) -> Result<Vec<u8>>;
    async fn decrypt(&self, user_id: &str, data: &[u8]) -> Result<Vec<u8>>;
}

impl DistributedDocumentStore {
    pub async fn new(
        shard_id: ShardId,
        router: Arc<dyn ShardRouter>,
        wal: Arc<WriteAheadLog>,
        redis_url: &str,
        db_url: &str,
        blob_store: Arc<dyn BlobStorage>,
        encryption: Arc<dyn EncryptionProvider>,
    ) -> Result<Self> {
        let cache = Arc::new(RedisConnectionPool::new(redis_url, 10).await?);
        let db = Arc::new(PgPool::connect(db_url).await?);
        
        // Run migrations
        sqlx::migrate!("../migrations").run(&*db).await?;
        
        Ok(Self {
            shard_id,
            router,
            wal,
            cache,
            db,
            blob_store,
            encryption,
        })
    }
    
    /// Create a new document
    pub async fn create(
        &self,
        user_id: &str,
        name: String,
        content: &str,
        parent_folder_id: Option<Uuid>,
        doc_type: DocumentType,
    ) -> Result<Uuid> {
        // Verify user belongs to this shard
        let user_shard = self.router.route_user(user_id).await?;
        if user_shard != self.shard_id {
            return Err(anyhow!("User not on this shard"));
        }
        
        let doc_id = Uuid::new_v4();
        let timestamp = Utc::now().timestamp_millis() as u64;
        
        // Create CRDT document
        let doc = Document::new(
            doc_id,
            name.clone(),
            content,
            user_id.to_string(),
            parent_folder_id,
            doc_type,
        )?;
        
        // Encrypt if needed
        let doc_bytes = if self.should_encrypt(user_id).await {
            self.encryption.encrypt(user_id, &doc.snapshot_bytes()?).await?
        } else {
            doc.snapshot_bytes()?
        };
        
        // Write to WAL first
        let entry = LogEntry {
            sequence: 0,
            timestamp,
            user_id: user_id.to_string(),
            doc_id,
            operation: Operation::Create {
                name: name.clone(),
                doc_type: doc_type.as_str().to_string(),
                initial_content: doc_bytes.clone(),
            },
        };
        
        let sequence = self.wal.append(entry).await?;
        
        // Write to database
        let encrypted = self.should_encrypt(user_id).await;
        sqlx::query!(
            r#"
            INSERT INTO documents (id, owner, name, parent_folder_id, doc_type, 
                                   size_bytes, version, shard_id, encrypted, wal_sequence)
            VALUES ($1, $2, $3, $4, $5, $6, 1, $7, $8, $9)
            "#,
            doc_id,
            user_id,
            name,
            parent_folder_id,
            doc_type.as_str(),
            doc_bytes.len() as i64,
            self.shard_id.0 as i32,
            encrypted,
            sequence as i64,
        )
        .execute(&*self.db)
        .await?;
        
        // Store document content
        let blob_key = self.blob_key(doc_id);
        self.blob_store.put(&blob_key, &doc_bytes).await?;
        
        // Cache metadata
        self.cache_metadata(&doc).await?;
        
        // Update parent folder
        if let Some(parent_id) = parent_folder_id {
            self.add_to_folder(parent_id, doc_id, &name, doc_type).await?;
        }
        
        Ok(doc_id)
    }
    
    /// Get a document
    pub async fn get(&self, user_id: &str, doc_id: Uuid) -> Result<Document> {
        // Check cache first
        if let Some(doc) = self.get_from_cache(doc_id).await? {
            if self.check_permission(&doc, user_id, AccessLevel::Read).await? {
                return Ok(doc);
            } else {
                return Err(anyhow!("Permission denied"));
            }
        }
        
        // Load metadata from database
        let metadata = self.load_metadata(doc_id).await?;
        
        // Check permissions
        if metadata.owner != user_id {
            let has_access = self.check_acl(doc_id, user_id, AccessLevel::Read).await?;
            if !has_access {
                return Err(anyhow!("Permission denied"));
            }
        }
        
        // Load document content
        let blob_key = self.blob_key(doc_id);
        let mut doc_bytes = self.blob_store.get(&blob_key).await?;
        
        // Decrypt if needed
        if metadata.encrypted {
            doc_bytes = self.encryption.decrypt(&metadata.owner, &doc_bytes).await?;
        }
        
        // Reconstruct document
        let doc = Document::from_bytes(doc_id, &doc_bytes)?;
        
        // Cache for future reads
        self.cache_metadata(&doc).await?;
        
        Ok(doc)
    }
    
    /// Update a document
    pub async fn update(&self, user_id: &str, doc_id: Uuid, content: &str) -> Result<()> {
        // Load current document
        let mut doc = self.get(user_id, doc_id).await?;
        
        // Check write permission
        if !self.check_permission(&doc, user_id, AccessLevel::Write).await? {
            return Err(anyhow!("Permission denied"));
        }
        
        // Update content
        doc.set_text(content)?;
        
        // Write to WAL
        let timestamp = Utc::now().timestamp_millis() as u64;
        let entry = LogEntry {
            sequence: 0,
            timestamp,
            user_id: user_id.to_string(),
            doc_id,
            operation: Operation::Update {
                crdt_ops: doc.snapshot_bytes()?,
            },
        };
        
        let sequence = self.wal.append(entry).await?;
        
        // Update database
        sqlx::query!(
            r#"
            UPDATE documents 
            SET updated_at = NOW(), version = version + 1, 
                size_bytes = $1, wal_sequence = $2
            WHERE id = $3
            "#,
            doc.snapshot_bytes()?.len() as i64,
            sequence as i64,
            doc_id,
        )
        .execute(&*self.db)
        .await?;
        
        // Store updated content
        let doc_bytes = if self.should_encrypt(&doc.owner()).await {
            self.encryption.encrypt(&doc.owner(), &doc.snapshot_bytes()?).await?
        } else {
            doc.snapshot_bytes()?
        };
        
        let blob_key = self.blob_key(doc_id);
        self.blob_store.put(&blob_key, &doc_bytes).await?;
        
        // Invalidate cache
        self.invalidate_cache(doc_id).await?;
        
        Ok(())
    }
    
    /// Delete a document
    pub async fn delete(&self, user_id: &str, doc_id: Uuid) -> Result<()> {
        // Check permission
        let doc = self.get(user_id, doc_id).await?;
        if doc.owner() != user_id {
            return Err(anyhow!("Only owner can delete"));
        }
        
        // Write to WAL
        let timestamp = Utc::now().timestamp_millis() as u64;
        let entry = LogEntry {
            sequence: 0,
            timestamp,
            user_id: user_id.to_string(),
            doc_id,
            operation: Operation::Delete,
        };
        
        self.wal.append(entry).await?;
        
        // Soft delete in database
        sqlx::query!(
            "UPDATE documents SET deleted_at = NOW() WHERE id = $1",
            doc_id,
        )
        .execute(&*self.db)
        .await?;
        
        // Remove from parent folder
        if let Some(parent_id) = doc.parent_folder_id() {
            self.remove_from_folder(parent_id, doc_id).await?;
        }
        
        // Invalidate cache
        self.invalidate_cache(doc_id).await?;
        
        // Schedule blob deletion after retention period
        self.schedule_blob_deletion(doc_id).await?;
        
        Ok(())
    }
    
    /// Add or update ACL entry
    pub async fn update_acl(
        &self,
        user_id: &str,
        doc_id: Uuid,
        principal: String,
        access: AccessLevel,
    ) -> Result<()> {
        // Check permission
        let doc = self.get(user_id, doc_id).await?;
        if doc.owner() != user_id {
            return Err(anyhow!("Only owner can update ACL"));
        }
        
        // Update in database
        sqlx::query!(
            r#"
            INSERT INTO document_acl (document_id, principal, access_level)
            VALUES ($1, $2, $3)
            ON CONFLICT (document_id, principal) 
            DO UPDATE SET access_level = EXCLUDED.access_level
            "#,
            doc_id,
            principal,
            match access {
                AccessLevel::Read => "read",
                AccessLevel::Write => "write",
            },
        )
        .execute(&*self.db)
        .await?;
        
        // Write to WAL
        let acl_entry = AclEntry { principal, access };
        let timestamp = Utc::now().timestamp_millis() as u64;
        let entry = LogEntry {
            sequence: 0,
            timestamp,
            user_id: user_id.to_string(),
            doc_id,
            operation: Operation::UpdateAcl {
                acl: serde_json::to_vec(&acl_entry)?,
            },
        };
        
        self.wal.append(entry).await?;
        
        // Invalidate cache
        self.invalidate_cache(doc_id).await?;
        
        Ok(())
    }
    
    // Helper methods
    
    async fn should_encrypt(&self, user_id: &str) -> bool {
        // Could check user preferences or compliance requirements
        true
    }
    
    fn blob_key(&self, doc_id: Uuid) -> String {
        format!("shard-{}/docs/{}", self.shard_id.0, doc_id)
    }
    
    async fn cache_metadata(&self, doc: &Document) -> Result<()> {
        let mut conn = self.cache.get().await?;
        let key = format!("doc:meta:{}", doc.id());
        let data = serde_json::to_string(&doc)?;
        
        conn.set_ex(&key, data, CACHE_TTL_SECS).await?;
        self.cache.put(conn).await;
        
        Ok(())
    }
    
    async fn get_from_cache(&self, doc_id: Uuid) -> Result<Option<Document>> {
        let mut conn = self.cache.get().await?;
        let key = format!("doc:meta:{}", doc_id);
        
        let data: Option<String> = conn.get(&key).await?;
        self.cache.put(conn).await;
        
        if let Some(data) = data {
            Ok(Some(serde_json::from_str(&data)?))
        } else {
            Ok(None)
        }
    }
    
    async fn invalidate_cache(&self, doc_id: Uuid) -> Result<()> {
        let mut conn = self.cache.get().await?;
        let key = format!("doc:meta:{}", doc_id);
        
        conn.del(&key).await?;
        self.cache.put(conn).await;
        
        Ok(())
    }
    
    async fn load_metadata(&self, doc_id: Uuid) -> Result<DocumentMetadata> {
        let row = sqlx::query!(
            r#"
            SELECT id, owner, name, parent_folder_id, doc_type, size_bytes,
                   created_at, updated_at, version, shard_id, encrypted
            FROM documents
            WHERE id = $1 AND deleted_at IS NULL
            "#,
            doc_id,
        )
        .fetch_one(&*self.db)
        .await?;
        
        Ok(DocumentMetadata {
            id: row.id,
            owner: row.owner,
            name: row.name,
            parent_folder_id: row.parent_folder_id,
            doc_type: DocumentType::from_str(&row.doc_type),
            size_bytes: row.size_bytes,
            created_at: row.created_at,
            updated_at: row.updated_at,
            version: row.version,
            shard_id: row.shard_id,
            encrypted: row.encrypted,
        })
    }
    
    async fn check_permission(
        &self,
        doc: &Document,
        user_id: &str,
        level: AccessLevel,
    ) -> Result<bool> {
        if doc.owner() == user_id {
            return Ok(true);
        }
        
        self.check_acl(doc.id(), user_id, level).await
    }
    
    async fn check_acl(
        &self,
        doc_id: Uuid,
        user_id: &str,
        level: AccessLevel,
    ) -> Result<bool> {
        let row = sqlx::query!(
            r#"
            SELECT access_level 
            FROM document_acl 
            WHERE document_id = $1 AND principal = $2
            "#,
            doc_id,
            user_id,
        )
        .fetch_optional(&*self.db)
        .await?;
        
        if let Some(row) = row {
            match (level, row.access_level.as_str()) {
                (AccessLevel::Read, "read") | (AccessLevel::Read, "write") => Ok(true),
                (AccessLevel::Write, "write") => Ok(true),
                _ => Ok(false),
            }
        } else {
            Ok(false)
        }
    }
    
    async fn add_to_folder(
        &self,
        folder_id: Uuid,
        doc_id: Uuid,
        name: &str,
        doc_type: DocumentType,
    ) -> Result<()> {
        // Would update folder's children list
        Ok(())
    }
    
    async fn remove_from_folder(&self, folder_id: Uuid, doc_id: Uuid) -> Result<()> {
        // Would remove from folder's children list
        Ok(())
    }
    
    async fn schedule_blob_deletion(&self, doc_id: Uuid) -> Result<()> {
        // Would schedule deletion after retention period
        Ok(())
    }
}

/// S3-compatible blob storage implementation
pub struct S3BlobStorage {
    pub client: aws_sdk_s3::Client,
    pub bucket: String,
}

#[async_trait]
impl BlobStorage for S3BlobStorage {
    async fn put(&self, key: &str, data: &[u8]) -> Result<()> {
        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .body(data.to_vec().into())
            .send()
            .await?;
        Ok(())
    }
    
    async fn get(&self, key: &str) -> Result<Vec<u8>> {
        let resp = self.client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await?;
        
        let data = resp.body.collect().await?;
        Ok(data.into_bytes().to_vec())
    }
    
    async fn delete(&self, key: &str) -> Result<()> {
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await?;
        Ok(())
    }
    
    async fn exists(&self, key: &str) -> Result<bool> {
        match self.client
            .head_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
        {
            Ok(_) => Ok(true),
            Err(_) => Ok(false),
        }
    }
}