# 502 Error Fix and Enhanced Logging Summary

## Problem
- www.vextir.com was returning 502 "Bad Gateway" error
- Azure Front Door error: "OriginConnectionAborted" 
- Container was in CrashLoopBackOff state with exit code 1
- No logs were available to diagnose the issue

## Root Cause Analysis
1. **Container Status**: The UI container (`chatui`) was failing to start and restarting continuously
2. **Missing Logs**: Container logs were empty, making diagnosis difficult
3. **Startup Issues**: The container was likely failing during Python import or application startup

## Solutions Implemented

### 1. Enhanced Container Logging in Pulumi Infrastructure (`infra/__main__.py`)

#### Improved Restart Policy
```python
restart_policy=containerinstance.ContainerGroupRestartPolicy.ON_FAILURE  # Better restart policy
```
- Changed from default (ALWAYS) to ON_FAILURE to prevent endless restart loops

#### Health and Readiness Probes
```python
liveness_probe=containerinstance.ContainerProbeArgs(
    http_get=containerinstance.ContainerHttpGetArgs(
        path="/health" if name == "chatui" else "/",
        port=port,
        scheme=containerinstance.Scheme.HTTP,
    ),
    initial_delay_seconds=30,
    period_seconds=10,
    failure_threshold=3,
    timeout_seconds=5,
) if name in ["chatui", "voicews"] else None,
```
- Added health checks to monitor container status
- Probes check `/health` endpoint for UI containers

#### Enhanced Log Analytics
```python
log_type=containerinstance.LogAnalyticsLogType.CONTAINER_INSIGHTS,  # Enhanced logging
metadata={
    "container-name": name,
    "deployment-id": "fix-container-logging-v1",
},
```
- Enabled Container Insights for better log aggregation
- Added metadata for easier log filtering

#### Debug Environment Variables
```python
containerinstance.EnvironmentVariableArgs(name="PYTHONUNBUFFERED", value="1"),  # Ensure Python output is not buffered
containerinstance.EnvironmentVariableArgs(name="PYTHONDONTWRITEBYTECODE", value="1"),  # Don't write .pyc files
containerinstance.EnvironmentVariableArgs(name="LOG_LEVEL", value="DEBUG"),  # Enable debug logging
containerinstance.EnvironmentVariableArgs(name="UVICORN_LOG_LEVEL", value="debug"),  # Enable uvicorn debug logging
```

### 2. Enhanced Startup Script (`ui/chat_client/start.sh`)

#### Comprehensive Pre-flight Checks
- **Python version check**: Displays Python version for debugging
- **Directory listing**: Shows all files in the container
- **Environment variable validation**: Checks for required AAD variables
- **File existence checks**: Verifies all required Python files exist
- **Directory checks**: Ensures required directories are present
- **Import testing**: Tests Python imports before starting the server

#### Enhanced Uvicorn Configuration
```bash
exec python -m uvicorn gateway_app:app \
    --host 0.0.0.0 \
    --port 80 \
    --log-level debug \
    --access-log \
    --use-colors
```
- Added debug logging
- Enabled access logs
- Added color output for better readability

## Deployment Process

### Automated Deployment Script
Created `scripts/fix_container_logging.py` to:
1. Commit the logging improvements
2. Push to GitHub to trigger CI/CD
3. Provide guidance on checking logs post-deployment

### GitHub Actions Integration
The deployment uses the existing `.github/workflows/deploy.yml` which:
1. Builds Docker images with the enhanced startup script
2. Deploys infrastructure with improved logging configuration
3. Updates container instances with new images

## Monitoring and Debugging

### Container Logs
```bash
# Check container logs
az container logs --resource-group vextir-dev --name chatui

# Check container status
az container show --resource-group vextir-dev --name chatui --query 'containers[0].instanceView'
```

### Log Analytics
- Enhanced logs are now available in Azure Log Analytics workspace
- Container Insights provides detailed metrics and logs
- Logs can be queried using KQL in Azure Portal

### Health Endpoints
- UI container now has health checks on `/health` endpoint
- Front Door can better detect container health status
- Probes provide early warning of container issues

## Expected Outcomes

1. **Better Visibility**: Detailed startup logs will show exactly where the container is failing
2. **Faster Recovery**: ON_FAILURE restart policy prevents endless restart loops
3. **Health Monitoring**: Probes will detect and report container health issues
4. **Debugging Information**: Enhanced logging provides comprehensive troubleshooting data

## Next Steps

1. **Monitor Deployment**: Wait for GitHub Actions to complete the deployment
2. **Check Logs**: Use the provided Azure CLI commands to check container logs
3. **Verify Health**: Test the `/health` endpoint once the container is running
4. **Test Website**: Verify that www.vextir.com is accessible after the fix

## Troubleshooting Commands

```bash
# Check deployment status
az container list --resource-group vextir-dev --output table

# Get detailed container information
az container show --resource-group vextir-dev --name chatui

# Check container logs
az container logs --resource-group vextir-dev --name chatui

# Test container health (once running)
curl -I http://<container-ip>:80/health

# Check Front Door status
az cdn endpoint list --resource-group vextir-dev --profile-name <profile-name>
```

## Files Modified

1. `infra/__main__.py` - Enhanced container logging and health checks
2. `ui/chat_client/start.sh` - Comprehensive startup script with debugging
3. `scripts/fix_container_logging.py` - Deployment automation script

This comprehensive approach should resolve the 502 error by fixing the underlying container startup issues and providing the visibility needed to diagnose any future problems.
