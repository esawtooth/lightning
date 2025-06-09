//! CRDT-based document storage built on [Automerge](https://crates.io/crates/automerge).
//! Documents are stored individually on disk and loaded at startup.

use anyhow::Result;
use automerge::{
    transaction::Transactable, AutoCommit, ObjType, ReadDoc, ScalarValue, Value, ROOT,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
};
use uuid::Uuid;

const DEFAULT_USER: &str = "user1";
const CONTENT_KEY: &str = "content";
const CHILDREN_KEY: &str = "children";

/// Different kinds of documents managed by the store.
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum DocumentType {
    Folder,
    IndexGuide,
    Text,
}

impl DocumentType {
    fn as_str(&self) -> &'static str {
        match self {
            DocumentType::Folder => "Folder",
            DocumentType::IndexGuide => "IndexGuide",
            DocumentType::Text => "Text",
        }
    }
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
        match doc_type {
            DocumentType::Folder => {
                doc.put_object(ROOT, CHILDREN_KEY, ObjType::Map)?;
            }
            _ => {
                let list_id = doc.put_object(ROOT, CONTENT_KEY, ObjType::List)?;
                doc.insert(&list_id, 0, text)?;
            }
        }
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
        if self.doc_type == DocumentType::Folder {
            return String::new();
        }
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
        if self.doc_type == DocumentType::Folder {
            return Ok(());
        }
        let list_id = self.doc.get(ROOT, CONTENT_KEY)?.unwrap().1;
        let len = self.doc.length(&list_id);
        for i in (0..len).rev() {
            self.doc.delete(&list_id, i)?;
        }
        self.doc.insert(&list_id, 0, text)?;
        Ok(())
    }

    pub fn insert_pointer(&mut self, index: usize, pointer: Pointer) -> Result<()> {
        if self.doc_type == DocumentType::Folder {
            return Ok(());
        }
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
        if self.doc_type == DocumentType::Folder {
            return Ok(());
        }
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
        let doc_type = if doc.get(ROOT, CHILDREN_KEY).ok().flatten().is_some() {
            DocumentType::Folder
        } else {
            DocumentType::Text
        };
        Ok(Self {
            id,
            doc,
            owner,
            name: id.to_string(),
            parent_folder_id: None,
            doc_type,
        })
    }

    pub fn add_child(&mut self, child_id: Uuid, name: &str, doc_type: DocumentType) -> Result<()> {
        if self.doc_type != DocumentType::Folder {
            return Ok(());
        }
        let map_id = self.doc.get(ROOT, CHILDREN_KEY)?.unwrap().1;
        let child = self
            .doc
            .put_object(&map_id, child_id.to_string(), ObjType::Map)?;
        self.doc.put(&child, "id", child_id.to_string())?;
        self.doc.put(&child, "name", name.to_string())?;
        self.doc.put(&child, "type", doc_type.as_str())?;
        Ok(())
    }

    pub fn child_count(&self) -> usize {
        if self.doc_type != DocumentType::Folder {
            return 0;
        }
        if let Ok(Some((_, map_id))) = self.doc.get(ROOT, CHILDREN_KEY) {
            self.doc.keys(&map_id).count()
        } else {
            0
        }
    }

    pub fn child_ids(&self) -> Vec<Uuid> {
        if self.doc_type != DocumentType::Folder {
            return Vec::new();
        }
        if let Ok(Some((_, map_id))) = self.doc.get(ROOT, CHILDREN_KEY) {
            self.doc
                .keys(&map_id)
                .filter_map(|k| Uuid::parse_str(&k).ok())
                .collect()
        } else {
            Vec::new()
        }
    }

    pub fn remove_child(&mut self, child_id: Uuid) -> Result<()> {
        if self.doc_type != DocumentType::Folder {
            return Ok(());
        }
        if let Ok(Some((_, map_id))) = self.doc.get(ROOT, CHILDREN_KEY) {
            let _ = self.doc.delete(&map_id, child_id.to_string());
        }
        Ok(())
    }
}

/// Simple filesystem-backed store for `Document` instances.
pub struct DocumentStore {
    docs: HashMap<Uuid, Document>,
    dir: PathBuf,
    roots: HashMap<String, Uuid>,
}

impl DocumentStore {
    pub fn new(dir: impl Into<PathBuf>) -> Result<Self> {
        let dir = dir.into();
        std::fs::create_dir_all(&dir)?;
        // load existing
        let mut docs = HashMap::new();
        let mut roots = HashMap::new();
        for entry in std::fs::read_dir(&dir)? {
            let entry = entry?;
            if entry.file_type()?.is_file() {
                if let Some(name) = entry.path().file_stem().and_then(|s| s.to_str()) {
                    if let Ok(id) = Uuid::parse_str(name) {
                        if let Ok(doc) = Document::load(id, &entry.path(), DEFAULT_USER.to_string())
                        {
                            if doc.doc_type() == DocumentType::Folder
                                && doc.parent_folder_id().is_none()
                            {
                                roots.insert(doc.owner().to_string(), id);
                            }
                            docs.insert(id, doc);
                        }
                    }
                }
            }
        }
        Ok(Self { docs, dir, roots })
    }

    fn path(&self, id: Uuid) -> PathBuf {
        self.dir.join(format!("{}.bin", id))
    }

    /// Ensure a root folder exists for the given user and return its ID.
    pub fn ensure_root(&mut self, user: &str) -> Result<Uuid> {
        if let Some(id) = self.roots.get(user) {
            return Ok(*id);
        }
        // search existing docs
        if let Some((id, _)) = self.docs.iter().find(|(_, d)| {
            d.owner() == user
                && d.doc_type() == DocumentType::Folder
                && d.parent_folder_id().is_none()
        }) {
            self.roots.insert(user.to_string(), *id);
            return Ok(*id);
        }
        let id = self.create(
            "root".to_string(),
            "",
            user.to_string(),
            None,
            DocumentType::Folder,
        )?;
        self.roots.insert(user.to_string(), id);
        Ok(id)
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
        let mut doc = Document::new(id, name, text, owner.clone(), parent_folder_id, doc_type)?;
        doc.save(&self.path(id))?;
        self.docs.insert(id, doc);
        if doc_type == DocumentType::Folder && parent_folder_id.is_none() {
            self.roots.insert(owner, id);
        }
        Ok(id)
    }

    pub fn create_folder(&mut self, parent: Uuid, name: String, owner: String) -> Result<Uuid> {
        let id = self.create(
            name.clone(),
            "",
            owner.clone(),
            Some(parent),
            DocumentType::Folder,
        )?;
        let path = self.path(parent);
        if let Some(parent_doc) = self.docs.get_mut(&parent) {
            parent_doc.add_child(id, &name, DocumentType::Folder)?;
            parent_doc.save(&path)?;
        }
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
        if let Some(doc) = self.docs.get(&id) {
            let doc_type = doc.doc_type();
            let parent = doc.parent_folder_id();
            let children = doc.child_ids();
            if doc_type == DocumentType::Folder {
                for child in children {
                    self.delete(child)?;
                }
            }
            if let Some(pid) = parent {
                let path = self.path(pid);
                if let Some(parent_doc) = self.docs.get_mut(&pid) {
                    parent_doc.remove_child(id)?;
                    parent_doc.save(&path)?;
                }
            }
        }
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
    fn create_folder_updates_parent() {
        let tempdir = tempfile::tempdir().unwrap();
        let mut store = DocumentStore::new(tempdir.path()).unwrap();
        let root_id = store
            .create(
                "root".to_string(),
                "",
                "user1".to_string(),
                None,
                DocumentType::Folder,
            )
            .unwrap();
        let child_id = store
            .create_folder(root_id, "child".to_string(), "user1".to_string())
            .unwrap();
        let root_doc = store.get(root_id).unwrap();
        assert_eq!(root_doc.doc_type(), DocumentType::Folder);
        assert_eq!(root_doc.child_count(), 1);
        let child_doc = store.get(child_id).unwrap();
        assert_eq!(child_doc.doc_type(), DocumentType::Folder);
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

    #[test]
    fn ensure_root_creates_per_user() {
        let tempdir = tempfile::tempdir().unwrap();
        let mut store = DocumentStore::new(tempdir.path()).unwrap();
        let root1 = store.ensure_root("user1").unwrap();
        let again = store.ensure_root("user1").unwrap();
        assert_eq!(root1, again);
        let doc1 = store.get(root1).unwrap();
        assert_eq!(doc1.owner(), "user1");
        assert!(doc1.parent_folder_id().is_none());

        let root2 = store.ensure_root("user2").unwrap();
        assert_ne!(root1, root2);
        let doc2 = store.get(root2).unwrap();
        assert_eq!(doc2.owner(), "user2");
    }

    #[test]
    fn delete_folder_recursively() {
        let tempdir = tempfile::tempdir().unwrap();
        let mut store = DocumentStore::new(tempdir.path()).unwrap();
        let root = store
            .create(
                "root".to_string(),
                "",
                "user1".to_string(),
                None,
                DocumentType::Folder,
            )
            .unwrap();
        let child = store
            .create_folder(root, "child".to_string(), "user1".to_string())
            .unwrap();
        let grand = store
            .create_folder(child, "grand".to_string(), "user1".to_string())
            .unwrap();

        assert_eq!(store.get(root).unwrap().child_count(), 1);
        assert_eq!(store.get(child).unwrap().child_count(), 1);

        store.delete(child).unwrap();

        assert!(store.get(child).is_none());
        assert!(store.get(grand).is_none());
        assert_eq!(store.get(root).unwrap().child_count(), 0);
    }

    #[test]
    fn delete_updates_parent() {
        let tempdir = tempfile::tempdir().unwrap();
        let mut store = DocumentStore::new(tempdir.path()).unwrap();
        let root = store
            .create(
                "root".to_string(),
                "",
                "user1".to_string(),
                None,
                DocumentType::Folder,
            )
            .unwrap();
        let doc_id = store
            .create(
                "file.txt".to_string(),
                "hello",
                "user1".to_string(),
                Some(root),
                DocumentType::Text,
            )
            .unwrap();
        {
            let path = store.path(root);
            let root_doc = store.docs.get_mut(&root).unwrap();
            root_doc
                .add_child(doc_id, "file.txt", DocumentType::Text)
                .unwrap();
            root_doc.save(&path).unwrap();
        }

        assert_eq!(store.get(root).unwrap().child_count(), 1);

        store.delete(doc_id).unwrap();

        assert!(store.get(doc_id).is_none());
        assert_eq!(store.get(root).unwrap().child_count(), 0);
    }
}
