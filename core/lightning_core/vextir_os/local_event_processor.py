"""
Local Event Processor Service

This module runs the universal event processor as a standalone service,
listening for events from the local event bus (Redis) and processing them.
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Optional

from lightning_core.abstractions import EventMessage, ExecutionMode, RuntimeConfig
from lightning_core.runtime import get_runtime, initialize_runtime
from lightning_core.vextir_os.driver_initialization import (
    configure_drivers_for_environment,
    initialize_all_drivers,
)
from lightning_core.vextir_os.serverless_processor import (
    universal_event_processor_handler,
)

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class LocalEventProcessorService:
    """Service that processes events from the local event bus."""

    def __init__(self):
        self.runtime: Optional[Any] = None
        self.function_id: Optional[str] = None
        self.subscription_id: Optional[str] = None
        self.running = False
        self._shutdown_event = asyncio.Event()

    async def start(self):
        """Start the event processor service."""
        logger.info("Starting Local Event Processor Service...")

        # Configure environment
        configure_drivers_for_environment()

        # Initialize runtime
        config = RuntimeConfig.from_env()
        self.runtime = await initialize_runtime(config)
        logger.info(f"Runtime initialized in {config.mode.value} mode")

        # Initialize drivers
        logger.info("Initializing drivers...")
        await initialize_all_drivers()
        logger.info("Drivers initialized")

        # Deploy the event processor function
        logger.info("Deploying event processor function...")
        self.function_id = await self.runtime.serverless.deploy_function(
            config={
                "name": "universal-event-processor",
                "handler": "universal_event_processor_handler",
                "runtime": "python",
                "memory_mb": 512,
                "timeout_seconds": 300,
                "environment_variables": {
                    "LOGGING_LEVEL": os.getenv("LOG_LEVEL", "INFO")
                },
            },
            handler=universal_event_processor_handler,
        )
        logger.info(f"Event processor function deployed: {self.function_id}")

        # Subscribe to all events
        async def process_event(event: EventMessage):
            """Process incoming events."""
            try:
                logger.info(f"Processing event: {event.event_type} (ID: {event.id})")

                # Invoke the serverless function
                response = await self.runtime.serverless.invoke_function(
                    self.function_id,
                    {
                        "type": event.event_type,
                        "userID": event.metadata.get("userID", "system"),
                        "id": event.id,
                        "timestamp": event.timestamp.isoformat(),
                        "source": event.metadata.get("source", "unknown"),
                        "data": event.data,
                        "metadata": event.metadata,
                    },
                )

                if response.is_error:
                    logger.error(f"Event processing failed: {response.error_message}")
                else:
                    result = response.body
                    if isinstance(result, dict):
                        output_count = result.get("output_count", 0)
                        logger.info(
                            f"Event processed successfully, generated {output_count} output events"
                        )
                    else:
                        logger.info("Event processed successfully")

            except Exception as e:
                logger.error(f"Error processing event {event.id}: {e}", exc_info=True)

        # Subscribe to all event types
        self.subscription_id = await self.runtime.event_bus.subscribe(
            "*", process_event, topic="vextir-events"  # Subscribe to all events
        )
        logger.info(f"Subscribed to events with ID: {self.subscription_id}")

        # Mark as running
        self.running = True
        logger.info("Local Event Processor Service started successfully")

        # Process some startup events
        await self._send_startup_event()

    async def _send_startup_event(self):
        """Send a startup event to verify the system is working."""
        startup_event = EventMessage(
            event_type="system.startup",
            data={
                "service": "local-event-processor",
                "version": "1.0.0",
                "mode": os.getenv("LIGHTNING_MODE", "local"),
            },
            metadata={"source": "event-processor", "userID": "system"},
        )

        await self.runtime.publish_event(startup_event, topic="vextir-events")
        logger.info("Startup event published")

    async def stop(self):
        """Stop the event processor service."""
        logger.info("Stopping Local Event Processor Service...")
        self.running = False

        # Unsubscribe from events
        if self.subscription_id and self.runtime:
            await self.runtime.event_bus.unsubscribe(self.subscription_id)
            logger.info("Unsubscribed from events")

        # Delete the function
        if self.function_id and self.runtime:
            await self.runtime.serverless.delete_function(self.function_id)
            logger.info("Event processor function deleted")

        # Shutdown runtime
        if self.runtime:
            await self.runtime.shutdown()
            logger.info("Runtime shutdown complete")

        logger.info("Local Event Processor Service stopped")
        self._shutdown_event.set()

    async def run(self):
        """Run the service until shutdown."""
        await self.start()

        # Wait for shutdown signal
        await self._shutdown_event.wait()

    def handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.stop())


async def main():
    """Main entry point."""
    service = LocalEventProcessorService()

    # Set up signal handlers
    signal.signal(signal.SIGINT, service.handle_signal)
    signal.signal(signal.SIGTERM, service.handle_signal)

    try:
        await service.run()
    except Exception as e:
        logger.error(f"Service error: {e}", exc_info=True)
        await service.stop()
        sys.exit(1)


if __name__ == "__main__":
    print(
        """
╔════════════════════════════════════════════════════════╗
║        Lightning Core - Local Event Processor          ║
║                                                        ║
║  Processing events from the local event bus...         ║
╚════════════════════════════════════════════════════════╝
"""
    )

    asyncio.run(main())
