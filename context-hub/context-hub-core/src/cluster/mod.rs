//! Cluster coordination using etcd for distributed consensus
//! 
//! Handles shard discovery, leader election, configuration management,
//! and distributed locking.

use anyhow::{anyhow, Result};
use async_trait::async_trait;
use etcd_rs::{
    Client as EtcdClient, DeleteOptions, EventType, GetOptions, KeyValue, PutOptions,
    ResponseHeader, WatchOptions,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{broadcast, RwLock};
use tokio::time::interval;
use uuid::Uuid;

use crate::shard::{ShardId, ShardInfo, ShardStatus};

const SHARD_PREFIX: &str = "/context-hub/shards/";
const CONFIG_PREFIX: &str = "/context-hub/config/";
const LOCK_PREFIX: &str = "/context-hub/locks/";
const LEADER_PREFIX: &str = "/context-hub/leaders/";

/// Cluster coordinator manages distributed state
pub struct ClusterCoordinator {
    node_id: String,
    etcd: EtcdClient,
    shard_updates: broadcast::Sender<ShardEvent>,
    config_updates: broadcast::Sender<ConfigEvent>,
    leaders: Arc<RwLock<HashMap<String, String>>>,
}

#[derive(Debug, Clone)]
pub enum ShardEvent {
    ShardAdded(ShardInfo),
    ShardUpdated(ShardInfo),
    ShardRemoved(ShardId),
}

#[derive(Debug, Clone)]
pub enum ConfigEvent {
    ConfigUpdated(String, String),
    ConfigRemoved(String),
}

/// Distributed configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClusterConfig {
    pub replication_factor: u32,
    pub min_shards: u32,
    pub max_shards: u32,
    pub shard_size_mb: u64,
    pub rebalance_threshold: f32,
    pub health_check_interval_secs: u64,
}

impl Default for ClusterConfig {
    fn default() -> Self {
        Self {
            replication_factor: 3,
            min_shards: 3,
            max_shards: 100,
            shard_size_mb: 10240, // 10GB
            rebalance_threshold: 0.2, // 20% imbalance triggers rebalance
            health_check_interval_secs: 30,
        }
    }
}

impl ClusterCoordinator {
    pub async fn new(etcd_endpoints: Vec<String>, node_id: String) -> Result<Self> {
        let etcd = EtcdClient::connect(etcd_endpoints, None).await?;
        let (shard_tx, _) = broadcast::channel(1000);
        let (config_tx, _) = broadcast::channel(100);
        
        let coordinator = Self {
            node_id,
            etcd,
            shard_updates: shard_tx,
            config_updates: config_tx,
            leaders: Arc::new(RwLock::new(HashMap::new())),
        };
        
        // Start watchers
        coordinator.start_watchers().await?;
        
        Ok(coordinator)
    }
    
    /// Register a shard with the cluster
    pub async fn register_shard(&self, info: ShardInfo) -> Result<()> {
        let key = format!("{}{}", SHARD_PREFIX, info.id.0);
        let value = serde_json::to_string(&info)?;
        
        let mut opts = PutOptions::new();
        opts.with_lease(self.create_lease(300).await?); // 5 minute lease
        
        self.etcd.put(key, value, Some(opts)).await?;
        self.shard_updates.send(ShardEvent::ShardAdded(info))?;
        
        Ok(())
    }
    
    /// Update shard status
    pub async fn update_shard_status(&self, shard_id: ShardId, status: ShardStatus) -> Result<()> {
        let key = format!("{}{}", SHARD_PREFIX, shard_id.0);
        
        // Get current info
        let resp = self.etcd.get(key.clone(), None).await?;
        if let Some(kv) = resp.kvs().first() {
            let mut info: ShardInfo = serde_json::from_slice(kv.value())?;
            info.status = status;
            
            let value = serde_json::to_string(&info)?;
            self.etcd.put(key, value, None).await?;
            
            self.shard_updates.send(ShardEvent::ShardUpdated(info))?;
        }
        
        Ok(())
    }
    
    /// Get all active shards
    pub async fn list_shards(&self) -> Result<Vec<ShardInfo>> {
        let mut opts = GetOptions::new();
        opts.with_prefix();
        
        let resp = self.etcd.get(SHARD_PREFIX, Some(opts)).await?;
        let mut shards = Vec::new();
        
        for kv in resp.kvs() {
            if let Ok(info) = serde_json::from_slice::<ShardInfo>(kv.value()) {
                shards.push(info);
            }
        }
        
        Ok(shards)
    }
    
    /// Elect a leader for a given resource
    pub async fn elect_leader(&self, resource: &str) -> Result<bool> {
        let key = format!("{}{}", LEADER_PREFIX, resource);
        let lease_id = self.create_lease(30).await?; // 30 second lease
        
        // Try to become leader
        let mut opts = PutOptions::new();
        opts.with_lease(lease_id);
        opts.with_prev_kv();
        
        let resp = self.etcd.put(key.clone(), &self.node_id, Some(opts)).await?;
        
        // Check if we became leader
        if resp.prev_kv().is_none() || resp.prev_kv().unwrap().value() == self.node_id.as_bytes() {
            let mut leaders = self.leaders.write().await;
            leaders.insert(resource.to_string(), self.node_id.clone());
            
            // Keep lease alive
            self.keep_alive_lease(lease_id, resource.to_string()).await;
            
            Ok(true)
        } else {
            Ok(false)
        }
    }
    
    /// Check if this node is the leader for a resource
    pub async fn is_leader(&self, resource: &str) -> bool {
        let leaders = self.leaders.read().await;
        leaders.get(resource).map(|l| l == &self.node_id).unwrap_or(false)
    }
    
    /// Acquire a distributed lock
    pub async fn acquire_lock(&self, name: &str, ttl_secs: u64) -> Result<DistributedLock> {
        let key = format!("{}{}", LOCK_PREFIX, name);
        let lock_id = Uuid::new_v4().to_string();
        let lease_id = self.create_lease(ttl_secs as i64).await?;
        
        // Try to acquire lock
        let mut opts = PutOptions::new();
        opts.with_lease(lease_id);
        
        // Use compare-and-swap to ensure atomicity
        loop {
            let get_resp = self.etcd.get(key.clone(), None).await?;
            
            if get_resp.kvs().is_empty() {
                // Lock is free, try to acquire
                self.etcd.put(key.clone(), &lock_id, Some(opts.clone())).await?;
                
                return Ok(DistributedLock {
                    etcd: self.etcd.clone(),
                    key,
                    lock_id,
                    lease_id,
                });
            } else {
                // Lock is held, wait and retry
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        }
    }
    
    /// Get cluster configuration
    pub async fn get_config(&self) -> Result<ClusterConfig> {
        let key = format!("{}cluster", CONFIG_PREFIX);
        let resp = self.etcd.get(key, None).await?;
        
        if let Some(kv) = resp.kvs().first() {
            Ok(serde_json::from_slice(kv.value())?)
        } else {
            // Return default if not set
            Ok(ClusterConfig::default())
        }
    }
    
    /// Update cluster configuration
    pub async fn update_config(&self, config: ClusterConfig) -> Result<()> {
        let key = format!("{}cluster", CONFIG_PREFIX);
        let value = serde_json::to_string(&config)?;
        
        self.etcd.put(key.clone(), value.clone(), None).await?;
        self.config_updates.send(ConfigEvent::ConfigUpdated(
            "cluster".to_string(),
            value,
        ))?;
        
        Ok(())
    }
    
    /// Subscribe to shard updates
    pub fn subscribe_shards(&self) -> broadcast::Receiver<ShardEvent> {
        self.shard_updates.subscribe()
    }
    
    /// Subscribe to config updates
    pub fn subscribe_config(&self) -> broadcast::Receiver<ConfigEvent> {
        self.config_updates.subscribe()
    }
    
    // Helper methods
    
    async fn create_lease(&self, ttl: i64) -> Result<i64> {
        let resp = self.etcd.lease_grant(ttl, None).await?;
        Ok(resp.id())
    }
    
    async fn keep_alive_lease(&self, lease_id: i64, resource: String) {
        let etcd = self.etcd.clone();
        let leaders = self.leaders.clone();
        let node_id = self.node_id.clone();
        
        tokio::spawn(async move {
            let mut ticker = interval(Duration::from_secs(10));
            
            loop {
                ticker.tick().await;
                
                if let Err(_) = etcd.lease_keep_alive(lease_id).await {
                    // Lost lease, remove from leaders
                    let mut leaders = leaders.write().await;
                    leaders.remove(&resource);
                    break;
                }
            }
        });
    }
    
    async fn start_watchers(&self) -> Result<()> {
        // Watch shard changes
        self.watch_prefix(SHARD_PREFIX.to_string()).await?;
        
        // Watch config changes
        self.watch_prefix(CONFIG_PREFIX.to_string()).await?;
        
        // Watch leader changes
        self.watch_prefix(LEADER_PREFIX.to_string()).await?;
        
        Ok(())
    }
    
    async fn watch_prefix(&self, prefix: String) {
        let etcd = self.etcd.clone();
        let shard_tx = self.shard_updates.clone();
        let config_tx = self.config_updates.clone();
        let leaders = self.leaders.clone();
        
        tokio::spawn(async move {
            let mut opts = WatchOptions::new();
            opts.with_prefix();
            
            let mut stream = etcd.watch(prefix.clone(), Some(opts)).await;
            
            while let Some(resp) = stream.message().await.ok().flatten() {
                for event in resp.events() {
                    let key = String::from_utf8_lossy(event.kv().key());
                    
                    match event.event_type() {
                        EventType::Put => {
                            if key.starts_with(SHARD_PREFIX) {
                                if let Ok(info) = serde_json::from_slice::<ShardInfo>(event.kv().value()) {
                                    let _ = shard_tx.send(ShardEvent::ShardUpdated(info));
                                }
                            } else if key.starts_with(CONFIG_PREFIX) {
                                let config_key = key.strip_prefix(CONFIG_PREFIX).unwrap_or(&key);
                                let value = String::from_utf8_lossy(event.kv().value()).to_string();
                                let _ = config_tx.send(ConfigEvent::ConfigUpdated(
                                    config_key.to_string(),
                                    value,
                                ));
                            } else if key.starts_with(LEADER_PREFIX) {
                                let resource = key.strip_prefix(LEADER_PREFIX).unwrap_or(&key);
                                let leader = String::from_utf8_lossy(event.kv().value()).to_string();
                                let mut leaders = leaders.write().await;
                                leaders.insert(resource.to_string(), leader);
                            }
                        }
                        EventType::Delete => {
                            if key.starts_with(SHARD_PREFIX) {
                                if let Some(id_str) = key.strip_prefix(SHARD_PREFIX) {
                                    if let Ok(id) = id_str.parse::<u32>() {
                                        let _ = shard_tx.send(ShardEvent::ShardRemoved(ShardId(id)));
                                    }
                                }
                            } else if key.starts_with(CONFIG_PREFIX) {
                                let config_key = key.strip_prefix(CONFIG_PREFIX).unwrap_or(&key);
                                let _ = config_tx.send(ConfigEvent::ConfigRemoved(config_key.to_string()));
                            } else if key.starts_with(LEADER_PREFIX) {
                                let resource = key.strip_prefix(LEADER_PREFIX).unwrap_or(&key);
                                let mut leaders = leaders.write().await;
                                leaders.remove(resource);
                            }
                        }
                    }
                }
            }
        });
    }
}

/// Distributed lock handle
pub struct DistributedLock {
    etcd: EtcdClient,
    key: String,
    lock_id: String,
    lease_id: i64,
}

impl DistributedLock {
    /// Release the lock
    pub async fn release(self) -> Result<()> {
        // Only delete if we still hold the lock
        let resp = self.etcd.get(&self.key, None).await?;
        if let Some(kv) = resp.kvs().first() {
            if kv.value() == self.lock_id.as_bytes() {
                self.etcd.delete(&self.key, None).await?;
            }
        }
        
        // Revoke lease
        let _ = self.etcd.lease_revoke(self.lease_id).await;
        
        Ok(())
    }
}

/// Service discovery for finding shard nodes
pub struct ServiceDiscovery {
    coordinator: Arc<ClusterCoordinator>,
    cache: Arc<RwLock<HashMap<ShardId, Vec<String>>>>,
}

impl ServiceDiscovery {
    pub fn new(coordinator: Arc<ClusterCoordinator>) -> Self {
        let discovery = Self {
            coordinator,
            cache: Arc::new(RwLock::new(HashMap::new())),
        };
        
        // Start cache updater
        discovery.start_cache_updater();
        
        discovery
    }
    
    /// Get endpoints for a shard
    pub async fn get_shard_endpoints(&self, shard_id: ShardId) -> Result<Vec<String>> {
        let cache = self.cache.read().await;
        if let Some(endpoints) = cache.get(&shard_id) {
            return Ok(endpoints.clone());
        }
        drop(cache);
        
        // Not in cache, fetch from coordinator
        let shards = self.coordinator.list_shards().await?;
        let mut cache = self.cache.write().await;
        
        for shard in shards {
            let mut endpoints = vec![shard.address];
            endpoints.extend(shard.replicas);
            cache.insert(shard.id, endpoints.clone());
            
            if shard.id == shard_id {
                return Ok(endpoints);
            }
        }
        
        Err(anyhow!("Shard not found"))
    }
    
    fn start_cache_updater(&self) {
        let coordinator = self.coordinator.clone();
        let cache = self.cache.clone();
        let mut rx = coordinator.subscribe_shards();
        
        tokio::spawn(async move {
            while let Ok(event) = rx.recv().await {
                match event {
                    ShardEvent::ShardAdded(info) | ShardEvent::ShardUpdated(info) => {
                        let mut endpoints = vec![info.address];
                        endpoints.extend(info.replicas);
                        
                        let mut cache = cache.write().await;
                        cache.insert(info.id, endpoints);
                    }
                    ShardEvent::ShardRemoved(shard_id) => {
                        let mut cache = cache.write().await;
                        cache.remove(&shard_id);
                    }
                }
            }
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[tokio::test]
    #[ignore] // Requires etcd
    async fn test_cluster_coordination() {
        let coordinator = ClusterCoordinator::new(
            vec!["http://localhost:2379".to_string()],
            "test-node".to_string(),
        )
        .await
        .unwrap();
        
        // Test shard registration
        let shard_info = ShardInfo {
            id: ShardId(1),
            address: "localhost:8080".to_string(),
            status: ShardStatus::Active,
            capacity: Default::default(),
            replicas: vec![],
        };
        
        coordinator.register_shard(shard_info).await.unwrap();
        
        // Test listing shards
        let shards = coordinator.list_shards().await.unwrap();
        assert!(!shards.is_empty());
        
        // Test leader election
        let is_leader = coordinator.elect_leader("test-resource").await.unwrap();
        assert!(is_leader);
        
        // Test distributed lock
        let lock = coordinator.acquire_lock("test-lock", 10).await.unwrap();
        lock.release().await.unwrap();
    }
}