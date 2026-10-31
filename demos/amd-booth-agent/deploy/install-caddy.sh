#!/usr/bin/env bash
set -euo pipefail

ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
    pwd
)"

DOMAIN="${BOOTH_HOSTNAME:-agent.165.245.129.230.sslip.io}"
PORT="${BOOTH_PORT:-18090}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
MARKER="# BEGIN AMD OPENCLAW BOOTH"

if grep -qF "$MARKER" "$CADDYFILE"; then
  python3 - "$CADDYFILE" "$MARKER" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
marker = sys.argv[2]
text = path.read_text()
start = text.index(marker)
end = text.index("# END AMD OPENCLAW BOOTH", start)
end = text.index("\n", end) + 1 if "\n" in text[end:] else len(text)
path.write_text(text[:start] + text[end:])
PY
fi

cat >>"$CADDYFILE" <<EOF

$MARKER
$DOMAIN {
	encode zstd gzip
	reverse_proxy 127.0.0.1:$PORT {
		flush_interval -1
		header_up Host {host}
		header_up X-Real-IP {remote_host}
		header_up X-Forwarded-Proto {scheme}
	}
}
# END AMD OPENCLAW BOOTH
EOF

caddy fmt --overwrite "$CADDYFILE"
caddy validate --config "$CADDYFILE"

if command -v ufw >/dev/null 2>&1; then
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
fi

systemctl reload caddy
echo "Caddy configured for https://$DOMAIN"
