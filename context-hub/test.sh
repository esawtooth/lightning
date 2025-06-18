#!/bin/bash
set -e

echo "Running Context Hub test suite..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2${NC}"
    else
        echo -e "${RED}✗ $2${NC}"
        exit 1
    fi
}

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"
command -v cargo >/dev/null 2>&1 || { echo -e "${RED}Cargo is required but not installed.${NC}"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo -e "${RED}Docker is required but not installed.${NC}"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo -e "${RED}Docker Compose is required but not installed.${NC}"; exit 1; }

# Run cargo fmt check
echo -e "\n${YELLOW}Running format check...${NC}"
cargo fmt -- --check
print_status $? "Format check"

# Run clippy
echo -e "\n${YELLOW}Running clippy...${NC}"
cargo clippy -- -D warnings
print_status $? "Clippy"

# Run unit tests
echo -e "\n${YELLOW}Running unit tests...${NC}"
cargo test --lib --verbose
print_status $? "Unit tests"

# Build the project
echo -e "\n${YELLOW}Building project...${NC}"
cargo build --release
print_status $? "Build"

# Start test infrastructure
echo -e "\n${YELLOW}Starting test infrastructure...${NC}"
docker-compose -f docker-compose.test.yml up -d etcd1 etcd2 etcd3 postgres redis minio minio-init
sleep 10  # Wait for services to start

# Run integration tests with infrastructure
echo -e "\n${YELLOW}Running integration tests...${NC}"
DATABASE_URL="postgres://contexthub:testpass@localhost:5432/contexthub" \
REDIS_URL="redis://:testpass@localhost:6379" \
cargo test --test integration_test
print_status $? "Integration tests"

# Clean up
echo -e "\n${YELLOW}Cleaning up...${NC}"
docker-compose -f docker-compose.test.yml down -v
print_status $? "Cleanup"

echo -e "\n${GREEN}All tests passed!${NC}"