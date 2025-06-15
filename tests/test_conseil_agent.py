#!/usr/bin/env python3
"""
Test script for the Conseil Agent capabilities:
1. Use bash to accomplish tasks
2. Access and use context hub
3. Have web search tools
4. Queue up events in the service bus
"""

import os
import sys
import json
import subprocess
from pathlib import Path
import pytest

# Add agents directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "agents"))

from agents import AGENT_REGISTRY

def test_bash_execution():
    """Test 1: Use bash to accomplish tasks"""
    print("🔧 Testing bash execution capabilities...")
    
    # Test if conseil agent can execute bash commands
    conseil_agent = AGENT_REGISTRY.get("conseil")
    if not conseil_agent:
        print("❌ Conseil agent not found in registry")
        return False
    
    try:
        # Test simple bash command through conseil
        result = conseil_agent.run("echo 'Hello from conseil agent'")
        print(f"✅ Bash execution test: {result.strip()}")
        return True
    except Exception as e:
        print(f"❌ Bash execution failed: {e}")
        return False

def test_context_hub_access():
    """Test 2: Access and use context hub"""
    print("\n📚 Testing context hub access...")
    
    conseil_agent = AGENT_REGISTRY.get("conseil")
    if not conseil_agent:
        print("❌ Conseil agent not found")
        return False
    
    try:
        # Test context hub CLI access
        hub_result = conseil_agent.hub("pwd")
        print(f"✅ Context hub working directory: {hub_result.strip()}")
        
        # Test listing context hub contents
        ls_result = conseil_agent.hub("ls")
        print(f"✅ Context hub contents: {ls_result.strip()}")
        
        return True
    except Exception as e:
        print(f"❌ Context hub access failed: {e}")
        return False

def test_web_search_tools():
    """Test 3: Have web search tools"""
    print("\n🔍 Testing web search capabilities...")
    
    # Check if web search utilities are available
    web_search_path = Path("web_search.py")
    get_url_path = Path("get_url.py")
    
    if not web_search_path.exists():
        print("❌ web_search.py utility not found")
        return False
    
    if not get_url_path.exists():
        print("❌ get_url.py utility not found")
        return False
    
    # Check if firecrawl dependency is available
    try:
        import subprocess
        result = subprocess.run([sys.executable, "-c", "import firecrawl"], 
                               capture_output=True, text=True)
        if result.returncode != 0:
            print("⚠️ firecrawl-py package not installed, installing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "firecrawl-py"], 
                          check=True)
    except Exception as e:
        print(f"❌ Failed to install firecrawl dependency: {e}")
        return False
    
    print("✅ Web search utilities are available")
    print("✅ firecrawl dependency is ready")
    
    # Note: We won't actually make web requests in this test to avoid API usage
    print("ℹ️ Web search functionality ready (skipping actual API calls)")
    return True

def test_service_bus_events():
    """Test 4: Queue up events in the service bus"""
    print("\n📨 Testing service bus event queuing...")
    
    # Check if Azure Service Bus integration is available
    try:
        # Look for service bus related code
        azure_function_path = Path("azure-function")
        events_path = Path("events")
        
        if not azure_function_path.exists():
            print("❌ Azure function directory not found")
            return False
        
        if not events_path.exists():
            print("❌ Events directory not found")
            return False
        
        # Check for service bus configuration in infrastructure
        infra_path = Path("infra/__main__.py")
        if infra_path.exists():
            with open(infra_path, 'r') as f:
                content = f.read()
                if "servicebus" in content.lower():
                    print("✅ Service Bus infrastructure configured")
                else:
                    print("❌ Service Bus not found in infrastructure")
                    return False
        
        print("✅ Service Bus event system is available")
        print("ℹ️ Event queuing capability ready (would require deployment to test fully)")
        return True
        
    except Exception as e:
        print(f"❌ Service bus test failed: {e}")
        return False

def test_conseil_agent_integration():
    """Test the full conseil agent integration"""
    print("\n🤖 Testing full conseil agent integration...")
    
    conseil_agent = AGENT_REGISTRY.get("conseil")
    if not conseil_agent:
        print("❌ Conseil agent not found in registry")
        return False

    try:
        # Test that the conseil CLI is accessible
        result = subprocess.run(["conseil", "--help"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Conseil CLI is accessible")
        else:
            print("❌ Conseil CLI not accessible")
            return False
        
        # Test OpenAI API key availability (needed for conseil)
        if not os.getenv("OPENAI_API_KEY"):
            print("⚠️ OPENAI_API_KEY not set - conseil will require API key")
        else:
            print("✅ OpenAI API key is configured")
        
        print("✅ Conseil agent integration is ready")
        return True
        
    except Exception as e:
        print(f"❌ Conseil agent integration test failed: {e}")
        return False


def test_conseil_error_handling(monkeypatch):
    """Ensure errors from conseil are returned as strings."""
    conseil_agent = AGENT_REGISTRY.get("conseil")
    assert conseil_agent is not None

    def fake_run(cmd, capture_output=False, text=False):
        return subprocess.CompletedProcess(cmd, 1, stdout="out", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = conseil_agent.run("bad")
    assert "boom" in result

def main():
    """Run all tests for the conseil agent"""
    print("🧪 Testing Conseil Agent Capabilities")
    print("=" * 50)
    
    tests = [
        test_bash_execution,
        test_context_hub_access,
        test_web_search_tools,
        test_service_bus_events,
        test_conseil_agent_integration,
        test_conseil_error_handling,
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test_func.__name__} failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    print(f"✅ Passed: {sum(results)}/{len(results)}")
    print(f"❌ Failed: {len(results) - sum(results)}/{len(results)}")
    
    if all(results):
        print("\n🎉 All conseil agent capabilities are working!")
        return 0
    else:
        print("\n⚠️ Some capabilities need attention")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 