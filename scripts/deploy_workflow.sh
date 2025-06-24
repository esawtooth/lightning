#!/usr/bin/env bash
set -euo pipefail

# Ensure we run from the repository root regardless of the CWD
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Load variables from a local .env file if present
if [[ -f .env ]]; then
    set -o allexport
    # shellcheck source=/dev/null
    source .env
    set +o allexport
fi

# Replicates the steps from .github/workflows/deploy.yml
# Requires: az cli, docker with buildx, pulumi, python3 with pip

# Map ARM_* vars from AZURE_* if they are not set
: "${ARM_CLIENT_ID:=${AZURE_CLIENT_ID:-}}"
: "${ARM_CLIENT_SECRET:=${AZURE_CLIENT_SECRET:-}}"
: "${ARM_TENANT_ID:=${AZURE_TENANT_ID:-}}"
: "${ARM_SUBSCRIPTION_ID:=${AZURE_SUBSCRIPTION_ID:-}}"

export ARM_CLIENT_ID ARM_CLIENT_SECRET ARM_TENANT_ID ARM_SUBSCRIPTION_ID
export PULUMI_ACCESS_TOKEN OPENAI_API_KEY TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN

# Required secrets
: "${PULUMI_ACCESS_TOKEN:?}"
: "${OPENAI_API_KEY:?}"
: "${TWILIO_ACCOUNT_SID:?}"
: "${TWILIO_AUTH_TOKEN:?}"
: "${ARM_CLIENT_ID:?}"
: "${ARM_CLIENT_SECRET:?}"
: "${ARM_TENANT_ID:?}"
: "${ARM_SUBSCRIPTION_ID:?}"

GITHUB_SHA=$(git rev-parse HEAD)

login_azure() {
    echo "Logging in to Azure..."
    az login --service-principal \
        --username "$ARM_CLIENT_ID" \
        --password "$ARM_CLIENT_SECRET" \
        --tenant "$ARM_TENANT_ID"
    az account set --subscription "$ARM_SUBSCRIPTION_ID"
}

setup_infrastructure() {
    echo "Installing infra dependencies..."
    pip install -r infra/requirements.txt
    pip install --upgrade pip
    pip install -r azure-function/requirements.txt \
        --target azure-function/.python_packages \
        --platform manylinux2014_x86_64 \
        --implementation cp \
        --python-version 3.10 \
        --only-binary=:all:

    echo "Configuring Pulumi stack..."
    pushd infra >/dev/null
    pulumi stack select dev --create --non-interactive
    pulumi config set aadClientId "$ARM_CLIENT_ID" --secret
    pulumi config set aadClientSecret "$ARM_CLIENT_SECRET" --secret
    pulumi config set aadTenantId "$ARM_TENANT_ID"
    pulumi config set openaiApiKey "$OPENAI_API_KEY" --secret
    pulumi config set twilioAccountSid "$TWILIO_ACCOUNT_SID" --secret
    pulumi config set twilioAuthToken "$TWILIO_AUTH_TOKEN" --secret
    pulumi config set workerImage "mcr.microsoft.com/azuredocs/aci-helloworld:latest"
    pulumi config set uiImage "mcr.microsoft.com/azuredocs/aci-helloworld:latest"
    pulumi config set voiceWsImage "mcr.microsoft.com/azuredocs/aci-helloworld:latest"
    pulumi config set hubImage "mcr.microsoft.com/azuredocs/aci-helloworld:latest"
    pulumi config set domain "vextir.com"
    pulumi refresh --yes
    pulumi up --yes
    popd >/dev/null
}

validate_functions() {
    echo "Validating Azure Functions..."
    python scripts/validate_functions.py || {
        echo "Function validation failed! Aborting deployment."
        exit 1
    }
}

build_images() {
    echo "Building Docker images..."
    docker buildx create --use --name deploy_builder || docker buildx use deploy_builder

    az acr login --name vextiracrdev

    docker buildx build \
        --platform linux/amd64 \
        --file ./Dockerfile.worker \
        --tag vextiracrdev.azurecr.io/worker-task:${GITHUB_SHA} \
        --tag vextiracrdev.azurecr.io/worker-task:latest \
        --push .

    docker buildx build \
        --platform linux/amd64 \
        --file ./chat_client/Dockerfile \
        --tag vextiracrdev.azurecr.io/chainlit-client:${GITHUB_SHA} \
        --tag vextiracrdev.azurecr.io/chainlit-client:latest \
        --push .

    docker buildx build \
        --platform linux/amd64 \
        ./agents/voice-agent/websocket-server \
        --tag vextiracrdev.azurecr.io/voice-ws:${GITHUB_SHA} \
        --tag vextiracrdev.azurecr.io/voice-ws:latest \
        --push

    docker buildx build \
        --platform linux/amd64 \
        ./agents/voice-agent/webapp \
        --tag vextiracrdev.azurecr.io/voice-webapp:${GITHUB_SHA} \
        --tag vextiracrdev.azurecr.io/voice-webapp:latest \
        --push

    docker buildx build \
        --platform linux/amd64 \
        ./context-hub \
        --file ./context-hub/Dockerfile \
        --tag vextiracrdev.azurecr.io/context-hub:${GITHUB_SHA} \
        --tag vextiracrdev.azurecr.io/context-hub:latest \
        --push
}

deploy_stack() {
    echo "Deploying stack with Pulumi..."
    pushd infra >/dev/null
    pulumi stack select dev --create --non-interactive
    pulumi config set aadClientId "$ARM_CLIENT_ID" --secret
    pulumi config set aadClientSecret "$ARM_CLIENT_SECRET" --secret
    pulumi config set aadTenantId "$ARM_TENANT_ID"
    pulumi config set openaiApiKey "$OPENAI_API_KEY" --secret
    pulumi config set twilioAccountSid "$TWILIO_ACCOUNT_SID" --secret
    pulumi config set twilioAuthToken "$TWILIO_AUTH_TOKEN" --secret
    pulumi config set workerImage "vextiracrdev.azurecr.io/worker-task:${GITHUB_SHA}"
    pulumi config set uiImage "vextiracrdev.azurecr.io/chainlit-client:${GITHUB_SHA}"
    pulumi config set voiceWsImage "vextiracrdev.azurecr.io/voice-ws:${GITHUB_SHA}"
    pulumi config set hubImage "vextiracrdev.azurecr.io/context-hub:${GITHUB_SHA}"
    pulumi config set domain "vextir.com"
    pulumi refresh --yes
    pulumi up --yes
    popd >/dev/null
}

test_endpoints() {
    echo "Testing deployed endpoints..."
    python scripts/test_auth_endpoint.py || {
        echo "Endpoint tests failed! Please check the deployment."
        exit 1
    }
}

main() {
    login_azure
    validate_functions
    setup_infrastructure
    build_images
    deploy_stack
    test_endpoints
}

main "$@"
