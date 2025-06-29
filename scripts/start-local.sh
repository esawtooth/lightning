#!/bin/bash
#
# Start Lightning OS locally with Docker Compose
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

# Check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose (prefer v2, fallback to v1)
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="docker-compose"
        print_warn "Using docker-compose v1 (deprecated). Consider upgrading to Docker Compose v2."
    else
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi
    
    print_info "✓ Prerequisites checked"
}

# Set up environment variables
setup_environment() {
    print_info "Setting up environment..."
    
    # Check if .env.local exists
    if [ ! -f .env.local ]; then
        print_error ".env.local file not found!"
        print_info "Please ensure .env.local exists with your configuration."
        exit 1
    fi
    
    # Source environment variables from .env.local
    set -a  # automatically export all variables
    source .env.local
    set +a  # turn off automatic export
    
    # Check for required variables
    if [ -z "$OPENAI_API_KEY" ]; then
        print_error "OPENAI_API_KEY is not set in .env.local"
        print_info "Please configure your API keys in .env.local"
        exit 1
    fi
    
    print_info "✓ Environment configured from .env.local"
}

# Build services
build_services() {
    print_info "Building services..."
    
    # Build with Docker Compose
    $DOCKER_COMPOSE -f docker-compose.local.yml build
    
    print_info "✓ Services built"
}

# Start services
start_services() {
    print_info "Starting Lightning OS services..."
    
    # Start core services first
    $DOCKER_COMPOSE -f docker-compose.local.yml up -d postgres redis rabbitmq
    
    # Wait for databases to be ready
    print_info "Waiting for databases to initialize..."
    sleep 10
    
    # Start remaining services
    $DOCKER_COMPOSE -f docker-compose.local.yml up -d
    
    print_info "✓ All services started"
}

# Show service status
show_status() {
    print_info "Service Status:"
    $DOCKER_COMPOSE -f docker-compose.local.yml ps
    
    echo ""
    print_info "Access Points:"
    echo "  • Integrated UI:     http://localhost:8080"
    echo "  • Chat Client:       http://localhost:8501"
    echo "  • Dashboard:         http://localhost:8502"
    echo "  • API:              http://localhost:8000"
    echo "  • API Docs:         http://localhost:8000/docs"
    echo "  • Context Hub:      http://localhost:3000"
    echo "  • RabbitMQ Admin:   http://localhost:15672 (lightning/lightning123)"
    echo ""
    print_info "Logs: $DOCKER_COMPOSE logs -f [service-name]"
    print_info "Stop: $DOCKER_COMPOSE down"
}

# Main execution
main() {
    cd "$(dirname "$0")/.."
    
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║          Lightning OS - Local Development              ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
    
    check_prerequisites
    setup_environment
    
    # Check if --build flag is passed
    if [ "$1" == "--build" ]; then
        build_services
    fi
    
    start_services
    show_status
    
    echo ""
    print_info "Lightning OS is running locally! 🚀"
}

# Run main function
main "$@"