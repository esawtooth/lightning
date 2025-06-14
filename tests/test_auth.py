import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import jwt
from common.jwt_utils import verify_token


def test_missing_aad_config(monkeypatch):
    """Test that missing AAD configuration raises proper error."""
    # Clear all AAD environment variables
    for var in ['AAD_CLIENT_ID', 'AAD_TENANT_ID', 'ARM_CLIENT_ID', 'ARM_TENANT_ID', 'AZURE_CLIENT_ID', 'AZURE_TENANT_ID']:
        monkeypatch.delenv(var, raising=False)
    
    with pytest.raises(RuntimeError, match="AAD_TENANT_ID and AAD_CLIENT_ID must be configured"):
        verify_token('Bearer some-token')


def test_missing_tenant_id(monkeypatch):
    """Test that missing tenant ID raises proper error."""
    monkeypatch.setenv('AAD_CLIENT_ID', 'test-client-id')
    for var in ['AAD_TENANT_ID', 'ARM_TENANT_ID', 'AZURE_TENANT_ID']:
        monkeypatch.delenv(var, raising=False)
    
    with pytest.raises(RuntimeError, match="AAD_TENANT_ID and AAD_CLIENT_ID must be configured"):
        verify_token('Bearer some-token')


def test_missing_client_id(monkeypatch):
    """Test that missing client ID raises proper error."""
    monkeypatch.setenv('AAD_TENANT_ID', 'test-tenant-id')
    for var in ['AAD_CLIENT_ID', 'ARM_CLIENT_ID', 'AZURE_CLIENT_ID']:
        monkeypatch.delenv(var, raising=False)
    
    with pytest.raises(RuntimeError, match="AAD_TENANT_ID and AAD_CLIENT_ID must be configured"):
        verify_token('Bearer some-token')


@patch('common.jwt_utils._verify_aad')
def test_valid_aad_token(mock_verify_aad, monkeypatch):
    """Test successful AAD token verification."""
    monkeypatch.setenv('AAD_CLIENT_ID', 'test-client-id')
    monkeypatch.setenv('AAD_TENANT_ID', 'test-tenant-id')
    
    # Mock successful AAD verification
    mock_verify_aad.return_value = {'oid': 'user-123', 'sub': 'subject-123'}
    
    result = verify_token('Bearer valid-aad-token')
    assert result == 'user-123'
    mock_verify_aad.assert_called_once_with('valid-aad-token', 'test-tenant-id', 'test-client-id')


@patch('common.jwt_utils._verify_aad')
def test_invalid_aad_token(mock_verify_aad, monkeypatch):
    """Test invalid AAD token raises ValueError."""
    monkeypatch.setenv('AAD_CLIENT_ID', 'test-client-id')
    monkeypatch.setenv('AAD_TENANT_ID', 'test-tenant-id')
    
    # Mock AAD verification failure
    mock_verify_aad.side_effect = jwt.InvalidTokenError("Invalid token")
    
    with pytest.raises(ValueError, match="Invalid token"):
        verify_token('Bearer invalid-aad-token')


@patch('common.jwt_utils._verify_aad')
def test_missing_user_id_in_claims(mock_verify_aad, monkeypatch):
    """Test that missing user ID claim raises ValueError."""
    monkeypatch.setenv('AAD_CLIENT_ID', 'test-client-id')
    monkeypatch.setenv('AAD_TENANT_ID', 'test-tenant-id')
    
    # Mock AAD verification with missing user ID claims
    mock_verify_aad.return_value = {'exp': time.time() + 60}
    
    with pytest.raises(ValueError, match="user id claim missing"):
        verify_token('Bearer token-without-user-id')


def test_missing_bearer_token():
    """Test that missing token raises ValueError."""
    with pytest.raises(ValueError, match="Missing bearer token"):
        verify_token('')


def test_bearer_prefix_handling(monkeypatch):
    """Test that Bearer prefix is properly handled."""
    monkeypatch.setenv('AAD_CLIENT_ID', 'test-client-id')
    monkeypatch.setenv('AAD_TENANT_ID', 'test-tenant-id')
    
    with patch('common.jwt_utils._verify_aad') as mock_verify_aad:
        mock_verify_aad.return_value = {'oid': 'user-123'}
        
        # Test with Bearer prefix
        verify_token('Bearer test-token')
        mock_verify_aad.assert_called_with('test-token', 'test-tenant-id', 'test-client-id')
        
        # Test without Bearer prefix
        verify_token('test-token-direct')
        mock_verify_aad.assert_called_with('test-token-direct', 'test-tenant-id', 'test-client-id')


@patch('common.jwt_utils._verify_aad')
def test_alternative_user_id_claims(mock_verify_aad, monkeypatch):
    """Test that alternative user ID claims are properly handled."""
    monkeypatch.setenv('AAD_CLIENT_ID', 'test-client-id')
    monkeypatch.setenv('AAD_TENANT_ID', 'test-tenant-id')
    
    # Test with 'sub' claim
    mock_verify_aad.return_value = {'sub': 'subject-123'}
    result = verify_token('Bearer token-with-sub')
    assert result == 'subject-123'
    
    # Test with 'user_id' claim
    mock_verify_aad.return_value = {'user_id': 'userid-123'}
    result = verify_token('Bearer token-with-user-id')
    assert result == 'userid-123'
    
    # Test with 'userID' claim
    mock_verify_aad.return_value = {'userID': 'userID-123'}
    result = verify_token('Bearer token-with-userID')
    assert result == 'userID-123'


@patch('common.jwt_utils._verify_aad')
def test_arm_environment_variables(mock_verify_aad, monkeypatch):
    """Test that ARM_* environment variables are properly used."""
    # Clear AAD_* variables and set ARM_* variables
    for var in ['AAD_CLIENT_ID', 'AAD_TENANT_ID']:
        monkeypatch.delenv(var, raising=False)
    
    monkeypatch.setenv('ARM_CLIENT_ID', 'arm-client-id')
    monkeypatch.setenv('ARM_TENANT_ID', 'arm-tenant-id')
    
    mock_verify_aad.return_value = {'oid': 'user-arm'}
    
    result = verify_token('Bearer arm-token')
    assert result == 'user-arm'
    mock_verify_aad.assert_called_once_with('arm-token', 'arm-tenant-id', 'arm-client-id')


@patch('common.jwt_utils._verify_aad')
def test_azure_environment_variables(mock_verify_aad, monkeypatch):
    """Test that AZURE_* environment variables are properly used."""
    # Clear AAD_* and ARM_* variables and set AZURE_* variables
    for var in ['AAD_CLIENT_ID', 'AAD_TENANT_ID', 'ARM_CLIENT_ID', 'ARM_TENANT_ID']:
        monkeypatch.delenv(var, raising=False)
    
    monkeypatch.setenv('AZURE_CLIENT_ID', 'azure-client-id')
    monkeypatch.setenv('AZURE_TENANT_ID', 'azure-tenant-id')
    
    mock_verify_aad.return_value = {'oid': 'user-azure'}
    
    result = verify_token('Bearer azure-token')
    assert result == 'user-azure'
    mock_verify_aad.assert_called_once_with('azure-token', 'azure-tenant-id', 'azure-client-id')
