#!/bin/bash
# lb-fix.sh: apply the LB heartbeat/daemon fix to an already-installed LB (run as root).
# Fetches the current sub_FINAL.zip from the release, checks its SHA-256, extracts
# only the patched PHP files, fixes the xc-start unit, and restarts services.
#   wget -O lb-fix.sh https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/lb-fix.sh; bash lb-fix.sh
set -u

RELEASE_BASE="https://github.com/prabhjotdunglay/xtream-ui-custom/releases"
SUB_ZIP_URL="${SUB_ZIP_URL:-$RELEASE_BASE/download/v1/sub_FINAL.zip}"
SUB_ZIP_SHA256_URL="${SUB_ZIP_SHA256_URL:-$RELEASE_BASE/download/v1/sub_FINAL.zip.sha256}"
XC_BASE="/home/xtreamcodes/iptv_xtream_codes"
UNIT="/etc/systemd/system/xc-start.service"

red()    { echo -e "\033[31m$*\033[0m"; }
green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
die() { red "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run as root."
[ -d "$XC_BASE" ] || die "$XC_BASE not found. Install the LB first with install-lb."
command -v unzip >/dev/null 2>&1 || die "unzip is not installed (apt-get install -y unzip)."

FILES=(
    iptv_xtream_codes/crons/servers_checker.php
    iptv_xtream_codes/crons/offline_cons.php
    iptv_xtream_codes/crons/tmp_del.php
    iptv_xtream_codes/crons/stream_errors.php
    iptv_xtream_codes/crons/users_checker.php
    iptv_xtream_codes/crons/vod_checker.php
    iptv_xtream_codes/tools/watchdog_data.php
    iptv_xtream_codes/tools/signal_receiver.php
    iptv_xtream_codes/tools/pipe_reader.php
    iptv_xtream_codes/tools/stream_monitor.php
    iptv_xtream_codes/tools/delay.php
    iptv_xtream_codes/tools/archive.php
)

green "Downloading sub_FINAL.zip"
zip_path="/var/tmp/sub_FINAL.zip"
curl -L -s -o "$zip_path" "$SUB_ZIP_URL" || die "Failed to download $SUB_ZIP_URL"
expected_sha="$(curl -L -s "$SUB_ZIP_SHA256_URL" | awk '{print $1}')"
if [ -n "$expected_sha" ]; then
    actual_sha="$(sha256sum "$zip_path" | awk '{print $1}')"
    [ "$expected_sha" = "$actual_sha" ] || die "SHA-256 mismatch for sub_FINAL.zip (expected $expected_sha, got $actual_sha)."
else
    yellow "Could not fetch sub_FINAL.zip.sha256, skipping checksum verification."
fi

green "Extracting patched files"
unzip -q -o "$zip_path" "${FILES[@]}" -d /home/xtreamcodes/ || die "Failed to extract patched files"
rm -f "$zip_path"
for f in "${FILES[@]}"; do
    chown xtreamcodes:xtreamcodes "/home/xtreamcodes/$f"
done

if [ -f "$UNIT" ] && ! grep -q '^KillMode=process' "$UNIT"; then
    green "Adding KillMode=process to xc-start.service"
    sed -i '/^RemainAfterExit=yes/a KillMode=process' "$UNIT"
fi
mkdir -p /etc/needrestart/conf.d
cat > /etc/needrestart/conf.d/gtb.conf <<'NREOF'
$nrconf{override_rc}{qr(^fpm@)} = 0;
$nrconf{override_rc}{qr(^nginx-xc)} = 0;
$nrconf{override_rc}{qr(^xc-start)} = 0;
NREOF
systemctl daemon-reload

green "Stopping old daemons"
for name in watchdog_data signal_receiver pipe_reader; do
    pkill -u xtreamcodes -f "tools/$name" >/dev/null 2>&1
done
sleep 1

green "Restarting services"
systemctl restart xc-start
sleep 3
sudo -u xtreamcodes "$XC_BASE/php/bin/php" "$XC_BASE/crons/servers_checker.php"

green "Done. Check the daemons: ps aux | grep -E 'watchdog_data|signal_receiver|pipe_reader' | grep -v grep"
