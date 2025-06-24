#!/usr/bin/env python3
"""
Debug Azure Front Door 502 Bad Gateway Error for vextir.com
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(msg: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{msg}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")


def print_info(msg: str):
    print(f"{Colors.OKBLUE}ℹ️  {msg}{Colors.ENDC}")


def print_success(msg: str):
    print(f"{Colors.OKGREEN}✅ {msg}{Colors.ENDC}")


def print_warning(msg: str):
    print(f"{Colors.WARNING}⚠️  {msg}{Colors.ENDC}")


def print_error(msg: str):
    print(f"{Colors.FAIL}❌ {msg}{Colors.ENDC}")


def run_az_command(cmd: str, parse_json: bool = True) -> Optional[Dict]:
    """Run Azure CLI command and return JSON output"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=True
        )
        if parse_json and result.stdout:
            return json.loads(result.stdout)
        return {"stdout": result.stdout, "stderr": result.stderr}
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {cmd}")
        print_error(f"Error: {e.stderr}")
        return None
    except json.JSONDecodeError as e:
        print_error(f"Failed to parse JSON: {e}")
        return {"stdout": result.stdout}


def check_azure_login():
    """Check if Azure CLI is logged in"""
    print_header("Checking Azure CLI Login")
    result = run_az_command("az account show")
    if result:
        print_success(f"Logged in to subscription: {result.get('name', 'Unknown')}")
        return True
    else:
        print_error("Not logged in to Azure CLI")
        print_info("Please run: az login")
        return False


def get_resource_group_info():
    """Get resource group information"""
    print_header("Resource Group Information")
    rg_name = "vextir-dev"
    
    result = run_az_command(f"az group show --name {rg_name}")
    if result:
        print_success(f"Resource group '{rg_name}' exists in {result.get('location', 'Unknown')}")
        return rg_name
    else:
        print_error(f"Resource group '{rg_name}' not found")
        return None


def check_front_door_status(rg_name: str):
    """Check Azure Front Door status and configuration"""
    print_header("Azure Front Door Status")
    
    profile_name = "vextir-fd-dev"
    endpoint_name = "vextir-ep-dev"
    
    # Check profile
    profile = run_az_command(f"az afd profile show -g {rg_name} --profile-name {profile_name}")
    if not profile:
        print_error("Front Door profile not found")
        return
    
    print_success(f"Front Door profile exists: {profile_name}")
    print_info(f"State: {profile.get('enabledState', 'Unknown')}")
    
    # Check endpoint
    endpoint = run_az_command(f"az afd endpoint show -g {rg_name} --profile-name {profile_name} --endpoint-name {endpoint_name}")
    if endpoint:
        print_success(f"Endpoint exists: {endpoint_name}")
        print_info(f"Hostname: {endpoint.get('hostName', 'Unknown')}")
        print_info(f"Enabled State: {endpoint.get('enabledState', 'Unknown')}")
        
        if endpoint.get('enabledState') != 'Enabled':
            print_warning("Endpoint is not enabled!")
    
    # Check origin groups
    print("\n📡 Origin Groups:")
    origin_groups = run_az_command(f"az afd origin-group list -g {rg_name} --profile-name {profile_name}")
    
    if origin_groups:
        for og in origin_groups:
            og_name = og.get('name', 'Unknown')
            print(f"\n  Origin Group: {Colors.BOLD}{og_name}{Colors.ENDC}")
            
            # Get origin group details
            og_details = run_az_command(f"az afd origin-group show -g {rg_name} --profile-name {profile_name} --origin-group-name {og_name}")
            if og_details:
                health_probe = og_details.get('healthProbeSettings', {})
                print(f"    Probe Path: {health_probe.get('probePath', 'N/A')}")
                print(f"    Probe Protocol: {health_probe.get('probeProtocol', 'N/A')}")
                print(f"    Probe Interval: {health_probe.get('probeIntervalInSeconds', 'N/A')}s")
            
            # Get origins in this group
            origins = run_az_command(f"az afd origin list -g {rg_name} --profile-name {profile_name} --origin-group-name {og_name}")
            if origins:
                for origin in origins:
                    print(f"\n    Origin: {origin.get('name', 'Unknown')}")
                    print(f"      Hostname: {origin.get('hostName', 'Unknown')}")
                    print(f"      Enabled: {origin.get('enabledState', 'Unknown')}")
                    print(f"      HTTP Port: {origin.get('httpPort', 'N/A')}")
                    print(f"      HTTPS Port: {origin.get('httpsPort', 'N/A')}")
                    print(f"      Priority: {origin.get('priority', 'N/A')}")
                    print(f"      Weight: {origin.get('weight', 'N/A')}")
                    
                    # Check origin health
                    if og_name and origin.get('name'):
                        health = check_origin_health(rg_name, profile_name, og_name, origin.get('name'))
                        if health:
                            print(f"      Health: {health}")


def check_origin_health(rg_name: str, profile_name: str, og_name: str, origin_name: str) -> str:
    """Check health of a specific origin"""
    # Note: This requires additional permissions and may not be available in all scenarios
    try:
        result = run_az_command(
            f"az afd origin show -g {rg_name} --profile-name {profile_name} "
            f"--origin-group-name {og_name} --origin-name {origin_name}"
        )
        if result:
            return result.get('originHostHeader', 'Unknown')
    except:
        pass
    return "Unable to determine"


def check_container_instances(rg_name: str):
    """Check Azure Container Instances status"""
    print_header("Container Instances Status")
    
    containers = run_az_command(f"az container list -g {rg_name}")
    if not containers:
        print_error("No container instances found")
        return
    
    for container in containers:
        name = container.get('name', 'Unknown')
        print(f"\n🐳 Container: {Colors.BOLD}{name}{Colors.ENDC}")
        
        # Get detailed info
        details = run_az_command(f"az container show -g {rg_name} --name {name}")
        if details:
            # Basic info
            state = details.get('instanceView', {}).get('state', 'Unknown')
            print(f"  State: {state}")
            
            # IP Address
            ip_address = details.get('ipAddress')
            if ip_address:
                if ip_address.get('type') == 'Public':
                    print(f"  Public IP: {ip_address.get('ip', 'N/A')}")
                    print(f"  FQDN: {ip_address.get('fqdn', 'N/A')}")
                else:
                    print(f"  Private IP: {ip_address.get('ip', 'N/A')}")
            else:
                print(f"  No IP address assigned")
            
            # Containers
            containers_info = details.get('containers', [])
            for cont in containers_info:
                cont_name = cont.get('name', 'Unknown')
                instance_view = cont.get('instanceView', {})
                current_state = instance_view.get('currentState', {})
                
                print(f"\n  Container Instance: {cont_name}")
                print(f"    State: {current_state.get('state', 'Unknown')}")
                print(f"    Start Time: {current_state.get('startTime', 'N/A')}")
                
                # Check if container is crashing
                if current_state.get('state') == 'Terminated':
                    print_warning(f"    Exit Code: {current_state.get('exitCode', 'N/A')}")
                    print_warning(f"    Message: {current_state.get('detailStatus', 'N/A')}")
                
                # Previous state (if exists)
                previous_state = instance_view.get('previousState', {})
                if previous_state:
                    print_warning(f"    Previous State: {previous_state.get('state', 'Unknown')}")
                    print_warning(f"    Previous Exit Code: {previous_state.get('exitCode', 'N/A')}")
                
                # Restart count
                restart_count = instance_view.get('restartCount', 0)
                if restart_count > 0:
                    print_warning(f"    Restart Count: {restart_count}")
            
            # Get recent logs
            print(f"\n  Recent Logs for {name}:")
            logs = run_az_command(f"az container logs -g {rg_name} --name {name}", parse_json=False)
            if logs and logs.get('stdout'):
                log_lines = logs['stdout'].strip().split('\n')
                for line in log_lines[-20:]:  # Last 20 lines
                    print(f"    {line}")


def check_function_app(rg_name: str):
    """Check Function App status"""
    print_header("Function App Status")
    
    # List function apps
    func_apps = run_az_command(f"az functionapp list -g {rg_name}")
    if not func_apps:
        print_error("No function apps found")
        return
    
    for app in func_apps:
        name = app.get('name', 'Unknown')
        print(f"\n⚡ Function App: {Colors.BOLD}{name}{Colors.ENDC}")
        print(f"  State: {app.get('state', 'Unknown')}")
        print(f"  Default Hostname: {app.get('defaultHostName', 'Unknown')}")
        print(f"  Enabled: {app.get('enabled', 'Unknown')}")
        
        # Check if running
        if app.get('state') != 'Running':
            print_warning("  Function app is not running!")
        
        # Get app settings (without secrets)
        print("\n  Key Configuration:")
        settings = run_az_command(f"az functionapp config appsettings list -g {rg_name} --name {name}")
        if settings:
            important_settings = [
                'FUNCTIONS_WORKER_RUNTIME',
                'FUNCTIONS_EXTENSION_VERSION',
                'WEBSITE_RUN_FROM_PACKAGE',
                'COSMOS_DATABASE',
                'USER_CONTAINER',
                'HUB_URL',
                'CONSEIL_URL'
            ]
            for setting in settings:
                if setting.get('name') in important_settings:
                    value = setting.get('value', 'N/A')
                    if 'KEY' in setting.get('name', '') or 'SECRET' in setting.get('name', ''):
                        value = '***'
                    print(f"    {setting.get('name')}: {value}")


def check_dns_records(domain: str = "vextir.com"):
    """Check DNS records"""
    print_header(f"DNS Records for {domain}")
    
    # Check DNS zone
    zones = run_az_command("az network dns zone list")
    if not zones:
        print_error("No DNS zones found")
        return
    
    zone = next((z for z in zones if z.get('name') == domain), None)
    if not zone:
        print_error(f"DNS zone for {domain} not found")
        return
    
    rg_name = zone.get('resourceGroup')
    print_success(f"DNS zone exists in resource group: {rg_name}")
    
    # Check specific records
    subdomains = ['www', 'api', 'voice-ws', 'hub']
    
    for subdomain in subdomains:
        print(f"\n📍 Checking {subdomain}.{domain}:")
        
        # Check CNAME record
        cname = run_az_command(f"az network dns record-set cname show -g {rg_name} -z {domain} -n {subdomain}", parse_json=True)
        if cname:
            target = cname.get('cnameRecord', {}).get('cname', 'Unknown')
            print_success(f"  CNAME: {target}")
        else:
            print_error(f"  No CNAME record found")
        
        # Check TXT records for validation
        txt = run_az_command(f"az network dns record-set txt show -g {rg_name} -z {domain} -n _dnsauth.{subdomain}", parse_json=True)
        if txt:
            print_success(f"  Validation TXT record exists")


def test_endpoints():
    """Test actual endpoint connectivity"""
    print_header("Endpoint Connectivity Tests")
    
    endpoints = [
        ("https://www.vextir.com/health", "UI Health Check"),
        ("https://api.vextir.com/api/health", "API Health Check"),
        ("https://hub.vextir.com/health", "Context Hub Health Check"),
        ("https://voice-ws.vextir.com/health", "Voice WebSocket Health Check")
    ]
    
    for url, description in endpoints:
        print(f"\n🔍 Testing: {description}")
        print(f"   URL: {url}")
        
        # Use curl to test
        curl_cmd = f"curl -s -o /dev/null -w '%{{http_code}} - %{{time_total}}s' -H 'Cache-Control: no-cache' {url}"
        result = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            output = result.stdout.strip()
            if output.startswith('200'):
                print_success(f"   Response: {output}")
            elif output.startswith('502'):
                print_error(f"   Response: {output} - Bad Gateway!")
            else:
                print_warning(f"   Response: {output}")
        else:
            print_error(f"   Failed to connect")
        
        # Get detailed error with verbose curl
        print("   Detailed trace:")
        trace_cmd = f"curl -sv --max-time 10 {url} 2>&1 | grep -E '(< HTTP|< |> Host:|x-azure-ref)' | head -10"
        trace_result = subprocess.run(trace_cmd, shell=True, capture_output=True, text=True)
        if trace_result.stdout:
            for line in trace_result.stdout.strip().split('\n'):
                print(f"     {line}")


def check_recent_deployments(rg_name: str):
    """Check recent deployment history"""
    print_header("Recent Deployments")
    
    # Get deployments from the last 24 hours
    deployments = run_az_command(f"az deployment group list -g {rg_name}")
    if not deployments:
        print_warning("No deployments found")
        return
    
    # Sort by timestamp and show recent ones
    recent = sorted(deployments, key=lambda x: x.get('properties', {}).get('timestamp', ''), reverse=True)[:5]
    
    for deployment in recent:
        name = deployment.get('name', 'Unknown')
        props = deployment.get('properties', {})
        timestamp = props.get('timestamp', 'Unknown')
        state = props.get('provisioningState', 'Unknown')
        
        print(f"\n📋 Deployment: {name}")
        print(f"   Timestamp: {timestamp}")
        print(f"   State: {state}")
        
        if state != 'Succeeded':
            print_warning(f"   Deployment did not succeed!")


def generate_fix_commands(rg_name: str):
    """Generate commands to potentially fix the issue"""
    print_header("Potential Fix Commands")
    
    print("\n1️⃣  Restart Container Instances:")
    containers = ['chatui', 'contexthub', 'voicews', 'conseil']
    for container in containers:
        print(f"   az container restart -g {rg_name} --name {container}")
    
    print("\n2️⃣  Enable/Refresh Front Door Endpoint:")
    print(f"   az afd endpoint update -g {rg_name} --profile-name vextir-fd-dev --endpoint-name vextir-ep-dev --enabled-state Enabled")
    
    print("\n3️⃣  Purge Front Door Cache:")
    print(f"   az afd endpoint purge -g {rg_name} --profile-name vextir-fd-dev --endpoint-name vextir-ep-dev --content-paths '/*'")
    
    print("\n4️⃣  Check Container Logs:")
    for container in containers:
        print(f"   az container logs -g {rg_name} --name {container}")
    
    print("\n5️⃣  Update Container Images (if needed):")
    print("   Run the GitHub Actions workflow to rebuild and deploy latest images")
    
    print("\n6️⃣  Check Front Door origin health probes:")
    print(f"   az afd origin-group show -g {rg_name} --profile-name vextir-fd-dev --origin-group-name ui")


def main():
    """Main debugging function"""
    print(f"{Colors.BOLD}{Colors.HEADER}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║         Azure Front Door 502 Debug Tool for vextir.com    ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")
    
    # Check Azure login
    if not check_azure_login():
        return
    
    # Get resource group
    rg_name = get_resource_group_info()
    if not rg_name:
        return
    
    # Run all checks
    check_front_door_status(rg_name)
    check_container_instances(rg_name)
    check_function_app(rg_name)
    check_dns_records()
    test_endpoints()
    check_recent_deployments(rg_name)
    
    # Generate fix commands
    generate_fix_commands(rg_name)
    
    print(f"\n{Colors.BOLD}Debug completed!{Colors.ENDC}")
    print("\nNext steps:")
    print("1. Review the container logs for any errors")
    print("2. Check if containers are running and healthy")
    print("3. Verify Front Door origin configurations match container endpoints")
    print("4. Try the suggested fix commands if issues are found")


if __name__ == "__main__":
    main()
