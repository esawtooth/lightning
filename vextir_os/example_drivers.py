"""
Example drivers demonstrating Vextir OS driver architecture
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from events import Event, EmailEvent, CalendarEvent, ContextUpdateEvent
from .drivers import Driver, AgentDriver, ToolDriver, IODriver, DriverManifest, DriverType, ResourceSpec, driver
from .registries import get_model_registry, get_tool_registry


@driver("email_assistant", DriverType.AGENT, 
        capabilities=["email.process", "email.summarize", "meeting.schedule"],
        name="Email Assistant Agent",
        description="AI agent that processes emails and manages calendar")
class EmailAssistantDriver(AgentDriver):
    """Example agent driver for email processing"""
    
    def __init__(self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest, config)
        self.system_prompt = """
You are an email assistant. You help manage emails by:
- Summarizing important messages
- Drafting responses
- Scheduling meetings
- Maintaining context about ongoing conversations

Available tools: email_read, email_send, calendar_check, context_write
"""
    
    def get_capabilities(self) -> List[str]:
        return ["email.process", "email.summarize", "meeting.schedule"]
    
    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=1024, timeout_seconds=60)
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Process email-related events"""
        output_events = []
        
        if event.type == "email.process":
            # Process incoming email
            if isinstance(event, EmailEvent):
                # Create context update event
                context_event = ContextUpdateEvent(
                    timestamp=datetime.utcnow(),
                    source="EmailAssistantDriver",
                    type="context.update",
                    user_id=event.user_id,
                    context_key="email_summary",
                    update_operation="synthesize",
                    content=f"Email from {event.email_data.get('from', 'unknown')}: {event.email_data.get('subject', 'No subject')}",
                    synthesis_prompt="Update email summary with this new email"
                )
                output_events.append(context_event)
                
                # Check if meeting scheduling is needed
                subject = event.email_data.get('subject', '').lower()
                body = event.email_data.get('body', '').lower()
                
                if any(keyword in subject + body for keyword in ['meeting', 'schedule', 'call', 'appointment']):
                    # Create meeting scheduling event
                    meeting_event = Event(
                        timestamp=datetime.utcnow(),
                        source="EmailAssistantDriver",
                        type="meeting.schedule_request",
                        user_id=event.user_id,
                        metadata={
                            "email_id": event.email_data.get('id'),
                            "from": event.email_data.get('from'),
                            "subject": event.email_data.get('subject'),
                            "suggested_action": "schedule_meeting"
                        }
                    )
                    output_events.append(meeting_event)
        
        return output_events


@driver("github_integration", DriverType.TOOL,
        capabilities=["github.issue.create", "github.pr.list", "github.repo.search"],
        name="GitHub Integration Tool",
        description="GitHub repository management via MCP")
class GitHubToolDriver(ToolDriver):
    """Example tool driver for GitHub integration"""
    
    def __init__(self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest, config)
        # In real implementation, this would initialize MCP client
        self.mcp_endpoint = "github.com/modelcontextprotocol/servers/github"
    
    def get_capabilities(self) -> List[str]:
        return ["github.issue.create", "github.pr.list", "github.repo.search"]
    
    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=512, timeout_seconds=30)
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Handle GitHub-related events"""
        output_events = []
        
        if event.type == "github.issue.create":
            # Simulate creating GitHub issue
            issue_data = event.metadata
            
            # In real implementation, this would call MCP server
            result = {
                "issue_id": "12345",
                "url": f"https://github.com/{issue_data.get('repo')}/issues/12345",
                "title": issue_data.get('title'),
                "status": "created"
            }
            
            # Create result event
            result_event = Event(
                timestamp=datetime.utcnow(),
                source="GitHubToolDriver",
                type="github.issue.created",
                user_id=event.user_id,
                metadata=result
            )
            output_events.append(result_event)
            
        elif event.type == "github.pr.list":
            # Simulate listing pull requests
            repo = event.metadata.get('repo')
            
            # Mock PR data
            prs = [
                {"id": 1, "title": "Fix bug in authentication", "status": "open"},
                {"id": 2, "title": "Add new feature", "status": "merged"}
            ]
            
            result_event = Event(
                timestamp=datetime.utcnow(),
                source="GitHubToolDriver",
                type="github.pr.listed",
                user_id=event.user_id,
                metadata={"repo": repo, "pull_requests": prs}
            )
            output_events.append(result_event)
        
        return output_events


@driver("notification_io", DriverType.IO,
        capabilities=["notification.send", "notification.email", "notification.slack"],
        name="Notification IO Driver",
        description="Send notifications via various channels")
class NotificationIODriver(IODriver):
    """Example IO driver for sending notifications"""
    
    def get_capabilities(self) -> List[str]:
        return ["notification.send", "notification.email", "notification.slack"]
    
    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=256, timeout_seconds=15)
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Handle notification events"""
        output_events = []
        
        if event.type == "notification.send":
            notification_data = event.metadata
            channel = notification_data.get('channel', 'default')
            
            # Simulate sending notification
            if channel == 'email':
                # Create email event
                email_event = EmailEvent(
                    timestamp=datetime.utcnow(),
                    source="NotificationIODriver",
                    type="email.send",
                    user_id=event.user_id,
                    operation="send",
                    provider="gmail",
                    email_data={
                        "to": notification_data.get('recipient'),
                        "subject": notification_data.get('title', 'Notification'),
                        "body": notification_data.get('message', '')
                    }
                )
                output_events.append(email_event)
                
            elif channel == 'slack':
                # Create Slack notification event
                slack_event = Event(
                    timestamp=datetime.utcnow(),
                    source="NotificationIODriver",
                    type="slack.message",
                    user_id=event.user_id,
                    metadata={
                        "channel": notification_data.get('slack_channel', '#general'),
                        "message": notification_data.get('message', ''),
                        "priority": notification_data.get('priority', 'normal')
                    }
                )
                output_events.append(slack_event)
            
            # Create confirmation event
            confirmation_event = Event(
                timestamp=datetime.utcnow(),
                source="NotificationIODriver",
                type="notification.sent",
                user_id=event.user_id,
                metadata={
                    "channel": channel,
                    "status": "sent",
                    "original_event_id": event.id
                }
            )
            output_events.append(confirmation_event)
        
        return output_events


@driver("research_agent", DriverType.AGENT,
        capabilities=["research.request", "question.complex"],
        name="Research Agent",
        description="AI agent that gathers and synthesizes information")
class ResearchAgentDriver(AgentDriver):
    """Example research agent driver"""
    
    def __init__(self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest, config)
        self.system_prompt = """
You are a research assistant. You help by:
- Gathering information from multiple sources
- Synthesizing findings into coherent summaries
- Answering complex questions with citations
- Maintaining research context over time

Available tools: web_search, context_read, context_write
"""
    
    def get_capabilities(self) -> List[str]:
        return ["research.request", "question.complex"]
    
    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=2048, timeout_seconds=120)
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Handle research requests"""
        output_events = []
        
        if event.type == "research.request":
            query = event.metadata.get('query', '')
            topic = event.metadata.get('topic', 'general')
            
            # Simulate research process
            # 1. Search for information
            search_event = Event(
                timestamp=datetime.utcnow(),
                source="ResearchAgentDriver",
                type="web.search",
                user_id=event.user_id,
                metadata={"query": query, "max_results": 10}
            )
            output_events.append(search_event)
            
            # 2. Update context with research findings
            context_event = ContextUpdateEvent(
                timestamp=datetime.utcnow(),
                source="ResearchAgentDriver",
                type="context.update",
                user_id=event.user_id,
                context_key=f"research/{topic}",
                update_operation="synthesize",
                content=f"Research query: {query}",
                synthesis_prompt="Synthesize research findings and update knowledge base"
            )
            output_events.append(context_event)
            
            # 3. Create research completion event
            completion_event = Event(
                timestamp=datetime.utcnow(),
                source="ResearchAgentDriver",
                type="research.completed",
                user_id=event.user_id,
                metadata={
                    "query": query,
                    "topic": topic,
                    "status": "completed",
                    "context_key": f"research/{topic}"
                }
            )
            output_events.append(completion_event)
        
        return output_events


# Function to register all example drivers
async def register_example_drivers():
    """Register all example drivers with the system"""
    from .drivers import get_driver_registry
    
    registry = get_driver_registry()
    
    # Register drivers
    drivers = [
        (EmailAssistantDriver._vextir_manifest, EmailAssistantDriver),
        (GitHubToolDriver._vextir_manifest, GitHubToolDriver),
        (NotificationIODriver._vextir_manifest, NotificationIODriver),
        (ResearchAgentDriver._vextir_manifest, ResearchAgentDriver)
    ]
    
    for manifest, driver_class in drivers:
        try:
            await registry.register_driver(manifest, driver_class)
            logging.info(f"Registered example driver: {manifest.id}")
        except Exception as e:
            logging.error(f"Failed to register driver {manifest.id}: {e}")
