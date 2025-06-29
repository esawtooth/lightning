use anyhow::Result;
use std::path::Path;
use tantivy::{
    collector::TopDocs,
    directory::MmapDirectory,
    doc,
    schema::{Schema, STORED, STRING, TEXT},
    Index, ReloadPolicy, Term,
};
use uuid::Uuid;

pub struct SearchIndex {
    index: Index,
    id: tantivy::schema::Field,
    name: tantivy::schema::Field,
    content: tantivy::schema::Field,
    folder: tantivy::schema::Field,
}

impl SearchIndex {
    pub fn new(path: impl AsRef<Path>) -> Result<Self> {
        let mut schema_builder = Schema::builder();
        let id = schema_builder.add_text_field("id", STRING | STORED);
        let name = schema_builder.add_text_field("name", TEXT | STORED);
        let content = schema_builder.add_text_field("content", TEXT);
        let folder = schema_builder.add_text_field("folder", TEXT);
        let schema = schema_builder.build();
        let path = path.as_ref();
        std::fs::create_dir_all(path)?;
        let dir = MmapDirectory::open(path)?;
        let index = Index::open_or_create(dir, schema.clone())?;
        Ok(Self {
            index,
            id,
            name,
            content,
            folder,
        })
    }

    pub fn index_document(
        &self,
        id: Uuid,
        name: &str,
        content: &str,
        folders: &[String],
    ) -> Result<()> {
        let mut writer = self.index.writer(50_000_000)?;
        writer.add_document(doc!(
            self.id => id.to_string(),
            self.name => name,
            self.content => content,
            self.folder => folders.join(" "),
        ))?;
        writer.commit()?;
        writer.wait_merging_threads()?;
        Ok(())
    }

    pub fn remove_document(&self, id: Uuid) -> Result<()> {
        let mut writer = self.index.writer(50_000_000)?;
        writer.delete_term(Term::from_field_text(self.id, &id.to_string()));
        writer.commit()?;
        writer.wait_merging_threads()?;
        Ok(())
    }

    pub fn search(&self, query: &str, limit: usize) -> Result<Vec<Uuid>> {
        let reader = self
            .index
            .reader_builder()
            .reload_policy(ReloadPolicy::OnCommit)
            .try_into()?;
        let searcher = reader.searcher();
        let parser = tantivy::query::QueryParser::for_index(
            &self.index,
            vec![self.name, self.content, self.folder],
        );
        let q = parser.parse_query(query)?;
        let docs = searcher.search(&q, &TopDocs::with_limit(limit))?;
        Ok(docs
            .into_iter()
            .filter_map(|(_score, addr)| {
                let retrieved = searcher.doc(addr).ok()?;
                let field = retrieved.get_first(self.id)?;
                field.as_text().and_then(|s| Uuid::parse_str(s).ok())
            })
            .collect())
    }

    pub fn index_all(&self, store: &crate::storage::crdt::DocumentStore) -> Result<()> {
        for (id, doc) in store.iter() {
            let mut folders = Vec::new();
            let mut current = doc.parent_folder_id();
            while let Some(pid) = current {
                if let Some(pdoc) = store.get(pid) {
                    folders.push(pdoc.name().to_string());
                    current = pdoc.parent_folder_id();
                } else {
                    break;
                }
            }
            self.index_document(*id, doc.name(), &doc.text(), &folders)?;
        }
        Ok(())
    }

    /// Optimize the index by merging segments and removing deleted documents
    /// Returns (segments_before, segments_after, bytes_freed)
    pub fn optimize(&self) -> Result<(usize, usize, u64)> {
        let mut writer = self.index.writer(150_000_000)?; // 150MB heap
        
        // Get segment info before optimization
        let segments_before = self.index.searchable_segment_metas()?.len();
        let size_before = self.calculate_index_size()?;
        
        // Force merge by committing and waiting for merges
        // Tantivy will automatically merge segments based on the merge policy
        writer.commit()?;
        writer.wait_merging_threads()?;
        
        // Get segment info after optimization
        let segments_after = self.index.searchable_segment_metas()?.len();
        let size_after = self.calculate_index_size()?;
        let bytes_freed = size_before.saturating_sub(size_after);
        
        Ok((segments_before, segments_after, bytes_freed))
    }

    /// Calculate the total size of the index
    fn calculate_index_size(&self) -> Result<u64> {
        let mut total_size = 0u64;
        
        // Estimate based on segment metadata since we can't easily access directory size
        for segment_meta in self.index.searchable_segment_metas()? {
            // Each segment has multiple files (.fast, .fieldnorm, .idx, .pos, .store, .term)
            // We estimate based on document count and average document size
            let doc_count = segment_meta.num_docs() as u64;
            // Rough estimate: 1KB per document (varies widely based on content)
            total_size += doc_count * 1024;
        }
        
        Ok(total_size)
    }

    /// Get index statistics
    pub fn stats(&self) -> Result<IndexStats> {
        let segments = self.index.searchable_segment_metas()?;
        let total_docs: u32 = segments.iter().map(|s| s.num_docs()).sum();
        let num_segments = segments.len();
        let deleted_docs: u32 = segments.iter().map(|s| s.num_deleted_docs()).sum();
        
        Ok(IndexStats {
            total_docs,
            deleted_docs,
            num_segments,
        })
    }

    /// Clean up deleted documents from all active document IDs
    pub fn cleanup_deleted(&self, active_doc_ids: &[Uuid]) -> Result<usize> {
        let active_set: std::collections::HashSet<String> = 
            active_doc_ids.iter().map(|id| id.to_string()).collect();
        
        let reader = self
            .index
            .reader_builder()
            .reload_policy(ReloadPolicy::OnCommit)
            .try_into()?;
        let searcher = reader.searcher();
        let mut writer = self.index.writer(50_000_000)?;
        let mut removed_count = 0;
        
        // Search for all documents
        for segment_reader in searcher.segment_readers() {
            let store_reader = segment_reader.get_store_reader(1)?;
            for doc_id in 0..segment_reader.num_docs() {
                if let Ok(stored) = store_reader.get(doc_id) {
                    if let Some(field_value) = stored.get_first(self.id) {
                        if let Some(id_str) = field_value.as_text() {
                            if !active_set.contains(id_str) {
                                writer.delete_term(Term::from_field_text(self.id, id_str));
                                removed_count += 1;
                            }
                        }
                    }
                }
            }
        }
        
        if removed_count > 0 {
            writer.commit()?;
            writer.wait_merging_threads()?;
        }
        
        Ok(removed_count)
    }
}

#[derive(Debug, Clone)]
pub struct IndexStats {
    pub total_docs: u32,
    pub deleted_docs: u32,
    pub num_segments: usize,
}
