#!/bin/bash
#
# Setup Docker Compose and fix Lightning OS for local development
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Install Docker Compose
install_docker_compose() {
    print_info "Installing Docker Compose..."
    
    # Create plugins directory
    mkdir -p ~/.docker/cli-plugins
    
    # Download Docker Compose v2
    COMPOSE_VERSION="v2.23.3"
    ARCH=$(uname -m)
    
    if [ "$ARCH" = "arm64" ]; then
        ARCH="aarch64"
    fi
    
    print_info "Downloading Docker Compose for $ARCH..."
    curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-darwin-${ARCH}" \
        -o ~/.docker/cli-plugins/docker-compose
    
    # Make it executable
    chmod +x ~/.docker/cli-plugins/docker-compose
    
    # Also install standalone version
    print_info "Installing standalone docker-compose..."
    curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-darwin-${ARCH}" \
        -o /usr/local/bin/docker-compose 2>/dev/null || \
    sudo curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-darwin-${ARCH}" \
        -o /usr/local/bin/docker-compose
    
    sudo chmod +x /usr/local/bin/docker-compose 2>/dev/null || chmod +x /usr/local/bin/docker-compose
    
    print_info "Docker Compose installed!"
}

# Check installation
check_compose() {
    if docker compose version >/dev/null 2>&1; then
        print_info "Docker Compose v2 is available: $(docker compose version)"
        return 0
    elif docker-compose --version >/dev/null 2>&1; then
        print_info "Docker Compose standalone is available: $(docker-compose --version)"
        return 0
    else
        return 1
    fi
}

# Main
main() {
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║     Lightning OS - Docker Compose Setup for Mac        ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
    
    # Check if Docker Compose is installed
    if check_compose; then
        print_info "Docker Compose is already installed!"
    else
        install_docker_compose
        
        # Verify installation
        if check_compose; then
            print_info "✓ Docker Compose installation successful!"
        else
            print_error "Failed to install Docker Compose"
            exit 1
        fi
    fi
    
    echo ""
    print_info "Setup complete! You can now use:"
    echo "  • docker compose [commands]  (recommended)"
    echo "  • docker-compose [commands]  (standalone)"
}

main "$@"