#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/hengzhe-new-product"

mkdir -p \
  "$APP_ROOT/app" \
  "$APP_ROOT/data" \
  "$APP_ROOT/backups" \
  "$APP_ROOT/hermes" \
  "$APP_ROOT/logs"

if ! command -v dockerd >/dev/null 2>&1; then
  dnf remove -y podman-docker || true
  dnf install -y dnf-plugins-core ca-certificates curl
  curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo -o /etc/yum.repos.d/docker-ce.repo
  dnf clean metadata
  dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1panel.live",
    "https://docker.1ms.run"
  ]
}
EOF

systemctl enable --now docker

if ! docker compose version >/dev/null 2>&1; then
  dnf install -y docker-compose-plugin
fi

docker --version
docker compose version || true
df -h /
free -h
