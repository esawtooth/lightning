"""
Flexible Conseil Agent for Lightning
Supports multiple job roles beyond coding
"""

import os
import sys
import logging
from typing import Dict, Any, Optional, List
from enum import Enum

# Add the core directory to the path if running standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

from lightning_core.vextir_os.drivers import AgentDriver, DriverManifest, DriverType, ResourceSpec
from lightning_core.vextir_os.events import Event
from lightning_core.llm import get_completions_api, Message, MessageRole


class JobRole(Enum):
    """Available job roles for the Conseil agent"""
    CODING = "coding"
    LEGAL = "legal"
    PERSONAL = "personal"
    FINANCE = "finance"
    RESEARCH = "research"
    TECHNICAL_WRITER = "technical_writer"
    PROJECT_MANAGER = "project_manager"
    DATA_ANALYST = "data_analyst"
    CUSTOM = "custom"


class FlexibleConseilAgent(AgentDriver):
    """
    Flexible Conseil agent that can operate in different professional roles.

    This agent uses the Lightning Core model registry and completions API,
    allowing it to function as a coding assistant, legal document reviewer, 
    personal assistant, financial analyst, or any custom-defined role.
    """
    def __init__(
        self,
        name: str = "flexible_conseil",
        role: JobRole = JobRole.CODING,
        custom_description: Optional[str] = None,
        custom_guidelines: Optional[str] = None,
        enable_sandbox: bool = True,
        approval_policy: str = "manual",
        model: str = "gpt-4o-mini",
        working_directory: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize the flexible Conseil agent.

        Args:
            name: Agent identifier
            role: Job role for the agent
            custom_description: Description for custom role
            custom_guidelines: Guidelines for custom role
            enable_sandbox: Whether to sandbox file operations
            approval_policy: Command approval policy (auto, manual, guided)
            model: AI model to use (from Lightning model registry)
            working_directory: Directory for agent operations
        """
        # Create manifest
        manifest = DriverManifest(
            id=name,
            name=f"Flexible Conseil Agent ({role.value})",
            version="1.0.0",
            author="Lightning",
            description=custom_description or f"Conseil agent in {role.value} role",
            driver_type=DriverType.AGENT,
            capabilities=[f"conseil.{role.value}", "chat", "task_execution"],
            resource_requirements=ResourceSpec(memory_mb=1024, timeout_seconds=300),
        )
        
        # Initialize parent with model configuration
        config = kwargs.get("config", {})
        config.update({
            "model": model,
            "system_prompt": self._build_system_prompt(role, custom_description, custom_guidelines)
        })
        
        super().__init__(manifest=manifest, config=config)

        self.role = role
        self.custom_description = custom_description
        self.custom_guidelines = custom_guidelines
        self.enable_sandbox = enable_sandbox
        self.approval_policy = approval_policy
        self.model = model
        self.working_directory = working_directory or os.getcwd()

        # Validate custom role configuration
        if role == JobRole.CUSTOM and not custom_description:
            raise ValueError("Custom role requires a description")
    
    def _build_system_prompt(self, role: JobRole, custom_description: Optional[str], custom_guidelines: Optional[str]) -> str:
        """Build role-specific system prompt."""
        base_prompts = {
            JobRole.CODING: """You are a skilled software engineer assistant. You help with coding tasks, 
            debugging, code reviews, and software architecture. You write clean, efficient, and well-documented code.""",
            
            JobRole.LEGAL: """You are a legal document assistant. You help review contracts, agreements, 
            and legal documents. You identify potential issues, suggest improvements, and ensure clarity. 
            Note: You provide assistance but are not a lawyer and cannot give legal advice.""",
            
            JobRole.PERSONAL: """You are a helpful personal assistant. You help with scheduling, reminders, 
            email drafts, travel planning, and various personal tasks. You are organized, proactive, and considerate.""",
            
            JobRole.FINANCE: """You are a financial analysis assistant. You help analyze financial data, 
            create reports, track expenses, and provide insights. You are detail-oriented and accurate with numbers.""",
            
            JobRole.RESEARCH: """You are a research assistant. You help gather information, analyze sources, 
            create summaries, and compile research reports. You are thorough, objective, and cite sources properly.""",
            
            JobRole.TECHNICAL_WRITER: """You are a technical writing assistant. You help create documentation, 
            user guides, API references, and technical articles. You write clearly and structure information logically.""",
            
            JobRole.PROJECT_MANAGER: """You are a project management assistant. You help with project planning, 
            task tracking, timeline management, and team coordination. You are organized and deadline-focused.""",
            
            JobRole.DATA_ANALYST: """You are a data analysis assistant. You help analyze datasets, create 
            visualizations, identify patterns, and generate insights. You are skilled in statistics and data interpretation.""",
        }
        
        if role == JobRole.CUSTOM:
            prompt = custom_description or "You are a helpful assistant."
            if custom_guidelines:
                prompt += f"\n\nGuidelines:\n{custom_guidelines}"
        else:
            prompt = base_prompts.get(role, "You are a helpful assistant.")
            
        # Add general instructions
        prompt += "\n\nAlways be helpful, accurate, and professional. If you're unsure about something, say so."
        
        return prompt

    async def initialize(self):
        """Initialize the agent with role-specific configuration"""
        await super().initialize()

        # Log role configuration  
        self.logger = logging.getLogger(self.__class__.__name__)
        role_desc = self.custom_description if self.role == JobRole.CUSTOM else f"{self.role.value} assistant"
        self.logger.info(f"Initialized {self.name} as {role_desc}")
        self.logger.info(f"Sandbox: {'Enabled' if self.enable_sandbox else 'Disabled'}")
        self.logger.info(f"Approval: {self.approval_policy}")

    def get_capabilities(self) -> List[str]:
        """Return agent capabilities based on role."""
        return self.manifest.capabilities
    
    def get_resource_requirements(self) -> ResourceSpec:
        """Return resource requirements."""
        return self.manifest.resource_requirements

    async def process_request(self, request: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Process a request using the Lightning Core completions API.

        Args:
            request: The task or question for the agent
            context: Optional context (working directory, files, etc.)

        Returns:
            Agent's response or action summary
        """
        # Build context information
        context_info = ""
        if context:
            if "working_directory" in context:
                context_info += f"\nWorking Directory: {context['working_directory']}"
            if "files" in context:
                context_info += f"\nRelevant Files: {', '.join(context['files'])}"
            if "additional_info" in context:
                context_info += f"\n{context['additional_info']}"
        
        # Prepare messages
        messages = []
        
        # Add context if available
        if context_info:
            messages.append({
                "role": "user",
                "content": f"Context for this request:{context_info}"
            })
        
        # Add the main request
        messages.append({
            "role": "user", 
            "content": request
        })
        
        # Make completion request using the Lightning Core API
        try:
            response = await self.complete(
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error processing request: {e}")
            return f"Error: Unable to process request - {str(e)}"

    async def handle_event(self, event: Event) -> List[Event]:
        """Handle incoming events"""
        output_events = []
        
        if event.type == "agent.task" and event.metadata.get("agent_id") == self.name:
            # Process the request
            request = event.metadata.get("task", "")
            context = event.metadata.get("context", {})

            result = await self.process_request(request, context)

            # Return result event
            output_events.append(Event(
                type="agent.task.completed",
                source=self.name,
                user_id=event.user_id,
                metadata={
                    "result": result,
                    "role": self.role.value,
                    "request_id": event.metadata.get("request_id"),
                    "agent_id": self.name
                }
            ))

        return output_events


# Factory functions for common agent configurations

def create_legal_assistant(
    name: str = "legal_conseil",
    working_directory: str = "./legal_docs",
    **kwargs
) -> FlexibleConseilAgent:
    """Create a pre-configured legal document assistant"""
    return FlexibleConseilAgent(
        name=name,
        role=JobRole.LEGAL,
        enable_sandbox=False,  # Legal docs often need direct access
        approval_policy="manual",  # Careful review for legal changes
        working_directory=working_directory,
        model="gpt-4o",  # Use more capable model for legal work
        **kwargs
    )


def create_personal_assistant(
    name: str = "personal_conseil",
    **kwargs
) -> FlexibleConseilAgent:
    """Create a pre-configured personal assistant"""
    return FlexibleConseilAgent(
        name=name,
        role=JobRole.PERSONAL,
        enable_sandbox=False,
        approval_policy="auto",  # Trust for personal tasks
        **kwargs
    )


def create_research_assistant(
    name: str = "research_conseil",
    **kwargs
) -> FlexibleConseilAgent:
    """Create a pre-configured research assistant"""
    return FlexibleConseilAgent(
        name=name,
        role=JobRole.RESEARCH,
        enable_sandbox=True,  # Sandbox for web research
        approval_policy="guided",
        **kwargs
    )


def create_finance_assistant(
    name: str = "finance_conseil",
    working_directory: str = "./financial_data",
    **kwargs
) -> FlexibleConseilAgent:
    """Create a pre-configured financial assistant"""
    return FlexibleConseilAgent(
        name=name,
        role=JobRole.FINANCE,
        enable_sandbox=False,
        approval_policy="manual",  # Careful with financial data
        working_directory=working_directory,
        **kwargs
    )


# Example usage in a Lightning workflow
async def example_multi_role_workflow():
    """Example showing multiple Conseil agents with different roles"""

    # Create agents for different tasks
    legal_agent = create_legal_assistant()
    research_agent = create_research_assistant()
    finance_agent = create_finance_assistant()

    # Legal document review
    legal_result = await legal_agent.process_request(
        "Review the consulting agreement in contracts/acme-consulting.md and flag any issues",
        context={"working_directory": "./legal_docs"}
    )

    # Research task
    research_result = await research_agent.process_request(
        "Research best practices for SaaS pricing models and create a summary"
    )

    # Financial analysis
    finance_result = await finance_agent.process_request(
        "Analyze Q4 expenses and create a trend report",
        context={"working_directory": "./finance/2024"}
    )

    return {
        "legal": legal_result,
        "research": research_result,
        "finance": finance_result
    }


# Custom role example
def create_hr_assistant(**kwargs) -> FlexibleConseilAgent:
    """Create a custom HR assistant"""
    return FlexibleConseilAgent(
        name="hr_conseil",
        role=JobRole.CUSTOM,
        custom_description="""You are an HR assistant helping with employee documentation,
        onboarding processes, policy updates, and maintaining employee records. You can
        create offer letters, update employee handbooks, track PTO, and manage HR workflows.""",
        custom_guidelines="""- Maintain strict confidentiality with employee information
        - Follow all company HR policies and legal requirements
        - Use inclusive, professional language in all documents
        - Create clear audit trails for all HR decisions
        - Flag any potential compliance issues""",
        enable_sandbox=False,
        approval_policy="manual",
        **kwargs
    )
