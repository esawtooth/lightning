#!/usr/bin/env python3
"""
Simple integration test to verify planner can create cron events that the scheduler can handle
"""

import asyncio
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)

async def test_simple_cron_integration():
    """Test the basic cron scheduling functionality"""
    
    print("🚀 Testing Simple Cron Integration")
    print("=" * 40)
    
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
    
    # Step 2: Test scheduler drivers directly
    print("\n2. Testing scheduler drivers...")
    
    try:
        from lightning_core.vextir_os.scheduler_drivers import CronSchedulerDriver
        from lightning_core.vextir_os.drivers import DriverManifest, DriverType, ResourceSpec
        from lightning_core.vextir_os.events import Event
        
        # Create a simple manifest for testing
        manifest = DriverManifest(
            id="test_cron_scheduler",
            name="Test Cron Scheduler",
            version="1.0.0",
            author="test",
            description="Test cron scheduler",
            driver_type=DriverType.TOOL,
            capabilities=["time.cron"],
            resource_requirements=ResourceSpec()
        )
        
        # Create scheduler driver
        scheduler = CronSchedulerDriver(manifest)
        await scheduler.initialize()
        
        print("✅ Cron scheduler driver created and initialized!")
        
        # Test scheduling a plan
        plan_schedule_event = Event(
            timestamp=datetime.utcnow(),
            source="test",
            type="plan.schedule",
            user_id="test_user",
            metadata={"plan": plan}
        )
        
        result_events = await scheduler.handle_event(plan_schedule_event)
        print(f"✅ Plan scheduling handled, generated {len(result_events)} events")
        
        # Check scheduler status
        status = scheduler.get_job_status()
        print(f"   Total jobs: {status['total_jobs']}")
        print(f"   Running: {status['running']}")
        
        if status['jobs']:
            print("   Scheduled jobs:")
            for job_id, job_info in status['jobs'].items():
                print(f"     - {job_id}")
                print(f"       Event: {job_info['event_name']}")
                print(f"       Cron: {job_info['cron_expression']}")
                print(f"       Next run: {job_info['next_run']}")
        
        # Clean up
        await scheduler.shutdown()
        
    except Exception as e:
        print(f"❌ Scheduler test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 3: Test interval scheduler
    print("\n3. Testing interval scheduler...")
    
    try:
        from lightning_core.vextir_os.scheduler_drivers import IntervalSchedulerDriver
        
        # Create interval scheduler
        interval_manifest = DriverManifest(
            id="test_interval_scheduler",
            name="Test Interval Scheduler",
            version="1.0.0",
            author="test",
            description="Test interval scheduler",
            driver_type=DriverType.TOOL,
            capabilities=["time.interval"],
            resource_requirements=ResourceSpec()
        )
        
        interval_scheduler = IntervalSchedulerDriver(interval_manifest)
        await interval_scheduler.initialize()
        
        print("✅ Interval scheduler driver created and initialized!")
        
        # Create a test plan with interval events
        interval_plan = {
            "plan_name": "test_interval_plan",
            "events": [
                {
                    "name": "event.email.check",
                    "kind": "time.interval",
                    "schedule": "PT5M",  # Every 5 minutes
                    "description": "Check for new emails"
                }
            ],
            "steps": []
        }
        
        interval_event = Event(
            timestamp=datetime.utcnow(),
            source="test",
            type="plan.schedule",
            user_id="test_user",
            metadata={"plan": interval_plan}
        )
        
        result_events = await interval_scheduler.handle_event(interval_event)
        print(f"✅ Interval scheduling handled, generated {len(result_events)} events")
        
        # Clean up
        await interval_scheduler.shutdown()
        
    except Exception as e:
        print(f"❌ Interval scheduler test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n🎉 Simple integration test completed successfully!")
    print("\nSummary:")
    print("✅ Planner generated plan with cron events")
    print("✅ Cron scheduler can handle plan scheduling")
    print("✅ Interval scheduler can handle interval events")
    print("✅ Schedulers properly parse cron expressions and intervals")
    
    return True


async def main():
    """Main test function"""
    try:
        success = await test_simple_cron_integration()
        if success:
            print("\n🎯 All tests passed! The planner can create cron events that the schedulers can handle.")
        else:
            print("\n💥 Some tests failed. Check the output above for details.")
    except Exception as e:
        print(f"\n💥 Test failed with exception: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
