//! Tests for storage metrics module

use anyhow::Result;
use context_hub_core::storage::metrics::StorageMetrics;
use std::fs;
use tempfile::TempDir;
use tokio::fs::File;
use tokio::io::AsyncWriteExt;

#[tokio::test]
async fn test_storage_metrics_calculation() -> Result<()> {
    let temp_dir = TempDir::new()?;
    let data_dir = temp_dir.path().join("data");
    let index_dir = temp_dir.path().join("index");
    let blob_dir = temp_dir.path().join("blobs");
    let wal_dir = temp_dir.path().join("wal");

    // Create directories
    fs::create_dir_all(&data_dir)?;
    fs::create_dir_all(&index_dir)?;
    fs::create_dir_all(&blob_dir)?;
    fs::create_dir_all(&wal_dir)?;

    // Create test files
    let mut data_file = File::create(data_dir.join("doc1.bin")).await?;
    data_file.write_all(&vec![0u8; 1024]).await?; // 1KB
    data_file.sync_all().await?;

    let mut index_file = File::create(index_dir.join("segment.idx")).await?;
    index_file.write_all(&vec![0u8; 2048]).await?; // 2KB
    index_file.sync_all().await?;

    let mut blob_file = File::create(blob_dir.join("blob1.dat")).await?;
    blob_file.write_all(&vec![0u8; 4096]).await?; // 4KB
    blob_file.sync_all().await?;

    let mut wal_file = File::create(wal_dir.join("wal-00000001.log")).await?;
    wal_file.write_all(&vec![0u8; 512]).await?; // 512B
    wal_file.sync_all().await?;

    // Calculate metrics
    let metrics = StorageMetrics::calculate_current(
        &data_dir,
        &index_dir,
        Some(&blob_dir),
        &wal_dir,
    ).await?;

    // Verify sizes
    assert_eq!(metrics.component_sizes["documents"], 1024);
    assert_eq!(metrics.component_sizes["index"], 2048);
    assert_eq!(metrics.component_sizes["blobs"], 4096);
    assert_eq!(metrics.component_sizes["wal"], 512);
    assert_eq!(metrics.current_size, 1024 + 2048 + 4096 + 512);

    Ok(())
}

#[test]
fn test_growth_percentage() {
    let mut metrics = StorageMetrics::new();
    
    // Test first snapshot (no previous size)
    metrics.current_size = 1000;
    assert_eq!(metrics.growth_percentage(), 100.0);
    
    // Test growth
    metrics.last_snapshot_size = 1000;
    metrics.current_size = 1500;
    assert_eq!(metrics.growth_percentage(), 50.0);
    
    // Test shrinkage
    metrics.current_size = 800;
    assert_eq!(metrics.growth_percentage(), -20.0);
    
    // Test no change
    metrics.current_size = 1000;
    assert_eq!(metrics.growth_percentage(), 0.0);
}

#[test]
fn test_should_compress() {
    let mut metrics = StorageMetrics::new();
    metrics.last_snapshot_size = 1000;
    
    // Below threshold
    metrics.current_size = 1499;
    assert!(!metrics.should_compress(50.0));
    
    // At threshold
    metrics.current_size = 1500;
    assert!(metrics.should_compress(50.0));
    
    // Above threshold
    metrics.current_size = 2000;
    assert!(metrics.should_compress(50.0));
    
    // First snapshot always triggers
    metrics.last_snapshot_size = 0;
    metrics.current_size = 100;
    assert!(metrics.should_compress(50.0));
}

#[test]
fn test_format_size() {
    assert_eq!(StorageMetrics::format_size(0), "0.00 B");
    assert_eq!(StorageMetrics::format_size(512), "512.00 B");
    assert_eq!(StorageMetrics::format_size(1024), "1.00 KB");
    assert_eq!(StorageMetrics::format_size(1536), "1.50 KB");
    assert_eq!(StorageMetrics::format_size(1048576), "1.00 MB");
    assert_eq!(StorageMetrics::format_size(1572864), "1.50 MB");
    assert_eq!(StorageMetrics::format_size(1073741824), "1.00 GB");
    assert_eq!(StorageMetrics::format_size(1099511627776), "1.00 TB");
}

#[test]
fn test_metrics_summary() {
    let mut metrics = StorageMetrics::new();
    metrics.last_snapshot_size = 1000000; // 1MB
    metrics.current_size = 1500000; // 1.5MB
    metrics.component_sizes.insert("documents".to_string(), 800000);
    metrics.component_sizes.insert("index".to_string(), 400000);
    metrics.component_sizes.insert("blobs".to_string(), 300000);
    
    let summary = metrics.summary();
    
    // Verify summary contains expected information
    assert!(summary.contains("Total Size: 1.43 MB"));
    assert!(summary.contains("50% growth"));
    assert!(summary.contains("documents: 781.25 KB"));
    assert!(summary.contains("index: 390.62 KB"));
    assert!(summary.contains("blobs: 292.97 KB"));
}

#[tokio::test]
async fn test_wal_size_calculation() -> Result<()> {
    let temp_dir = TempDir::new()?;
    let wal_dir = temp_dir.path();

    // Create WAL files and non-WAL files
    let mut wal1 = File::create(wal_dir.join("wal-00000001.log")).await?;
    wal1.write_all(&vec![0u8; 1024]).await?;
    wal1.sync_all().await?;

    let mut wal2 = File::create(wal_dir.join("wal-00000002.log")).await?;
    wal2.write_all(&vec![0u8; 2048]).await?;
    wal2.sync_all().await?;

    // This should not be counted
    let mut other = File::create(wal_dir.join("other.txt")).await?;
    other.write_all(&vec![0u8; 512]).await?;
    other.sync_all().await?;

    // Calculate WAL size only
    let wal_size = StorageMetrics::calculate_wal_size(wal_dir).await?;
    assert_eq!(wal_size, 3072); // 1024 + 2048, excluding other.txt

    Ok(())
}