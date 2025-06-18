//! Sharding layer for horizontal scalability
//! 
//! Implements consistent hashing to distribute users across shards,
//! with support for rebalancing and failover.

use anyhow::{anyhow, Result};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};
use std::hash::{Hash, Hasher};
use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

const VIRTUAL_NODES: u32 = 150; // Virtual nodes per physical shard for better distribution

/// Shard identifier
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ShardId(pub u32);

/// Information about a shard
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShardInfo {
    pub id: ShardId,
    pub address: String,
    pub status: ShardStatus,
    pub capacity: ShardCapacity,
    pub replicas: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ShardStatus {
    Active,
    ReadOnly,
    Draining,
    Offline,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ShardCapacity {
    pub user_count: u64,
    pub storage_bytes: u64,
    pub cpu_percent: f32,
    pub memory_percent: f32,
}

/// Trait for shard routing strategies
#[async_trait]
pub trait ShardRouter: Send + Sync {
    /// Find the shard for a given user
    async fn route_user(&self, user_id: &str) -> Result<ShardId>;
    
    /// Find shards for a shared document (may be replicated)
    async fn route_shared(&self, doc_id: Uuid, users: &[String]) -> Result<Vec<ShardId>>;
    
    /// Get information about a shard
    async fn shard_info(&self, shard_id: ShardId) -> Result<ShardInfo>;
    
    /// List all active shards
    async fn list_shards(&self) -> Result<Vec<ShardInfo>>;
    
    /// Register a new shard
    async fn register_shard(&self, info: ShardInfo) -> Result<()>;
    
    /// Update shard status
    async fn update_shard_status(&self, shard_id: ShardId, status: ShardStatus) -> Result<()>;
}

/// Consistent hash ring for shard routing
pub struct ConsistentHashRouter {
    ring: Arc<RwLock<BTreeMap<u64, ShardId>>>,
    shards: Arc<RwLock<HashMap<ShardId, ShardInfo>>>,
}

impl ConsistentHashRouter {
    pub fn new() -> Self {
        Self {
            ring: Arc::new(RwLock::new(BTreeMap::new())),
            shards: Arc::new(RwLock::new(HashMap::new())),
        }
    }
    
    /// Hash a key to a position on the ring
    fn hash_key(key: &str) -> u64 {
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        key.hash(&mut hasher);
        hasher.finish()
    }
    
    /// Add a shard to the ring with virtual nodes
    async fn add_to_ring(&self, shard_id: ShardId) {
        let mut ring = self.ring.write().await;
        
        for i in 0..VIRTUAL_NODES {
            let virtual_key = format!("{}:{}", shard_id.0, i);
            let hash = Self::hash_key(&virtual_key);
            ring.insert(hash, shard_id);
        }
    }
    
    /// Remove a shard from the ring
    async fn remove_from_ring(&self, shard_id: ShardId) {
        let mut ring = self.ring.write().await;
        ring.retain(|_, &mut v| v != shard_id);
    }
}

#[async_trait]
impl ShardRouter for ConsistentHashRouter {
    async fn route_user(&self, user_id: &str) -> Result<ShardId> {
        let hash = Self::hash_key(user_id);
        let ring = self.ring.read().await;
        
        if ring.is_empty() {
            return Err(anyhow!("No shards available"));
        }
        
        // Find the first shard with hash >= user hash
        let shard_id = ring
            .range(hash..)
            .next()
            .or_else(|| ring.iter().next()) // Wrap around
            .map(|(_, &shard_id)| shard_id)
            .ok_or_else(|| anyhow!("Failed to find shard"))?;
        
        // Verify shard is active
        let shards = self.shards.read().await;
        let info = shards.get(&shard_id)
            .ok_or_else(|| anyhow!("Shard not found"))?;
        
        match info.status {
            ShardStatus::Active => Ok(shard_id),
            ShardStatus::ReadOnly => Ok(shard_id), // Allow reads
            _ => {
                // Find next available shard
                drop(shards);
                drop(ring);
                self.find_next_active_shard(hash).await
            }
        }
    }
    
    async fn route_shared(&self, _doc_id: Uuid, users: &[String]) -> Result<Vec<ShardId>> {
        let mut shards = Vec::new();
        
        for user in users {
            if let Ok(shard) = self.route_user(user).await {
                if !shards.contains(&shard) {
                    shards.push(shard);
                }
            }
        }
        
        if shards.is_empty() {
            return Err(anyhow!("No shards available for shared document"));
        }
        
        Ok(shards)
    }
    
    async fn shard_info(&self, shard_id: ShardId) -> Result<ShardInfo> {
        let shards = self.shards.read().await;
        shards.get(&shard_id)
            .cloned()
            .ok_or_else(|| anyhow!("Shard not found"))
    }
    
    async fn list_shards(&self) -> Result<Vec<ShardInfo>> {
        let shards = self.shards.read().await;
        Ok(shards.values().cloned().collect())
    }
    
    async fn register_shard(&self, info: ShardInfo) -> Result<()> {
        let mut shards = self.shards.write().await;
        let shard_id = info.id;
        shards.insert(shard_id, info);
        drop(shards);
        
        self.add_to_ring(shard_id).await;
        Ok(())
    }
    
    async fn update_shard_status(&self, shard_id: ShardId, status: ShardStatus) -> Result<()> {
        let mut shards = self.shards.write().await;
        let info = shards.get_mut(&shard_id)
            .ok_or_else(|| anyhow!("Shard not found"))?;
        
        let old_status = info.status;
        info.status = status;
        drop(shards);
        
        // Update ring based on status change
        match (old_status, status) {
            (ShardStatus::Active, ShardStatus::Offline) |
            (ShardStatus::Active, ShardStatus::Draining) => {
                self.remove_from_ring(shard_id).await;
            }
            (ShardStatus::Offline, ShardStatus::Active) |
            (ShardStatus::Draining, ShardStatus::Active) => {
                self.add_to_ring(shard_id).await;
            }
            _ => {}
        }
        
        Ok(())
    }
}

impl ConsistentHashRouter {
    async fn find_next_active_shard(&self, start_hash: u64) -> Result<ShardId> {
        let ring = self.ring.read().await;
        let shards = self.shards.read().await;
        
        // Try shards in order from the hash position
        for (_, &shard_id) in ring.range(start_hash..).chain(ring.iter()) {
            if let Some(info) = shards.get(&shard_id) {
                if info.status == ShardStatus::Active {
                    return Ok(shard_id);
                }
            }
        }
        
        Err(anyhow!("No active shards available"))
    }
}

/// Manages connections to shard nodes
pub struct ShardConnectionPool {
    pools: Arc<RwLock<HashMap<ShardId, ConnectionPool>>>,
}

struct ConnectionPool {
    address: String,
    connections: Vec<ShardConnection>,
}

pub struct ShardConnection {
    // Would contain actual gRPC/HTTP client
}

impl ShardConnectionPool {
    pub fn new() -> Self {
        Self {
            pools: Arc::new(RwLock::new(HashMap::new())),
        }
    }
    
    pub async fn get_connection(&self, _shard: ShardId) -> Result<Arc<ShardConnection>> {
        // Implementation would get or create connection
        todo!()
    }
}

/// Monitors shard health and triggers rebalancing
pub struct ShardMonitor {
    router: Arc<dyn ShardRouter>,
    thresholds: RebalanceThresholds,
}

#[derive(Debug, Clone)]
pub struct RebalanceThresholds {
    pub max_user_count: u64,
    pub max_storage_gb: u64,
    pub max_cpu_percent: f32,
    pub max_memory_percent: f32,
}

impl Default for RebalanceThresholds {
    fn default() -> Self {
        Self {
            max_user_count: 50_000,
            max_storage_gb: 100,
            max_cpu_percent: 70.0,
            max_memory_percent: 80.0,
        }
    }
}

impl ShardMonitor {
    pub fn new(router: Arc<dyn ShardRouter>) -> Self {
        Self {
            router,
            thresholds: RebalanceThresholds::default(),
        }
    }
    
    pub async fn check_health(&self) -> Result<Vec<ShardId>> {
        let shards = self.router.list_shards().await?;
        let mut unhealthy = Vec::new();
        
        for shard in shards {
            if self.needs_rebalance(&shard) {
                unhealthy.push(shard.id);
            }
        }
        
        Ok(unhealthy)
    }
    
    fn needs_rebalance(&self, shard: &ShardInfo) -> bool {
        shard.capacity.user_count > self.thresholds.max_user_count ||
        shard.capacity.storage_bytes > self.thresholds.max_storage_gb * 1024 * 1024 * 1024 ||
        shard.capacity.cpu_percent > self.thresholds.max_cpu_percent ||
        shard.capacity.memory_percent > self.thresholds.max_memory_percent
    }
}

#[cfg(test)]
mod tests;

#[cfg(test)]
pub use tests::*;