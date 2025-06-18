"""
Driver initialization module for Vextir OS.

This module handles the initialization of all system drivers,
supporting both local and cloud deployment scenarios.
"""

import logging
import os
from typing import Any, List, Tuple, Type

from .drivers import BaseDriver, DriverManifest
from .registries import get_driver_registry

logger = logging.getLogger(__name__)


async def initialize_all_drivers():
    """
    Initialize all drivers for the Vextir OS system.

    This function registers all available drivers with the driver registry.
    It handles both core drivers and optional drivers based on configuration.
    """
    registry = get_driver_registry()

    # Get all driver definitions
    drivers_to_register = get_driver_definitions()

    # Register each driver
    successful = 0
    failed = 0

    for manifest, driver_class in drivers_to_register:
        try:
            await registry.register_driver(manifest, driver_class)
            logger.info(f"Registered driver: {manifest.id}")
            successful += 1
        except Exception as e:
            logger.error(f"Failed to register driver {manifest.id}: {e}")
            failed += 1

    logger.info(
        f"Driver initialization complete: {successful} successful, {failed} failed"
    )

    if failed > 0:
        logger.warning(
            f"{failed} drivers failed to initialize - system may have reduced functionality"
        )


def get_driver_definitions() -> List[Tuple[DriverManifest, Type[BaseDriver]]]:
    """
    Get all driver definitions based on current configuration.

    Returns:
        List of (manifest, driver_class) tuples
    """
    drivers = []

    # Import drivers conditionally to avoid import errors if dependencies are missing
    try:
        from .core_drivers import (
            AuthenticationDriver,
            ChatAgentDriver,
            ContextHubDriver,
        )

        drivers.extend(
            [
                (ContextHubDriver._vextir_manifest, ContextHubDriver),
                (ChatAgentDriver._vextir_manifest, ChatAgentDriver),
                (AuthenticationDriver._vextir_manifest, AuthenticationDriver),
            ]
        )
    except ImportError as e:
        logger.warning(f"Could not import core drivers: {e}")

    # Communication drivers
    try:
        from .communication_drivers import (
            CalendarConnectorDriver,
            EmailConnectorDriver,
            UserMessengerDriver,
            VoiceCallDriver,
        )

        drivers.extend(
            [
                (EmailConnectorDriver._vextir_manifest, EmailConnectorDriver),
                (CalendarConnectorDriver._vextir_manifest, CalendarConnectorDriver),
                (UserMessengerDriver._vextir_manifest, UserMessengerDriver),
                (VoiceCallDriver._vextir_manifest, VoiceCallDriver),
            ]
        )
    except ImportError as e:
        logger.warning(f"Could not import communication drivers: {e}")

    # Orchestration drivers
    try:
        from .orchestration_drivers import (
            InstructionEngineDriver,
            SchedulerDriver,
            TaskMonitorDriver,
        )

        drivers.extend(
            [
                (InstructionEngineDriver._vextir_manifest, InstructionEngineDriver),
                (TaskMonitorDriver._vextir_manifest, TaskMonitorDriver),
                (SchedulerDriver._vextir_manifest, SchedulerDriver),
            ]
        )
    except ImportError as e:
        logger.warning(f"Could not import orchestration drivers: {e}")

    # Example drivers (optional)
    if os.getenv("ENABLE_EXAMPLE_DRIVERS", "false").lower() == "true":
        try:
            from .example_drivers import EchoDriver, HelloWorldDriver, WeatherDriver

            drivers.extend(
                [
                    (HelloWorldDriver._vextir_manifest, HelloWorldDriver),
                    (WeatherDriver._vextir_manifest, WeatherDriver),
                    (EchoDriver._vextir_manifest, EchoDriver),
                ]
            )
        except ImportError as e:
            logger.debug(f"Example drivers not available: {e}")

    return drivers


def get_required_drivers() -> List[str]:
    """
    Get list of required driver IDs that must be initialized.

    Returns:
        List of driver IDs that are required for basic operation
    """
    return [
        "core.context_hub",
        "core.authentication",
        "orchestration.instruction_engine",
    ]


async def initialize_required_drivers():
    """
    Initialize only the required drivers for minimal operation.

    This is useful for testing or when running with limited functionality.
    """
    registry = get_driver_registry()
    required_ids = get_required_drivers()
    all_drivers = get_driver_definitions()

    # Filter to only required drivers
    required_drivers = [
        (manifest, driver_class)
        for manifest, driver_class in all_drivers
        if manifest.id in required_ids
    ]

    if len(required_drivers) < len(required_ids):
        registered_ids = {m.id for m, _ in required_drivers}
        missing = set(required_ids) - registered_ids
        logger.warning(f"Missing required drivers: {missing}")

    # Register required drivers
    for manifest, driver_class in required_drivers:
        try:
            await registry.register_driver(manifest, driver_class)
            logger.info(f"Registered required driver: {manifest.id}")
        except Exception as e:
            logger.error(f"Failed to register required driver {manifest.id}: {e}")
            raise RuntimeError(
                f"Required driver {manifest.id} failed to initialize"
            ) from e

    logger.info(
        f"Required driver initialization complete: {len(required_drivers)} drivers"
    )


def configure_drivers_for_environment():
    """
    Configure driver settings based on the deployment environment.

    This function sets appropriate configuration values for drivers
    based on whether we're running locally or in the cloud.
    """
    mode = os.getenv("LIGHTNING_MODE", "local")

    if mode == "local":
        # Local development settings
        logger.info("Configuring drivers for local development")

        # Use local endpoints and mock services where appropriate
        os.environ.setdefault("CONTEXT_HUB_ENDPOINT", "http://localhost:8000")
        os.environ.setdefault("ENABLE_EXAMPLE_DRIVERS", "true")
        os.environ.setdefault("USE_MOCK_EXTERNAL_SERVICES", "true")

    elif mode == "azure":
        # Azure production settings
        logger.info("Configuring drivers for Azure deployment")

        # Use Azure services
        os.environ.setdefault("CONTEXT_HUB_ENDPOINT", os.getenv("CONTEXT_HUB_URL", ""))
        os.environ.setdefault("ENABLE_EXAMPLE_DRIVERS", "false")
        os.environ.setdefault("USE_MOCK_EXTERNAL_SERVICES", "false")

    else:
        logger.warning(f"Unknown mode: {mode}, using default configuration")


# Driver health check functionality
async def check_driver_health() -> Dict[str, Any]:
    """
    Check the health of all registered drivers.

    Returns:
        Dictionary with health status of each driver
    """
    registry = get_driver_registry()
    health_status = {}

    for driver_id in registry._drivers:
        try:
            driver = await registry.get_driver(driver_id)
            # Most drivers don't have a health check method yet
            # This is a placeholder for future implementation
            health_status[driver_id] = {"status": "healthy", "active": True}
        except Exception as e:
            health_status[driver_id] = {
                "status": "unhealthy",
                "error": str(e),
                "active": False,
            }

    return health_status
