#!/bin/bash
# Simple Azure CLI script to check and test Vextir Function App

if [ $# -lt 2 ]; then
  echo "Usage: $0 <resource-group> <function-app-name>" >&2
  exit 1
fi

RESOURCE_GROUP="$1"
FUNCTION_APP="$2"

# Get function host name
HOST=$(az functionapp show --resource-group "$RESOURCE_GROUP" --name "$FUNCTION_APP" --query defaultHostName -o tsv)
if [ -z "$HOST" ]; then
  echo "Could not find Function App '$FUNCTION_APP' in resource group '$RESOURCE_GROUP'" >&2
  exit 1
fi

STATE=$(az functionapp show --resource-group "$RESOURCE_GROUP" --name "$FUNCTION_APP" --query state -o tsv)

echo "Function App: $FUNCTION_APP"
echo "State: $STATE"

if [ "$STATE" != "Running" ]; then
  echo "Function App is not running" >&2
  exit 1
fi

BASE_URL="https://$HOST/api/auth"
TEST_USER="cli_test_${RANDOM}"
TEST_PASS="Password1"

set -e

echo "Registering test user $TEST_USER..."
az rest --method post --uri "$BASE_URL/register" --headers Content-Type=application/json --body "{\"username\": \"$TEST_USER\", \"password\": \"$TEST_PASS\"}"

echo "Logging in user $TEST_USER..."
az rest --method post --uri "$BASE_URL/login" --headers Content-Type=application/json --body "{\"username\": \"$TEST_USER\", \"password\": \"$TEST_PASS\"}"

