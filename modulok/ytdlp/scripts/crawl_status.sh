#!/usr/bin/env bash
# crawl_status.sh - how far has the scripts/crawl_all.sh run got? Read-only.
#
#   scripts/crawl_status.sh              # the state, once
#   scripts/crawl_status.sh --watch      # refreshed every minute until the run ends
#   scripts/crawl_status.sh --watch 20   # ... every 20 seconds
#
# Reads the newest logs/crawl_all-*.log (what the run printed), its lock (is
# the run alive) and the pipeline log (timestamps, for the estimated finish).
# It writes nothing and never touches the run itself.

set -u

usage() {
  cat <<'EOF'
usage: scripts/crawl_status.sh [--watch [SECONDS]]

Show how far the current or the last scripts/crawl_all.sh run has got.
  -w, --watch [SECONDS]  refresh every SECONDS (default: 60) until the run ends
  -h, --help             show this help
EOF
}

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P) || exit 1
ROOT=$(dirname "$SCRIPT_DIR")
cd "$ROOT" || exit 1

WATCH=0
EVERY=60
while [ $# -gt 0 ]; do
  case $1 in
    -w | --watch)
      WATCH=1
      case ${2-} in '' | *[!0-9]*) ;; *) EVERY=$2; shift ;; esac ;;
    -h | --help) usage; exit 0 ;;
    *) usage >&2; echo "ERROR: unknown argument: $1" >&2; exit 64 ;;
  esac
  shift
done
[ "$EVERY" -gt 0 ] || EVERY=60

# The same interpreter, and so the same log directory, as crawl_all.sh.
if [ -n "${MSP_PYTHON:-}" ]; then
  PY=$MSP_PYTHON
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python3" ]; then
  PY="$VIRTUAL_ENV/bin/python3"
elif [ -x "$ROOT/.venv.nosync/bin/python3" ]; then
  PY="$ROOT/.venv.nosync/bin/python3"
elif [ -x "$ROOT/.venv/bin/python3" ]; then
  PY="$ROOT/.venv/bin/python3"
else
  PY=python3
fi
LOG_DIR=$("$PY" scripts/download.py --check 2>/dev/null | sed -n 's/^log_dir *: //p' | head -n 1)
[ -n "$LOG_DIR" ] || LOG_DIR="$ROOT/logs"
LOCK="$LOG_DIR/crawl_all.lock"

running_pid() {
  local pid
  pid=$(cat "$LOCK/pid" 2>/dev/null) || return 1
  case $pid in '' | *[!0-9]*) return 1 ;; esac
  ps -p "$pid" -o command= 2>/dev/null | grep -qF crawl_all.sh || return 1
  echo "$pid"
}

# "YYYY-MM-DD HH:MM:SS" <-> epoch seconds: BSD date on macOS, GNU date elsewhere.
epoch() { date -j -f '%Y-%m-%d %H:%M:%S' "$1" +%s 2>/dev/null || date -d "$1" +%s 2>/dev/null; }
clock() { date -r "$1" +%H:%M 2>/dev/null || date -d "@$1" +%H:%M 2>/dev/null; }

# "<batch start>|<last video finished>|<videos finished>" for the newest crawl
# batch, from the timestamps of the pipeline log (the run spans midnight, so
# the last two daily files are read).
pace() {
  ls -1 "$LOG_DIR"/pipeline-*.log 2>/dev/null | tail -n 2 |
    while IFS= read -r file; do cat "$file"; done |
    awk '/ msp Crawl: [0-9]+ to stage/ { start = substr($0, 1, 19); n = 0; last = "" }
         / msp (OK: |FAILED )/ { if (start != "") { n++; last = substr($0, 1, 19) } }
         END { if (n > 0) print start "|" last "|" n }'
}

status() {
  local log pid n section header found todo skipped ok failed m cur title progress
  local start last count s l avg remaining lastline
  log=$(ls -1 "$LOG_DIR"/crawl_all-*.log 2>/dev/null | tail -n 1)
  if [ -z "$log" ]; then
    echo "Még nem volt crawl_all.sh futás (nincs napló itt: $LOG_DIR)."
    return
  fi

  echo "crawl_all.sh állapota - $(date '+%Y-%m-%d %H:%M')"
  if pid=$(running_pid); then
    echo "  fut:          igen (PID $pid), leállítás: scripts/crawl_all.sh --stop"
  else
    echo "  fut:          nem"
  fi
  echo "  napló:        ${log#"$ROOT"/}"

  if grep -q '^==== Summary ====' "$log"; then
    echo
    sed -n '/^==== Summary ====/,$p' "$log"
    return
  fi

  n=$(grep -n '^==== Round ' "$log" | tail -n 1 | cut -d: -f1)
  if [ -z "$n" ]; then
    echo
    tail -n 5 "$log"
    return
  fi
  section=$(tail -n +"$n" "$log")
  header=$(printf '%s\n' "$section" | head -n 1 |
    sed -n 's/^==== Round \([0-9]*\/[0-9]*\) .*(\([0-9:]*\)) ====$/\1 (indult: \2)/p')
  echo "  kör:          $header"

  found=$(printf '%s\n' "$section" | sed -n 's/^Crawl found \([0-9]*\) video.*/\1/p' | tail -n 1)
  read -r todo skipped <<EOF
$(printf '%s\n' "$section" | sed -n 's/^Crawl: \([0-9]*\) to stage, \([0-9]*\) already staged.*/\1 \2/p' | tail -n 1)
EOF
  if [ -z "$found" ]; then
    # Still reading listing pages, before the first download.
    echo "  felderítés:   $(printf '%s\n' "$section" | grep -o '\[[0-9]* read, [0-9]* queued\]' | tail -n 1)"
    return
  fi
  echo "  talált:       $found videó, ebből ${skipped:-0} már korábban kész volt, ${todo:-0} letöltendő"

  ok=$(printf '%s\n' "$section" | grep -c '^OK: ')
  failed=$(printf '%s\n' "$section" | grep -c '^ERROR: FAILED ')
  echo "  kész:         $ok/${todo:-0}, sikertelen: $failed"

  # The video in progress: everything after the last "[i/N] URL" line, unless
  # that one has already finished.
  m=$(printf '%s\n' "$section" | grep -n '^\[[0-9]*/[0-9]*\] ' | tail -n 1 | cut -d: -f1)
  if [ -n "$m" ]; then
    cur=$(printf '%s\n' "$section" | tail -n +"$m")
    if ! printf '%s\n' "$cur" | grep -q '^OK: \|^ERROR: FAILED '; then
      title=$(printf '%s\n' "$cur" | sed -n 's/^Downloading: //p' | tail -n 1)
      progress=$(printf '%s\n' "$cur" | sed -n 's/.*transcribed .*(\([0-9]*%\)).*/\1/p' | tail -n 1)
      [ -n "$title" ] || title=$(printf '%s\n' "$cur" | head -n 1 | cut -d' ' -f2)
      echo "  most:         $(printf '%s\n' "$cur" | head -n 1 | cut -d' ' -f1) $title${progress:+ (transcript: $progress)}"
    fi
  fi

  IFS='|' read -r start last count <<EOF
$(pace)
EOF
  if [ -n "$start" ] && [ -n "$todo" ] && [ "${count:-0}" -gt 0 ] && running_pid >/dev/null; then
    s=$(epoch "$start")
    l=$(epoch "$last")
    if [ -n "$s" ] && [ -n "$l" ]; then
      avg=$(((l - s) / count))
      remaining=$((todo - ok - failed))
      [ "$remaining" -ge 0 ] || remaining=0
      echo "  várható vége: kb. $(clock $(($(date +%s) + avg * remaining))) (még $remaining videó, átlag $((avg / 60)) perc $((avg % 60)) mp/videó)"
    fi
  fi

  if [ "$failed" -gt 0 ]; then
    echo "  sikertelen ebben a körben (ha marad kör, újrapróbálja):"
    printf '%s\n' "$section" | sed -n 's/^ERROR: FAILED /    - /p' | cut -c1-150
  fi

  lastline=$(grep -v '^[[:space:]]*$' "$log" | tail -n 1)
  case $lastline in
    *"next round in"*) echo "  most:         szünet a következő kör előtt ($lastline)" ;;
  esac
}

if [ "$WATCH" = 0 ]; then
  status
  exit 0
fi
while :; do
  [ -t 1 ] && printf '\033[H\033[2J'
  status
  running_pid >/dev/null || break
  echo
  echo "(frissítés ${EVERY} mp-enként, kilépés: Ctrl-C - a letöltés ettől nem áll le)"
  sleep "$EVERY"
done
