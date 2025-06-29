//! Storage metrics tracking for Context Hub
//! 
//! Monitors storage usage across all components and determines when compression is needed.

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use tokio::fs;
use walkdir::WalkDir;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StorageMetrics {
    /// Size in bytes at last snapshot
    pub last_snapshot_size: u64,
    /// Current total size in bytes
    pub current_size: u64,
    /// Breakdown by component
    pub component_sizes: HashMap<String, u64>,
    /// Timestamp of last calculation
    pub calculated_at: chrono::DateTime<chrono::Utc>,
}

impl StorageMetrics {
    pub fn new() -> Self {
        Self {
            last_snapshot_size: 0,
            current_size: 0,
            component_sizes: HashMap::new(),
            calculated_at: chrono::Utc::now(),
        }
    }

    /// Calculate current storage usage across all components
    pub async fn calculate_current(
        data_dir: &Path,
        index_dir: &Path,
        blob_dir: Option<&Path>,
        wal_dir: &Path,
    ) -> Result<Self> {
        let mut metrics = Self::new();
        let mut components = HashMap::new();

        // Calculate document storage size
        let doc_size = Self::calculate_dir_size(data_dir).await?;
        components.insert("documents".to_string(), doc_size);

        // Calculate index size
        let index_size = Self::calculate_dir_size(index_dir).await?;
        components.insert("index".to_string(), index_size);

        // Calculate blob storage size if configured
        if let Some(blob_path) = blob_dir {
            let blob_size = Self::calculate_dir_size(blob_path).await?;
            components.insert("blobs".to_string(), blob_size);
        }

        // Calculate WAL size
        let wal_size = Self::calculate_wal_size(wal_dir).await?;
        components.insert("wal".to_string(), wal_size);

        // Calculate total
        let total: u64 = components.values().sum();
        
        metrics.current_size = total;
        metrics.component_sizes = components;
        metrics.calculated_at = chrono::Utc::now();

        Ok(metrics)
    }

    /// Calculate the size of a directory recursively
    async fn calculate_dir_size(dir: &Path) -> Result<u64> {
        if !dir.exists() {
            return Ok(0);
        }

        let mut total_size = 0u64;
        
        for entry in WalkDir::new(dir).into_iter().filter_map(|e| e.ok()) {
            if entry.file_type().is_file() {
                if let Ok(metadata) = entry.metadata() {
                    total_size += metadata.len();
                }
            }
        }

        Ok(total_size)
    }

    /// Calculate WAL size (only .log files)
    pub async fn calculate_wal_size(wal_dir: &Path) -> Result<u64> {
        if !wal_dir.exists() {
            return Ok(0);
        }

        let mut total_size = 0u64;
        let mut entries = fs::read_dir(wal_dir).await?;
        
        while let Some(entry) = entries.next_entry().await? {
            let path = entry.path();
            if path.extension().and_then(|s| s.to_str()) == Some("log") {
                if let Ok(metadata) = entry.metadata().await {
                    total_size += metadata.len();
                }
            }
        }

        Ok(total_size)
    }

    /// Calculate growth percentage since last snapshot
    pub fn growth_percentage(&self) -> f64 {
        if self.last_snapshot_size == 0 {
            return 100.0; // First snapshot
        }
        
        let growth = self.current_size as f64 - self.last_snapshot_size as f64;
        (growth / self.last_snapshot_size as f64) * 100.0
    }

    /// Check if compression should be triggered based on threshold
    pub fn should_compress(&self, threshold_percent: f64) -> bool {
        self.growth_percentage() >= threshold_percent
    }

    /// Update metrics after a successful snapshot
    pub fn mark_snapshot(&mut self) {
        self.last_snapshot_size = self.current_size;
    }

    /// Get human-readable size
    pub fn format_size(bytes: u64) -> String {
        const UNITS: &[&str] = &["B", "KB", "MB", "GB", "TB"];
        let mut size = bytes as f64;
        let mut unit_index = 0;

        while size >= 1024.0 && unit_index < UNITS.len() - 1 {
            size /= 1024.0;
            unit_index += 1;
        }

        format!("{:.2} {}", size, UNITS[unit_index])
    }

    /// Get a summary report
    pub fn summary(&self) -> String {
        let mut report = format!(
            "Storage Metrics ({})\n",
            self.calculated_at.format("%Y-%m-%d %H:%M:%S UTC")
        );
        report.push_str(&format!(
            "Total Size: {} ({}% growth)\n",
            Self::format_size(self.current_size),
            self.growth_percentage() as i64
        ));
        report.push_str("Components:\n");
        
        for (component, size) in &self.component_sizes {
            let percentage = (*size as f64 / self.current_size as f64) * 100.0;
            report.push_str(&format!(
                "  {}: {} ({:.1}%)\n",
                component,
                Self::format_size(*size),
                percentage
            ));
        }
        
        report
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    use tokio::fs::File;
    use tokio::io::AsyncWriteExt;

    #[tokio::test]
    async fn test_calculate_dir_size() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let path = temp_dir.path();

        // Create some test files
        let mut file1 = File::create(path.join("file1.txt")).await?;
        file1.write_all(b"Hello").await?;
        file1.sync_all().await?;

        let mut file2 = File::create(path.join("file2.txt")).await?;
        file2.write_all(b"World!").await?;
        file2.sync_all().await?;

        let size = StorageMetrics::calculate_dir_size(path).await?;
        assert_eq!(size, 11); // "Hello" (5) + "World!" (6)

        Ok(())
    }

    #[test]
    fn test_growth_percentage() {
        let mut metrics = StorageMetrics::new();
        metrics.last_snapshot_size = 1000;
        metrics.current_size = 2000;
        
        assert_eq!(metrics.growth_percentage(), 100.0);
        
        metrics.current_size = 1500;
        assert_eq!(metrics.growth_percentage(), 50.0);
        
        metrics.current_size = 1000;
        assert_eq!(metrics.growth_percentage(), 0.0);
    }

    #[test]
    fn test_format_size() {
        assert_eq!(StorageMetrics::format_size(512), "512.00 B");
        assert_eq!(StorageMetrics::format_size(1024), "1.00 KB");
        assert_eq!(StorageMetrics::format_size(1536), "1.50 KB");
        assert_eq!(StorageMetrics::format_size(1048576), "1.00 MB");
        assert_eq!(StorageMetrics::format_size(1073741824), "1.00 GB");
    }
}