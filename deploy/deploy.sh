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

# The two pages that live beside the app, at the same address
export PUBLIC_STRATEGY_URL="https://$HOST/strategy"
export PUBLIC_SBTN_URL="https://$HOST/sbtn-review/"

echo "== build (frontend/build)"
( cd "$ROOT/frontend" && npm run build >/dev/null )

# The SBTN review page, exported from its Colab notebook for this address (if the notebook is here)
NOTEBOOK="${SBTN_NOTEBOOK:-$ROOT/sbtn/Climate_Lens_SBTN_Lite.ipynb}"
if [[ -f "$NOTEBOOK" ]]; then
  ( cd "$ROOT/sbtn" && SBTN_GLOBE_ORIGINS="https://$HOST" SBTN_REPORT_URL="https://$HOST/sbtn/report/pdf" \
      SBTN_MAP_URL="https://$HOST/sbtn/map" python3 export.py "$NOTEBOOK" >/dev/null )
fi

echo "== upload"
rsync -az --delete -e "ssh ${SSH_OPTS[*]}" "$ROOT/frontend/build/" "root@$IP:/opt/bluesky/app/build/"
rsync -az -e "ssh ${SSH_OPTS[*]}" "$ROOT/frontend/package.json" "$ROOT/frontend/package-lock.json" "root@$IP:/opt/bluesky/app/"
rsync -az --delete --exclude __pycache__ --exclude tests -e "ssh ${SSH_OPTS[*]}" "$ROOT/terra/" "root@$IP:/opt/bluesky/terra/"
# Report backend (strategy page, SBTN report) and the strategy page it serves
rsync -az --delete --exclude .venv --exclude __pycache__ --exclude .env --exclude tests -e "ssh ${SSH_OPTS[*]}" "$ROOT/backend/" "root@$IP:/opt/bluesky/backend/"
rsync -az --delete -e "ssh ${SSH_OPTS[*]}" "$ROOT/strategy/" "root@$IP:/opt/bluesky/strategy/"
[[ -f "$ROOT/backend/.env" ]] && scp -q "${SSH_OPTS[@]}" "$ROOT/backend/.env" "root@$IP:/opt/bluesky/backend/.env"
[[ -f "$ROOT/sbtn/site/index.html" ]] && rsync -az --delete -e "ssh ${SSH_OPTS[*]}" "$ROOT/sbtn/site/" "root@$IP:/srv/bluesky-sbtn/"

# Server environment: only the keys the app needs, never the Anthropic key
ENVFILE="$(mktemp)"; trap 'rm -f "$ENVFILE"' EXIT
grep -E '^(PUBLIC_[A-Z_]+|MONGODB_URI|MONGODB_DB)=' "$ROOT/frontend/.env" > "$ENVFILE" || true
grep -vE '^PUBLIC_(STRATEGY|SBTN)_URL=' "$ENVFILE" > "$ENVFILE.tmp" && mv "$ENVFILE.tmp" "$ENVFILE"
printf 'PORT=3000\nHOST=127.0.0.1\nORIGIN=https://%s\nPUBLIC_STRATEGY_URL=%s\nPUBLIC_SBTN_URL=%s\n' "$HOST" "$PUBLIC_STRATEGY_URL" "$PUBLIC_SBTN_URL" >> "$ENVFILE"
scp -q "${SSH_OPTS[@]}" "$ENVFILE" "root@$IP:/opt/bluesky/app/.env"

echo "== install and restart"
ssh "${SSH_OPTS[@]}" "root@$IP" PROTECT="$PROTECT" SITE_USER="$SITE_USER" SITE_PASSWORD="$SITE_PASSWORD" HOST="$HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
# Report backend system packages (also in setup.sh; installed here for servers set up before they were added)
PKGS="python3-venv libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core"
dpkg -s $PKGS >/dev/null 2>&1 || { apt-get -o DPkg::Lock::Timeout=600 update -qq && DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600 install -y -qq $PKGS >/dev/null; }
cd /opt/bluesky/app && npm ci --omit=dev --no-audit --no-fund --loglevel=error
cd /opt/bluesky/backend && { [[ -d .venv ]] || python3 -m venv .venv; } && .venv/bin/pip install -q -r requirements.txt
touch /opt/bluesky/backend/.env && mkdir -p /srv/bluesky-sbtn && chmod 755 /srv/bluesky-sbtn
chown -R bluesky:bluesky /opt/bluesky && chmod 600 /opt/bluesky/app/.env /opt/bluesky/backend/.env

cat > /etc/systemd/system/bluesky-backend.service <<UNIT
[Unit]
Description=BlueSky report backend (FastAPI: strategy page, SBTN report, port 8000, local only)
After=network-online.target
Wants=network-online.target
[Service]
User=bluesky
WorkingDirectory=/opt/bluesky/backend
EnvironmentFile=/opt/bluesky/backend/.env
ExecStart=/opt/bluesky/backend/.venv/bin/uvicorn climate_lens.app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT

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
	log {
		output file /var/log/caddy/access.log {
			roll_size 20MiB
			roll_keep 3
		}
		format json
	}
	header X-Robots-Tag "noindex, nofollow"
$AUTH
	# The report backend: Farm Missions strategy page and the SBTN report/map
	@backend path /strategy /strategy/* /sbtn/report* /sbtn/map*
	handle @backend {
		reverse_proxy 127.0.0.1:8000
	}
	redir /sbtn-review /sbtn-review/ permanent
	# The SBTN screening review page (exported from its notebook)
	handle_path /sbtn-review/* {
		root * /srv/bluesky-sbtn
		file_server
	}
	handle {
		reverse_proxy 127.0.0.1:3000 {
			flush_interval -1
		}
	}
}
CADDY

systemctl daemon-reload
systemctl enable --now bluesky-terra bluesky-backend bluesky-app >/dev/null 2>&1
systemctl restart bluesky-terra bluesky-backend bluesky-app
systemctl reload caddy || systemctl restart caddy
sleep 4
systemctl is-active bluesky-terra bluesky-backend bluesky-app caddy
REMOTE

echo "== check"
AUTHARG=(); [[ $PROTECT == 1 ]] && AUTHARG=(-u "$SITE_USER:$SITE_PASSWORD")
for path in api/dev strategy sbtn-review/; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "${AUTHARG[@]}" "https://$HOST/$path" || true)
  echo "https://$HOST/$path -> $code"
done
if [[ $PROTECT == 1 ]]; then echo "Site: https://$HOST   user: $SITE_USER   password: in deploy/.secrets"; else echo "Site: https://$HOST   (public, not indexed)"; fi
