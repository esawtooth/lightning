#[cfg(test)]
mod tests {
    use super::super::*;
    use std::collections::HashSet;
    
    #[tokio::test]
    async fn test_consistent_hash_basic() {
        let router = ConsistentHashRouter::new();
        
        // Register a single shard
        let shard_info = ShardInfo {
            id: ShardId(0),
            address: "localhost:8080".to_string(),
            status: ShardStatus::Active,
            capacity: ShardCapacity {
                user_count: 0,
                storage_bytes: 0,
                cpu_percent: 0.0,
                memory_percent: 0.0,
            },
            replicas: vec![],
        };
        
        router.register_shard(shard_info).await.unwrap();
        
        // All users should route to the only shard
        let shard1 = router.route_user("user1").await.unwrap();
        let shard2 = router.route_user("user2").await.unwrap();
        
        assert_eq!(shard1, ShardId(0));
        assert_eq!(shard2, ShardId(0));
    }
    
    #[tokio::test]
    async fn test_consistent_hash_distribution() {
        let router = ConsistentHashRouter::new();
        
        // Register multiple shards
        for i in 0..5 {
            let info = ShardInfo {
                id: ShardId(i),
                address: format!("shard-{}.local:8080", i),
                status: ShardStatus::Active,
                capacity: ShardCapacity {
                    user_count: 0,
                    storage_bytes: 0,
                    cpu_percent: 0.0,
                    memory_percent: 0.0,
                },
                replicas: vec![],
            };
            router.register_shard(info).await.unwrap();
        }
        
        // Test distribution of users
        let mut distribution = HashMap::new();
        for i in 0..1000 {
            let user = format!("user{}", i);
            let shard = router.route_user(&user).await.unwrap();
            *distribution.entry(shard.0).or_insert(0) += 1;
        }
        
        // Check that distribution is relatively even
        // With 5 shards and 1000 users, expect ~200 per shard
        for (shard_id, count) in &distribution {
            assert!(
                *count > 100 && *count < 300,
                "Shard {} has {} users, expected ~200",
                shard_id,
                count
            );
        }
        
        // All shards should have some users
        assert_eq!(distribution.len(), 5);
    }
    
    #[tokio::test]
    async fn test_consistent_hash_stability() {
        let router = ConsistentHashRouter::new();
        
        // Register initial shards
        for i in 0..3 {
            let info = ShardInfo {
                id: ShardId(i),
                address: format!("shard-{}.local:8080", i),
                status: ShardStatus::Active,
                capacity: Default::default(),
                replicas: vec![],
            };
            router.register_shard(info).await.unwrap();
        }
        
        // Record initial routing
        let mut initial_routing = HashMap::new();
        for i in 0..100 {
            let user = format!("user{}", i);
            let shard = router.route_user(&user).await.unwrap();
            initial_routing.insert(user, shard);
        }
        
        // Add a new shard
        let new_shard = ShardInfo {
            id: ShardId(3),
            address: "shard-3.local:8080".to_string(),
            status: ShardStatus::Active,
            capacity: Default::default(),
            replicas: vec![],
        };
        router.register_shard(new_shard).await.unwrap();
        
        // Check how many users moved
        let mut moved_count = 0;
        for (user, old_shard) in &initial_routing {
            let new_shard = router.route_user(user).await.unwrap();
            if new_shard != *old_shard {
                moved_count += 1;
            }
        }
        
        // With consistent hashing, only ~25% of users should move
        assert!(
            moved_count < 35,
            "Too many users moved: {} out of 100",
            moved_count
        );
    }
    
    #[tokio::test]
    async fn test_shard_status_handling() {
        let router = ConsistentHashRouter::new();
        
        // Register shards with different statuses
        let shards = vec![
            (ShardId(0), ShardStatus::Active),
            (ShardId(1), ShardStatus::ReadOnly),
            (ShardId(2), ShardStatus::Draining),
            (ShardId(3), ShardStatus::Offline),
        ];
        
        for (id, status) in shards {
            let info = ShardInfo {
                id,
                address: format!("shard-{}.local:8080", id.0),
                status,
                capacity: Default::default(),
                replicas: vec![],
            };
            router.register_shard(info).await.unwrap();
        }
        
        // Users should only route to Active or ReadOnly shards
        let mut routed_shards = HashSet::new();
        for i in 0..100 {
            let user = format!("user{}", i);
            if let Ok(shard) = router.route_user(&user).await {
                routed_shards.insert(shard.0);
            }
        }
        
        // Should only route to shards 0 and 1 (Active and ReadOnly)
        assert!(routed_shards.contains(&0));
        assert!(routed_shards.contains(&1));
        assert!(!routed_shards.contains(&2)); // Draining
        assert!(!routed_shards.contains(&3)); // Offline
    }
    
    #[tokio::test]
    async fn test_shared_document_routing() {
        let router = ConsistentHashRouter::new();
        
        // Register shards
        for i in 0..3 {
            let info = ShardInfo {
                id: ShardId(i),
                address: format!("shard-{}.local:8080", i),
                status: ShardStatus::Active,
                capacity: Default::default(),
                replicas: vec![],
            };
            router.register_shard(info).await.unwrap();
        }
        
        // Test routing for a shared document
        let doc_id = Uuid::new_v4();
        let users = vec![
            "alice@example.com".to_string(),
            "bob@example.com".to_string(),
            "charlie@example.com".to_string(),
        ];
        
        let shards = router.route_shared(doc_id, &users).await.unwrap();
        
        // Should return shards for all users (may be 1-3 shards)
        assert!(!shards.is_empty());
        assert!(shards.len() <= 3);
        
        // All returned shards should be unique
        let unique_shards: HashSet<_> = shards.iter().collect();
        assert_eq!(unique_shards.len(), shards.len());
    }
    
    #[tokio::test]
    async fn test_shard_failover() {
        let router = ConsistentHashRouter::new();
        
        // Register initial shards
        for i in 0..3 {
            let info = ShardInfo {
                id: ShardId(i),
                address: format!("shard-{}.local:8080", i),
                status: ShardStatus::Active,
                capacity: Default::default(),
                replicas: vec![],
            };
            router.register_shard(info).await.unwrap();
        }
        
        // Get initial routing for a user
        let user = "test_user";
        let initial_shard = router.route_user(user).await.unwrap();
        
        // Mark that shard as offline
        router.update_shard_status(initial_shard, ShardStatus::Offline).await.unwrap();
        
        // User should now route to a different shard
        let new_shard = router.route_user(user).await.unwrap();
        assert_ne!(initial_shard, new_shard);
        
        // Mark original shard as active again
        router.update_shard_status(initial_shard, ShardStatus::Active).await.unwrap();
        
        // User should route back to original shard
        let final_shard = router.route_user(user).await.unwrap();
        assert_eq!(initial_shard, final_shard);
    }
    
    #[tokio::test]
    async fn test_shard_capacity_monitoring() {
        let monitor = ShardMonitor::new(Arc::new(ConsistentHashRouter::new()));
        
        let shard_normal = ShardInfo {
            id: ShardId(0),
            address: "shard-0:8080".to_string(),
            status: ShardStatus::Active,
            capacity: ShardCapacity {
                user_count: 10_000,
                storage_bytes: 10 * 1024 * 1024 * 1024, // 10GB
                cpu_percent: 50.0,
                memory_percent: 60.0,
            },
            replicas: vec![],
        };
        
        let shard_overloaded = ShardInfo {
            id: ShardId(1),
            address: "shard-1:8080".to_string(),
            status: ShardStatus::Active,
            capacity: ShardCapacity {
                user_count: 60_000, // Over threshold
                storage_bytes: 150 * 1024 * 1024 * 1024, // 150GB - over threshold
                cpu_percent: 85.0, // Over threshold
                memory_percent: 90.0, // Over threshold
            },
            replicas: vec![],
        };
        
        assert!(!monitor.needs_rebalance(&shard_normal));
        assert!(monitor.needs_rebalance(&shard_overloaded));
    }
    
    #[tokio::test]
    async fn test_virtual_nodes_distribution() {
        let router = ConsistentHashRouter::new();
        
        // Register two shards
        let shard1 = ShardInfo {
            id: ShardId(0),
            address: "shard-0:8080".to_string(),
            status: ShardStatus::Active,
            capacity: Default::default(),
            replicas: vec![],
        };
        
        let shard2 = ShardInfo {
            id: ShardId(1),
            address: "shard-1:8080".to_string(),
            status: ShardStatus::Active,
            capacity: Default::default(),
            replicas: vec![],
        };
        
        router.register_shard(shard1).await.unwrap();
        router.register_shard(shard2).await.unwrap();
        
        // With virtual nodes, distribution should be very even
        let mut distribution = HashMap::new();
        for i in 0..10000 {
            let user = format!("test_user_{}", i);
            let shard = router.route_user(&user).await.unwrap();
            *distribution.entry(shard.0).or_insert(0) += 1;
        }
        
        // Check distribution is within 10% of perfect (5000 each)
        for (_, count) in &distribution {
            assert!(
                *count > 4500 && *count < 5500,
                "Distribution not balanced: {}",
                count
            );
        }
    }
}