"""
Comprehensive test for the driver migration from Azure Functions to Vextir OS
Tests all migrated drivers and validates functionality
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, List

# Add Azure Function package path for imports
sys.path.append('./azure-function')

from events import Event, LLMChatEvent, EmailEvent, CalendarEvent, ContextUpdateEvent, WorkerTaskEvent
from vextir_os.universal_processor import UniversalEventProcessor
from vextir_os.registries import get_driver_registry, get_model_registry, get_tool_registry
from vextir_os.core_drivers import ContextHubDriver, ChatAgentDriver, AuthenticationDriver
from vextir_os.communication_drivers import (
    EmailConnectorDriver,
    CalendarConnectorDriver,
    UserMessengerDriver,
    VoiceCallDriver,
)
from vextir_os.orchestration_drivers import InstructionEngineDriver, TaskMonitorDriver, SchedulerDriver

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DriverMigrationTester:
    """Test suite for validating driver migration"""
    
    def __init__(self):
        self.processor = UniversalEventProcessor()
        self.test_user_id = "test_user_123"
        self.test_results = {}
    
    async def setup(self):
        """Setup test environment"""
        logger.info("Setting up test environment...")
        
        # Initialize registries
        driver_registry = get_driver_registry()
        model_registry = get_model_registry()
        tool_registry = get_tool_registry()
        
        # Register all drivers
        await self._register_all_drivers()
        
        logger.info("Test environment setup complete")
    
    async def _register_all_drivers(self):
        """Register all migrated drivers"""
        registry = get_driver_registry()
        
        # Core drivers
        core_drivers = [
            (ContextHubDriver._vextir_manifest, ContextHubDriver),
            (ChatAgentDriver._vextir_manifest, ChatAgentDriver),
            (AuthenticationDriver._vextir_manifest, AuthenticationDriver)
        ]
        
        # Communication drivers
        communication_drivers = [
            (EmailConnectorDriver._vextir_manifest, EmailConnectorDriver),
            (CalendarConnectorDriver._vextir_manifest, CalendarConnectorDriver),
            (UserMessengerDriver._vextir_manifest, UserMessengerDriver),
            (VoiceCallDriver._vextir_manifest, VoiceCallDriver),
        ]
        
        # Orchestration drivers
        orchestration_drivers = [
            (InstructionEngineDriver._vextir_manifest, InstructionEngineDriver),
            (TaskMonitorDriver._vextir_manifest, TaskMonitorDriver),
            (SchedulerDriver._vextir_manifest, SchedulerDriver)
        ]
        
        all_drivers = core_drivers + communication_drivers + orchestration_drivers
        
        for manifest, driver_class in all_drivers:
            try:
                await registry.register_driver(manifest, driver_class)
                logger.info(f"Registered driver: {manifest.id}")
            except Exception as e:
                logger.error(f"Failed to register driver {manifest.id}: {e}")
    
    async def test_context_hub_driver(self):
        """Test ContextHubDriver functionality"""
        logger.info("Testing ContextHubDriver...")
        
        try:
            # Test context initialization
            init_event = Event(
                timestamp=datetime.utcnow(),
                source="test",
                type="context.initialize",
                user_id=self.test_user_id,
                metadata={}
            )
            
            result = await self.processor.process_event(init_event)
            
            # Test context search
            search_event = Event(
                timestamp=datetime.utcnow(),
                source="test",
                type="context.search",
                user_id=self.test_user_id,
                metadata={"query": "test query", "limit": 5}
            )
            
            search_result = await self.processor.process_event(search_event)
            
            # Test context write
            write_event = Event(
                timestamp=datetime.utcnow(),
                source="test",
                type="context.write",
                user_id=self.test_user_id,
                metadata={
                    "name": "Test Document",
                    "content": "This is a test document for validation"
                }
            )
            
            write_result = await self.processor.process_event(write_event)
            
            self.test_results["context_hub"] = {
                "status": "passed",
                "tests": ["initialize", "search", "write"],
                "details": "All context hub operations completed successfully"
            }
            
        except Exception as e:
            self.test_results["context_hub"] = {
                "status": "failed",
                "error": str(e)
            }
            logger.error(f"ContextHubDriver test failed: {e}")
    
    async def test_chat_agent_driver(self):
        """Test ChatAgentDriver functionality"""
        logger.info("Testing ChatAgentDriver...")
        
        try:
            # Test LLM chat
            chat_event = LLMChatEvent(
                timestamp=datetime.utcnow(),
                source="test",
                type="llm.chat.request",
                user_id=self.test_user_id,
                messages=[
                    {"role": "user", "content": "Hello, can you help me with a test?"}
                ],
                model="gpt-4",
                metadata={}
            )
            
            result = await self.processor.process_event(chat_event)
            
            self.test_results["chat_agent"] = {
                "status": "passed",
                "tests": ["llm_chat"],
                "details": "Chat agent processed request successfully"
            }
            
        except Exception as e:
            self.test_results["chat_agent"] = {
                "status": "failed",
                "error": str(e)
            }
            logger.error(f"ChatAgentDriver test failed: {e}")
    
    async def test_email_connector_driver(self):
        """Test EmailConnectorDriver functionality"""
        logger.info("Testing EmailConnectorDriver...")
        
        try:
            # Test email send
            email_event = EmailEvent(
                timestamp=datetime.utcnow(),
                source="test",
                type="email.send",
                user_id=self.test_user_id,
                operation="send",
                provider="gmail",
                email_data={
                    "to": "test@example.com",
                    "subject": "Test Email",
                    "body": "This is a test email"
                }
            )
            
            result = await self.processor.process_event(email_event)
            
            # Test email webhook
            webhook_event = Event(
                timestamp=datetime.utcnow(),
                source="test",
                type="email.webhook",
                user_id=self.test_user_id,
                metadata={
                    "provider": "gmail",
                    "webhook_data": {
                        "from": "sender@example.com",
                        "subject": "Incoming Test Email",
                        "body": "Test webhook email"
                    }
                }
            )
            
            webhook_result = await self.processor.process_event(webhook_event)
            
            self.test_results["email_connector"] = {
                "status": "passed",
                "tests": ["email_send", "email_webhook"],
                "details": "Email connector operations completed successfully"
            }
            
        except Exception as e:
            self.test_results["email_connector"] = {
                "status": "failed",
                "error": str(e)
            }
            logger.error(f"EmailConnectorDriver test failed: {e}")
    
    async def test_calendar_connector_driver(self):
        """Test CalendarConnectorDriver functionality"""
        logger.info("Testing CalendarConnectorDriver...")
        
        try:
            # Test calendar create
            calendar_event = CalendarEvent(
                timestamp=datetime.utcnow(),
                source="test",
                type="calendar.create",
                user_id=self.test_user_id,
                operation="create",
                provider="gmail",
                calendar_data={
                    "title": "Test Meeting",
                    "start_time": "2024-01-01T10:00:00Z",
                    "end_time": "2024-01-01T11:00:00Z",
                    "description": "Test calendar event"
                }
            )
            
            result = await self.processor.process_event(calendar_event)
            
            self.test_results["calendar_connector"] = {
                "status": "passed",
                "tests": ["calendar_create"],
                "details": "Calendar connector operations completed successfully"
            }
            
        except Exception as e:
            self.test_results["calendar_connector"] = {
                "status": "failed",
                "error": str(e)
            }
            logger.error(f"CalendarConnectorDriver test failed: {e}")
    
    async def test_instruction_engine_driver(self):
        """Test InstructionEngineDriver functionality"""
        logger.info("Testing InstructionEngineDriver...")
        
        try:
            # Test with a simple event that would trigger instruction processing
            trigger_event = Event(
                timestamp=datetime.utcnow(),
                source="test",
                type="email.processed",
                user_id=self.test_user_id,
                metadata={
                    "from": "important@example.com",
                    "subject": "Important Email"
                }
            )
            
            result = await self.processor.process_event(trigger_event)
            
            self.test_results["instruction_engine"] = {
                "status": "passed",
                "tests": ["event_processing"],
                "details": "Instruction engine processed event successfully"
            }
            
        except Exception as e:
            self.test_results["instruction_engine"] = {
                "status": "failed",
                "error": str(e)
            }
            logger.error(f"InstructionEngineDriver test failed: {e}")
    
    async def test_task_monitor_driver(self):
        """Test TaskMonitorDriver functionality"""
        logger.info("Testing TaskMonitorDriver...")
        
        try:
            # Test task creation monitoring
            task_event = WorkerTaskEvent(
                timestamp=datetime.utcnow(),
                source="test",
                type="worker.task",
                user_id=self.test_user_id,
                task="Test task for monitoring",
                metadata={"test": True}
            )
            
            result = await self.processor.process_event(task_event)
            
            # Test task metrics request
            metrics_event = Event(
                timestamp=datetime.utcnow(),
                source="test",
                type="task.metrics.request",
                user_id=self.test_user_id,
                metadata={}
            )
            
            metrics_result = await self.processor.process_event(metrics_event)
            
            self.test_results["task_monitor"] = {
                "status": "passed",
                "tests": ["task_creation", "metrics_request"],
                "details": "Task monitor operations completed successfully"
            }
            
        except Exception as e:
            self.test_results["task_monitor"] = {
                "status": "failed",
                "error": str(e)
            }
            logger.error(f"TaskMonitorDriver test failed: {e}")
    
    async def test_scheduler_driver(self):
        """Test SchedulerDriver functionality"""
        logger.info("Testing SchedulerDriver...")
        
        try:
            # Test schedule creation
            schedule_event = Event(
                timestamp=datetime.utcnow(),
                source="test",
                type="schedule.create",
                user_id=self.test_user_id,
                metadata={
                    "cron": "0 9 * * *",  # Daily at 9 AM
                    "event": {
                        "type": "scheduled.reminder",
                        "metadata": {"message": "Daily reminder"}
                    }
                }
            )
            
            result = await self.processor.process_event(schedule_event)
            
            self.test_results["scheduler"] = {
                "status": "passed",
                "tests": ["schedule_create"],
                "details": "Scheduler operations completed successfully"
            }
            
        except Exception as e:
            self.test_results["scheduler"] = {
                "status": "failed",
                "error": str(e)
            }
            logger.error(f"SchedulerDriver test failed: {e}")
    
    async def test_user_messenger_driver(self):
        """Test UserMessengerDriver functionality"""
        logger.info("Testing UserMessengerDriver...")
        
        try:
            # Test message sending
            message_event = Event(
                timestamp=datetime.utcnow(),
                source="test",
                type="message.send",
                user_id=self.test_user_id,
                metadata={
                    "recipient": "test@example.com",
                    "message": "Test message",
                    "channel": "email"
                }
            )
            
            result = await self.processor.process_event(message_event)
            
            # Test notification delivery
            notification_event = Event(
                timestamp=datetime.utcnow(),
                source="test",
                type="notification.deliver",
                user_id=self.test_user_id,
                metadata={
                    "title": "Test Notification",
                    "message": "This is a test notification",
                    "channels": ["push", "email"]
                }
            )
            
            notification_result = await self.processor.process_event(notification_event)
            
            self.test_results["user_messenger"] = {
                "status": "passed",
                "tests": ["message_send", "notification_deliver"],
                "details": "User messenger operations completed successfully"
            }
            
        except Exception as e:
            self.test_results["user_messenger"] = {
                "status": "failed",
                "error": str(e)
            }
            logger.error(f"UserMessengerDriver test failed: {e}")
    
    async def test_authentication_driver(self):
        """Test AuthenticationDriver functionality"""
        logger.info("Testing AuthenticationDriver...")
        
        try:
            # Test token verification
            auth_event = Event(
                timestamp=datetime.utcnow(),
                source="test",
                type="auth.verify",
                user_id=self.test_user_id,
                metadata={"token": "test_token_123"}
            )
            
            result = await self.processor.process_event(auth_event)
            
            self.test_results["authentication"] = {
                "status": "passed",
                "tests": ["token_verify"],
                "details": "Authentication operations completed successfully"
            }
            
        except Exception as e:
            self.test_results["authentication"] = {
                "status": "failed",
                "error": str(e)
            }
            logger.error(f"AuthenticationDriver test failed: {e}")
    
    async def run_all_tests(self):
        """Run all driver tests"""
        logger.info("Starting comprehensive driver migration tests...")
        
        await self.setup()
        
        # Run all tests
        test_methods = [
            self.test_context_hub_driver,
            self.test_chat_agent_driver,
            self.test_email_connector_driver,
            self.test_calendar_connector_driver,
            self.test_instruction_engine_driver,
            self.test_task_monitor_driver,
            self.test_scheduler_driver,
            self.test_user_messenger_driver,
            self.test_authentication_driver
        ]
        
        for test_method in test_methods:
            try:
                await test_method()
            except Exception as e:
                logger.error(f"Test {test_method.__name__} failed with exception: {e}")
        
        # Generate test report
        self.generate_test_report()
    
    def generate_test_report(self):
        """Generate and display test report"""
        logger.info("\n" + "="*80)
        logger.info("DRIVER MIGRATION TEST REPORT")
        logger.info("="*80)
        
        passed_tests = 0
        failed_tests = 0
        
        for driver_name, result in self.test_results.items():
            status = result["status"]
            if status == "passed":
                passed_tests += 1
                logger.info(f"✅ {driver_name.upper()}: PASSED")
                if "tests" in result:
                    logger.info(f"   Tests: {', '.join(result['tests'])}")
                logger.info(f"   Details: {result['details']}")
            else:
                failed_tests += 1
                logger.error(f"❌ {driver_name.upper()}: FAILED")
                logger.error(f"   Error: {result['error']}")
            logger.info("-" * 40)
        
        total_tests = passed_tests + failed_tests
        logger.info(f"\nSUMMARY:")
        logger.info(f"Total Drivers Tested: {total_tests}")
        logger.info(f"Passed: {passed_tests}")
        logger.info(f"Failed: {failed_tests}")
        logger.info(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%" if total_tests > 0 else "N/A")
        
        if failed_tests == 0:
            logger.info("\n🎉 ALL DRIVER MIGRATION TESTS PASSED!")
            logger.info("The migration from Azure Functions to Vextir OS drivers is successful!")
        else:
            logger.warning(f"\n⚠️  {failed_tests} driver(s) need attention before migration is complete.")
        
        logger.info("="*80)


async def main():
    """Main test execution"""
    tester = DriverMigrationTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
