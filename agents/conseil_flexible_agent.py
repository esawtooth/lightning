"""
Flexible Conseil Agent for Lightning
Supports multiple job roles beyond coding
"""

import os
from typing import Dict, Any, Optional, List
from enum import Enum

from lightning_core.drivers import AgentDriver
from lightning_core.events import Event, EventType


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

    This agent wraps the Conseil CLI with configurable job roles, allowing it
    to function as a coding assistant, legal document reviewer, personal assistant,
    financial analyst, or any custom-defined role.
    """
    def __init__(
        self,
        name: str = "flexible_conseil",
        role: JobRole = JobRole.CODING,
        custom_description: Optional[str] = None,
        custom_guidelines: Optional[str] = None,
        enable_sandbox: bool = True,
        approval_policy: str = "manual",
        model: str = "gpt-4",
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
            model: AI model to use
            working_directory: Directory for agent operations
        """
        super().__init__(name=name, **kwargs)

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

    async def initialize(self):
        """Initialize the agent with role-specific configuration"""
        await super().initialize()

        # Log role configuration
        role_desc = self.custom_description if self.role == JobRole.CUSTOM else f"{self.role.value} assistant"
        self.logger.info(f"Initialized {self.name} as {role_desc}")
        self.logger.info(f"Sandbox: {'Enabled' if self.enable_sandbox else 'Disabled'}")
        self.logger.info(f"Approval: {self.approval_policy}")

    def _build_conseil_command(self, prompt: str) -> List[str]:
        """Build the Conseil CLI command with role configuration"""
        cmd = ["conseil"]

        # Add role configuration
        cmd.extend(["--role", self.role.value])

        # Add custom role details if applicable
        if self.role == JobRole.CUSTOM:
            cmd.extend(["--description", self.custom_description])
            if self.custom_guidelines:
                cmd.extend(["--guidelines", self.custom_guidelines])

        # Add sandbox configuration
        if not self.enable_sandbox:
            cmd.append("--no-sandbox")

        # Add other options
        cmd.extend([
            "--model", self.model,
            "--approval", self.approval_policy
        ])

        return cmd

    async def process_request(self, request: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Process a request using the configured Conseil agent.

        Args:
            request: The task or question for the agent
            context: Optional context (working directory, files, etc.)

        Returns:
            Agent's response or action summary
        """
        # Change to working directory if specified
        original_dir = os.getcwd()
        if context and "working_directory" in context:
            os.chdir(context["working_directory"])
        elif self.working_directory != original_dir:
            os.chdir(self.working_directory)

        try:
            # Build command
            cmd = self._build_conseil_command(request)

            # Log the command for debugging
            self.logger.debug(f"Executing Conseil command: {' '.join(cmd)}")

            # Execute Conseil (simplified - in practice would use subprocess)
            # This is a placeholder for the actual implementation
            result = await self._execute_conseil(cmd, request)

            return result

        finally:
            # Restore original directory
            os.chdir(original_dir)

    async def _execute_conseil(self, cmd: List[str], prompt: str) -> str:
        """Execute Conseil CLI and return results"""
        # This would actually run the Conseil CLI process
        # For now, return a placeholder
        return f"Executed {self.role.value} assistant for: {prompt}"

    async def handle_event(self, event: Event) -> Optional[Event]:
        """Handle incoming events"""
        if event.type == EventType.INPUT and event.data.get("agent") == self.name:
            # Process the request
            request = event.data.get("prompt", "")
            context = event.data.get("context", {})

            result = await self.process_request(request, context)

            # Return result event
            return Event(
                type=EventType.OUTPUT,
                source=self.name,
                data={
                    "result": result,
                    "role": self.role.value,
                    "request_id": event.data.get("request_id")
                }
            )

        return None


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
