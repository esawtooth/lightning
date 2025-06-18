"""
Serverless-compatible universal event processor.

This module provides a universal event processor that works with
the serverless abstraction, allowing it to run both locally and
in cloud serverless environments (Azure Functions, AWS Lambda, etc.).
"""

import logging
import os
from typing import Any, Dict, Optional

from lightning_core.abstractions.serverless import (
    FunctionContext,
    FunctionResponse,
    TriggerType,
)

from .driver_initialization import initialize_all_drivers
from .universal_processor import get_universal_processor, process_event_message

logger = logging.getLogger(__name__)


# Track initialization state
_initialized = False


async def universal_event_processor_handler(
    context: FunctionContext,
) -> FunctionResponse:
    """
    Universal event processor handler that works with serverless abstraction.

    This handler can be deployed to any serverless platform through the
    Lightning Core abstraction layer.

    Args:
        context: Serverless function context containing trigger data

    Returns:
        FunctionResponse with processing results
    """
    global _initialized

    try:
        # Initialize drivers on first invocation
        if not _initialized:
            logger.info("Initializing drivers for universal event processor")
            await initialize_all_drivers()
            _initialized = True
            logger.info("Driver initialization complete")

        # Extract event data based on trigger type
        event_data = _extract_event_data(context)

        if not event_data:
            return FunctionResponse(
                status_code=400,
                body={"error": "No event data found in context"},
                is_error=True,
                error_message="Missing event data",
            )

        logger.info(
            f"Processing event: {event_data.get('type', 'unknown')} for user {event_data.get('userID', 'unknown')}"
        )

        # Process through universal processor
        result = await process_event_message(event_data)

        # Log results
        if result["status"] == "success":
            logger.info(
                f"Successfully processed event, generated {result.get('output_count', 0)} output events"
            )

            # Log driver results if available
            if "driver_results" in result:
                for driver_id, driver_result in result["driver_results"].items():
                    if driver_result.get("handled", False):
                        output_count = len(driver_result.get("output_events", []))
                        logger.info(
                            f"Driver {driver_id} handled event and generated {output_count} output events"
                        )
        else:
            logger.error(
                f"Failed to process event: {result.get('error', 'unknown error')}"
            )

        # Build response
        return FunctionResponse(
            status_code=200 if result["status"] == "success" else 500,
            body=result,
            headers={
                "Content-Type": "application/json",
                "X-Function-Name": context.function_name,
                "X-Invocation-ID": context.invocation_id,
            },
            is_error=result["status"] != "success",
            error_message=result.get("error"),
            logs=[f"Processed event type: {event_data.get('type', 'unknown')}"],
        )

    except Exception as e:
        logger.error(f"Error in universal event processor: {e}", exc_info=True)

        return FunctionResponse(
            status_code=500,
            body={"status": "error", "error": str(e), "error_type": type(e).__name__},
            is_error=True,
            error_message=str(e),
            logs=[f"Fatal error: {e}"],
        )


def _extract_event_data(context: FunctionContext) -> Optional[Dict[str, Any]]:
    """
    Extract event data from function context based on trigger type.

    Args:
        context: Function context

    Returns:
        Event data dictionary or None if not found
    """
    trigger_data = context.trigger_data

    if context.trigger_type == TriggerType.EVENT:
        # Direct event trigger - data should be in trigger_data
        return trigger_data.get("data") or trigger_data

    elif context.trigger_type == TriggerType.QUEUE:
        # Queue trigger (Service Bus, SQS, etc.)
        # Data might be wrapped in a message envelope
        if "body" in trigger_data:
            return trigger_data["body"]
        elif "data" in trigger_data:
            return trigger_data["data"]
        else:
            return trigger_data

    elif context.trigger_type == TriggerType.HTTP:
        # HTTP trigger - look for body
        if "body" in trigger_data:
            return trigger_data["body"]
        else:
            return trigger_data

    elif context.trigger_type == TriggerType.TIMER:
        # Timer trigger - might have scheduled event data
        return trigger_data.get("scheduled_event") or trigger_data

    else:
        # Unknown trigger type - return raw data
        logger.warning(f"Unknown trigger type: {context.trigger_type}")
        return trigger_data


async def create_test_handler():
    """
    Create a test handler for local development.

    Returns a simplified handler that logs events without full processing.
    """

    async def test_handler(context: FunctionContext) -> FunctionResponse:
        """Test handler that simply logs and echoes events."""
        event_data = _extract_event_data(context)

        logger.info(f"Test handler received event: {event_data}")

        return FunctionResponse(
            status_code=200,
            body={
                "status": "success",
                "message": "Test handler processed event",
                "received_data": event_data,
                "context": {
                    "function_name": context.function_name,
                    "invocation_id": context.invocation_id,
                    "trigger_type": context.trigger_type.value,
                },
            },
        )

    return test_handler


# Configuration for deployment
FUNCTION_CONFIG = {
    "name": "universal-event-processor",
    "handler": "universal_event_processor_handler",
    "runtime": "python",
    "memory_mb": 512,
    "timeout_seconds": 300,
    "environment_variables": {
        "LOGGING_LEVEL": os.getenv("LOGGING_LEVEL", "INFO"),
        "COSMOS_CONNECTION_STRING": os.getenv("COSMOS_CONNECTION_STRING", ""),
        "SERVICE_BUS_CONNECTION_STRING": os.getenv("SERVICE_BUS_CONNECTION_STRING", ""),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
    },
    "triggers": [
        {
            "type": "queue",
            "queue_name": os.getenv("SERVICE_BUS_QUEUE_NAME", "vextir-events"),
            "connection": "SERVICE_BUS_CONNECTION_STRING",
        }
    ],
}
