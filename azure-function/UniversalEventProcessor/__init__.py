"""
Universal Event Processor - Azure Functions Adapter

This adapter bridges Azure Functions with the Lightning Core serverless abstraction,
allowing the same event processing logic to run both locally and in Azure.
"""

import json
import logging
import os
import sys
from datetime import datetime

import azure.functions as func

# Add core directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "core"))

# Import the abstracted event processor
from lightning_core.vextir_os.serverless_processor import universal_event_processor_handler
from lightning_core.abstractions.serverless import FunctionContext, TriggerType


# Configure logging
logging.basicConfig(level=os.getenv("LOGGING_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


async def main(msg: func.ServiceBusMessage) -> None:
    """
    Azure Functions adapter for universal event processor.
    
    This function receives Service Bus messages and processes them through
    the Lightning Core universal event processor using the serverless abstraction.
    """
    invocation_start = datetime.utcnow()
    
    try:
        # Parse message body
        body = msg.get_body().decode("utf-8")
        event_data = json.loads(body)
        
        # Create function context from Azure Functions message
        context = FunctionContext(
            function_name="UniversalEventProcessor",
            invocation_id=msg.message_id or f"azure-{invocation_start.timestamp()}",
            trigger_type=TriggerType.QUEUE,
            trigger_data=event_data,
            environment=dict(os.environ),
            metadata={
                "azure_message_id": msg.message_id,
                "azure_enqueued_time": msg.enqueued_time_utc.isoformat() if msg.enqueued_time_utc else None,
                "azure_delivery_count": msg.delivery_count,
                "azure_session_id": msg.session_id,
                "azure_correlation_id": msg.correlation_id,
                "source": "azure_service_bus"
            }
        )
        
        # Log invocation details
        logger.info(f"Azure Function invoked - ID: {context.invocation_id}")
        logger.info(f"Processing event type: {event_data.get('type', 'unknown')}")
        logger.info(f"User ID: {event_data.get('userID', 'unknown')}")
        
        # Process through unified handler
        response = await universal_event_processor_handler(context)
        
        # Log response
        if response.is_error:
            logger.error(f"Processing failed - Status: {response.status_code}")
            logger.error(f"Error: {response.error_message or response.body}")
            
            # For Azure Functions, we need to raise an exception to trigger retry/dead-letter
            error_msg = response.error_message or "Event processing failed"
            raise Exception(error_msg)
        else:
            logger.info(f"Processing succeeded - Status: {response.status_code}")
            
            # Log output events if available
            if isinstance(response.body, dict):
                output_count = response.body.get("output_count", 0)
                if output_count > 0:
                    logger.info(f"Generated {output_count} output events")
        
        # Calculate processing time
        processing_time = (datetime.utcnow() - invocation_start).total_seconds()
        logger.info(f"Processing completed in {processing_time:.2f} seconds")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse message body: {e}")
        logger.error(f"Raw message: {body[:500]}...")  # Log first 500 chars
        raise
    except Exception as e:
        logger.error(f"Error in Azure Function adapter: {e}", exc_info=True)
        raise


# Alternative HTTP trigger for testing/debugging
async def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger endpoint for testing the event processor.
    
    This allows invoking the processor via HTTP for debugging purposes.
    """
    try:
        # Get request body
        req_body = req.get_json()
        
        # Create function context
        context = FunctionContext(
            function_name="UniversalEventProcessor-HTTP",
            invocation_id=f"http-{datetime.utcnow().timestamp()}",
            trigger_type=TriggerType.HTTP,
            trigger_data=req_body,
            environment=dict(os.environ),
            metadata={
                "http_method": req.method,
                "http_url": req.url,
                "http_headers": dict(req.headers),
                "source": "http_trigger"
            }
        )
        
        # Process event
        response = await universal_event_processor_handler(context)
        
        # Return HTTP response
        return func.HttpResponse(
            body=json.dumps(response.body),
            status_code=response.status_code,
            headers=response.headers,
            mimetype="application/json"
        )
        
    except ValueError:
        return func.HttpResponse(
            body=json.dumps({"error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception as e:
        logger.error(f"Error in HTTP trigger: {e}", exc_info=True)
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )