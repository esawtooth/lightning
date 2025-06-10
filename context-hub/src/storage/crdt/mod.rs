//! CRDT-based document storage built on [Automerge](https://crates.io/crates/automerge).
//! Documents are stored individually on disk and loaded at startup.

use anyhow::Result;
use automerge::{
    transaction::Transactable, AutoCommit, ObjType, ReadDoc, ScalarValue, Value, ROOT,
};
use serde::{Deserialize, Serialize};
use serde_json;
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

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum AccessLevel {
    Read,
    Write,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct AclEntry {
    pub principal: String,
    pub access: AccessLevel,
}

impl DocumentType {
    fn as_str(&self) -> &'static str {
        match self {
            DocumentType::Folder => "Folder",
            DocumentType::IndexGuide => "IndexGuide",
            DocumentType::Text => "Text",
        }
    }

    fn from_str(s: &str) -> Self {
        match s {
            "Folder" => DocumentType::Folder,
            "IndexGuide" => DocumentType::IndexGuide,
            "Text" => DocumentType::Text,
            _ => DocumentType::Text,
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
    acl: Vec<AclEntry>,
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
        doc.put(ROOT, "doc_type", doc_type.as_str())?;
        Ok(Self {
            id,
            doc,
            owner,
            name,
            parent_folder_id,
            doc_type,
            acl: Vec::new(),
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

    pub fn acl(&self) -> &[AclEntry] {
        &self.acl
    }

    fn matches_principal(entry: &AclEntry, user: &str, agent: Option<&str>) -> bool {
        entry.principal == user || agent.map_or(false, |a| entry.principal == a)
    }

    pub fn can_read(&self, user: &str, agent: Option<&str>) -> bool {
        if self.owner == user {
            return true;
        }
        self.acl
            .iter()
            .any(|e| Self::matches_principal(e, user, agent))
    }

    pub fn can_write(&self, user: &str, agent: Option<&str>) -> bool {
        if self.owner == user {
            return true;
        }
        self.acl
            .iter()
            .any(|e| Self::matches_principal(e, user, agent) && e.access == AccessLevel::Write)
    }

    pub fn add_acl_entry(&mut self, entry: AclEntry) {
        self.acl.push(entry);
    }

    pub fn remove_acl_entry(&mut self, principal: &str) {
        self.acl.retain(|e| e.principal != principal);
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
        let doc_type = if let Ok(Some((val, _))) = doc.get(ROOT, "doc_type") {
            if let Value::Scalar(s) = val {
                if let ScalarValue::Str(s) = s.as_ref() {
                    DocumentType::from_str(s)
                } else if doc.get(ROOT, CHILDREN_KEY).ok().flatten().is_some() {
                    DocumentType::Folder
                } else {
                    DocumentType::Text
                }
            } else if doc.get(ROOT, CHILDREN_KEY).ok().flatten().is_some() {
                DocumentType::Folder
            } else {
                DocumentType::Text
            }
        } else if doc.get(ROOT, CHILDREN_KEY).ok().flatten().is_some() {
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
            acl: Vec::new(),
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

    /// Return information about children stored in this folder.
    pub fn children(&self) -> Vec<(Uuid, String, DocumentType)> {
        if self.doc_type != DocumentType::Folder {
            return Vec::new();
        }
        if let Ok(Some((_, map_id))) = self.doc.get(ROOT, CHILDREN_KEY) {
            self.doc
                .keys(&map_id)
                .filter_map(|k| {
                    let id = Uuid::parse_str(&k).ok()?;
                    let (_, obj_id) = self.doc.get(&map_id, &k).ok()??;
                    let name = match self.doc.get(&obj_id, "name").ok().flatten() {
                        Some((Value::Scalar(s), _)) => {
                            if let ScalarValue::Str(n) = s.as_ref() {
                                n.to_string()
                            } else {
                                return None;
                            }
                        }
                        _ => return None,
                    };
                    let doc_type = match self.doc.get(&obj_id, "type").ok().flatten() {
                        Some((Value::Scalar(s), _)) => {
                            if let ScalarValue::Str(t) = s.as_ref() {
                                DocumentType::from_str(t)
                            } else {
                                DocumentType::Text
                            }
                        }
                        _ => DocumentType::Text,
                    };
                    Some((id, name, doc_type))
                })
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
    agent_scopes: HashMap<String, HashMap<String, Vec<Uuid>>>,
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

        let scopes_path = dir.join("agent_scopes.json");
        let agent_scopes = if scopes_path.exists() {
            let data = std::fs::read_to_string(&scopes_path)?;
            serde_json::from_str(&data).unwrap_or_default()
        } else {
            HashMap::new()
        };

        Ok(Self {
            docs,
            dir,
            roots,
            agent_scopes,
        })
    }

    /// Directory where documents are persisted.
    pub fn data_dir(&self) -> &Path {
        &self.dir
    }

    fn path(&self, id: Uuid) -> PathBuf {
        self.dir.join(format!("{}.bin", id))
    }

    fn save_agent_scopes(&self) -> Result<()> {
        let path = self.dir.join("agent_scopes.json");
        let data = serde_json::to_string(&self.agent_scopes)?;
        std::fs::write(path, data)?;
        Ok(())
    }

    fn agent_allowed(&self, user: &str, agent: Option<&str>, doc_id: Uuid) -> bool {
        let Some(agent_id) = agent else { return true };
        let scopes = match self.agent_scopes.get(user).and_then(|m| m.get(agent_id)) {
            Some(s) => s,
            None => return true,
        };
        if scopes.is_empty() {
            return false;
        }
        let mut current = Some(doc_id);
        while let Some(id) = current {
            if scopes.contains(&id) {
                return true;
            }
            current = self.docs.get(&id).and_then(|d| d.parent_folder_id());
        }
        false
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
        self.create_index_for(id, "root", user)?;
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

    fn create_index_for(&mut self, folder: Uuid, folder_name: &str, owner: &str) -> Result<Uuid> {
        let index_name = "_index.guide".to_string();
        let content = format!("# {}", folder_name);
        let index_id = self.create(
            index_name.clone(),
            &content,
            owner.to_string(),
            Some(folder),
            DocumentType::IndexGuide,
        )?;
        let path = self.path(folder);
        if let Some(doc) = self.docs.get_mut(&folder) {
            doc.add_child(index_id, &index_name, DocumentType::IndexGuide)?;
            doc.save(&path)?;
        }
        Ok(index_id)
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
        let _ = self.create_index_for(id, &name, &owner)?;
        Ok(id)
    }

    pub fn get(&self, id: Uuid) -> Option<&Document> {
        self.docs.get(&id)
    }

    /// Check if the given user/agent has the requested access to the document.
    /// This walks up parent folders if needed to inherit permissions.
    pub fn has_permission(
        &self,
        doc_id: Uuid,
        user: &str,
        agent: Option<&str>,
        level: AccessLevel,
    ) -> bool {
        if !self.agent_allowed(user, agent, doc_id) {
            return false;
        }
        let mut current = self.docs.get(&doc_id);
        while let Some(doc) = current {
            if doc.owner() == user {
                return true;
            }
            for entry in doc.acl() {
                let principal_match =
                    entry.principal == user || agent.map_or(false, |a| entry.principal == a);
                if principal_match {
                    if level == AccessLevel::Read || entry.access == AccessLevel::Write {
                        return true;
                    }
                }
            }
            current = doc.parent_folder_id().and_then(|pid| self.docs.get(&pid));
        }
        false
    }

    /// Return the ID of the Index Guide document for the given folder, if one exists.
    pub fn index_guide_id(&self, folder: Uuid) -> Option<Uuid> {
        let doc = self.docs.get(&folder)?;
        if doc.doc_type() != DocumentType::Folder {
            return None;
        }
        for child_id in doc.child_ids() {
            if let Some(child) = self.docs.get(&child_id) {
                if child.doc_type() == DocumentType::IndexGuide {
                    return Some(child_id);
                }
            }
        }
        None
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

    /// Add an ACL entry to the given document or folder.
    pub fn add_acl(&mut self, id: Uuid, principal: String, access: AccessLevel) -> Result<()> {
        let path = self.path(id);
        if let Some(doc) = self.docs.get_mut(&id) {
            doc.add_acl_entry(AclEntry { principal, access });
            doc.save(&path)?;
        }
        Ok(())
    }

    /// Remove an ACL entry from the given document or folder.
    pub fn remove_acl(&mut self, id: Uuid, principal: &str) -> Result<()> {
        let path = self.path(id);
        if let Some(doc) = self.docs.get_mut(&id) {
            doc.remove_acl_entry(principal);
            doc.save(&path)?;
        }
        Ok(())
    }

    /// Restrict an agent acting for a user to the given folders.
    pub fn set_agent_scope(
        &mut self,
        user: String,
        agent: String,
        folders: Vec<Uuid>,
    ) -> Result<()> {
        self.agent_scopes
            .entry(user)
            .or_default()
            .insert(agent, folders);
        self.save_agent_scopes()
    }

    /// Remove any scope restrictions for an agent.
    pub fn clear_agent_scope(&mut self, user: &str, agent: &str) -> Result<()> {
        if let Some(map) = self.agent_scopes.get_mut(user) {
            map.remove(agent);
        }
        self.save_agent_scopes()
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
    fn acl_defaults_and_permissions() {
        let mut doc = Document::new(
            Uuid::new_v4(),
            "note.txt".to_string(),
            "hi",
            "owner".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();
        // ACL should start empty
        assert!(doc.acl().is_empty());
        // owner always has access
        assert!(doc.can_read("owner", None));
        assert!(doc.can_write("owner", None));
        // other user has no access
        assert!(!doc.can_read("other", None));
        assert!(!doc.can_write("other", None));

        doc.add_acl_entry(AclEntry {
            principal: "other".to_string(),
            access: AccessLevel::Read,
        });
        assert!(doc.can_read("other", None));
        assert!(!doc.can_write("other", None));

        doc.add_acl_entry(AclEntry {
            principal: "writer".to_string(),
            access: AccessLevel::Write,
        });
        assert!(doc.can_write("writer", None));
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
    fn folder_has_index_guide() {
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
        let folder = store
            .create_folder(root, "project".to_string(), "user1".to_string())
            .unwrap();
        let doc = store.get(folder).unwrap();
        assert_eq!(doc.child_count(), 1);
        let idx_id = doc.child_ids()[0];
        let idx = store.get(idx_id).unwrap();
        assert_eq!(idx.doc_type(), DocumentType::IndexGuide);
        assert_eq!(idx.name(), "_index.guide");
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
        assert_eq!(store.get(child).unwrap().child_count(), 2);

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

    #[test]
    fn acl_inheritance() {
        let tempdir = tempfile::tempdir().unwrap();
        let mut store = DocumentStore::new(tempdir.path()).unwrap();
        let folder = store
            .create(
                "root".to_string(),
                "",
                "owner".to_string(),
                None,
                DocumentType::Folder,
            )
            .unwrap();
        let child = store
            .create(
                "note.txt".to_string(),
                "hi",
                "owner".to_string(),
                Some(folder),
                DocumentType::Text,
            )
            .unwrap();
        {
            let root_doc = store.docs.get_mut(&folder).unwrap();
            root_doc.add_acl_entry(AclEntry {
                principal: "reader".to_string(),
                access: AccessLevel::Read,
            });
        }
        assert!(store.has_permission(child, "reader", None, AccessLevel::Read));
        assert!(!store.has_permission(child, "reader", None, AccessLevel::Write));
        assert!(!store.has_permission(child, "writer", None, AccessLevel::Read));
        {
            let root_doc = store.docs.get_mut(&folder).unwrap();
            root_doc.add_acl_entry(AclEntry {
                principal: "writer".to_string(),
                access: AccessLevel::Write,
            });
        }
        assert!(store.has_permission(child, "writer", None, AccessLevel::Write));
    }

    #[test]
    fn agent_scope_restriction() {
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
        let cal = store
            .create_folder(root, "calendar".to_string(), "user1".to_string())
            .unwrap();
        let note = store
            .create(
                "note.txt".to_string(),
                "hi",
                "user1".to_string(),
                Some(cal),
                DocumentType::Text,
            )
            .unwrap();
        store
            .set_agent_scope("user1".to_string(), "sched".to_string(), vec![cal])
            .unwrap();

        assert!(store.has_permission(cal, "user1", Some("sched"), AccessLevel::Read));
        assert!(store.has_permission(note, "user1", Some("sched"), AccessLevel::Read));

        let private = store
            .create_folder(root, "private".to_string(), "user1".to_string())
            .unwrap();
        let secret = store
            .create(
                "secret.txt".to_string(),
                "no",
                "user1".to_string(),
                Some(private),
                DocumentType::Text,
            )
            .unwrap();

        assert!(!store.has_permission(secret, "user1", Some("sched"), AccessLevel::Read));
        assert!(store.has_permission(secret, "user1", None, AccessLevel::Read));
    }
}
