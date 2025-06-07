#!/usr/bin/env bash
set -euo pipefail

# Bootstrap development environment for the Codex monorepo.
# This script installs all Node.js dependencies using pnpm.

# Ensure corepack is available and enable it to manage pnpm versions.
command -v corepack >/dev/null 2>&1 || {
  echo "corepack is required but not installed." >&2
  exit 1
}
corepack enable

# Install workspace dependencies.
pnpm install

