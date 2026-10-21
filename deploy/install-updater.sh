#!/usr/bin/env bash
# Einmalig auf der VM ausführen (als root): sudo ./deploy/install-updater.sh
# Richtet einen systemd-Dienst ein, der data/update.request überwacht.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$REPO/deploy/update.sh"
mkdir -p "$REPO/data"
OWNER=$(stat -c %U "$REPO")   # git pull als Besitzer des Repos (sonst "dubious ownership")
chown "$OWNER" "$REPO/data"
if [ "$OWNER" != root ]; then usermod -aG docker "$OWNER"; fi

cat > /etc/systemd/system/preischecker-update.service <<UNIT
[Unit]
Description=Preis-Checker aktualisieren
After=network-online.target docker.service

[Service]
Type=oneshot
User=$OWNER
WorkingDirectory=$REPO
ExecStart=$REPO/deploy/update.sh
UNIT

cat > /etc/systemd/system/preischecker-update.path <<UNIT
[Unit]
Description=Preis-Checker Update-Anfrage überwachen

[Path]
PathExists=$REPO/data/update.request

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now preischecker-update.path
sudo -u "$OWNER" git -C "$REPO" log -1 --format='%h %cd %s' --date=format:'%d.%m.%Y %H:%M' > "$REPO/data/version.txt"
echo "Updater aktiv. Test: touch $REPO/data/update.request ; Log: $REPO/data/update.log"
