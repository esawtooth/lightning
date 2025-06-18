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

# Copy package files
COPY agents/conseil/codex-cli/package.json agents/conseil/codex-cli/pnpm-lock.yaml ./

# Install pnpm
RUN npm install -g pnpm

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy source code
COPY agents/conseil/codex-cli/ ./

# Build the application
RUN pnpm build

# Create symlinks for global access
RUN ln -s /app/bin/conseil.js /usr/local/bin/conseil
RUN ln -s /app/bin/codex.js /usr/local/bin/codex
RUN chmod +x /usr/local/bin/conseil /usr/local/bin/codex

# Set default command
CMD ["conseil", "--help"]