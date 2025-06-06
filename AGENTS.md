The following secrets are available

AZURE_SUBSCRIPTION_ID
AZURE_CLIENT_SECRET
AZURE_TENANT_ID
AZURE_CLIENT_ID

You can gain the use of az cli with the following preamble

az login --service-principal \
  --username "$AZURE_CLIENT_ID" \
  --password "$AZURE_CLIENT_SECRET" \
  --tenant "$AZURE_TENANT_ID"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
