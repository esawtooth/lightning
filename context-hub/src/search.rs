use anyhow::Result;
use std::path::Path;
use tantivy::{
    collector::TopDocs,
    directory::MmapDirectory,
    doc,
    schema::{Schema, STORED, STRING, TEXT},
    Index, ReloadPolicy,
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
}
