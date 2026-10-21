#!/usr/bin/env bash
# Holt den neuesten Stand von GitHub und baut den Container neu.
# Aufruf direkt oder über den systemd-Dienst (Button im Dashboard / Aktualisieren.bat).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
LOG=data/update.log
exec >>"$LOG" 2>&1
echo "=== $(date '+%F %T') Update gestartet ==="
rm -f data/update.request
echo "laeuft" > data/update.status
alt=$(git rev-parse --short HEAD)
if git pull --ff-only; then
  neu=$(git rev-parse --short HEAD)
  if [ "$alt" != "$neu" ] || [ "${1:-}" = "--force" ]; then
    docker compose up -d --build
    docker image prune -f >/dev/null
  fi
  git log -1 --format='%h %cd %s' --date=format:'%d.%m.%Y %H:%M' > data/version.txt
  echo "ok $alt -> $neu" > data/update.status
  echo "fertig: $alt -> $neu"
else
  echo "fehler: git pull fehlgeschlagen (siehe update.log)" > data/update.status
  exit 1
fi
