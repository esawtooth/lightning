#!/bin/bash
# Build script for Lightning OS Docker images
# Supports building for local, azure, and aws modes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
MODE="local"
SERVICES="all"
PUSH="false"
REGISTRY=""
TAG="latest"

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
    echo "Build Lightning OS Docker images for different deployment modes"
    echo ""
    echo "Options:"
    echo "  -m, --mode MODE          Deployment mode: local, azure, aws (default: local)"
    echo "  -s, --services SERVICES  Services to build: all, api, processor, ui, hub (default: all)"
    echo "  -p, --push              Push images to registry after building"
    echo "  -r, --registry REGISTRY Registry URL (required if --push is used)"
    echo "  -t, --tag TAG           Image tag (default: latest)"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -m local                           # Build all services for local mode"
    echo "  $0 -m azure -s api,processor          # Build API and processor for Azure"
    echo "  $0 -m azure -p -r myregistry.azurecr.io -t v1.0.0  # Build and push with tag"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--mode)
            MODE="$2"
            shift 2
            ;;
        -s|--services)
            SERVICES="$2"
            shift 2
            ;;
        -p|--push)
            PUSH="true"
            shift
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -t|--tag)
            TAG="$2"
            shift 2
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
if [[ ! "$MODE" =~ ^(local|azure|aws)$ ]]; then
    print_error "Invalid mode: $MODE. Must be one of: local, azure, aws"
    exit 1
fi

# Validate registry if push is requested
if [[ "$PUSH" == "true" && -z "$REGISTRY" ]]; then
    print_error "Registry URL is required when --push is used"
    exit 1
fi

# Set image prefix
if [[ -n "$REGISTRY" ]]; then
    IMAGE_PREFIX="$REGISTRY/"
else
    IMAGE_PREFIX="lightning-"
fi

print_info "Building Lightning OS images..."
print_info "Mode: $MODE"
print_info "Services: $SERVICES"
print_info "Tag: $TAG"
if [[ "$PUSH" == "true" ]]; then
    print_info "Registry: $REGISTRY"
fi

# Function to build an image
build_image() {
    local service=$1
    local dockerfile=$2
    local context=$3
    local service_type=$4
    
    local image_name="${IMAGE_PREFIX}${service}:${TAG}"
    
    print_info "Building $service ($MODE mode)..."
    
    # Build command
    local build_cmd="docker build"
    build_cmd="$build_cmd --build-arg LIGHTNING_MODE=$MODE"
    
    if [[ -n "$service_type" ]]; then
        build_cmd="$build_cmd --build-arg SERVICE_TYPE=$service_type"
    fi
    
    build_cmd="$build_cmd -f $dockerfile"
    build_cmd="$build_cmd -t $image_name"
    build_cmd="$build_cmd $context"
    
    print_info "Running: $build_cmd"
    
    if eval "$build_cmd"; then
        print_success "Built $image_name"
        
        # Push if requested
        if [[ "$PUSH" == "true" ]]; then
            print_info "Pushing $image_name..."
            if docker push "$image_name"; then
                print_success "Pushed $image_name"
            else
                print_error "Failed to push $image_name"
                return 1
            fi
        fi
    else
        print_error "Failed to build $image_name"
        return 1
    fi
}

# Build services based on selection
build_services() {
    local services_array
    IFS=',' read -ra services_array <<< "$SERVICES"
    
    for service in "${services_array[@]}"; do
        case $service in
            "all")
                build_image "lightning-api" "core/Dockerfile" "./core" "api"
                build_image "lightning-processor" "core/Dockerfile.processor" "./core" ""
                build_image "lightning-ui" "ui/app/Dockerfile" "." ""
                build_image "context-hub" "context-hub/Dockerfile" "./context-hub" ""
                ;;
            "api")
                build_image "lightning-api" "core/Dockerfile" "./core" "api"
                ;;
            "processor")
                build_image "lightning-processor" "core/Dockerfile.processor" "./core" ""
                ;;
            "ui")
                build_image "lightning-ui" "ui/app/Dockerfile" "." ""
                ;;
            "hub")
                build_image "context-hub" "context-hub/Dockerfile" "./context-hub" ""
                ;;
            *)
                print_warning "Unknown service: $service"
                ;;
        esac
    done
}

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    print_error "Docker is not running or accessible"
    exit 1
fi

# Change to project root
cd "$(dirname "$0")/.."

# Build services
if build_services; then
    print_success "All builds completed successfully!"
    
    # Show built images
    print_info "Built images:"
    docker images --filter "reference=${IMAGE_PREFIX}*:${TAG}" --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
else
    print_error "Some builds failed"
    exit 1
fi