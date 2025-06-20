#!/bin/bash
# Test deployment script for Lightning OS
# Supports local and azure testing modes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
MODE="local"
ACTION="up"
DETACHED="true"
BUILD="false"

# Function to print colored output
print_info() {
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

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Test Lightning OS deployment in different modes"
    echo ""
    echo "Options:"
    echo "  -m, --mode MODE    Deployment mode: local, azure (default: local)"
    echo "  -a, --action ACTION Action: up, down, restart, logs, status (default: up)"
    echo "  -f, --foreground   Run in foreground (not detached)"
    echo "  -b, --build        Force rebuild of images"
    echo "  -h, --help         Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                           # Start local deployment"
    echo "  $0 -m azure                  # Start Azure test deployment"
    echo "  $0 -a down                   # Stop current deployment"
    echo "  $0 -a logs                   # Show logs"
    echo "  $0 -a status                 # Show status"
    echo "  $0 -m azure -b               # Build and start Azure test"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--mode)
            MODE="$2"
            shift 2
            ;;
        -a|--action)
            ACTION="$2"
            shift 2
            ;;
        -f|--foreground)
            DETACHED="false"
            shift
            ;;
        -b|--build)
            BUILD="true"
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate mode
if [[ ! "$MODE" =~ ^(local|azure)$ ]]; then
    print_error "Invalid mode: $MODE. Must be one of: local, azure"
    exit 1
fi

# Set compose file based on mode
if [[ "$MODE" == "azure" ]]; then
    COMPOSE_FILE="docker-compose.azure.yml"
    ENV_FILE=".env.azure"
else
    COMPOSE_FILE="docker-compose.yml"
    ENV_FILE=".env.local"
fi

# Change to project root
cd "$(dirname "$0")/.."

# Check if compose file exists
if [[ ! -f "$COMPOSE_FILE" ]]; then
    print_error "Compose file not found: $COMPOSE_FILE"
    exit 1
fi

# Load environment file if it exists
if [[ -f "$ENV_FILE" ]]; then
    print_info "Loading environment from $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
fi

# Function to check service health
check_health() {
    local service=$1
    local url=$2
    local max_attempts=30
    local attempt=1
    
    print_info "Checking health of $service..."
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -s -f "$url" >/dev/null 2>&1; then
            print_success "$service is healthy"
            return 0
        fi
        
        if [[ $attempt -eq $max_attempts ]]; then
            print_warning "$service health check failed after $max_attempts attempts"
            return 1
        fi
        
        echo -n "."
        sleep 2
        ((attempt++))
    done
}

# Function to show status
show_status() {
    print_info "Service status for $MODE mode:"
    docker compose -f "$COMPOSE_FILE" ps
    
    echo ""
    print_info "Health checks:"
    
    # Check API health
    if check_health "Lightning API" "http://localhost:8000/health"; then
        echo ""
    fi
    
    # Check UI health
    if check_health "Integrated UI" "http://localhost:8080/health"; then
        echo ""
    fi
    
    # Check Context Hub
    if check_health "Context Hub" "http://localhost:3000/health"; then
        echo ""
    fi
}

# Main logic based on action
case "$ACTION" in
    "up")
        print_info "Starting Lightning OS in $MODE mode..."
        
        # Build if requested
        if [[ "$BUILD" == "true" ]]; then
            print_info "Building images..."
            docker compose -f "$COMPOSE_FILE" build
        fi
        
        # Start services
        if [[ "$DETACHED" == "true" ]]; then
            docker compose -f "$COMPOSE_FILE" up -d
        else
            docker compose -f "$COMPOSE_FILE" up
        fi
        
        if [[ "$DETACHED" == "true" ]]; then
            print_success "Services started in detached mode"
            sleep 5
            show_status
            
            print_info "Access URLs:"
            echo "  - Lightning UI: http://localhost:8080"
            echo "  - Lightning API: http://localhost:8000"
            echo "  - Context Hub: http://localhost:3000"
            if [[ "$MODE" == "local" ]]; then
                echo "  - RabbitMQ Management: http://localhost:15672 (lightning/lightning123)"
            fi
        fi
        ;;
        
    "down")
        print_info "Stopping Lightning OS..."
        docker compose -f "$COMPOSE_FILE" down
        print_success "Services stopped"
        ;;
        
    "restart")
        print_info "Restarting Lightning OS in $MODE mode..."
        docker compose -f "$COMPOSE_FILE" restart
        print_success "Services restarted"
        sleep 5
        show_status
        ;;
        
    "logs")
        print_info "Showing logs for $MODE mode..."
        docker compose -f "$COMPOSE_FILE" logs -f
        ;;
        
    "status")
        show_status
        ;;
        
    *)
        print_error "Unknown action: $ACTION"
        show_usage
        exit 1
        ;;
esac