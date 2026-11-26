#!/bin/bash
# relink_plus_movies.sh - helper for AFTER fix_plus_symlink.sh (run on a load balancer)
#
# Finds movie/episode symlinks in movies/ that are dangling because the old code turned '+' into a
# space in the link target, and the real file exists with '+' (group PLUS: the folder exists and
# its entry name equals the link's target name once '+' is read as a space; the same check as
#   ls "$D" | sed 's/+/ /g' | grep -qxF "$B").
#
# Default (read-only, changes nothing): prints "<id> <ext>" per PLUS link on stdout, a summary on
# stderr. Press Start on those movies in the panel in batches of about 20: Start recreates the link
# with the fixed code and re-probes the movie. That is the main route.
#
#   --fix-links   OPTIONAL shortcut. Re-points each dangling PLUS link to the real '+' file
#                 (ln -sfn to a temp name, then mv -T over the link: atomic). Old and new targets are
#                 written to a log (--log FILE, default ./relink_plus_movies-<date>.log) for --undo.
#                 Never touches links that are not dangling, not PLUS, or ambiguous. Re-pointing the
#                 link alone does NOT turn a red row green: the row stays red until you press Start or
#                 vod_checker re-probes it. Prefer running it as the xtreamcodes user.
#   --undo LOG    put back the old targets recorded in LOG (only links that still point at the logged
#                 new target are changed).
#   --movies DIR  movies directory (default /home/xtreamcodes/iptv_xtream_codes/movies)
#   --log FILE    log file for --fix-links
#   -h, --help
#
# No network access. Touches only symlinks directly inside the movies directory.

set -u

MOVIES=/home/xtreamcodes/iptv_xtream_codes/movies
FIX=0
UNDO=""
LOG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --fix-links) FIX=1 ;;
    --undo) shift; [ $# -gt 0 ] || { echo "--undo needs a log file" >&2; exit 2; }; UNDO=$1 ;;
    --movies) shift; [ $# -gt 0 ] || { echo "--movies needs a directory" >&2; exit 2; }; MOVIES=$1 ;;
    --log) shift; [ $# -gt 0 ] || { echo "--log needs a file" >&2; exit 2; }; LOG=$1 ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done
[ "$FIX" -eq 1 ] && [ -n "$UNDO" ] && { echo "use --fix-links or --undo, not both" >&2; exit 2; }

# mv -T (GNU) when available; plain mv -f otherwise (renaming over a symlink replaces the link itself)
if mv -T /dev/null /dev/null 2>&1 | grep -qi 'illegal option\|invalid option\|unknown option'; then
  MVT=(mv -f)
else
  MVT=(mv -T)
fi

# atomically point LINK at TARGET: $1=link path, $2=new target
repoint() {
  local link=$1 target=$2 dir tmp
  dir=$(dirname -- "$link")
  tmp="$dir/.relink.$$.$RANDOM"
  ln -sfn -- "$target" "$tmp" || return 1
  "${MVT[@]}" -- "$tmp" "$link" || { rm -f -- "$tmp"; return 1; }
}

# --------------------------------------------------------------------------- undo
if [ -n "$UNDO" ]; then
  [ -f "$UNDO" ] || { echo "log not found: $UNDO" >&2; exit 1; }
  ok=0; skip=0
  while IFS=$'\t' read -r link old new; do
    [ -n "$link" ] || continue
    if [ -L "$link" ] && [ "$(readlink -- "$link")" = "$new" ]; then
      if repoint "$link" "$old"; then ok=$((ok+1)); else echo "FAILED: $link" >&2; skip=$((skip+1)); fi
    else
      echo "skip (no longer points at the logged new target): $link" >&2; skip=$((skip+1))
    fi
  done < "$UNDO"
  echo "undo: $ok restored, $skip skipped" >&2
  exit 0
fi

# --------------------------------------------------------------------------- scan
[ -d "$MOVIES" ] || { echo "not a directory: $MOVIES" >&2; exit 1; }
if [ "$FIX" -eq 1 ] && [ -z "$LOG" ]; then LOG="./relink_plus_movies-$(date +%Y%m%d-%H%M%S).log"; fi
[ "$FIX" -eq 1 ] && : > "$LOG" || true

n_dangling=0; n_plus=0; n_ambig=0; n_other=0; n_nodir=0; n_fixed=0; n_skipped=0

while IFS= read -r -d '' link; do
  [ -e "$link" ] && continue                 # not dangling
  n_dangling=$((n_dangling+1))
  tgt=$(readlink -- "$link")
  d=$(dirname -- "$tgt"); b=${tgt##*/}
  if [ ! -d "$d" ]; then n_nodir=$((n_nodir+1)); continue; fi
  matches=()
  for e in "$d"/* "$d"/.[!.]* "$d"/..?*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    n=${e##*/}
    [ "${n//+/ }" = "$b" ] && matches+=("$e")
  done
  if [ "${#matches[@]}" -eq 0 ]; then n_other=$((n_other+1)); continue; fi
  if [ "${#matches[@]}" -gt 1 ]; then n_ambig=$((n_ambig+1)); echo "ambiguous (several '+' variants), not listed: $link" >&2; continue; fi
  real=${matches[0]}
  [ "$real" = "$tgt" ] && { n_other=$((n_other+1)); continue; }   # cannot happen for a dangling link; defensive
  n_plus=$((n_plus+1))
  name=${link##*/}
  printf '%s %s\n' "${name%.*}" "${name##*.}"
  if [ "$FIX" -eq 1 ]; then
    case "$link$tgt$real" in
      *$'\t'*|*$'\n'*) echo "skip (tab or newline in a path, cannot log safely): $link" >&2; n_skipped=$((n_skipped+1)); continue ;;
    esac
    # re-check just before changing: still the same dangling link
    if [ -L "$link" ] && [ ! -e "$link" ] && [ "$(readlink -- "$link")" = "$tgt" ] && [ -e "$real" ]; then
      printf '%s\t%s\t%s\n' "$link" "$tgt" "$real" >> "$LOG"
      if repoint "$link" "$real"; then n_fixed=$((n_fixed+1)); else echo "FAILED: $link" >&2; n_skipped=$((n_skipped+1)); fi
    else
      echo "skip (changed meanwhile): $link" >&2; n_skipped=$((n_skipped+1))
    fi
  fi
done < <(find "$MOVIES" -maxdepth 1 -type l -print0)

{
  echo "dangling links      : $n_dangling"
  echo "  PLUS (listed)     : $n_plus"
  echo "  ambiguous (skip)  : $n_ambig"
  echo "  folder gone       : $n_nodir   (not handled here)"
  echo "  other mismatch    : $n_other   (not handled here: file renamed/upgraded)"
  if [ "$FIX" -eq 1 ]; then
    echo "re-pointed          : $n_fixed (skipped $n_skipped); undo log: $LOG"
    echo "Rows stay red until you press Start in the panel (or vod_checker re-probes)."
  else
    echo "read-only run, nothing changed. Press Start on the listed ids in the panel, about 20 at a time."
  fi
} >&2
exit 0
