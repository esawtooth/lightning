"""
Universal Event Processor - Core Vextir OS event processing function
Enhanced to work with all migrated drivers
"""

import json
import logging
import os
import sys
from datetime import datetime

import azure.functions as func

# Add the parent directory to the path to import vextir_os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vextir_os.universal_processor import process_event_message
from vextir_os.registries import get_driver_registry
from vextir_os.core_drivers import ContextHubDriver, ChatAgentDriver, AuthenticationDriver
from vextir_os.communication_drivers import EmailConnectorDriver, CalendarConnectorDriver, UserMessengerDriver
from vextir_os.orchestration_drivers import InstructionEngineDriver, TaskMonitorDriver, SchedulerDriver
from simple_auth import get_user_id_permissive


async def initialize_drivers():
    """Initialize all drivers for the system"""
    registry = get_driver_registry()
    
    # Register core drivers
    core_drivers = [
        (ContextHubDriver._vextir_manifest, ContextHubDriver),
        (ChatAgentDriver._vextir_manifest, ChatAgentDriver),
        (AuthenticationDriver._vextir_manifest, AuthenticationDriver)
    ]
    
    # Register communication drivers
    communication_drivers = [
        (EmailConnectorDriver._vextir_manifest, EmailConnectorDriver),
        (CalendarConnectorDriver._vextir_manifest, CalendarConnectorDriver),
        (UserMessengerDriver._vextir_manifest, UserMessengerDriver)
    ]
    
    # Register orchestration drivers
    orchestration_drivers = [
        (InstructionEngineDriver._vextir_manifest, InstructionEngineDriver),
        (TaskMonitorDriver._vextir_manifest, TaskMonitorDriver),
        (SchedulerDriver._vextir_manifest, SchedulerDriver)
    ]
    
    all_drivers = core_drivers + communication_drivers + orchestration_drivers
    
    for manifest, driver_class in all_drivers:
        try:
            await registry.register_driver(manifest, driver_class)
            logging.info(f"Registered driver: {manifest.id}")
        except Exception as e:
            logging.error(f"Failed to register driver {manifest.id}: {e}")
    
    logging.info(f"Initialized {len(all_drivers)} drivers")


# Global flag to track initialization
_drivers_initialized = False


async def main(msg: func.ServiceBusMessage) -> None:
    """Main handler for universal event processing"""
    
    global _drivers_initialized
    
    try:
        # Initialize drivers on first run
        if not _drivers_initialized:
            await initialize_drivers()
            _drivers_initialized = True
        
        # Parse message body
        body = msg.get_body().decode("utf-8")
        event_data = json.loads(body)
        
        logging.info(f"Processing event: {event_data.get('type', 'unknown')} for user {event_data.get('userID', 'unknown')}")
        
        # Process through universal processor with all drivers available
        result = await process_event_message(event_data)
        
        if result["status"] == "success":
            logging.info(f"Successfully processed event, generated {result['output_count']} output events")
            
            # Log which drivers handled the event
            if "driver_results" in result:
                for driver_id, driver_result in result["driver_results"].items():
                    if driver_result.get("handled", False):
                        logging.info(f"Driver {driver_id} handled event and generated {len(driver_result.get('output_events', []))} output events")
        else:
            logging.error(f"Failed to process event: {result.get('error', 'unknown error')}")
            
    except Exception as e:
        logging.error(f"Error in universal event processor: {e}")
        raise
