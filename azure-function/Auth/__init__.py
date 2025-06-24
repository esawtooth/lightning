import azure.functions as func
import os
import logging
from urllib.parse import urlencode, quote, urlparse, parse_qs

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main(req: func.HttpRequest) -> func.HttpResponse:
    """Azure AD OAuth2 authentication endpoint."""
    try:
        # Get domain from environment
        domain = os.environ.get('DOMAIN', 'vextir.com')
        
        # Get redirect URL from query parameters
        redirect = req.params.get('redirect', f'https://www.{domain}/')
        logger.info(f"Auth endpoint called with redirect: {redirect}")
        
        # Get Azure AD configuration
        tenant_id = os.environ.get('AAD_TENANT_ID')
        client_id = os.environ.get('AAD_CLIENT_ID')
        
        if not tenant_id or not client_id:
            logger.error("Missing Azure AD configuration")
            return func.HttpResponse(
                "Authentication configuration error",
                status_code=500
            )
        
        # Build Azure AD authorization URL
        auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
        
        # Use the actual callback URL that the UI expects
        callback_url = f"https://www.{domain}/auth/callback"
        
        params = {
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': callback_url,
            'scope': 'openid profile email User.Read offline_access',
            'state': quote(redirect),  # Pass the original redirect URL in state
            'response_mode': 'query'
        }
        
        # Build the full URL
        full_auth_url = f"{auth_url}?{urlencode(params)}"
        logger.info(f"Redirecting to Azure AD: {full_auth_url}")
        
        # Return redirect response
        return func.HttpResponse(
            status_code=302,
            headers={
                'Location': full_auth_url
            }
        )
        
    except Exception as e:
        logger.error(f"Error in Auth function: {str(e)}")
        return func.HttpResponse(
            f"Authentication error: {str(e)}",
            status_code=500
        )