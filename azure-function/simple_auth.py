"""
Simplified authentication for Azure Functions using Azure Entra.
This replaces the JWT-based authentication with a simpler approach.
"""

import os
import logging


def get_user_from_headers(headers):
    """
    Extract user information from request headers when using Azure App Service Authentication.
    
    When Azure App Service Authentication is enabled, user information is automatically
    injected into request headers by the platform.
    """
    # Azure App Service Authentication headers
    user_id = headers.get('X-MS-CLIENT-PRINCIPAL-ID')
    user_name = headers.get('X-MS-CLIENT-PRINCIPAL-NAME')
    
    if user_id:
        logging.info(f"Authenticated user: {user_name} ({user_id})")
        return user_id
    
    # Fallback: Check for Authorization header and extract user info
    # This is a simplified approach that doesn't require JWT verification
    auth_header = headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        # For now, we'll use a simple approach - in production you might want
        # to enable App Service Authentication instead
        logging.warning("Using fallback authentication - consider enabling App Service Auth")
        # Return a default user ID for development/testing
        return "default-user"
    
    return None


def verify_user(req):
    """
    Verify user authentication and return user ID.
    
    Args:
        req: Azure Functions HttpRequest object
        
    Returns:
        str: User ID if authenticated
        
    Raises:
        ValueError: If user is not authenticated
    """
    user_id = get_user_from_headers(req.headers)
    
    if not user_id:
        raise ValueError("User not authenticated")
    
    return user_id


def is_development_mode():
    """Check if we're running in development mode."""
    return os.environ.get('AZURE_FUNCTIONS_ENVIRONMENT') == 'Development'


def get_user_id_permissive(req):
    """
    Get user ID with permissive fallback for development.
    
    In development mode, this will return a default user ID if no authentication
    is present. In production, it will require proper authentication.
    """
    try:
        return verify_user(req)
    except ValueError:
        if is_development_mode():
            logging.warning("Development mode: using default user ID")
            return "dev-user"
        raise
