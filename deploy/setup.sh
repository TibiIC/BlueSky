#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 Vultr server for BlueSky. Run from the repository root:
#   ssh -i ~/.ssh/bluesky_vultr root@SERVER_IP 'bash -s' < deploy/setup.sh
# Installs Node 22, Caddy (HTTPS + password) and a firewall; Python 3 comes with Ubuntu.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl ca-certificates gnupg rsync python3 ufw debian-keyring debian-archive-keyring apt-transport-https

# Node.js 22 from NodeSource (the package source linked from nodejs.org)
if ! command -v node >/dev/null || [[ "$(node -v)" != v22* ]]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

# Caddy from its official apt repository: automatic HTTPS certificates and the site password
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

# A service account that owns the app; nobody logs in as it
id bluesky >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/bluesky --shell /usr/sbin/nologin bluesky
mkdir -p /opt/bluesky/app /opt/bluesky/terra
chown -R bluesky:bluesky /opt/bluesky

# 2 GB swap so installs never run out of memory on small plans
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Only SSH and the website are reachable from outside
ufw allow OpenSSH >/dev/null && ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null && ufw --force enable >/dev/null
echo "setup done: node $(node -v), $(caddy version | cut -d' ' -f1), $(python3 -V)"
