"""
Index Guide Generation Driver

This driver handles the generation of index guides for folders using an LLM.
It listens for folder creation events and generates contextual guides based
on the folder hierarchy.
"""

import logging
from typing import Any, Dict, List, Optional

from lightning_core.events.models import (
    BaseEvent,
    IndexGuideGeneratedEvent,
)
from lightning_core.vextir_os.drivers import (
    AgentDriver,
    DriverManifest,
    DriverType,
    ResourceSpec,
    driver
)

logger = logging.getLogger(__name__)


@driver(
    "index_guide_generator",
    DriverType.AGENT,
    capabilities=["llm.index_guide.generate"],
    name="Index Guide Generator",
    description="Generates contextual index guides for folders using LLM"
)
class IndexGuideGeneratorDriver(AgentDriver):
    """Driver that generates index guides for folders using an LLM."""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        # Set up config with our defaults
        if config is None:
            config = {}
        config["model_name"] = config.get("model_name", "gpt-4-turbo-preview")
        config["system_prompt"] = self._get_system_prompt()
        
        super().__init__(manifest, config)
        logger.info("IndexGuideGeneratorDriver initialized")

    def _get_system_prompt(self) -> str:
        """Get the system prompt for index guide generation."""
        return (
            "You are an expert at creating helpful index guides for folders "
            "in a personal knowledge management system.\n\n"
            "Your task is to generate a comprehensive index guide for a "
            "specific folder based on:\n"
            "1. The folder name and its purpose\n"
            "2. The folder's position in the hierarchy\n"
            "3. The types of content that would logically belong in this folder\n\n"
            "Guidelines for creating index guides:\n"
            "- Start with a clear purpose statement for the folder\n"
            "- Provide specific organization guidelines relevant to the "
            "folder's content\n"
            "- Include best practices that make sense for this type of content\n"
            "- Consider the folder's relationship to parent and sibling folders\n"
            "- Make recommendations concrete and actionable\n"
            "- Use markdown formatting with proper headers\n\n"
            "The guide should be practical and help users understand:\n"
            "- What belongs in this folder\n"
            "- How to organize content within it\n"
            "- Naming conventions to follow\n"
            "- When to create subfolders\n"
            "- How this folder relates to their overall knowledge system\n\n"
            "Keep the tone helpful and professional. Focus on practical "
            "guidance rather than generic advice."
        )

    async def handle_event(self, event: BaseEvent) -> Optional[BaseEvent]:
        """Handle index guide generation requests."""
        logger.info(f"IndexGuideGeneratorDriver received event: {event.type}")
        try:
            if event.type != "llm.index_guide.generate":
                logger.info(f"Ignoring event type: {event.type}")
                return None
            
            logger.info("Processing index guide generation request")
            # Extract folder information from event
            folder_name = event.data.get("folder_name", "")
            folder_path = event.data.get("folder_path", "")
            parent_folders = event.data.get("parent_folders", [])
            sibling_folders = event.data.get("sibling_folders", [])
            folder_id = event.data.get("folder_id", "")
            response_event_type = event.data.get(
                "response_event_type", "context.index_guide.generated"
            )

            if not folder_name or not folder_id:
                logger.error("Missing required folder information in event")
                return None

            # Build context for the LLM
            prompt = self._build_prompt(
                folder_name, folder_path, parent_folders, sibling_folders
            )

            # Generate the index guide
            response = await self.complete(prompt)

            if not response:
                logger.error("Failed to generate index guide")
                return None

            # Create response event with the generated guide
            response_event = IndexGuideGeneratedEvent(
                type=response_event_type,
                data={
                    "folder_id": folder_id,
                    "folder_name": folder_name,
                    "folder_path": folder_path,
                    "content": response,
                    "format": "markdown"
                },
                source=self.id,
                user_id=event.user_id
            )

            return response_event

        except Exception as e:
            logger.error(f"Error generating index guide: {e}")
            return None

    def _build_prompt(
        self,
        folder_name: str,
        folder_path: str,
        parent_folders: List[str],
        sibling_folders: List[str]
    ) -> str:
        """Build the prompt for index guide generation."""
        prompt_parts = [
            f"Generate an index guide for the folder: '{folder_name}'",
            f"\nFull path: {folder_path}"
        ]

        if parent_folders:
            prompt_parts.append(f"\nParent folders: {', '.join(parent_folders)}")

        if sibling_folders:
            # Filter out system folders like _index.guide
            user_siblings = [f for f in sibling_folders if not f.startswith('_')]
            if user_siblings:
                prompt_parts.append(
                    f"\nSibling folders: {', '.join(user_siblings[:10])}"
                )  # Limit to 10

        prompt_parts.append(
            "\n\nCreate a comprehensive, practical index guide for this folder."
        )

        return "\n".join(prompt_parts)

    def get_capabilities(self) -> List[str]:
        """Get the capabilities this driver provides."""
        return ["llm.index_guide.generate"]

    def get_resource_requirements(self) -> ResourceSpec:
        """Get resource requirements for this driver."""
        return ResourceSpec(memory_mb=512, timeout_seconds=30)
