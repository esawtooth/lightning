import azure.functions as func
import os
import json
import logging
from urllib.parse import urlencode, urlparse, parse_qs

logger = logging.getLogger(__name__)

def main(req: func.HttpRequest) -> func.HttpResponse:
    """Azure AD OAuth2 authentication endpoint."""
    
    # Get configuration
    client_id = os.environ.get('AAD_CLIENT_ID')
    tenant_id = os.environ.get('AAD_TENANT_ID')
    
    if not client_id or not tenant_id:
        return func.HttpResponse(
            json.dumps({"error": "Authentication not configured"}),
            status_code=500,
            mimetype="application/json"
        )
    
    # Get redirect URL from query params
    redirect_uri = req.params.get('redirect', 'https://www.vextir.com/')
    
    # Check if this is a callback from Azure AD
    code = req.params.get('code')
    if code:
        # This is the callback - redirect to UI with auth code
        # The UI will handle token exchange
        return func.HttpResponse(
            status_code=302,
            headers={
                'Location': f"{redirect_uri}?code={code}"
            }
        )
    
    # Build Azure AD authorization URL
    auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
    
    # Parse the function URL to get the base URL for callback
    func_url = req.url
    parsed = urlparse(func_url)
    callback_url = f"{parsed.scheme}://{parsed.netloc}/api/Auth"
    
    params = {
        'client_id': client_id,
        'response_type': 'code',
        'redirect_uri': callback_url,
        'response_mode': 'query',
        'scope': 'openid profile email User.Read',
        'state': redirect_uri,  # Store original redirect in state
        'prompt': 'select_account'
    }
    
    # Redirect to Azure AD
    return func.HttpResponse(
        status_code=302,
        headers={
            'Location': f"{auth_url}?{urlencode(params)}"
        }
    )