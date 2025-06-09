//! CRDT-based document storage built on [Automerge](https://crates.io/crates/automerge).
//! Documents are stored individually on disk and loaded at startup.

use anyhow::Result;
use automerge::{transaction::Transactable, AutoCommit, ObjType, ReadDoc, ROOT};
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
};
use uuid::Uuid;

/// In-memory wrapper around an Automerge document.
pub struct Document {
    id: Uuid,
    doc: AutoCommit,
}

impl Document {
    pub fn new(id: Uuid, text: &str) -> Result<Self> {
        let mut doc = AutoCommit::new();
        let text_id = doc.put_object(ROOT, "text", ObjType::Text)?;
        doc.splice_text(&text_id, 0, 0, text)?;
        Ok(Self { id, doc })
    }

    pub fn id(&self) -> Uuid {
        self.id
    }

    pub fn text(&self) -> String {
        let text_id = self.doc.get(ROOT, "text").unwrap().unwrap().1;
        self.doc.text(&text_id).unwrap_or_default()
    }

    pub fn set_text(&mut self, text: &str) -> Result<()> {
        let text_id = self.doc.get(ROOT, "text")?.unwrap().1;
        let len = self.doc.length(&text_id) as isize;
        self.doc.splice_text(&text_id, 0, len, text)?;
        Ok(())
    }

    pub fn save(&mut self, path: &Path) -> Result<()> {
        std::fs::write(path, self.doc.save())?;
        Ok(())
    }

    pub fn load(id: Uuid, path: &Path) -> Result<Self> {
        let bytes = std::fs::read(path)?;
        let doc = AutoCommit::load(&bytes)?;
        Ok(Self { id, doc })
    }
}

/// Simple filesystem-backed store for `Document` instances.
pub struct DocumentStore {
    docs: HashMap<Uuid, Document>,
    dir: PathBuf,
}

impl DocumentStore {
    pub fn new(dir: impl Into<PathBuf>) -> Result<Self> {
        let dir = dir.into();
        std::fs::create_dir_all(&dir)?;
        // load existing
        let mut docs = HashMap::new();
        for entry in std::fs::read_dir(&dir)? {
            let entry = entry?;
            if entry.file_type()?.is_file() {
                if let Some(name) = entry.path().file_stem().and_then(|s| s.to_str()) {
                    if let Ok(id) = Uuid::parse_str(name) {
                        if let Ok(doc) = Document::load(id, &entry.path()) {
                            docs.insert(id, doc);
                        }
                    }
                }
            }
        }
        Ok(Self { docs, dir })
    }

    fn path(&self, id: Uuid) -> PathBuf {
        self.dir.join(format!("{}.bin", id))
    }

    pub fn create(&mut self, text: &str) -> Result<Uuid> {
        let id = Uuid::new_v4();
        let mut doc = Document::new(id, text)?;
        doc.save(&self.path(id))?;
        self.docs.insert(id, doc);
        Ok(id)
    }

    pub fn get(&self, id: Uuid) -> Option<&Document> {
        self.docs.get(&id)
    }

    pub fn update(&mut self, id: Uuid, text: &str) -> Result<()> {
        let path = self.path(id);
        if let Some(doc) = self.docs.get_mut(&id) {
            doc.set_text(text)?;
            doc.save(&path)?;
        }
        Ok(())
    }

    pub fn delete(&mut self, id: Uuid) -> Result<()> {
        self.docs.remove(&id);
        let _ = std::fs::remove_file(self.path(id));
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn create_and_update_document() {
        let tempdir = tempfile::tempdir().unwrap();
        let mut store = DocumentStore::new(tempdir.path()).unwrap();
        let id = store.create("hello").unwrap();
        assert_eq!(store.get(id).unwrap().text(), "hello");
        store.update(id, "world").unwrap();
        assert_eq!(store.get(id).unwrap().text(), "world");
        store.delete(id).unwrap();
        assert!(store.get(id).is_none());
    }
}
