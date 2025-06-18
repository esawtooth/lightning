#!/usr/bin/env python3
"""
Deploy Voice Agent containers to Azure
"""
import subprocess
import json
import time
import os

def run_command(cmd, check=True):
    """Run a command and return the result"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        raise Exception(f"Command failed: {cmd}")
    return result

def main():
    # Configuration
    resource_group = "vextir-dev"
    registry_name = "vextirregistry"
    location = "eastus"
    
    # Container names
    webapp_image = f"{registry_name}.azurecr.io/voice-agent-webapp:latest"
    websocket_image = f"{registry_name}.azurecr.io/voice-agent-websocket:latest"
    
    print("🚀 Starting Voice Agent deployment to Azure...")
    
    # Step 1: Create Azure Container Registry if it doesn't exist
    print("\n📦 Setting up Azure Container Registry...")
    try:
        run_command(f"az acr show --name {registry_name} --resource-group {resource_group}")
        print("✅ Container Registry already exists")
    except:
        print("Creating new Container Registry...")
        run_command(f"az acr create --resource-group {resource_group} --name {registry_name} --sku Basic --location {location}")
    
    # Step 2: Enable admin access
    print("\n🔑 Enabling admin access...")
    run_command(f"az acr update -n {registry_name} --admin-enabled true")
    
    # Step 3: Login to ACR
    print("\n🔐 Logging into Container Registry...")
    run_command(f"az acr login --name {registry_name}")
    
    # Step 4: Build and push webapp container using ACR build
    print("\n🏗️ Building and pushing webapp container using ACR build...")
    run_command(f"az acr build --registry {registry_name} --image voice-agent-webapp:latest agents/voice-agent/webapp")
    
    # Step 5: Build and push websocket server container using ACR build
    print("\n🏗️ Building and pushing websocket server container using ACR build...")
    run_command(f"az acr build --registry {registry_name} --image voice-agent-websocket:latest agents/voice-agent/websocket-server")
    
    # Step 6: Get ACR credentials
    print("\n🔑 Getting ACR credentials...")
    creds_result = run_command(f"az acr credential show --name {registry_name}")
    creds = json.loads(creds_result.stdout)
    acr_username = creds['username']
    acr_password = creds['passwords'][0]['value']
    
    # Step 7: Deploy websocket server container instance
    print("\n🚀 Deploying websocket server...")
    websocket_env_vars = [
        f"OPENAI_API_KEY=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",
        f"COSMOS_CONNECTION=AccountEndpoint=https://vextir-cosmos-dev.documents.azure.com:443/;AccountKey=GbG0UJx1RfJczNERQkM4nq9Jp2xVtK4otxUH55baJgWiz895zeKJ2RnQeBBWdtzOyZMjRcHqnIAJACDb20hrxQ==;",
        f"COSMOS_DATABASE=vextir",
        f"USER_CONTAINER=users",
        f"CALL_CONTAINER=calls",
        f"TWILIO_ACCOUNT_SID=ACd1e6491be8c11d2ee9235ceb70e3d648",
        f"TWILIO_AUTH_TOKEN=7d620ddd0d76e2d5c0e3b1e33c89965e",
        f"TWILIO_FROM_NUMBER=+18106743049"
    ]
    
    # Create websocket container
    websocket_cmd = f"""az container create \\
        --resource-group {resource_group} \\
        --name voice-agent-websocket \\
        --image {websocket_image} \\
        --registry-login-server {registry_name}.azurecr.io \\
        --registry-username {acr_username} \\
        --registry-password {acr_password} \\
        --dns-name-label voice-agent-websocket-{int(time.time())} \\
        --ports 8081 \\
        --environment-variables {' '.join(websocket_env_vars)} \\
        --cpu 1 \\
        --memory 1.5"""
    
    run_command(websocket_cmd)
    
    # Get websocket server URL
    print("\n🔍 Getting websocket server URL...")
    websocket_result = run_command(f"az container show --resource-group {resource_group} --name voice-agent-websocket --query ipAddress.fqdn --output tsv")
    websocket_fqdn = websocket_result.stdout.strip()
    websocket_url = f"https://{websocket_fqdn}:8081"
    
    print(f"✅ Websocket server deployed at: {websocket_url}")
    
    # Step 8: Deploy webapp container instance
    print("\n🚀 Deploying webapp...")
    webapp_env_vars = [
        f"TWILIO_ACCOUNT_SID=ACd1e6491be8c11d2ee9235ceb70e3d648",
        f"TWILIO_AUTH_TOKEN=7d620ddd0d76e2d5c0e3b1e33c89965e",
        f"TWILIO_FROM_NUMBER=+18106743049",
        f"PUBLIC_URL={websocket_url}/voice-ws"
    ]
    
    webapp_cmd = f"""az container create \\
        --resource-group {resource_group} \\
        --name voice-agent-webapp \\
        --image {webapp_image} \\
        --registry-login-server {registry_name}.azurecr.io \\
        --registry-username {acr_username} \\
        --registry-password {acr_password} \\
        --dns-name-label voice-agent-webapp-{int(time.time())} \\
        --ports 3000 \\
        --environment-variables {' '.join(webapp_env_vars)} \\
        --cpu 1 \\
        --memory 1.5"""
    
    run_command(webapp_cmd)
    
    # Get webapp URL
    print("\n🔍 Getting webapp URL...")
    webapp_result = run_command(f"az container show --resource-group {resource_group} --name voice-agent-webapp --query ipAddress.fqdn --output tsv")
    webapp_fqdn = webapp_result.stdout.strip()
    webapp_url = f"http://{webapp_fqdn}:3000"
    
    print(f"\n🎉 Deployment Complete!")
    print(f"📱 Webapp URL: {webapp_url}")
    print(f"🔌 Websocket Server URL: {websocket_url}")
    print(f"\n📞 You can now configure Twilio to use the websocket URL for voice calls!")
    
    # Update environment files with the deployed URLs
    print("\n📝 Updating environment files...")
    
    # Update websocket server .env
    with open('agents/voice-agent/websocket-server/.env', 'r') as f:
        websocket_env = f.read()
    
    websocket_env = websocket_env.replace(
        'PUBLIC_URL="https://placeholder-will-update-with-ngrok.ngrok-free.app/voice-ws"',
        f'PUBLIC_URL="{websocket_url}/voice-ws"'
    )
    
    with open('agents/voice-agent/websocket-server/.env', 'w') as f:
        f.write(websocket_env)
    
    # Update webapp .env
    with open('agents/voice-agent/webapp/.env', 'r') as f:
        webapp_env = f.read()
    
    webapp_env = webapp_env.replace(
        'PUBLIC_URL="https://placeholder-will-update-with-ngrok.ngrok-free.app/voice-ws"',
        f'PUBLIC_URL="{websocket_url}/voice-ws"'
    )
    
    with open('agents/voice-agent/webapp/.env', 'w') as f:
        f.write(webapp_env)
    
    print("✅ Environment files updated!")

if __name__ == "__main__":
    main()
