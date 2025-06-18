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
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
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
    
    # Create .env file if it doesn't exist
    if [ ! -f .env ]; then
        cat > .env << EOF
# Lightning OS Local Development Environment

# OpenAI Configuration (required for LLM features)
OPENAI_API_KEY=your-openai-api-key-here

# Authentication (for local development)
JWT_SECRET=local-development-secret-key-change-in-production
AUTH_ENABLED=false

# Logging
LOG_LEVEL=INFO

# Agent Type (conseil, vex, etc.)
AGENT_TYPE=conseil

# Lightning Mode
LIGHTNING_MODE=local
EOF
        print_warn "Created .env file. Please update OPENAI_API_KEY before running."
        print_info "Edit .env file and run this script again."
        exit 0
    fi
    
    # Source environment variables
    source .env
    
    # Check for required variables
    if [ "$OPENAI_API_KEY" == "your-openai-api-key-here" ] || [ -z "$OPENAI_API_KEY" ]; then
        print_error "Please set OPENAI_API_KEY in .env file"
        exit 1
    fi
    
    print_info "✓ Environment configured"
}

# Build services
build_services() {
    print_info "Building services..."
    
    # Build with Docker Compose
    docker-compose build
    
    print_info "✓ Services built"
}

# Start services
start_services() {
    print_info "Starting Lightning OS services..."
    
    # Start core services first
    docker-compose up -d postgres redis rabbitmq
    
    # Wait for databases to be ready
    print_info "Waiting for databases to initialize..."
    sleep 10
    
    # Start remaining services
    docker-compose up -d
    
    print_info "✓ All services started"
}

# Show service status
show_status() {
    print_info "Service Status:"
    docker-compose ps
    
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
    print_info "Logs: docker-compose logs -f [service-name]"
    print_info "Stop: docker-compose down"
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