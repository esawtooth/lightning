# Container Apps Migration Guide

This guide helps you migrate from Azure Container Instances (ACI) to Azure Container Apps.

## Benefits of Migration

1. **Auto-scaling**: Scale from 0 to N replicas based on HTTP traffic or queue length
2. **Cost Savings**: ~50-70% reduction in costs due to scale-to-zero capability
3. **Simplified Networking**: No need for manual VNet/subnet management for containers
4. **Better Health Management**: Built-in health checks and automatic restarts
5. **Managed HTTPS**: Automatic SSL certificates for all apps

## Key Changes

### Infrastructure Simplifications
- Removed ACI subnet (Container Apps manages its own)
- Simplified networking - only need Container Apps infrastructure subnet
- No manual IP address management
- Built-in service discovery between apps

### Container Apps Features Used
- **External ingress** for UI, Voice, and Hub
- **Internal ingress** for Conseil (only accessible within environment)
- **Scale to zero** for Conseil (saves costs when not in use)
- **Always on** (min_replicas=1) for UI, Voice, and Hub
- **HTTP auto-scaling** for UI based on concurrent requests
- **Managed SSL** for all external endpoints

## Migration Steps

### 1. Review Configuration
Ensure your Pulumi config has all required values:
```bash
pulumi config set openaiApiKey <your-key> --secret
pulumi config set aadClientId <your-client-id> --secret
pulumi config set aadClientSecret <your-client-secret> --secret
pulumi config set aadTenantId <your-tenant-id>
pulumi config set twilioAccountSid <your-sid> --secret
pulumi config set twilioAuthToken <your-token> --secret
```

### 2. Backup Current State
```bash
# Export current stack state
pulumi stack export > aci-backup-$(date +%Y%m%d).json
```

### 3. Deploy Container Apps Infrastructure
```bash
# First, rename the current file to keep as backup
mv infra/__main__.py infra/__main___aci_backup.py

# Use the new Container Apps version
mv infra/__main___container_apps.py infra/__main__.py

# Preview changes
pulumi preview

# Deploy (this will replace ACI with Container Apps)
pulumi up
```

### 4. Verify Deployment
After deployment, verify all services are running:
```bash
# Check Container Apps status
az containerapp list --resource-group vextir-<stack> --output table

# Test endpoints
curl https://www.<your-domain>/health
curl https://hub.<your-domain>/health
curl https://voice-ws.<your-domain>/health
```

### 5. Monitor and Scale
Container Apps provides built-in monitoring:
```bash
# View logs
az containerapp logs show -n chatui-<stack> -g vextir-<stack>

# Check scaling status
az containerapp revision list -n chatui-<stack> -g vextir-<stack>
```

## Cost Comparison

### Before (ACI)
- 4 containers running 24/7
- ~$120/month total

### After (Container Apps)
- UI, Voice, Hub: Scale 1-10 replicas
- Conseil: Scale 0-5 replicas
- ~$40-80/month (depending on usage)

## Rollback Plan

If you need to rollback to ACI:
```bash
# Restore the ACI version
mv infra/__main__.py infra/__main___container_apps.py
mv infra/__main___aci_backup.py infra/__main__.py

# Deploy
pulumi up
```

## Architecture Improvements

1. **Simplified Front Door**: Container Apps provides HTTPS, reducing Front Door complexity
2. **Better Resilience**: Automatic restarts and health-based routing
3. **Easier Updates**: Built-in revision management and traffic splitting
4. **Reduced Complexity**: No manual subnet/IP management

## Next Steps

Consider these additional optimizations:
1. Enable Dapr for service-to-service communication
2. Add KEDA scalers for Service Bus queue-based scaling
3. Implement blue-green deployments with traffic splitting
4. Use Container Apps Jobs for background tasks