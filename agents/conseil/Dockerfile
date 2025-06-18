# Conseil Agent Dockerfile
FROM node:22-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy workspace configuration
COPY agents/conseil/pnpm-workspace.yaml ./
COPY agents/conseil/pnpm-lock.yaml ./
COPY agents/conseil/package.json ./

# Copy codex-cli package
COPY agents/conseil/codex-cli/ ./codex-cli/

# Install pnpm
RUN npm install -g pnpm

# Install dependencies
RUN pnpm install --frozen-lockfile

# Build the application
WORKDIR /app/codex-cli
RUN pnpm build

# Create symlinks for global access
RUN ln -s /app/codex-cli/bin/conseil.js /usr/local/bin/conseil
RUN ln -s /app/codex-cli/bin/codex.js /usr/local/bin/codex
RUN chmod +x /usr/local/bin/conseil /usr/local/bin/codex

# Set default command
CMD ["conseil", "--help"]