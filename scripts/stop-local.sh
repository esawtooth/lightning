#!/bin/bash
#
# Stop Lightning OS locally
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect Docker Compose command
detect_docker_compose() {
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="docker-compose"
    else
        print_error "Docker Compose is not installed."
        exit 1
    fi
}

# Main execution
main() {
    cd "$(dirname "$0")/.."
    
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║          Lightning OS - Stopping Services              ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
    
    detect_docker_compose
    
    print_info "Stopping Lightning OS services..."
    $DOCKER_COMPOSE -f docker-compose.local.yml down
    
    # Optional: Clean up volumes
    if [ "$1" == "--volumes" ]; then
        print_info "Removing volumes..."
        $DOCKER_COMPOSE -f docker-compose.local.yml down -v
    fi
    
    print_info "✓ Lightning OS stopped"
}

# Run main function
main "$@"