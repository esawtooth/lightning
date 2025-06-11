//! CRDT-based document storage built on [Loro](https://crates.io/crates/loro).
//! Documents are stored individually on disk and loaded at startup.

use anyhow::{anyhow, Result};
use loro::{LoroDoc, LoroMap, ToJson};
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
/// In-memory wrapper around a Loro document.
pub struct Document {
    id: Uuid,
    doc: LoroDoc,
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
        let doc = LoroDoc::new();
        match doc_type {
            DocumentType::Folder => {
                doc.get_map(CHILDREN_KEY);
            }
            _ => {
                let list = doc.get_list(CONTENT_KEY);
                list.insert(0, text).map_err(|e| anyhow!(e))?;
            }
        }
        doc.get_map("meta")
            .insert("doc_type", doc_type.as_str())
            .map_err(|e| anyhow!(e))?;
        doc.commit();
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

    pub fn set_name(&mut self, name: String) {
        self.name = name;
    }

    pub fn parent_folder_id(&self) -> Option<Uuid> {
        self.parent_folder_id
    }

    pub fn set_parent_folder_id(&mut self, parent: Option<Uuid>) {
        self.parent_folder_id = parent;
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
        let list = self.doc.get_list(CONTENT_KEY);
        let mut out = String::new();
        for i in 0..list.len() {
            if let Some(item) = list.get(i) {
                match item {
                    loro::ValueOrContainer::Value(v) => {
                        match v.to_json_value() {
                            serde_json::Value::String(s) => out.push_str(&s),
                            _ => out.push_str("[pointer]"),
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
        let list = self.doc.get_list(CONTENT_KEY);
        while list.len() > 0 {
            list.delete(0, 1).map_err(|e| anyhow!(e))?;
        }
        list.insert(0, text).map_err(|e| anyhow!(e))?;
        self.doc.commit();
        Ok(())
    }

    pub fn insert_pointer(&mut self, index: usize, _pointer: Pointer) -> Result<()> {
        if self.doc_type == DocumentType::Folder {
            return Ok(());
        }
        self
            .doc
            .get_list(CONTENT_KEY)
            .insert(index, loro::loro_value!({}))
            .map_err(|e| anyhow!(e))?;
        self.doc.commit();
        Ok(())
    }

    pub fn remove_at(&mut self, index: usize) -> Result<()> {
        if self.doc_type == DocumentType::Folder {
            return Ok(());
        }
        self
            .doc
            .get_list(CONTENT_KEY)
            .delete(index, 1)
            .map_err(|e| anyhow!(e))?;
        self.doc.commit();
        Ok(())
    }

    /// Reload the Automerge document from disk, replacing any in-memory
    /// change history with the serialized state on disk.
    pub fn reload(&mut self, path: &Path) -> Result<()> {
        let bytes = std::fs::read(path)?;
        self.doc = LoroDoc::new();
        self.doc.import(&bytes).map_err(|e| anyhow!(e))?;
        self.doc.commit();
        Ok(())
    }

    pub fn save(&mut self, path: &Path) -> Result<()> {
        std::fs::write(path, self.doc.export(loro::ExportMode::Snapshot).map_err(|e| anyhow!(e))?)?;
        Ok(())
    }

    pub fn load(id: Uuid, path: &Path, owner: String) -> Result<Self> {
        let bytes = std::fs::read(path)?;
        let doc = LoroDoc::new();
        doc.import(&bytes).map_err(|e| anyhow!(e))?;
        doc.commit();
        let doc_type = if doc.get_map(CHILDREN_KEY).is_attached() {
            DocumentType::Folder
        } else if let Some(t) = doc
            .get_by_str_path("meta/doc_type")
            .and_then(|v| v.into_value().ok())
            .and_then(|v| v.into_string().ok())
        {
            DocumentType::from_str(&t)
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
        let map = self.doc.get_map(CHILDREN_KEY);
        let child = map
            .insert_container(&child_id.to_string(), LoroMap::new())
            .map_err(|e| anyhow!(e))?;
        child.insert("id", child_id.to_string()).map_err(|e| anyhow!(e))?;
        child.insert("name", name).map_err(|e| anyhow!(e))?;
        child.insert("type", doc_type.as_str()).map_err(|e| anyhow!(e))?;
        self.doc.commit();
        Ok(())
    }

    pub fn child_count(&self) -> usize {
        if self.doc_type != DocumentType::Folder {
            return 0;
        }
        let map = self.doc.get_map(CHILDREN_KEY);
        if map.is_attached() {
            map.len()
        } else {
            0
        }
    }

    pub fn child_ids(&self) -> Vec<Uuid> {
        if self.doc_type != DocumentType::Folder {
            return Vec::new();
        }
        let map = self.doc.get_map(CHILDREN_KEY);
        if !map.is_attached() {
            return Vec::new();
        }
        let mut ids = Vec::new();
        map.for_each(|k, _| {
            if let Ok(id) = Uuid::parse_str(k) {
                ids.push(id);
            }
        });
        ids
    }

    /// Return information about children stored in this folder.
    pub fn children(&self) -> Vec<(Uuid, String, DocumentType)> {
        if self.doc_type != DocumentType::Folder {
            return Vec::new();
        }
        let map = self.doc.get_map(CHILDREN_KEY);
        if !map.is_attached() {
            return Vec::new();
        }
        let mut out = Vec::new();
        map.for_each(|k, _| {
            if let Ok(id) = Uuid::parse_str(k) {
                let name_path = format!("{}/{}/name", CHILDREN_KEY, k);
                let type_path = format!("{}/{}/type", CHILDREN_KEY, k);
                let name = self
                    .doc
                    .get_by_str_path(&name_path)
                    .and_then(|v| v.into_value().ok())
                    .and_then(|v| v.into_string().ok())
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| k.to_string());
                let typ = self
                    .doc
                    .get_by_str_path(&type_path)
                    .and_then(|v| v.into_value().ok())
                    .and_then(|v| v.into_string().ok())
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| "Text".to_string());
                out.push((id, name, DocumentType::from_str(&typ)));
            }
        });
        out
    }

    pub fn remove_child(&mut self, child_id: Uuid) -> Result<()> {
        if self.doc_type != DocumentType::Folder {
            return Ok(());
        }
        let map = self.doc.get_map(CHILDREN_KEY);
        if map.is_attached() {
            let _ = map.delete(&child_id.to_string());
        }
        self.doc.commit();
        Ok(())
    }

    pub fn rename_child(&mut self, child_id: Uuid, name: &str) -> Result<()> {
        if self.doc_type != DocumentType::Folder {
            return Ok(());
        }
        let map = self.doc.get_map(CHILDREN_KEY);
        if map.is_attached() {
            let key = child_id.to_string();
            if let Some(child) = map.get(&key) {
                if let Some(child_map) =
                    child.into_container().ok().and_then(|c| c.into_map().ok())
                {
                    child_map.insert("name", name).map_err(|e| anyhow!(e))?;
                }
            }
        }
        self.doc.commit();
        Ok(())
    }
}

/// Simple filesystem-backed store for `Document` instances.

pub struct DocumentStore {
    docs: HashMap<Uuid, Document>,
    dir: PathBuf,
    roots: HashMap<String, Uuid>,
    agent_scopes: HashMap<String, HashMap<String, Vec<Uuid>>>,
    dirty: bool,
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
            dirty: false,
        })
    }

    /// Directory where documents are persisted.
    pub fn data_dir(&self) -> &Path {
        &self.dir
    }

    /// Iterate over all documents in the store.
    pub fn iter(&self) -> std::collections::hash_map::Iter<'_, Uuid, Document> {
        self.docs.iter()
    }

    /// Reload the store contents from disk, discarding any in-memory state.
    pub fn reload(&mut self) -> Result<()> {
        let new_self = Self::new(&self.dir)?;
        *self = new_self;
        Ok(())
    }

    /// Return whether the store has un-snapshotted changes.
    pub fn is_dirty(&self) -> bool {
        self.dirty
    }

    /// Mark the store as having pending changes.
    fn mark_dirty(&mut self) {
        self.dirty = true;
    }

    /// Clear the dirty flag after a snapshot has been taken.
    pub fn clear_dirty(&mut self) {
        self.dirty = false;
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
        self.mark_dirty();
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
        self.mark_dirty();
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
        self.mark_dirty();
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

    pub fn rename(&mut self, id: Uuid, name: String) -> Result<()> {
        let doc_path = self.path(id);
        if let Some(doc) = self.docs.get_mut(&id) {
            doc.set_name(name.clone());
            doc.save(&doc_path)?;
            if let Some(pid) = doc.parent_folder_id() {
                let parent_path = self.path(pid);
                if let Some(parent_doc) = self.docs.get_mut(&pid) {
                    parent_doc.rename_child(id, &name)?;
                    parent_doc.save(&parent_path)?;
                }
            }
        }
        self.mark_dirty();
        Ok(())
    }

    pub fn move_item(&mut self, id: Uuid, new_parent: Uuid) -> Result<()> {
        if self.docs.get(&new_parent).map(|d| d.doc_type()) != Some(DocumentType::Folder) {
            return Ok(());
        }
        let old_parent = match self.docs.get(&id) {
            Some(d) => d.parent_folder_id(),
            None => return Ok(()),
        };
        let doc_path = self.path(id);
        let dest_path = self.path(new_parent);
        let (name, doc_type) = {
            let doc = self.docs.get_mut(&id).unwrap();
            if doc.parent_folder_id().is_none() {
                return Ok(());
            }
            doc.set_parent_folder_id(Some(new_parent));
            doc.save(&doc_path)?;
            (doc.name().to_string(), doc.doc_type())
        };
        if let Some(pid) = old_parent {
            let parent_path = self.path(pid);
            if let Some(parent_doc) = self.docs.get_mut(&pid) {
                parent_doc.remove_child(id)?;
                parent_doc.save(&parent_path)?;
            }
        }
        if let Some(dest) = self.docs.get_mut(&new_parent) {
            dest.add_child(id, &name, doc_type)?;
            dest.save(&dest_path)?;
        }
        self.mark_dirty();
        Ok(())
    }

    pub fn descendant_ids(&self, id: Uuid) -> Vec<Uuid> {
        fn gather(store: &DocumentStore, id: Uuid, out: &mut Vec<Uuid>) {
            out.push(id);
            if let Some(doc) = store.get(id) {
                if doc.doc_type() == DocumentType::Folder {
                    for child in doc.child_ids() {
                        gather(store, child, out);
                    }
                }
            }
        }
        let mut ids = Vec::new();
        gather(self, id, &mut ids);
        ids
    }

    pub fn update(&mut self, id: Uuid, text: &str) -> Result<()> {
        let path = self.path(id);
        if let Some(doc) = self.docs.get_mut(&id) {
            doc.set_text(text)?;
            doc.save(&path)?;
        }
        self.mark_dirty();
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
        self.mark_dirty();
        Ok(())
    }

    /// Add an ACL entry to the given document or folder.
    pub fn add_acl(&mut self, id: Uuid, principal: String, access: AccessLevel) -> Result<()> {
        let path = self.path(id);
        if let Some(doc) = self.docs.get_mut(&id) {
            doc.add_acl_entry(AclEntry { principal, access });
            doc.save(&path)?;
        }
        self.mark_dirty();
        Ok(())
    }

    /// Remove an ACL entry from the given document or folder.
    pub fn remove_acl(&mut self, id: Uuid, principal: &str) -> Result<()> {
        let path = self.path(id);
        if let Some(doc) = self.docs.get_mut(&id) {
            doc.remove_acl_entry(principal);
            doc.save(&path)?;
        }
        self.mark_dirty();
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
        self.mark_dirty();
        self.save_agent_scopes()
    }

    /// Remove any scope restrictions for an agent.
    pub fn clear_agent_scope(&mut self, user: &str, agent: &str) -> Result<()> {
        if let Some(map) = self.agent_scopes.get_mut(user) {
            map.remove(agent);
        }
        self.mark_dirty();
        self.save_agent_scopes()
    }

    /// Reload all documents from their serialized form to discard old CRDT
    /// history. This should be invoked after a snapshot to keep in-memory
    /// state small.
    pub fn compact_history(&mut self) -> Result<()> {
        let dir = self.dir.clone();
        for (id, doc) in self.docs.iter_mut() {
            let path = dir.join(format!("{}.bin", id));
            doc.reload(&path)?;
        }
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
    fn rename_updates_parent() {
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
            let parent = store.docs.get_mut(&root).unwrap();
            parent.add_child(doc_id, "file.txt", DocumentType::Text).unwrap();
            parent.save(&path).unwrap();
        }

        store.rename(doc_id, "renamed.txt".to_string()).unwrap();

        let doc = store.get(doc_id).unwrap();
        assert_eq!(doc.name(), "renamed.txt");
        let parent = store.get(root).unwrap();
        let child_names: Vec<_> = parent.children().into_iter().map(|c| c.1).collect();
        assert!(child_names.contains(&"renamed.txt".to_string()));
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
