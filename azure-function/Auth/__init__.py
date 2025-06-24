import azure.functions as func
import os
import json
import logging
from urllib.parse import urlencode, urlparse, parse_qs, quote

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
    state = req.params.get('state')  # Contains the original redirect URL
    
    if code:
        # This is the callback - redirect to UI auth callback with code
        # The state parameter contains the original redirect URL
        original_redirect = state or 'https://www.vextir.com/'
        
        # Redirect to the UI's auth callback endpoint
        ui_callback_url = f"https://www.vextir.com/auth/callback?code={code}&state={quote(original_redirect)}"
        
        return func.HttpResponse(
            status_code=302,
            headers={
                'Location': ui_callback_url
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
        'scope': 'openid profile email User.Read offline_access',
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