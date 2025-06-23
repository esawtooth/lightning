#!/usr/bin/env python3
"""
Integration demo script to test the Planner-VextirOS integration.
"""

import json
import sys
from pathlib import Path

def test_unified_tool_registry():
    """Test the unified tool registry system"""
    print("🔧 Testing Unified Tool Registry...")
    
    try:
        from lightning_core.tools import get_tool_registry, ToolSpec, ToolType
        
        # Get the registry
        registry = get_tool_registry()
        
        # List all tools
        tools = registry.list_tools()
        print(f"   Found {len(tools)} tools in unified registry")
        
        # Test planner format
        planner_tools = registry.get_planner_registry()
        print(f"   Planner format: {len(planner_tools)} tools")
        
        # Test VextirOS format
        vextir_tools = registry.get_vextir_tools()
        print(f"   VextirOS format: {len(vextir_tools)} tools")
        
        # Test capability filtering
        email_tools = registry.list_tools(capability="email_send")
        print(f"   Email tools: {len(email_tools)}")
        
        print("   ✅ Unified Tool Registry: PASS")
        return True
        
    except Exception as e:
        print(f"   ❌ Unified Tool Registry: FAIL - {e}")
        return False


def test_plan_execution_events():
    """Test plan execution event creation"""
    print("📋 Testing Plan Execution Events...")
    
    try:
        from lightning_core.planner.planner import execute_plan, setup_plan
        
        # Create a simple test plan
        test_plan = {
            "plan_name": "test-integration-plan",
            "graph_type": "acyclic",
            "events": [
                {"name": "event.test.trigger", "description": "Test trigger event"}
            ],
            "steps": [
                {
                    "name": "test_step",
                    "on": ["event.test.trigger"],
                    "action": "llm.summarize",
                    "args": {"text": "Test text", "style": "brief"},
                    "emits": ["event.test.complete"]
                }
            ]
        }
        
        # Save test plan
        test_plan_path = Path("test_plan.json")
        test_plan_path.write_text(json.dumps(test_plan, indent=2))
        
        # Test setup event creation
        setup_event = setup_plan(test_plan_path, "test_user")
        print(f"   Setup event type: {setup_event['type']}")
        print(f"   Setup event user: {setup_event['user_id']}")
        
        # Test execution event creation
        exec_event = execute_plan(test_plan_path, "test_user")
        print(f"   Execution event type: {exec_event['type']}")
        print(f"   Execution event user: {exec_event['user_id']}")
        
        # Cleanup
        test_plan_path.unlink()
        
        print("   ✅ Plan Execution Events: PASS")
        return True
        
    except Exception as e:
        print(f"   ❌ Plan Execution Events: FAIL - {e}")
        return False


def test_plan_validation():
    """Test the enhanced plan validation system"""
    print("🔍 Testing Plan Validation...")
    
    try:
        from lightning_core.planner.validator import run_validations_parallel
        
        # Create a valid test plan
        valid_plan = {
            "plan_name": "validation-test-plan",
            "graph_type": "acyclic",
            "events": [
                {"name": "event.test.start", "description": "Test start event"}
            ],
            "steps": [
                {
                    "name": "validation_step",
                    "on": ["event.test.start"],
                    "action": "llm.summarize",
                    "args": {"text": "Test validation", "style": "brief"},
                    "emits": ["event.test.done"]
                }
            ]
        }
        
        # Run parallel validation
        results = run_validations_parallel(valid_plan, max_workers=2)
        
        passed = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        print(f"   Validation results: {len(passed)}/{len(results)} passed")
        
        for result in failed:
            print(f"   ❌ {result.validator_name}: {result.error_message}")
        
        if len(failed) == 0:
            print("   ✅ Plan Validation: PASS")
            return True
        else:
            print("   ⚠️  Plan Validation: PARTIAL - Some validators failed")
            return False
        
    except Exception as e:
        print(f"   ❌ Plan Validation: FAIL - {e}")
        return False


def test_event_registry_integration():
    """Test event registry integration"""
    print("📅 Testing Event Registry Integration...")
    
    try:
        from lightning_core.events import EventRegistry
        
        # Test getting external events
        external_events = EventRegistry.get_external_events()
        print(f"   Found {len(external_events)} external events")
        
        # Test legacy compatibility
        from lightning_core.planner.registry import EventRegistry as LegacyEventRegistry
        legacy_events = dict(LegacyEventRegistry)
        print(f"   Legacy format: {len(legacy_events)} events")
        
        print("   ✅ Event Registry Integration: PASS")
        return True
        
    except Exception as e:
        print(f"   ❌ Event Registry Integration: FAIL - {e}")
        return False


def test_vextir_drivers():
    """Test VextirOS driver creation"""
    print("🚀 Testing VextirOS Drivers...")
    
    try:
        from lightning_core.vextir_os.plan_execution_drivers import (
            PlanExecutorDriver, PlanStepExecutorDriver
        )
        from lightning_core.vextir_os.drivers import DriverManifest, DriverType
        
        # Create driver manifests
        plan_manifest = DriverManifest(
            id="test_plan_executor",
            name="Test Plan Executor",
            description="Test plan executor driver",
            driver_type=DriverType.TOOL,
            capabilities=["plan.execute", "plan.setup"]
        )
        
        step_manifest = DriverManifest(
            id="test_step_executor", 
            name="Test Step Executor",
            description="Test step executor driver",
            driver_type=DriverType.TOOL,
            capabilities=["plan.step.execute"]
        )
        
        # Create driver instances
        plan_driver = PlanExecutorDriver(plan_manifest)
        step_driver = PlanStepExecutorDriver(step_manifest)
        
        print(f"   Plan driver capabilities: {plan_driver.get_capabilities()}")
        print(f"   Step driver capabilities: {step_driver.get_capabilities()}")
        
        print("   ✅ VextirOS Drivers: PASS")
        return True
        
    except Exception as e:
        print(f"   ❌ VextirOS Drivers: FAIL - {e}")
        return False


def main():
    """Run integration tests"""
    print("🧪 Lightning Core Integration Test Suite")
    print("=" * 50)
    
    tests = [
        test_unified_tool_registry,
        test_event_registry_integration,
        test_plan_validation,
        test_plan_execution_events,
        test_vextir_drivers
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"   💥 Test failed with exception: {e}")
            results.append(False)
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("📊 Test Summary")
    print("=" * 50)
    print(f"Passed: {passed}/{total}")
    print(f"Success Rate: {passed/total*100:.1f}%")
    
    if passed == total:
        print("🎉 All integration tests PASSED!")
        return 0
    else:
        print("⚠️  Some integration tests FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
