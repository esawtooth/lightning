//! CRDT-based document storage built on [Automerge](https://crates.io/crates/automerge).
//! Documents are stored individually on disk and loaded at startup.

use anyhow::Result;
use automerge::{transaction::Transactable, AutoCommit, ObjType, ReadDoc, ScalarValue, ROOT};
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
};
use uuid::Uuid;

const DEFAULT_USER: &str = "user1";

/// Different kinds of documents managed by the store.
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum DocumentType {
    Folder,
    IndexGuide,
    Text,
}
/// In-memory wrapper around an Automerge document.
pub struct Document {
    id: Uuid,
    doc: AutoCommit,
    owner: String,
    name: String,
    parent_folder_id: Option<Uuid>,
    doc_type: DocumentType,
}

impl Document {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        id: Uuid,
        name: String,
        text: &str,
        owner: String,
        parent_folder_id: Option<Uuid>,
        doc_type: DocumentType,
    ) -> Result<Self> {
        let mut doc = AutoCommit::new();
        let text_id = doc.put_object(ROOT, "text", ObjType::Text)?;
        doc.splice_text(&text_id, 0, 0, text)?;
        doc.put(ROOT, "name", name.clone())?;
        doc.put(ROOT, "owner", owner.clone())?;
        if let Some(folder_id) = parent_folder_id {
            doc.put(ROOT, "parent_folder_id", folder_id.to_string())?;
        } else {
            doc.put(ROOT, "parent_folder_id", ScalarValue::Null)?;
        }
        let doc_type_str = match doc_type {
            DocumentType::Folder => "folder",
            DocumentType::IndexGuide => "indexGuide",
            DocumentType::Text => "text",
        };
        doc.put(ROOT, "doc_type", doc_type_str)?;
        Ok(Self {
            id,
            doc,
            owner,
            name,
            parent_folder_id,
            doc_type,
        })
    }

    pub fn id(&self) -> Uuid {
        self.id
    }

    pub fn owner(&self) -> &str {
        &self.owner
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn parent_folder_id(&self) -> Option<Uuid> {
        self.parent_folder_id
    }

    pub fn doc_type(&self) -> DocumentType {
        self.doc_type
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

    pub fn load(id: Uuid, path: &Path, owner: String) -> Result<Self> {
        let bytes = std::fs::read(path)?;
        let doc = AutoCommit::load(&bytes)?;
        let name = if let Some((v, _)) = doc.get(ROOT, "name")? {
            v.to_str()
                .map(|s| s.to_string())
                .unwrap_or_else(|| id.to_string())
        } else {
            id.to_string()
        };
        let parent_folder_id = if let Some((v, _)) = doc.get(ROOT, "parent_folder_id")? {
            v.to_str().and_then(|s| Uuid::parse_str(s).ok())
        } else {
            None
        };
        let doc_type = if let Some((v, _)) = doc.get(ROOT, "doc_type")? {
            match v.to_str() {
                Some("folder") => DocumentType::Folder,
                Some("indexGuide") => DocumentType::IndexGuide,
                _ => DocumentType::Text,
            }
        } else {
            DocumentType::Text
        };
        Ok(Self {
            id,
            doc,
            owner,
            name,
            parent_folder_id,
            doc_type,
        })
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
                        if let Ok(doc) = Document::load(id, &entry.path(), DEFAULT_USER.to_string())
                        {
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

    #[allow(clippy::too_many_arguments)]
    pub fn create(
        &mut self,
        name: String,
        text: &str,
        owner: String,
        parent_folder_id: Option<Uuid>,
        doc_type: DocumentType,
    ) -> Result<Uuid> {
        let id = Uuid::new_v4();
        let mut doc = Document::new(id, name, text, owner, parent_folder_id, doc_type)?;
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
        let id = store
            .create(
                "test.txt".to_string(),
                "hello",
                "user1".to_string(),
                None,
                DocumentType::Text,
            )
            .unwrap();
        let doc = store.get(id).unwrap();
        assert_eq!(doc.text(), "hello");
        assert_eq!(doc.name(), "test.txt");
        assert_eq!(doc.owner(), "user1");
        store.update(id, "world").unwrap();
        assert_eq!(store.get(id).unwrap().text(), "world");
        store.delete(id).unwrap();
        assert!(store.get(id).is_none());
    }

    #[test]
    fn document_text_roundtrip() {
        let id = Uuid::new_v4();
        let mut doc = Document::new(
            id,
            "doc.txt".to_string(),
            "hello",
            "user".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();
        assert_eq!(doc.text(), "hello");
        doc.set_text("goodbye").unwrap();
        assert_eq!(doc.text(), "goodbye");
    }

    #[test]
    fn store_persists_to_disk() {
        let tempdir = tempfile::tempdir().unwrap();
        let mut store = DocumentStore::new(tempdir.path()).unwrap();
        let id = store
            .create(
                "persist.txt".to_string(),
                "persist",
                "user1".to_string(),
                None,
                DocumentType::Text,
            )
            .unwrap();
        store.update(id, "changed").unwrap();
        drop(store);

        let store2 = DocumentStore::new(tempdir.path()).unwrap();
        let doc = store2.get(id).unwrap();
        assert_eq!(doc.text(), "changed");
    }
}
