"""
Service launcher for Lightning Core.
Provides unified entry point for running different services in local or cloud mode.
"""
import os
import sys
import logging

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_api_service():
    """Run the API service in local or Azure mode."""
    mode = os.getenv("LIGHTNING_MODE", "local")
    
    logger.info(f"Starting Lightning API in {mode} mode")
    
    # Both local and Azure use FastAPI with uvicorn
    # The difference is in the configuration (handled by RuntimeConfig)
    import uvicorn
    from lightning_core.api.main import app
    
    # Port configuration
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    # Reload only in local development
    reload = mode == "local" and os.getenv("RELOAD", "true").lower() == "true"
    
    uvicorn.run(
        "lightning_core.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info").lower()
    )


def run_event_processor():
    """Run the event processor in local or Azure mode."""
    mode = os.getenv("LIGHTNING_MODE", "local")
    
    logger.info(f"Starting Event Processor in {mode} mode")
    
    if mode == "azure":
        # Check if running as Azure Function or Container
        deployment_type = os.getenv("AZURE_DEPLOYMENT_TYPE", "container")
        
        if deployment_type == "function":
            logger.info("Running as Azure Function - importing function app")
            # Import the function app module which Azure Functions runtime will use
            try:
                from lightning_core.azure import function_app
                logger.info("Azure Function app module imported successfully")
                # Azure Functions runtime takes over from here
            except ImportError as e:
                logger.error(f"Failed to import Azure Function app: {e}")
                logger.info("Falling back to container mode")
                deployment_type = "container"
        
        if deployment_type == "container":
            # Run continuous event processor for Azure Container Instance
            logger.info("Running as Azure Container Instance with continuous processing")
            # Check if azure event processor exists, otherwise use local with Azure config
            try:
                from lightning_core.vextir_os.azure_event_processor import main
                import asyncio
                asyncio.run(main())
            except ImportError:
                logger.info("Azure event processor not found, using local processor with Azure config")
                from lightning_core.vextir_os.local_event_processor import main
                import asyncio
                asyncio.run(main())
    else:
        # Local mode
        from lightning_core.vextir_os.local_event_processor import main
        import asyncio
        asyncio.run(main())


def run_agent(agent_type: str):
    """Run an agent service."""
    mode = os.getenv("LIGHTNING_MODE", "local")
    logger.info(f"Starting {agent_type} agent in {mode} mode")
    
    # Agents run the same way in both modes, configuration differs
    if agent_type == "conseil":
        try:
            from lightning_core.agents.conseil.main import main
            main()
        except ImportError:
            logger.error("Conseil agent not found in lightning_core")
            # Try running from agents directory
            os.system(f"cd /app/agents/conseil && npm start")
    elif agent_type == "voice":
        try:
            from lightning_core.agents.voice.main import main
            main()
        except ImportError:
            logger.error("Voice agent not found in lightning_core")
            # Try running from agents directory
            os.system(f"cd /app/agents/voice-agent && npm start")
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


def run_ui_service():
    """Run the UI service."""
    mode = os.getenv("LIGHTNING_MODE", "local")
    logger.info(f"Starting UI service in {mode} mode")
    
    # The UI runs the same way, just with different backend URLs
    ui_type = os.getenv("UI_TYPE", "integrated")
    
    if ui_type == "integrated":
        # Run the unified FastAPI app
        os.system("python /app/unified_app.py")
    else:
        raise ValueError(f"Unknown UI type: {ui_type}")


def main():
    """Main entry point that routes to appropriate service."""
    mode = os.getenv("LIGHTNING_MODE", "local")
    service_type = os.getenv("SERVICE_TYPE", "api")
    
    logger.info(f"Lightning Service Launcher - Mode: {mode}, Service: {service_type}")
    
    # Log configuration for debugging
    logger.info(f"Storage Provider: {os.getenv('LIGHTNING_STORAGE_PROVIDER', 'not set')}")
    logger.info(f"Event Bus Provider: {os.getenv('LIGHTNING_EVENT_BUS_PROVIDER', 'not set')}")
    
    # Special handling for Azure Function runtime
    if mode == "azure" and os.getenv("AZURE_FUNCTIONS_ENVIRONMENT"):
        logger.info("Detected Azure Functions environment, importing function app")
        from lightning_core.azure import function_app
        # Azure Functions runtime handles the rest
        return
    
    try:
        if service_type == "api":
            run_api_service()
        elif service_type == "event_processor":
            run_event_processor()
        elif service_type == "ui":
            run_ui_service()
        elif service_type.startswith("agent:"):
            # Format: agent:conseil or agent:voice
            agent_type = service_type.split(":", 1)[1]
            run_agent(agent_type)
        else:
            raise ValueError(f"Unknown service type: {service_type}")
    except Exception as e:
        logger.error(f"Failed to start service: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()