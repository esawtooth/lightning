"""
Simple Channel System for VextirOS

Channels are structured event topic patterns that provide standard
communication interfaces for agents within the existing event bus.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from .event_bus import EventBus, EventFilter, get_event_bus
from .events import Event


class ChannelType(Enum):
    """Standard channel types for all agents"""
    STATUS = "status"         # Agent state reporting (idle/busy/error/stopped)
    COMMAND = "command"       # OS commands to agent (stop/pause/configure)
    HEALTH = "health"         # Heartbeat and resource usage
    ACTIVITY = "activity"     # Tool execution and progress updates
    ERROR = "error"           # Error reporting and exception handling


@dataclass
class ChannelMessage:
    """Standard message format for channels"""
    channel_type: ChannelType
    agent_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[datetime] = None
    message_id: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def to_event(self) -> Event:
        """Convert channel message to VextirOS event"""
        return Event(
            type=f"agent.{self.agent_id}.{self.channel_type.value}",
            data=self.data,
            id=self.message_id,
            timestamp=self.timestamp,
            source=f"agent.{self.agent_id}",
            metadata={
                "channel_type": self.channel_type.value,
                "agent_id": self.agent_id
            }
        )
    
    @classmethod
    def from_event(cls, event: Event) -> Optional["ChannelMessage"]:
        """Create channel message from VextirOS event"""
        # Parse agent.{agent_id}.{channel_type} format
        parts = event.type.split(".")
        if len(parts) != 3 or parts[0] != "agent":
            return None
        
        try:
            agent_id = parts[1]
            channel_type = ChannelType(parts[2])
            
            return cls(
                channel_type=channel_type,
                agent_id=agent_id,
                data=event.data,
                timestamp=event.timestamp,
                message_id=event.id
            )
        except ValueError:
            return None


class Channel(ABC):
    """Base class for agent channels"""
    
    def __init__(self, agent_id: str, channel_type: ChannelType, event_bus: Optional[EventBus] = None):
        self.agent_id = agent_id
        self.channel_type = channel_type
        self.event_bus = event_bus or get_event_bus()
        self._subscribers: List[Callable[[ChannelMessage], None]] = []
        self._subscription_id: Optional[str] = None
        
    def get_topic_pattern(self) -> str:
        """Get the event topic pattern for this channel"""
        return f"agent.{self.agent_id}.{self.channel_type.value}"
    
    async def publish(self, data: Dict[str, Any]) -> str:
        """Publish a message to this channel"""
        message = ChannelMessage(
            channel_type=self.channel_type,
            agent_id=self.agent_id,
            data=data
        )
        event = message.to_event()
        return await self.event_bus.emit(event)
    
    def subscribe(self, callback: Callable[[ChannelMessage], None]) -> str:
        """Subscribe to messages on this channel"""
        self._subscribers.append(callback)
        
        # Create event filter for this channel
        event_filter = EventFilter(
            event_types=[self.get_topic_pattern()]
        )
        
        def event_callback(event: Event):
            message = ChannelMessage.from_event(event)
            if message:
                for subscriber in self._subscribers:
                    try:
                        subscriber(message)
                    except Exception as e:
                        logging.error(f"Error in channel subscriber: {e}")
        
        subscription_id = self.event_bus.subscribe(event_filter, event_callback)
        if self._subscription_id is None:
            self._subscription_id = subscription_id
        
        return subscription_id
    
    def unsubscribe(self, subscription_id: str):
        """Unsubscribe from channel messages"""
        self.event_bus.unsubscribe(subscription_id)


class StatusChannel(Channel):
    """Channel for agent status reporting"""
    
    def __init__(self, agent_id: str, event_bus: Optional[EventBus] = None):
        super().__init__(agent_id, ChannelType.STATUS, event_bus)
    
    async def report_status(self, status: str, activity: str = "", details: Optional[Dict[str, Any]] = None):
        """Report agent status"""
        data = {
            "status": status,
            "activity": activity,
            "timestamp": datetime.utcnow().isoformat()
        }
        if details:
            data.update(details)
        
        return await self.publish(data)


class CommandChannel(Channel):
    """Channel for receiving OS commands"""
    
    def __init__(self, agent_id: str, event_bus: Optional[EventBus] = None):
        super().__init__(agent_id, ChannelType.COMMAND, event_bus)
    
    async def send_command(self, command: str, params: Optional[Dict[str, Any]] = None):
        """Send a command to the agent"""
        data = {
            "command": command,
            "params": params or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        return await self.publish(data)


class HealthChannel(Channel):
    """Channel for health monitoring"""
    
    def __init__(self, agent_id: str, event_bus: Optional[EventBus] = None):
        super().__init__(agent_id, ChannelType.HEALTH, event_bus)
    
    async def report_health(self, memory_usage: Optional[int] = None, cpu_usage: Optional[float] = None, 
                           custom_metrics: Optional[Dict[str, Any]] = None):
        """Report agent health metrics"""
        data = {
            "heartbeat": datetime.utcnow().isoformat(),
            "memory_usage_mb": memory_usage,
            "cpu_usage_percent": cpu_usage
        }
        if custom_metrics:
            data.update(custom_metrics)
        
        return await self.publish(data)


class ActivityChannel(Channel):
    """Channel for activity reporting"""
    
    def __init__(self, agent_id: str, event_bus: Optional[EventBus] = None):
        super().__init__(agent_id, ChannelType.ACTIVITY, event_bus)
    
    async def report_activity(self, activity_type: str, description: str, 
                             details: Optional[Dict[str, Any]] = None):
        """Report agent activity"""
        data = {
            "activity_type": activity_type,
            "description": description,
            "timestamp": datetime.utcnow().isoformat()
        }
        if details:
            data.update(details)
        
        return await self.publish(data)


class ErrorChannel(Channel):
    """Channel for error reporting"""
    
    def __init__(self, agent_id: str, event_bus: Optional[EventBus] = None):
        super().__init__(agent_id, ChannelType.ERROR, event_bus)
    
    async def report_error(self, error_type: str, message: str, 
                          stack_trace: Optional[str] = None, recoverable: bool = True,
                          context: Optional[Dict[str, Any]] = None):
        """Report an error"""
        data = {
            "error_type": error_type,
            "message": message,
            "stack_trace": stack_trace,
            "recoverable": recoverable,
            "timestamp": datetime.utcnow().isoformat()
        }
        if context:
            data.update(context)
        
        return await self.publish(data)


class AgentChannelManager:
    """Manages all channels for an agent"""
    
    def __init__(self, agent_id: str, event_bus: Optional[EventBus] = None):
        self.agent_id = agent_id
        self.event_bus = event_bus or get_event_bus()
        
        # Create standard channels
        self.status = StatusChannel(agent_id, event_bus)
        self.command = CommandChannel(agent_id, event_bus)
        self.health = HealthChannel(agent_id, event_bus)
        self.activity = ActivityChannel(agent_id, event_bus)
        self.error = ErrorChannel(agent_id, event_bus)
        
        # Custom channels for specific agent types
        self._custom_channels: Dict[str, Channel] = {}
    
    def add_custom_channel(self, name: str, channel: Channel):
        """Add a custom channel for agent-specific functionality"""
        self._custom_channels[name] = channel
    
    def get_custom_channel(self, name: str) -> Optional[Channel]:
        """Get a custom channel by name"""
        return self._custom_channels.get(name)
    
    def get_all_channels(self) -> Dict[str, Channel]:
        """Get all channels (standard + custom)"""
        channels = {
            "status": self.status,
            "command": self.command,
            "health": self.health,
            "activity": self.activity,
            "error": self.error
        }
        channels.update(self._custom_channels)
        return channels
    
    async def setup_command_handler(self, command_handler: Callable[[str, Dict[str, Any]], None]):
        """Setup handler for incoming commands"""
        def handle_command_message(message: ChannelMessage):
            command = message.data.get("command")
            params = message.data.get("params", {})
            if command:
                command_handler(command, params)
        
        self.command.subscribe(handle_command_message)


def create_agent_channels(agent_id: str, event_bus: Optional[EventBus] = None) -> AgentChannelManager:
    """Convenience function to create standard agent channels"""
    return AgentChannelManager(agent_id, event_bus)


def subscribe_to_agent_channel(agent_id: str, channel_type: ChannelType, 
                              callback: Callable[[ChannelMessage], None],
                              event_bus: Optional[EventBus] = None) -> str:
    """Subscribe to another agent's channel"""
    bus = event_bus or get_event_bus()
    topic_pattern = f"agent.{agent_id}.{channel_type.value}"
    
    event_filter = EventFilter(event_types=[topic_pattern])
    
    def event_callback(event: Event):
        message = ChannelMessage.from_event(event)
        if message:
            callback(message)
    
    return bus.subscribe(event_filter, event_callback)


def subscribe_to_all_agents_channel(channel_type: ChannelType,
                                  callback: Callable[[ChannelMessage], None],
                                  event_bus: Optional[EventBus] = None) -> str:
    """Subscribe to a specific channel type from all agents"""
    bus = event_bus or get_event_bus()
    
    # Use wildcard pattern for all agents
    event_filter = EventFilter()  # No filter, will check in callback
    
    def event_callback(event: Event):
        # Check if event matches agent.*.{channel_type} pattern
        parts = event.type.split(".")
        if (len(parts) == 3 and 
            parts[0] == "agent" and 
            parts[2] == channel_type.value):
            
            message = ChannelMessage.from_event(event)
            if message:
                callback(message)
    
    return bus.subscribe(event_filter, event_callback)