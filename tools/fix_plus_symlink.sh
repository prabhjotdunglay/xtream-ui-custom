#!/bin/bash
# fix_plus_symlink.sh - fix "+ becomes a space" in movie/episode start (Xtream-UI GTB mods)
#
# Bug: wwwdir/includes/stream.php decodes the stored stream_source with urldecode(), which turns
# every '+' into a space (a path ending in "DD+5.1.mkv" becomes a symlink to "DD 5.1.mkv", which
# does not exist, so vod_checker marks the movie red).
# Fix: change that ONE call to rawurldecode() (3 bytes added). '+' stays '+', %XX is still decoded.
#
# Run as root on the load balancer (or the main server):
#   bash fix_plus_symlink.sh --dry-run    report only, change nothing
#   bash fix_plus_symlink.sh              patch
#   bash fix_plus_symlink.sh --revert     restore the newest stream.php.bak-plusfix-* backup
#
# Touches only wwwdir/includes/stream.php (plus its backup and a short-lived temp file next to it).
# Never restarts anything. No network access.
#
# Test hooks (not needed in production): XC_ROOT overrides /home/xtreamcodes/iptv_xtream_codes.

set -u

XC_ROOT="${XC_ROOT:-/home/xtreamcodes/iptv_xtream_codes}"
TARGET="$XC_ROOT/wwwdir/includes/stream.php"
PHP_BIN="$XC_ROOT/php/bin/php"
FPM_BIN="$XC_ROOT/php/sbin/php-fpm"
BAK_PREFIX="$TARGET.bak-plusfix-"

# sha256 of the unpatched files this fix was written for
SHA_LB_ZNUFF="860db915710067155491c0bb929aa7f11b1ef08909d0f1cc58638cc50e095c66"   # znuff LB original (also in our sub_FINAL.zip before this fix)
SHA_MAIN_BASE="f04e2822a544e54a1e6e01d976a1b5ee8703604cb7028763629a8426cf6cacbc"  # our main BASE original (main_FINAL.zip before this fix)

MODE=patch
case "${1:-}" in
  "") ;;
  --dry-run) MODE=dry ;;
  --revert) MODE=revert ;;
  -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
  *) echo "usage: $0 [--dry-run | --revert]" >&2; exit 2 ;;
esac
[ $# -le 1 ] || { echo "usage: $0 [--dry-run | --revert]" >&2; exit 2; }

die() { echo "ERROR: $*" >&2; exit 1; }

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}

command -v python3 >/dev/null 2>&1 || die "python3 not found (needed for the exact byte replacement)"
[ -f "$TARGET" ] || die "not found: $TARGET (is XC_ROOT right?)"

# --------------------------------------------------------------------------- revert
if [ "$MODE" = revert ]; then
  LATEST=$(ls -1 "$BAK_PREFIX"* 2>/dev/null | sort | tail -n 1)
  [ -n "$LATEST" ] || die "no backup matching $BAK_PREFIX* found"
  echo "Restoring $LATEST -> $TARGET"
  TMP="$TARGET.plusfix.tmp.$$"
  cp -p "$LATEST" "$TMP" || die "cannot copy backup"
  mv -f "$TMP" "$TARGET" || { rm -f "$TMP"; die "cannot move backup into place"; }
  echo "Restored. sha256 now: $(sha256_of "$TARGET")"
  echo "The backup file was kept. Same opcache note as for patching applies (see --dry-run output)."
  exit 0
fi

# --------------------------------------------------------------------------- inspect
CUR_SHA=$(sha256_of "$TARGET")
echo "Target : $TARGET"
echo "sha256 : $CUR_SHA"
KNOWN=none
[ "$CUR_SHA" = "$SHA_LB_ZNUFF" ] && KNOWN="znuff LB original"
[ "$CUR_SHA" = "$SHA_MAIN_BASE" ] && KNOWN="main BASE original"
echo "known  : $KNOWN"

# prints "<old_count> <new_count> <context_count>"
COUNTS=$(python3 - "$TARGET" <<'PY'
import re, sys
d = open(sys.argv[1], "rb").read()
old = b" urldecode(json_decode("      # leading space: does not match inside "rawurldecode("
new = b" rawurldecode(json_decode("
ctx = re.compile(rb" urldecode\(json_decode\([^;]{0,300}, true\)\[0\]\);")
print(d.count(old), d.count(new), len(ctx.findall(d)))
PY
) || die "could not read $TARGET"
set -- $COUNTS
OLD_N=$1; NEW_N=$2; CTX_N=$3
echo "snippet: old ' urldecode(json_decode(' x$OLD_N, new ' rawurldecode(json_decode(' x$NEW_N, old-with-', true)[0]);'-context x$CTX_N"

if [ "$NEW_N" -ge 1 ] && [ "$OLD_N" -eq 0 ]; then
  echo "Already patched (new snippet present x$NEW_N, old absent). Nothing to do."
  exit 0
fi
if [ "$NEW_N" -ne 0 ]; then
  die "mixed state (old x$OLD_N and new x$NEW_N both present). Refusing."
fi
if [ "$OLD_N" -ne 1 ] || [ "$CTX_N" -ne 1 ]; then
  die "expected exactly 1 occurrence of the old snippet (found $OLD_N, with context $CTX_N). This is not the file this fix was written for. Refusing; nothing changed."
fi
if [ "$KNOWN" = none ]; then
  echo "NOTE: sha256 matches neither known original, but the exact old snippet occurs exactly once, so patching is allowed."
fi

# --------------------------------------------------------------------------- opcache report
INFO_BIN=""
[ -x "$FPM_BIN" ] && INFO_BIN="$FPM_BIN"
[ -z "$INFO_BIN" ] && [ -x "$PHP_BIN" ] && INFO_BIN="$PHP_BIN"
OPC_ENABLE=""; OPC_VALIDATE=""; OPC_FREQ=""; INI_FILE=""
if [ -n "$INFO_BIN" ]; then
  INFO=$("$INFO_BIN" -i 2>/dev/null)
  INI_FILE=$(printf '%s\n' "$INFO" | awk -F' => ' '/^Loaded Configuration File/ {print $2; exit}')
  getv() { printf '%s\n' "$INFO" | awk -F' => ' -v k="$1" '$1==k {print $2; exit}'; }
  OPC_ENABLE=$(getv opcache.enable)
  OPC_VALIDATE=$(getv opcache.validate_timestamps)
  OPC_FREQ=$(getv opcache.revalidate_freq)
fi
report_opcache() {
  echo "--- PHP opcache ---"
  if [ -z "$INFO_BIN" ]; then
    echo "No php binary found under $XC_ROOT/php; cannot read the opcache settings."
    echo "Assume a reload is needed (see command below)."
    return
  fi
  echo "read via : $INFO_BIN -i"
  echo "php.ini  : ${INI_FILE:-unknown}"
  echo "opcache.enable=${OPC_ENABLE:-unset} validate_timestamps=${OPC_VALIDATE:-unset} revalidate_freq=${OPC_FREQ:-unset}"
  local ov
  ov=$(grep -hE 'opcache' "$XC_ROOT"/php/etc/*.conf 2>/dev/null | grep -E '^[[:space:]]*php(_admin)?_(value|flag)' )
  [ -n "$ov" ] && { echo "pool-level opcache overrides found in php/etc/*.conf (they win over php.ini):"; printf '%s\n' "$ov"; }
  case "$(printf '%s' "$OPC_ENABLE" | tr 'A-Z' 'a-z')" in
    off|0|"") echo "opcache is disabled or not loaded: the new file is read on the next request. No reload needed." ; return ;;
  esac
  case "$(printf '%s' "$OPC_VALIDATE" | tr 'A-Z' 'a-z')" in
    on|1)
      echo "opcache.validate_timestamps is On: the change goes live on its own within about ${OPC_FREQ:-2} seconds (revalidate_freq)."
      echo "Nothing is restarted by this script. Already running stream starts finish with the old code." ;;
    *)
      echo "opcache.validate_timestamps is Off (or unreadable): php-fpm keeps serving the OLD compiled stream.php until it is reloaded."
      echo "This script does NOT reload anything (a restart can drop viewers). At a quiet time run the reload for the pool(s) in use, e.g.:"
      echo "    systemctl list-units 'fpm@*'      # shows the php-fpm pool units, then for each one:"
      echo "    systemctl reload fpm@<name>       # graceful (SIGUSR2)"
      echo "(php-fpm reload = graceful, SIGUSR2. If your units do not support reload, use restart only when no one is watching.)"
      echo "The fix takes effect only after that reload." ;;
  esac
}

if [ "$MODE" = dry ]; then
  echo "--- DRY RUN: would back up to ${BAK_PREFIX}<date>, replace 1 occurrence ' urldecode(json_decode(' -> ' rawurldecode(json_decode(', lint with $PHP_BIN -l ---"
  [ -x "$PHP_BIN" ] || echo "WARNING: $PHP_BIN not executable; a real run would refuse to patch (no lint possible)."
  [ -w "$TARGET" ] || echo "WARNING: $TARGET is not writable by $(id -un); run as root."
  report_opcache
  exit 0
fi

# --------------------------------------------------------------------------- patch
[ -x "$PHP_BIN" ] || die "$PHP_BIN not executable: cannot lint, refusing to patch"
[ -w "$TARGET" ] || die "$TARGET is not writable by $(id -un); run as root"

BAK="$BAK_PREFIX$(date +%Y%m%d-%H%M%S)"
[ -e "$BAK" ] && BAK="$BAK.$$"
cp -p "$TARGET" "$BAK" || die "backup failed"
echo "Backup : $BAK"

TMP="$TARGET.plusfix.tmp.$$"
cp -p "$TARGET" "$TMP" || die "cannot create temp file"
if ! python3 - "$TMP" <<'PY'
import sys
p = sys.argv[1]
d = open(p, "rb").read()
old = b" urldecode(json_decode("
new = b" rawurldecode(json_decode("
if d.count(old) != 1:
    sys.exit("count mismatch")
open(p, "wb").write(d.replace(old, new))
PY
then
  rm -f "$TMP"; die "replacement failed; target unchanged (backup kept at $BAK)"
fi
mv -f "$TMP" "$TARGET" || { rm -f "$TMP"; die "cannot move patched file into place"; }

restore() {
  cp -p "$BAK" "$TMP" && mv -f "$TMP" "$TARGET" && echo "Restored original from $BAK" || echo "!!! RESTORE FAILED, copy $BAK to $TARGET by hand" >&2
}

if ! LINT=$("$PHP_BIN" -l "$TARGET" 2>&1); then
  echo "$LINT" >&2
  restore
  die "php -l failed on the patched file; original restored"
fi
echo "Lint   : $LINT"

# verify the result
NEWCOUNTS=$(python3 - "$TARGET" <<'PY'
import sys
d = open(sys.argv[1], "rb").read()
print(d.count(b" urldecode(json_decode("), d.count(b" rawurldecode(json_decode("))
PY
)
if [ "$NEWCOUNTS" != "0 1" ]; then
  restore
  die "post-check failed (old/new counts: $NEWCOUNTS); original restored"
fi
echo "Patched: 1 replacement done. New sha256: $(sha256_of "$TARGET")"
report_opcache
echo "Undo   : bash $0 --revert"
exit 0
