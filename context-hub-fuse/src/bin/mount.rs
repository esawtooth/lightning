use context_hub_fuse::HubFs;
use context_hub_core::storage::crdt::DocumentStore;
use std::env;

fn main() {
    let mountpoint = env::args().nth(1).expect("mountpoint required");
    let user = env::var("CONTEXT_USER").unwrap_or_else(|_| "user1".to_string());
    let data_dir = env::var("DATA_DIR").unwrap_or_else(|_| "data".to_string());
    let store = DocumentStore::new(data_dir).expect("load store");
    let fs = HubFs::new(store, user);
    fuser::mount2(fs, mountpoint, &[]).expect("mount failed");
}
