"""
Agent Configuration Manager

Provides centralized management of agent configurations with user customization support.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from lightning_core.abstractions import Document
from lightning_core.runtime import LightningRuntime
from .schemas import (
    AgentConfig,
    AgentType,
    ConseilAgentConfig,
    VoiceAgentConfig,
    ChatAgentConfig,
    PlannerAgentConfig,
)

logger = logging.getLogger(__name__)


class AgentConfigManager:
    """Manages agent configurations with user customization support"""
    
    CONTAINER_NAME = "agent_configs"
    
    def __init__(self, runtime: Optional[LightningRuntime] = None):
        self.runtime = runtime or LightningRuntime()
        self.defaults_path = Path(__file__).parent / "defaults"
        self.defaults_path.mkdir(exist_ok=True)
        
        # Cache for default configurations
        self._defaults_cache: Dict[str, AgentConfig] = {}
    
    async def get_agent_config(self, agent_id: str, user_id: Optional[str] = None) -> AgentConfig:
        """
        Get agent configuration, preferring user customizations over defaults.
        
        Args:
            agent_id: Unique identifier for the agent
            user_id: User ID for custom configurations
            
        Returns:
            AgentConfig instance
            
        Raises:
            ValueError: If agent configuration is not found
        """
        # Try user-specific config first
        if user_id:
            try:
                user_config = await self._load_user_config(agent_id, user_id)
                if user_config:
                    logger.info(f"Loaded user config for {agent_id} (user: {user_id})")
                    return user_config
            except Exception as e:
                logger.warning(f"Failed to load user config for {agent_id}: {e}")
        
        # Fall back to default config
        try:
            default_config = await self._load_default_config(agent_id)
            logger.info(f"Loaded default config for {agent_id}")
            return default_config
        except Exception as e:
            logger.error(f"Failed to load default config for {agent_id}: {e}")
            raise ValueError(f"Agent configuration '{agent_id}' not found")
    
    async def list_agent_configs(
        self, 
        agent_type: Optional[AgentType] = None, 
        user_id: Optional[str] = None,
        include_defaults: bool = True
    ) -> List[AgentConfig]:
        """
        List available agent configurations.
        
        Args:
            agent_type: Filter by agent type
            user_id: Include user-specific configurations
            include_defaults: Whether to include default configurations
            
        Returns:
            List of AgentConfig instances
        """
        configs = []
        
        # Load default configurations
        if include_defaults:
            default_configs = await self._load_all_default_configs()
            configs.extend(default_configs)
        
        # Load user-specific configurations
        if user_id:
            try:
                user_configs = await self._load_all_user_configs(user_id)
                configs.extend(user_configs)
            except Exception as e:
                logger.warning(f"Failed to load user configs for {user_id}: {e}")
        
        # Filter by type if specified
        if agent_type:
            configs = [c for c in configs if c.type == agent_type]
        
        return configs
    
    async def create_agent_config(self, config: AgentConfig, user_id: Optional[str] = None) -> str:
        """
        Create a new agent configuration.
        
        Args:
            config: AgentConfig to create
            user_id: User ID for user-specific config
            
        Returns:
            Agent ID of created configuration
        """
        if user_id:
            config.created_by = user_id
            await self._save_user_config(config, user_id)
        else:
            await self._save_default_config(config)
        
        logger.info(f"Created agent config: {config.id}")
        return config.id
    
    async def update_agent_config(
        self, 
        agent_id: str, 
        updates: Dict[str, Any], 
        user_id: Optional[str] = None
    ) -> bool:
        """
        Update an existing agent configuration.
        
        Args:
            agent_id: Agent configuration to update
            updates: Dictionary of updates to apply
            user_id: User ID for user-specific config
            
        Returns:
            True if successful
        """
        try:
            # Load existing config
            existing_config = await self.get_agent_config(agent_id, user_id)
            
            # Apply updates
            config_dict = existing_config.to_dict()
            config_dict.update(updates)
            
            # Recreate config object
            updated_config = AgentConfig.from_dict(config_dict)
            
            # Save updated config
            if user_id:
                await self._save_user_config(updated_config, user_id)
            else:
                await self._save_default_config(updated_config)
            
            logger.info(f"Updated agent config: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update agent config {agent_id}: {e}")
            return False
    
    async def clone_agent_config(
        self, 
        source_id: str, 
        new_id: str, 
        new_name: str, 
        user_id: Optional[str] = None
    ) -> str:
        """
        Clone an existing agent configuration.
        
        Args:
            source_id: Source agent configuration ID
            new_id: New agent configuration ID
            new_name: Name for the new configuration
            user_id: User ID for user-specific config
            
        Returns:
            New agent ID
        """
        # Load source config
        source_config = await self.get_agent_config(source_id, user_id)
        
        # Create cloned config
        cloned_dict = source_config.to_dict()
        cloned_dict.update({
            "id": new_id,
            "name": new_name,
            "is_default": False,
            "is_system": False,
            "created_by": user_id or "system"
        })
        
        cloned_config = AgentConfig.from_dict(cloned_dict)
        
        # Save cloned config
        await self.create_agent_config(cloned_config, user_id)
        
        logger.info(f"Cloned agent config {source_id} to {new_id}")
        return new_id
    
    async def delete_agent_config(self, agent_id: str, user_id: Optional[str] = None) -> bool:
        """
        Delete an agent configuration.
        
        Args:
            agent_id: Agent configuration to delete
            user_id: User ID for user-specific config
            
        Returns:
            True if successful
        """
        try:
            if user_id:
                doc_id = f"{user_id}:{agent_id}"
                await self.runtime.storage.delete_document(self.CONTAINER_NAME, doc_id)
            else:
                config_file = self.defaults_path / f"{agent_id}.json"
                if config_file.exists():
                    config_file.unlink()
                
                # Remove from cache
                self._defaults_cache.pop(agent_id, None)
            
            logger.info(f"Deleted agent config: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete agent config {agent_id}: {e}")
            return False
    
    async def create_custom_agent(
        self, 
        base_type: AgentType, 
        agent_id: str,
        name: str,
        user_id: str,
        customizations: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a custom agent based on a template.
        
        Args:
            base_type: Base agent type to use as template
            agent_id: Unique ID for the new agent
            name: Display name for the agent
            user_id: User creating the agent
            customizations: Custom settings to apply
            
        Returns:
            Agent ID of created configuration
        """
        # Get base template
        base_config = await self._get_default_for_type(base_type)
        
        # Apply customizations
        config_dict = base_config.to_dict()
        config_dict.update({
            "id": agent_id,
            "name": name,
            "created_by": user_id,
            "is_default": False,
            "is_system": False
        })
        
        if customizations:
            config_dict.update(customizations)
        
        # Create typed config
        custom_config = AgentConfig.from_dict(config_dict)
        
        # Save as user config
        await self._save_user_config(custom_config, user_id)
        
        logger.info(f"Created custom agent {agent_id} for user {user_id}")
        return agent_id
    
    async def _load_default_config(self, agent_id: str) -> AgentConfig:
        """Load default configuration from file"""
        # Check cache first
        if agent_id in self._defaults_cache:
            return self._defaults_cache[agent_id]
        
        config_file = self.defaults_path / f"{agent_id}.json"
        if not config_file.exists():
            raise ValueError(f"Default config file not found: {config_file}")
        
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        config = AgentConfig.from_dict(config_data)
        
        # Cache the config
        self._defaults_cache[agent_id] = config
        
        return config
    
    async def _save_default_config(self, config: AgentConfig):
        """Save default configuration to file"""
        config_file = self.defaults_path / f"{config.id}.json"
        
        with open(config_file, 'w') as f:
            json.dump(config.to_dict(), f, indent=2)
        
        # Update cache
        self._defaults_cache[config.id] = config
    
    async def _load_user_config(self, agent_id: str, user_id: str) -> Optional[AgentConfig]:
        """Load user-specific configuration"""
        try:
            doc_id = f"{user_id}:{agent_id}"
            doc = await self.runtime.storage.get_document(self.CONTAINER_NAME, doc_id)
            
            if doc and doc.data:
                return AgentConfig.from_dict(doc.data)
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to load user config {agent_id} for {user_id}: {e}")
            return None
    
    async def _save_user_config(self, config: AgentConfig, user_id: str):
        """Save user-specific configuration"""
        doc_id = f"{user_id}:{config.id}"
        
        doc = Document(
            id=doc_id,
            partition_key=user_id,
            data=config.to_dict()
        )
        
        # Check if document exists
        existing = await self.runtime.storage.get_document(self.CONTAINER_NAME, doc_id)
        
        if existing:
            await self.runtime.storage.update_document(self.CONTAINER_NAME, doc)
        else:
            await self.runtime.storage.create_document(self.CONTAINER_NAME, doc)
    
    async def _load_all_default_configs(self) -> List[AgentConfig]:
        """Load all default configurations"""
        configs = []
        
        for config_file in self.defaults_path.glob("*.json"):
            try:
                agent_id = config_file.stem
                config = await self._load_default_config(agent_id)
                configs.append(config)
            except Exception as e:
                logger.warning(f"Failed to load default config {config_file}: {e}")
        
        return configs
    
    async def _load_all_user_configs(self, user_id: str) -> List[AgentConfig]:
        """Load all user-specific configurations"""
        configs = []
        
        try:
            # This would need to be implemented based on your storage provider
            # For now, we'll return empty list
            # TODO: Implement listing documents with prefix filter
            pass
        except Exception as e:
            logger.warning(f"Failed to load user configs for {user_id}: {e}")
        
        return configs
    
    async def _get_default_for_type(self, agent_type: AgentType) -> AgentConfig:
        """Get a default configuration for an agent type"""
        # Try to load type-specific default first
        type_defaults = {
            AgentType.CONSEIL: "conseil-default",
            AgentType.VOICE: "voice-default", 
            AgentType.CHAT: "chat-default",
            AgentType.PLANNER: "planner-default"
        }
        
        default_id = type_defaults.get(agent_type)
        if default_id:
            try:
                return await self._load_default_config(default_id)
            except ValueError:
                pass
        
        # Fall back to creating a basic config
        if agent_type == AgentType.CONSEIL:
            return ConseilAgentConfig(
                id="conseil-template",
                name="Conseil Agent Template",
                description="Base template for Conseil agents"
            )
        elif agent_type == AgentType.VOICE:
            return VoiceAgentConfig(
                id="voice-template",
                name="Voice Agent Template", 
                description="Base template for Voice agents"
            )
        elif agent_type == AgentType.CHAT:
            return ChatAgentConfig(
                id="chat-template",
                name="Chat Agent Template",
                description="Base template for Chat agents"
            )
        elif agent_type == AgentType.PLANNER:
            return PlannerAgentConfig(
                id="planner-template",
                name="Planner Agent Template",
                description="Base template for Planner agents"
            )
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")


# Global instance
_config_manager: Optional[AgentConfigManager] = None

def get_agent_config_manager() -> AgentConfigManager:
    """Get the global agent configuration manager"""
    global _config_manager
    if _config_manager is None:
        _config_manager = AgentConfigManager()
    return _config_manager