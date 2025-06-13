use context_hub_core::storage::crdt::{DocumentStore, DocumentType};
use fuser::{Filesystem, Request, ReplyAttr, ReplyEntry, ReplyDirectory, ReplyData, FileAttr, FileType};
use libc::ENOENT;
use std::collections::HashMap;
use std::ffi::OsStr;
use std::time::{Duration, SystemTime};
use uuid::Uuid;

const TTL: Duration = Duration::from_secs(1);

pub struct HubFs {
    root_ino: u64,
    store: DocumentStore,
    inodes: HashMap<u64, Uuid>,
}

impl HubFs {
    pub fn new(mut store: DocumentStore, user: String) -> Self {
        let root_id = store.ensure_root(&user).expect("root");
        let mut inodes = HashMap::new();
        for (id, _) in store.iter() {
            let ino = Self::inode_for_uuid(*id);
            inodes.insert(ino, *id);
        }
        let root_ino = Self::inode_for_uuid(root_id);
        Self { store, inodes, root_ino }
    }

    fn inode_for_uuid(id: Uuid) -> u64 {
        let bytes = id.as_bytes();
        u64::from_le_bytes(bytes[0..8].try_into().unwrap())
    }

    fn attr_for(&self, doc: &context_hub_core::storage::crdt::Document, ino: u64) -> FileAttr {
        let kind = match doc.doc_type() {
            DocumentType::Folder => FileType::Directory,
            _ => FileType::RegularFile,
        };
        let size = if doc.doc_type() == DocumentType::Folder {
            0
        } else {
            doc.text().len() as u64
        };
        FileAttr {
            ino,
            size,
            blocks: 1,
            atime: SystemTime::UNIX_EPOCH,
            mtime: SystemTime::UNIX_EPOCH,
            ctime: SystemTime::UNIX_EPOCH,
            crtime: SystemTime::UNIX_EPOCH,
            kind,
            perm: if kind == FileType::Directory { 0o755 } else { 0o644 },
            nlink: 1,
            uid: 0,
            gid: 0,
            rdev: 0,
            blksize: 512,
            flags: 0,
        }
    }

    fn uuid_for_inode(&self, ino: u64) -> Option<Uuid> {
        self.inodes.get(&ino).cloned()
    }
}

impl Filesystem for HubFs {
    fn lookup(&mut self, _req: &Request<'_>, parent: u64, name: &OsStr, reply: ReplyEntry) {
        let Some(pid) = self.uuid_for_inode(parent) else { reply.error(ENOENT); return; };
        let Some(parent_doc) = self.store.get(pid) else { reply.error(ENOENT); return; };
        if parent_doc.doc_type() != DocumentType::Folder { reply.error(ENOENT); return; }
        let name_str = name.to_str().unwrap_or("");
        for (child_id, child_name, _) in parent_doc.children() {
            if child_name == name_str {
                if let Some(child) = self.store.get(child_id) {
                    let ino = Self::inode_for_uuid(child_id);
                    self.inodes.insert(ino, child_id);
                    let attr = self.attr_for(child, ino);
                    reply.entry(&TTL, &attr, 0);
                    return;
                }
            }
        }
        reply.error(ENOENT);
    }

    fn getattr(&mut self, _req: &Request<'_>, ino: u64, reply: ReplyAttr) {
        if ino == 1 { // FUSE root inode
            if let Some(root) = self.store.get(self.uuid_for_inode(self.root_ino).unwrap()) {
                let attr = self.attr_for(root, self.root_ino);
                reply.attr(&TTL, &attr);
                return;
            }
        }
        match self.uuid_for_inode(ino).and_then(|id| self.store.get(id)) {
            Some(doc) => {
                let attr = self.attr_for(doc, ino);
                reply.attr(&TTL, &attr);
            }
            None => reply.error(ENOENT),
        }
    }

    fn readdir(&mut self, _req: &Request<'_>, ino: u64, _fh: u64, offset: i64, mut reply: ReplyDirectory) {
        let Some(id) = self.uuid_for_inode(if ino == 1 { self.root_ino } else { ino }) else { reply.error(ENOENT); return; };
        let Some(doc) = self.store.get(id) else { reply.error(ENOENT); return; };
        if doc.doc_type() != DocumentType::Folder { reply.error(ENOENT); return; }
        let mut entries = Vec::new();
        entries.push((1, FileType::Directory, String::from(".")));
        entries.push((1, FileType::Directory, String::from("..")));
        for (child_id, name, _typ) in doc.children() {
            let ino = Self::inode_for_uuid(child_id);
            self.inodes.insert(ino, child_id);
            let kind = match _typ { DocumentType::Folder => FileType::Directory, _ => FileType::RegularFile };
            entries.push((ino, kind, name));
        }
        for (i, (ino, kind, name)) in entries.into_iter().enumerate().skip(offset as usize) {
            if reply.add(ino, (i + 1) as i64, kind, name) {
                break;
            }
        }
        reply.ok();
    }

    fn open(&mut self, _req: &Request<'_>, ino: u64, _flags: i32, reply: fuser::ReplyOpen) {
        if self.uuid_for_inode(ino).is_some() {
            reply.opened(0, 0);
        } else {
            reply.error(ENOENT);
        }
    }

    fn read(&mut self, _req: &Request<'_>, ino: u64, _fh: u64, offset: i64, size: u32, _flags: i32, _lock_owner: Option<u64>, reply: ReplyData) {
        let Some(id) = self.uuid_for_inode(ino) else { reply.error(ENOENT); return; };
        let Some(doc) = self.store.get(id) else { reply.error(ENOENT); return; };
        let data = doc.text();
        let start = offset as usize;
        let end = std::cmp::min(start + size as usize, data.len());
        if start >= data.len() {
            reply.data(&[]);
        } else {
            reply.data(&data.as_bytes()[start..end]);
        }
    }
}
