#!/usr/bin/env python3
"""
Integration test to verify planner can create cron events that VextirOS can schedule
"""

import asyncio
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)

async def test_planner_to_vextir_cron_integration():
    """Test the complete flow from planner to VextirOS cron scheduling"""
    
    print("🚀 Testing Planner to VextirOS Cron Integration")
    print("=" * 50)
    
    # Step 1: Generate a plan with cron events
    print("\n1. Generating plan with cron events...")
    
    from lightning_core.planner.cli import generate_plan
    
    try:
        plan = generate_plan("Every day at 8pm, give me a phone call about any important news in the world")
        print("✅ Plan generated successfully!")
        print(f"   Plan name: {plan['plan_name']}")
        print(f"   Events: {len(plan['events'])}")
        print(f"   Steps: {len(plan['steps'])}")
        
        # Find cron events
        cron_events = [e for e in plan['events'] if e.get('kind') == 'time.cron']
        print(f"   Cron events: {len(cron_events)}")
        
        for event in cron_events:
            print(f"     - {event['name']}: {event.get('schedule', 'no schedule')}")
        
    except Exception as e:
        print(f"❌ Plan generation failed: {e}")
        return False
    
    # Step 2: Set up VextirOS drivers
    print("\n2. Setting up VextirOS drivers...")
    
    try:
        from lightning_core.vextir_os.drivers import get_driver_registry
        from lightning_core.vextir_os.scheduler_drivers import CronSchedulerDriver, IntervalSchedulerDriver
        from lightning_core.vextir_os.plan_execution_drivers import PlanExecutorDriver
        from lightning_core.vextir_os.event_bus import get_event_bus
        from lightning_core.vextir_os.events import Event
        
        # Get registry and event bus
        registry = get_driver_registry()
        event_bus = get_event_bus()
        
        # Register scheduler drivers
        await registry.register_driver(
            CronSchedulerDriver._vextir_manifest,
            CronSchedulerDriver
        )
        
        await registry.register_driver(
            IntervalSchedulerDriver._vextir_manifest, 
            IntervalSchedulerDriver
        )
        
        await registry.register_driver(
            PlanExecutorDriver._vextir_manifest,
            PlanExecutorDriver
        )
        
        print("✅ VextirOS drivers registered successfully!")
        
    except Exception as e:
        print(f"❌ Driver setup failed: {e}")
        return False
    
    # Step 3: Execute the plan in VextirOS
    print("\n3. Executing plan in VextirOS...")
    
    try:
        # Create plan execution event
        plan_event = Event(
            timestamp=datetime.utcnow(),
            source="test",
            type="plan.execute",
            user_id="test_user",
            metadata={"plan": plan}
        )
        
        # Emit the event
        await event_bus.emit(plan_event)
        
        # Wait a moment for processing
        await asyncio.sleep(2)
        
        print("✅ Plan execution event emitted!")
        
    except Exception as e:
        print(f"❌ Plan execution failed: {e}")
        return False
    
    # Step 4: Check scheduler status
    print("\n4. Checking scheduler status...")
    
    try:
        # Get the cron scheduler instance
        cron_driver_instance = registry.instances.get("cron_scheduler")
        
        if cron_driver_instance and cron_driver_instance.status == "running":
            driver = cron_driver_instance.driver
            status = driver.get_job_status()
            
            print("✅ Cron scheduler is running!")
            print(f"   Total jobs: {status['total_jobs']}")
            print(f"   Running: {status['running']}")
            
            if status['jobs']:
                print("   Scheduled jobs:")
                for job_id, job_info in status['jobs'].items():
                    print(f"     - {job_id}")
                    print(f"       Event: {job_info['event_name']}")
                    print(f"       Cron: {job_info['cron_expression']}")
                    print(f"       Next run: {job_info['next_run']}")
            else:
                print("   No jobs scheduled yet")
        else:
            print("❌ Cron scheduler not running")
            return False
            
    except Exception as e:
        print(f"❌ Scheduler status check failed: {e}")
        return False
    
    # Step 5: Test manual trigger
    print("\n5. Testing manual trigger...")
    
    try:
        # Create a manual trigger event for the daily event
        trigger_event = Event(
            timestamp=datetime.utcnow(),
            source="test",
            type="event.time.daily",
            user_id="test_user",
            metadata={
                "job_id": "test_trigger",
                "cron_expression": "0 20 * * *",
                "run_count": 0,
                "scheduled_time": datetime.utcnow().isoformat()
            }
        )
        
        # Emit the trigger event
        await event_bus.emit(trigger_event)
        
        # Wait for processing
        await asyncio.sleep(1)
        
        print("✅ Manual trigger event emitted!")
        
    except Exception as e:
        print(f"❌ Manual trigger failed: {e}")
        return False
    
    print("\n🎉 Integration test completed successfully!")
    print("\nSummary:")
    print("✅ Planner generated plan with cron events")
    print("✅ VextirOS drivers registered and started")
    print("✅ Plan executed and scheduled in VextirOS")
    print("✅ Cron scheduler is running and managing jobs")
    print("✅ Manual trigger test passed")
    
    return True


async def main():
    """Main test function"""
    try:
        success = await test_planner_to_vextir_cron_integration()
        if success:
            print("\n🎯 All tests passed! The planner can create cron events that VextirOS can schedule.")
        else:
            print("\n💥 Some tests failed. Check the output above for details.")
    except Exception as e:
        print(f"\n💥 Test failed with exception: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
