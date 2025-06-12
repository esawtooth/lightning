use serde::Serialize;
use tokio::sync::broadcast;
use uuid::Uuid;

#[derive(Clone, Serialize)]
#[serde(tag = "type")]
pub enum Event {
    Created { id: Uuid },
    Updated { id: Uuid },
    Deleted { id: Uuid },
    Moved { id: Uuid, new_parent: Uuid },
    Shared { id: Uuid, principal: String },
    Unshared { id: Uuid, principal: String },
}

#[derive(Clone)]
pub struct EventBus {
    tx: broadcast::Sender<Event>,
}

impl EventBus {
    pub fn new() -> Self {
        let (tx, _) = broadcast::channel(100);
        Self { tx }
    }

    pub fn subscribe(&self) -> broadcast::Receiver<Event> {
        self.tx.subscribe()
    }

    pub fn send(&self, event: Event) {
        let _ = self.tx.send(event);
    }
}
