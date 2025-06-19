"""
Conversation Manager for Vextir OS
Ensures proper ordering and consistency of conversation events
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import logging

from lightning_core.abstractions import EventMessage
from lightning_core.events.models import Event

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """Represents a single turn in a conversation"""
    turn_number: int
    user_message: Dict[str, str]
    assistant_message: Optional[Dict[str, str]] = None
    user_event_id: Optional[str] = None
    assistant_event_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    processing_time: Optional[float] = None


@dataclass
class ConversationSession:
    """Manages a conversation session with ordering guarantees"""
    session_id: str
    user_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    turns: List[ConversationTurn] = field(default_factory=list)
    current_turn: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    async def add_user_message(self, content: str, event_id: str) -> Tuple[int, List[Dict[str, str]]]:
        """
        Add a user message and get the full conversation history.
        Returns (turn_number, messages_list)
        """
        async with self._lock:
            self.current_turn += 1
            turn = ConversationTurn(
                turn_number=self.current_turn,
                user_message={"role": "user", "content": content},
                user_event_id=event_id
            )
            self.turns.append(turn)
            
            # Build conversation history up to this turn
            messages = []
            for t in self.turns[:self.current_turn]:
                messages.append(t.user_message)
                if t.assistant_message:
                    messages.append(t.assistant_message)
            
            return self.current_turn, messages
    
    async def add_assistant_response(
        self, 
        turn_number: int, 
        content: str, 
        event_id: str
    ) -> bool:
        """
        Add assistant response for a specific turn.
        Returns True if successful, False if turn doesn't exist or already has response.
        """
        async with self._lock:
            # Find the turn
            for turn in self.turns:
                if turn.turn_number == turn_number:
                    if turn.assistant_message is not None:
                        logger.warning(
                            f"Turn {turn_number} already has assistant response. "
                            f"Ignoring duplicate response."
                        )
                        return False
                    
                    turn.assistant_message = {"role": "assistant", "content": content}
                    turn.assistant_event_id = event_id
                    turn.processing_time = (datetime.utcnow() - turn.timestamp).total_seconds()
                    return True
            
            logger.error(f"Turn {turn_number} not found in session {self.session_id}")
            return False
    
    def get_conversation_history(self, up_to_turn: Optional[int] = None) -> List[Dict[str, str]]:
        """Get conversation history up to a specific turn (or all if None)"""
        messages = []
        max_turn = up_to_turn or self.current_turn
        
        for turn in self.turns:
            if turn.turn_number > max_turn:
                break
            messages.append(turn.user_message)
            if turn.assistant_message:
                messages.append(turn.assistant_message)
        
        return messages


class ConversationManager:
    """Manages multiple conversation sessions with ordering guarantees"""
    
    def __init__(self):
        self.sessions: Dict[str, ConversationSession] = {}
        self._session_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._cleanup_task: Optional[asyncio.Task] = None
        self.max_session_age_hours = 24
        self.max_turns_per_session = 100
    
    async def start(self):
        """Start the conversation manager"""
        self._cleanup_task = asyncio.create_task(self._cleanup_old_sessions())
        logger.info("ConversationManager started")
    
    async def stop(self):
        """Stop the conversation manager"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("ConversationManager stopped")
    
    async def get_or_create_session(self, session_id: str, user_id: str) -> ConversationSession:
        """Get existing session or create a new one"""
        async with self._session_locks[session_id]:
            if session_id not in self.sessions:
                self.sessions[session_id] = ConversationSession(
                    session_id=session_id,
                    user_id=user_id
                )
                logger.info(f"Created new conversation session: {session_id}")
            return self.sessions[session_id]
    
    async def process_user_event(
        self, 
        event: EventMessage
    ) -> Tuple[int, List[Dict[str, str]]]:
        """
        Process a user chat event and return (turn_number, conversation_history).
        The turn_number should be included in the response event for ordering.
        """
        session_id = event.metadata.get("session_id", f"default_{event.metadata.get('user_id', 'unknown')}")
        user_id = event.metadata.get("user_id", "unknown")
        
        session = await self.get_or_create_session(session_id, user_id)
        
        # Extract user message
        messages = event.data.get("messages", [])
        if not messages:
            raise ValueError("No messages in event data")
        
        # Get the last user message (latest)
        user_message = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        
        if not user_message:
            raise ValueError("No user message found in messages")
        
        # Add to session and get turn number
        turn_number, conversation_history = await session.add_user_message(
            user_message, 
            event.id
        )
        
        logger.info(
            f"Processed user message for session {session_id}, "
            f"turn {turn_number}, history length: {len(conversation_history)}"
        )
        
        return turn_number, conversation_history
    
    async def process_assistant_event(
        self,
        event: EventMessage,
        turn_number: int
    ) -> bool:
        """Process an assistant response event for a specific turn"""
        session_id = event.metadata.get("session_id")
        if not session_id:
            # Try to extract from chat_request_id metadata
            chat_request_id = event.metadata.get("chat_request_id")
            # This is a limitation - we'd need to track request_id -> session_id mapping
            logger.warning("No session_id in assistant response event")
            return False
        
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return False
        
        response_text = event.data.get("response", "")
        success = await session.add_assistant_response(
            turn_number,
            response_text,
            event.id
        )
        
        if success:
            logger.info(
                f"Added assistant response for session {session_id}, turn {turn_number}"
            )
        
        return success
    
    async def _cleanup_old_sessions(self):
        """Periodically clean up old sessions"""
        while True:
            try:
                await asyncio.sleep(3600)  # Check every hour
                
                now = datetime.utcnow()
                sessions_to_remove = []
                
                for session_id, session in self.sessions.items():
                    age_hours = (now - session.created_at).total_seconds() / 3600
                    if age_hours > self.max_session_age_hours:
                        sessions_to_remove.append(session_id)
                    elif len(session.turns) > self.max_turns_per_session:
                        # Trim old turns but keep session
                        session.turns = session.turns[-self.max_turns_per_session:]
                
                for session_id in sessions_to_remove:
                    del self.sessions[session_id]
                    logger.info(f"Cleaned up old session: {session_id}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")


# Global conversation manager instance
_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """Get the global conversation manager instance"""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager