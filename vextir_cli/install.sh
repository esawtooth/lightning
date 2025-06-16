#!/bin/bash

# Vextir CLI Installation Script
# This script installs the Vextir CLI and sets up the environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Python version
check_python() {
    if command_exists python3; then
        PYTHON_CMD="python3"
    elif command_exists python; then
        PYTHON_CMD="python"
    else
        print_error "Python is not installed. Please install Python 3.8 or higher."
        exit 1
    fi

    # Check Python version
    PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
    REQUIRED_VERSION="3.8"
    
    if ! $PYTHON_CMD -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
        print_error "Python $PYTHON_VERSION is installed, but Python $REQUIRED_VERSION or higher is required."
        exit 1
    fi
    
    print_success "Python $PYTHON_VERSION found"
}

# Check pip
check_pip() {
    if command_exists pip3; then
        PIP_CMD="pip3"
    elif command_exists pip; then
        PIP_CMD="pip"
    else
        print_error "pip is not installed. Please install pip."
        exit 1
    fi
    
    print_success "pip found"
}

# Install dependencies
install_dependencies() {
    print_status "Installing Python dependencies..."
    
    if [ -f "requirements.txt" ]; then
        $PIP_CMD install -r requirements.txt
        print_success "Dependencies installed"
    else
        print_warning "requirements.txt not found, installing individual packages..."
        $PIP_CMD install click rich aiohttp pydantic python-dateutil PyYAML requests
    fi
}

# Install CLI
install_cli() {
    print_status "Installing Vextir CLI..."
    
    if [ -f "setup.py" ]; then
        $PIP_CMD install -e .
    else
        print_error "setup.py not found. Please run this script from the vextir_cli directory."
        exit 1
    fi
    
    print_success "Vextir CLI installed"
}

# Check Azure CLI
check_azure_cli() {
    if command_exists az; then
        print_success "Azure CLI found"
        
        # Check if logged in
        if az account show >/dev/null 2>&1; then
            ACCOUNT=$(az account show --query "user.name" -o tsv)
            print_success "Logged in to Azure as: $ACCOUNT"
        else
            print_warning "Azure CLI is installed but you're not logged in."
            print_status "Run 'az login' to authenticate with Azure."
        fi
    else
        print_warning "Azure CLI not found. This is recommended for authentication."
        print_status "Install Azure CLI: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    fi
}

# Create initial configuration
create_config() {
    print_status "Creating initial configuration..."
    
    # Create config directory
    CONFIG_DIR="$HOME/.vextir"
    mkdir -p "$CONFIG_DIR"
    
    # Create default config if it doesn't exist
    CONFIG_FILE="$CONFIG_DIR/config.json"
    if [ ! -f "$CONFIG_FILE" ]; then
        cat > "$CONFIG_FILE" << EOF
{
  "endpoint": "https://api.vextir.com",
  "auth": {
    "method": "azure_cli",
    "tenant_id": null,
    "client_id": null
  },
  "output": {
    "format": "table",
    "colors": true,
    "verbose": false
  },
  "event_streaming": {
    "buffer_size": 100,
    "timeout": 30
  },
  "context_hub": {
    "default_path": "/",
    "max_query_results": 1000,
    "endpoint": "https://hub.vextir.com"
  }
}
EOF
        print_success "Default configuration created at $CONFIG_FILE"
    else
        print_status "Configuration already exists at $CONFIG_FILE"
    fi
    
    # Create logs directory
    mkdir -p "$CONFIG_DIR/logs"
}

# Verify installation
verify_installation() {
    print_status "Verifying installation..."
    
    if command_exists vextir; then
        print_success "Vextir CLI is available in PATH"
        
        # Test basic command
        if vextir --help >/dev/null 2>&1; then
            print_success "Vextir CLI is working correctly"
        else
            print_error "Vextir CLI installed but not working correctly"
            exit 1
        fi
    else
        print_error "Vextir CLI not found in PATH"
        print_status "You may need to restart your shell or add the installation directory to PATH"
        exit 1
    fi
}

# Print next steps
print_next_steps() {
    echo
    print_success "Installation completed successfully!"
    echo
    echo "Next steps:"
    echo "1. Configure your Vextir OS endpoint:"
    echo "   vextir config set endpoint https://api.vextir.com"
    echo
    echo "2. If using Azure CLI authentication (recommended):"
    echo "   az login"
    echo "   vextir config set auth.method azure_cli"
    echo
    echo "3. Verify your setup:"
    echo "   vextir config get"
    echo "   vextir system status"
    echo
    echo "4. Get help:"
    echo "   vextir --help"
    echo "   vextir <command> --help"
    echo
    echo "For more information, see the README.md file or visit:"
    echo "https://docs.vextir.com/cli"
}

# Main installation process
main() {
    echo "Vextir CLI Installation Script"
    echo "=============================="
    echo
    
    # Check prerequisites
    check_python
    check_pip
    
    # Install
    install_dependencies
    install_cli
    
    # Setup
    check_azure_cli
    create_config
    
    # Verify
    verify_installation
    
    # Done
    print_next_steps
}

# Run main function
main "$@"
