#!/usr/bin/env bash
set -euo pipefail

echo "CPU: $(nproc)"
free -h
df -h /
docker --version 2>/dev/null || echo "docker: not installed"
docker compose version 2>/dev/null || echo "docker compose: not installed"
