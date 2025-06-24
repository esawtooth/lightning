# Azure Front Door 502 Bad Gateway Diagnosis for vextir.com

## Error Details
- **Error Code**: 502 Bad Gateway
- **Error Message**: Azure Front Door wasn't able to connect to the origin
- **Error Info**: OriginConnectionAborted
- **Azure Reference**: 20250623T182958Z-16bcbdc6bd8b9txchC1MAAs8qs0000000h9000000000728d

## Infrastructure Analysis

### 1. Azure Front Door Configuration
Based on the Pulumi infrastructure file, your setup includes:

- **Front Door Profile**: `vextir-fd-dev`
- **Endpoint**: `vextir-ep-dev`
- **Custom Domains**:
  - www.vextir.com → UI container
  - api.vextir.com → Function App
  - hub.vextir.com → Context Hub container
  - voice-ws.vextir.com → Voice WebSocket container

### 2. Origin Configuration Issues

The most likely causes of the 502 error:

1. **Container Health Issues**
   - Containers may have crashed or are not responding to health probes
   - Health probe paths configured:
     - UI: `/health`
     - API: `/api/health`
     - Hub: `/health`
     - Voice: `/health`

2. **Network Configuration**
   - UI container is set to `public=True` but uses HTTP (port 8000)
   - Context Hub is `public=True` but uses HTTP (port 3000)
   - Front Door expects HTTPS but origins use HTTP
   - Host header mismatches between Front Door and container expectations

3. **Container Startup Issues**
   - Containers may be failing to start properly
   - Liveness probe delays: 30-120 seconds
   - Readiness probe delays: 10-60 seconds

### 3. Potential Root Causes

1. **Container Crashes**
   - Check if containers are in a restart loop
   - Review container logs for startup errors

2. **Port Mismatches**
   - UI container expects port 8000
   - Context Hub expects port 3000
   - Voice WebSocket expects port 8081

3. **Environment Variable Issues**
   - Missing or incorrect configuration
   - JWT/Auth configuration problems

4. **Image Pull Issues**
   - ACR authentication problems
   - Wrong image tags after deployment

## Immediate Actions to Take

### 1. Run the Debug Script
```bash
python scripts/debug_frontdoor_502.py
```

This will check:
- Front Door configuration
- Container status and logs
- DNS records
- Endpoint connectivity
- Recent deployments

### 2. Quick Fixes to Try

#### Restart Containers
```bash
az container restart -g vextir-dev --name chatui
az container restart -g vextir-dev --name contexthub
az container restart -g vextir-dev --name voicews
az container restart -g vextir-dev --name conseil
```

#### Enable/Refresh Front Door
```bash
az afd endpoint update -g vextir-dev \
  --profile-name vextir-fd-dev \
  --endpoint-name vextir-ep-dev \
  --enabled-state Enabled
```

#### Purge Front Door Cache
```bash
az afd endpoint purge -g vextir-dev \
  --profile-name vextir-fd-dev \
  --endpoint-name vextir-ep-dev \
  --content-paths '/*'
```

### 3. Check Container Logs

Check each container for errors:
```bash
# UI Container
az container logs -g vextir-dev --name chatui --tail 50

# Context Hub
az container logs -g vextir-dev --name contexthub --tail 50

# Voice WebSocket
az container logs -g vextir-dev --name voicews --tail 50

# Conseil Agent
az container logs -g vextir-dev --name conseil --tail 50
```

### 4. Verify Container Status

Check if containers are running:
```bash
az container show -g vextir-dev --name chatui --query instanceView.state
az container show -g vextir-dev --name contexthub --query instanceView.state
```

### 5. Test Direct Container Access

Test if containers respond directly (bypassing Front Door):
```bash
# Get container FQDNs
az container show -g vextir-dev --name chatui --query ipAddress.fqdn -o tsv
az container show -g vextir-dev --name contexthub --query ipAddress.fqdn -o tsv

# Test direct access
curl -v http://<container-fqdn>:8000/health  # UI
curl -v http://<container-fqdn>:3000/health  # Context Hub
```

## Long-term Solutions

1. **Add Container Monitoring**
   - Enable Application Insights for containers
   - Set up alerts for container restarts

2. **Improve Health Probes**
   - Ensure health endpoints return quickly
   - Add more detailed health checks

3. **Review Container Resources**
   - Current allocation: 1 CPU, 1.5GB RAM
   - Consider increasing if containers are resource-constrained

4. **Enable HTTPS on Origins**
   - Configure SSL certificates for containers
   - Or use Azure Application Gateway as intermediate layer

5. **Implement Retry Logic**
   - Add retry policies in Front Door
   - Configure timeout settings appropriately

## GitHub Actions Deployment Check

The deployment workflow shows a two-phase approach:
1. Deploy infrastructure with placeholder images
2. Build real images and update deployment

Verify the latest deployment succeeded:
```bash
# Check GitHub Actions run status
gh run list --workflow=deploy.yml --limit 5

# Check if latest images were deployed
az container show -g vextir-dev --name chatui --query containers[0].image -o tsv
```

## Next Steps

1. Run the debug script to get current status
2. Check container logs for specific errors
3. Restart failed containers
4. Verify Front Door origin health
5. If issues persist, check ACR for correct images
6. Consider rolling back to previous working images
