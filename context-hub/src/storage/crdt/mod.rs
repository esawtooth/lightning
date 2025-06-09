//! CRDT-based document storage built on [Automerge](https://crates.io/crates/automerge).
//! Documents are stored individually on disk and loaded at startup.

use anyhow::Result;
use automerge::{transaction::Transactable, AutoCommit, ObjType, ReadDoc, ROOT, Value, ScalarValue};
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
};
use uuid::Uuid;

const DEFAULT_USER: &str = "user1";
const CONTENT_KEY: &str = "content";

/// Different kinds of documents managed by the store.
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum DocumentType {
    Folder,
    IndexGuide,
    Text,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Pointer {
    pub pointer_type: String,
    pub target: String,
    pub name: Option<String>,
    pub preview_text: Option<String>,
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
        let list_id = doc.put_object(ROOT, CONTENT_KEY, ObjType::List)?;
        doc.insert(&list_id, 0, text)?;
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
        let list_id = self.doc.get(ROOT, CONTENT_KEY).unwrap().unwrap().1;
        let len = self.doc.length(&list_id);
        let mut out = String::new();
        for i in 0..len {
            if let Ok(Some((val, _))) = self.doc.get(&list_id, i) {
                match val {
                    Value::Scalar(s) => {
                        if let ScalarValue::Str(s) = s.as_ref() {
                            out.push_str(s);
                        }
                    }
                    _ => out.push_str("[pointer]"),
                }
            }
        }
        out
    }

    pub fn set_text(&mut self, text: &str) -> Result<()> {
        let list_id = self.doc.get(ROOT, CONTENT_KEY)?.unwrap().1;
        let len = self.doc.length(&list_id);
        for i in (0..len).rev() {
            self.doc.delete(&list_id, i)?;
        }
        self.doc.insert(&list_id, 0, text)?;
        Ok(())
    }

    pub fn insert_pointer(&mut self, index: usize, pointer: Pointer) -> Result<()> {
        let list_id = self.doc.get(ROOT, CONTENT_KEY)?.unwrap().1;
        let ptr_id = self.doc.insert_object(&list_id, index, ObjType::Map)?;
        self.doc.put(&ptr_id, "type", pointer.pointer_type)?;
        self.doc.put(&ptr_id, "target", pointer.target)?;
        if let Some(name) = pointer.name {
            self.doc.put(&ptr_id, "name", name)?;
        }
        if let Some(preview) = pointer.preview_text {
            self.doc.put(&ptr_id, "preview_text", preview)?;
        }
        Ok(())
    }

    pub fn remove_at(&mut self, index: usize) -> Result<()> {
        let list_id = self.doc.get(ROOT, CONTENT_KEY)?.unwrap().1;
        self.doc.delete(&list_id, index)?;
        Ok(())
    }

    pub fn save(&mut self, path: &Path) -> Result<()> {
        std::fs::write(path, self.doc.save())?;
        Ok(())
    }

    pub fn load(id: Uuid, path: &Path, owner: String) -> Result<Self> {
        let bytes = std::fs::read(path)?;
        let doc = AutoCommit::load(&bytes)?;
        Ok(Self {
            id,
            doc,
            owner,
            name: id.to_string(),
            parent_folder_id: None,
            doc_type: DocumentType::Text,
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
                        if let Ok(doc) = Document::load(id, &entry.path(), DEFAULT_USER.to_string()) {
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

        // test pointer insertion
        let ptr = Pointer {
            pointer_type: "blob".to_string(),
            target: "123".to_string(),
            name: Some("file.pdf".to_string()),
            preview_text: None,
        };
        let doc_mut = store.docs.get_mut(&id).unwrap();
        doc_mut.insert_pointer(1, ptr).unwrap();
        assert_eq!(doc_mut.text(), "world[pointer]");
        doc_mut.remove_at(1).unwrap();
        assert_eq!(doc_mut.text(), "world");
        store.delete(id).unwrap();
        assert!(store.get(id).is_none());
    }

    #[test]
    fn document_text_roundtrip() {
        let id = Uuid::new_v4();
        let mut doc = Document::new(
            id,
            "file.txt".to_string(),
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
