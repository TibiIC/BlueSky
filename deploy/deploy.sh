#!/usr/bin/env bash
# Build locally and (re)deploy BlueSky to the Vultr server.  Usage, from the repository root:
#   deploy/deploy.sh SERVER_IP              public site (not indexed by search engines)
#   deploy/deploy.sh SERVER_IP --password   behind a password kept in deploy/.secrets
# Needs: frontend/.env (keys), the SSH key ~/.ssh/bluesky_vultr, and deploy/setup.sh run once on the server.
# The site is served at https://SERVER-IP-WITH-DASHES.sslip.io.
set -euo pipefail
IP="${1:?usage: deploy/deploy.sh SERVER_IP [--password]}"
PROTECT=0; [[ "${2:-}" == "--password" ]] && PROTECT=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="${SSH_KEY:-$HOME/.ssh/bluesky_vultr}"
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=accept-new)
HOST="${SITE_HOST:-$(echo "$IP" | tr . -).sslip.io}"
SECRETS="$ROOT/deploy/.secrets"

# The site password (only with --password): created once, kept out of git (deploy/.secrets is gitignored)
SITE_USER=""; SITE_PASSWORD=""
if [[ $PROTECT == 1 && ! -f "$SECRETS" ]]; then
  umask 077
  printf 'SITE_USER=bluesky\nSITE_PASSWORD=%s\n' "$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | cut -c1-16)" > "$SECRETS"
fi
# shellcheck disable=SC1090
[[ $PROTECT == 1 ]] && source "$SECRETS"

echo "== build (frontend/build)"
( cd "$ROOT/frontend" && npm run build >/dev/null )

echo "== upload"
rsync -az --delete -e "ssh ${SSH_OPTS[*]}" "$ROOT/frontend/build/" "root@$IP:/opt/bluesky/app/build/"
rsync -az -e "ssh ${SSH_OPTS[*]}" "$ROOT/frontend/package.json" "$ROOT/frontend/package-lock.json" "root@$IP:/opt/bluesky/app/"
rsync -az --delete --exclude __pycache__ --exclude tests -e "ssh ${SSH_OPTS[*]}" "$ROOT/terra/" "root@$IP:/opt/bluesky/terra/"

# Server environment: only the keys the app needs, never the Anthropic key
ENVFILE="$(mktemp)"; trap 'rm -f "$ENVFILE"' EXIT
grep -E '^(PUBLIC_[A-Z_]+|MONGODB_URI|MONGODB_DB)=' "$ROOT/frontend/.env" > "$ENVFILE" || true
printf 'PORT=3000\nHOST=127.0.0.1\nORIGIN=https://%s\n' "$HOST" >> "$ENVFILE"
scp -q "${SSH_OPTS[@]}" "$ENVFILE" "root@$IP:/opt/bluesky/app/.env"

echo "== install and restart"
ssh "${SSH_OPTS[@]}" "root@$IP" PROTECT="$PROTECT" SITE_USER="$SITE_USER" SITE_PASSWORD="$SITE_PASSWORD" HOST="$HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/bluesky/app && npm ci --omit=dev --no-audit --no-fund --loglevel=error
chown -R bluesky:bluesky /opt/bluesky && chmod 600 /opt/bluesky/app/.env

cat > /etc/systemd/system/bluesky-app.service <<UNIT
[Unit]
Description=BlueSky web app (SvelteKit, adapter-node)
After=network-online.target bluesky-terra.service
Wants=network-online.target
[Service]
User=bluesky
WorkingDirectory=/opt/bluesky/app
EnvironmentFile=/opt/bluesky/app/.env
ExecStart=/usr/bin/node build
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/bluesky-terra.service <<UNIT
[Unit]
Description=BlueSky TERRA live weather and land model (port 8765, local only)
After=network-online.target
Wants=network-online.target
[Service]
User=bluesky
WorkingDirectory=/opt/bluesky/terra
ExecStart=/usr/bin/python3 server.py --host 127.0.0.1 --port 8765
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT

AUTH=""
if [[ "$PROTECT" == 1 ]]; then
  AUTH="	basic_auth {
		$SITE_USER $(caddy hash-password --plaintext "$SITE_PASSWORD")
	}"
fi
cat > /etc/caddy/Caddyfile <<CADDY
$HOST {
	encode zstd gzip
	header X-Robots-Tag "noindex, nofollow"
$AUTH
	reverse_proxy 127.0.0.1:3000 {
		flush_interval -1
	}
}
CADDY

systemctl daemon-reload
systemctl enable --now bluesky-terra bluesky-app >/dev/null 2>&1
systemctl restart bluesky-terra bluesky-app
systemctl reload caddy || systemctl restart caddy
sleep 4
systemctl is-active bluesky-terra bluesky-app caddy
REMOTE

echo "== check"
AUTHARG=(); [[ $PROTECT == 1 ]] && AUTHARG=(-u "$SITE_USER:$SITE_PASSWORD")
code=$(curl -s -o /dev/null -w '%{http_code}' "${AUTHARG[@]}" "https://$HOST/api/dev" || true)
echo "https://$HOST/api/dev -> $code"
if [[ $PROTECT == 1 ]]; then echo "Site: https://$HOST   user: $SITE_USER   password: in deploy/.secrets"; else echo "Site: https://$HOST   (public, not indexed)"; fi
