use axum::{
    extract::{ws::{Message, WebSocket, WebSocketUpgrade}, State},
    response::Response,
};
use context_hub_core::timeline::TimelineState;
use futures::{sink::SinkExt, stream::StreamExt};
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use tokio::sync::broadcast;
use uuid::Uuid;
use std::sync::Arc;
use tokio::sync::RwLock;
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ClientMessage {
    #[serde(rename = "scrub_position")]
    ScrubPosition {
        timestamp: DateTime<Utc>,
    },
    #[serde(rename = "subscribe")]
    Subscribe {
        start_time: DateTime<Utc>,
        end_time: DateTime<Utc>,
    },
    #[serde(rename = "unsubscribe")]
    Unsubscribe,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type")]
pub enum ServerMessage {
    #[serde(rename = "state_update")]
    StateUpdate {
        timestamp: DateTime<Utc>,
        changes_since_last: Vec<DocumentChange>,
        stats: StateStats,
    },
    #[serde(rename = "preload_hint")]
    PreloadHint {
        timestamps: Vec<DateTime<Utc>>,
    },
    #[serde(rename = "error")]
    Error {
        message: String,
    },
}

#[derive(Debug, Clone, Serialize)]
pub struct DocumentChange {
    pub document_id: Uuid,
    pub change: String,
    pub name: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct StateStats {
    pub total_documents: usize,
    pub folders: usize,
}

#[derive(Clone)]
pub struct TimelineWebSocketState {
    pub timeline_state: TimelineState,
    pub connections: Arc<RwLock<HashMap<Uuid, broadcast::Sender<ServerMessage>>>>,
}

pub async fn websocket_handler(
    ws: WebSocketUpgrade,
    State(state): State<TimelineWebSocketState>,
) -> Response {
    ws.on_upgrade(move |socket| handle_socket(socket, state))
}

async fn handle_socket(socket: WebSocket, state: TimelineWebSocketState) {
    let (mut sender, mut receiver) = socket.split();
    let (tx, mut rx) = broadcast::channel(100);
    let connection_id = Uuid::new_v4();
    
    // Register connection
    {
        let mut connections = state.connections.write().await;
        connections.insert(connection_id, tx.clone());
    }
    
    // Handle outgoing messages
    let mut send_task = tokio::spawn(async move {
        while let Ok(msg) = rx.recv().await {
            let json = serde_json::to_string(&msg).unwrap();
            if sender.send(Message::Text(json.into())).await.is_err() {
                break;
            }
        }
    });
    
    // Handle incoming messages
    let timeline_state = state.timeline_state.clone();
    let tx_clone = tx.clone();
    let mut last_position: Option<DateTime<Utc>> = None;
    
    while let Some(msg) = receiver.next().await {
        if let Ok(msg) = msg {
            match msg {
                Message::Text(text) => {
                    if let Ok(client_msg) = serde_json::from_str::<ClientMessage>(&text) {
                        match client_msg {
                            ClientMessage::ScrubPosition { timestamp } => {
                                // Get state at timestamp
                                match timeline_state.reconstructor.get_state_at(timestamp).await {
                                    Ok(state) => {
                                        // Calculate changes since last position
                                        let changes = if let Some(last) = last_position {
                                            calculate_changes(&timeline_state, last, timestamp).await
                                        } else {
                                            vec![]
                                        };
                                        
                                        last_position = Some(timestamp);
                                        
                                        let msg = ServerMessage::StateUpdate {
                                            timestamp,
                                            changes_since_last: changes,
                                            stats: StateStats {
                                                total_documents: state.document_count,
                                                folders: 0, // Would calculate from folder_structure
                                            },
                                        };
                                        
                                        let _ = tx_clone.send(msg);
                                        
                                        // Send preload hints for nearby timestamps
                                        let preload_hints = generate_preload_hints(timestamp);
                                        let _ = tx_clone.send(ServerMessage::PreloadHint {
                                            timestamps: preload_hints,
                                        });
                                    }
                                    Err(e) => {
                                        let _ = tx_clone.send(ServerMessage::Error {
                                            message: format!("Failed to get state: {}", e),
                                        });
                                    }
                                }
                            }
                            ClientMessage::Subscribe { start_time, end_time } => {
                                // Subscribe to changes in time range
                                // This could be used to filter which updates are sent
                            }
                            ClientMessage::Unsubscribe => {
                                break;
                            }
                        }
                    }
                }
                Message::Close(_) => break,
                _ => {}
            }
        }
    }
    
    // Cleanup
    send_task.abort();
    {
        let mut connections = state.connections.write().await;
        connections.remove(&connection_id);
    }
}

async fn calculate_changes(
    timeline_state: &TimelineState,
    from: DateTime<Utc>,
    to: DateTime<Utc>,
) -> Vec<DocumentChange> {
    // This would calculate actual changes between timestamps
    // For now, return empty list
    vec![]
}

fn generate_preload_hints(current: DateTime<Utc>) -> Vec<DateTime<Utc>> {
    // Generate timestamps to preload for smooth scrubbing
    vec![
        current + chrono::Duration::minutes(15),
        current + chrono::Duration::minutes(30),
        current - chrono::Duration::minutes(15),
        current - chrono::Duration::minutes(30),
    ]
}