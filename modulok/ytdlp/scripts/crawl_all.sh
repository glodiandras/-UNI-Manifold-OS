#!/usr/bin/env bash
# crawl_all.sh - stage every video under a listing page, unattended.
#
#   scripts/crawl_all.sh https://zanza.tv/irodalom               # in this terminal
#   scripts/crawl_all.sh --background https://zanza.tv/irodalom  # survives closing it
#   scripts/crawl_all.sh --stop                                  # ends a running one
#
# A thin shell around the pipeline's own commands, like the Manifold-pult: it has
# no ingestion logic of its own. It adds what an hours-long run needs:
#
#   1. pre-flight   download.py --check, and a speech-to-text backend must exist
#   2. rounds       download.py --crawl (discovery, download, transcript), run
#                   again after a pause while videos failed - YouTube's
#                   occasional HTTP 403 passes, an age-gated video does not
#   3. transcripts  transcribe.py --pending, for any that failed inline
#   4. check        validate.py --repair-archive
#
# plus a log file in the configured log directory, a lock against two runs at
# once, and caffeinate so that the Mac does not fall asleep halfway through.
#
# Re-running is always safe: a video that is already staged is neither read
# nor downloaded again, so a second run only does what the first left undone.

set -u

usage() {
  cat <<'EOF'
usage: scripts/crawl_all.sh [options] URL|FILE ...
       scripts/crawl_all.sh --stop

Stage every video under one or more listing pages (a subject or topic page,
or a file with one such URL per line) with transcripts, retry what failed,
then check the staging tree. Safe to re-run: staged videos are skipped.

options:
  --background     keep running after the terminal is closed; prints the log path
  --stop           stop the run that is in progress
  --retries N      extra rounds while videos fail (default: 2)
  --pause SECONDS  wait before each extra round (default: 600)
  --max-items N    most videos accepted under one page (default: 500)
  --dry-run        discover and plan only, download nothing
  -h, --help       show this help

environment:
  MSP_PYTHON       interpreter to use (default: the active virtualenv, then
                   .venv.nosync, then .venv, then python3)
EOF
}

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P) || exit 1
SELF="$SCRIPT_DIR/$(basename "$0")"
ROOT=$(dirname "$SCRIPT_DIR")
cd "$ROOT" || exit 1

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
# Without this, Python block-buffers into the pipes below and progress arrives
# in bursts instead of line by line.
export PYTHONUNBUFFERED=1

die() {
  local code=$1
  shift
  printf 'ERROR: %s\n' "$*" >&2
  exit "$code"
}

need_number() {
  case ${2-} in
    '' | *[!0-9]*) die 64 "$1 needs a whole number, got '${2-}'" ;;
  esac
}

RETRIES=2
PAUSE=600
MAX_ITEMS=500
DRY_RUN=0
BACKGROUND=0
STOP=0
TARGETS=()
ARGS=("$@")

while [ $# -gt 0 ]; do
  case $1 in
    --background) BACKGROUND=1 ;;
    --stop) STOP=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --retries) need_number "$1" "${2-}"; RETRIES=$2; shift ;;
    --pause) need_number "$1" "${2-}"; PAUSE=$2; shift ;;
    --max-items) need_number "$1" "${2-}"; MAX_ITEMS=$2; shift ;;
    -h | --help) usage; exit 0 ;;
    --) shift; while [ $# -gt 0 ]; do TARGETS+=("$1"); shift; done; break ;;
    -*) usage >&2; die 64 "unknown option: $1" ;;
    *) TARGETS+=("$1") ;;
  esac
  shift
done

if [ "$STOP" = 0 ] && [ ${#TARGETS[@]} -eq 0 ]; then
  usage >&2
  die 64 "give at least one listing page URL, e.g. https://zanza.tv/irodalom"
fi
# A plan has nothing to retry and nothing to transcribe.
[ "$DRY_RUN" = 1 ] && RETRIES=0

# --- pre-flight -------------------------------------------------------------

CHECK=$("$PY" scripts/download.py --check 2>&1) || {
  printf '%s\n' "$CHECK" >&2
  die 69 "the pipeline does not start with $PY - see above (is the virtualenv set up? README section 3)"
}
case $CHECK in
  *"yt-dlp        : MISSING"*)
    printf '%s\n' "$CHECK" >&2
    die 69 "yt-dlp is missing: $PY -m pip install -e ." ;;
esac

# The log directory is whatever config/config.yaml says it is.
LOG_DIR=$(printf '%s\n' "$CHECK" | sed -n 's/^log_dir *: //p' | head -n 1)
[ -n "$LOG_DIR" ] || LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" || die 73 "cannot create the log directory $LOG_DIR"
LOCK="$LOG_DIR/crawl_all.lock"

# PID of the run that holds the lock, if that process is still a crawl_all run.
running_pid() {
  local pid
  pid=$(cat "$LOCK/pid" 2>/dev/null) || return 1
  case $pid in '' | *[!0-9]*) return 1 ;; esac
  ps -p "$pid" -o command= 2>/dev/null | grep -qF "$(basename "$SELF")" || return 1
  echo "$pid"
}

if [ "$STOP" = 1 ]; then
  pid=$(running_pid) || { echo "No crawl_all.sh run is in progress."; exit 0; }
  pgid=$(ps -o pgid= -p "$pid" | tr -d ' ')
  if [ "$pgid" = "$pid" ]; then
    kill -TERM -- "-$pid"  # the whole run at once: shell, python, tee, caffeinate
  else
    kill -TERM "$pid"
    pkill -TERM -P "$pid"
  fi
  echo "Stopped the run with PID $pid."
  echo "Nothing is lost: start the same command again to continue where it stopped."
  exit 0
fi

if [ "$DRY_RUN" = 0 ]; then
  BACKENDS=$("$PY" scripts/transcribe.py --list-backends 2>&1)
  # 'subtitles' reports itself available without a folder, but zanza.tv videos
  # carry no subtitles - only a speech-to-text engine makes a transcript here.
  if ! printf '%s\n' "$BACKENDS" | grep -v '^subtitles' | grep -Eq '^[a-z_]+[[:space:]]+available'; then
    printf '%s\n' "$BACKENDS" >&2
    die 69 "no speech-to-text backend is available, so every video would stay without a transcript.
       Install one first:  $PY -m pip install -e '.[faster-whisper]'"
  fi
fi

if pid=$(running_pid); then
  die 75 "another crawl_all.sh run is in progress (PID $pid). Wait for it, or: $SELF --stop"
fi

# --- detach -----------------------------------------------------------------

if [ "$BACKGROUND" = 1 ] && [ -z "${CRAWL_ALL_LOG:-}" ]; then
  LOG="$LOG_DIR/crawl_all-$(date +%Y%m%d-%H%M%S).log"
  # A session of its own: closing the terminal does not end it, and --stop can
  # end the whole process group at once. macOS has no setsid(1), hence Python.
  DETACH=$'import os, sys\ntry:\n    os.setsid()\nexcept OSError:\n    pass\nos.execv(sys.argv[1], sys.argv[1:])'
  CRAWL_ALL_LOG=$LOG nohup "$PY" -c "$DETACH" "$BASH" "$SELF" ${ARGS[@]+"${ARGS[@]}"} \
    >>"$LOG" 2>&1 </dev/null &
  echo "Started in the background (PID $!)."
  echo "  follow it:  tail -f \"$LOG\""
  echo "  stop it:    \"$SELF\" --stop"
  exit 0
fi

if [ -n "${CRAWL_ALL_LOG:-}" ]; then
  LOG=$CRAWL_ALL_LOG  # detached: stdout already goes there
else
  LOG="$LOG_DIR/crawl_all-$(date +%Y%m%d-%H%M%S).log"
  # Ctrl-C, --stop or a closed terminal end the run, not its log: this tee
  # ignores them and stops only when the run's output ends.
  exec > >(trap '' INT TERM HUP; exec tee -a "$LOG") 2>&1
fi

# --- the run ----------------------------------------------------------------

mkdir "$LOCK" 2>/dev/null || {
  # Taken since the check above, or left behind by a run that was killed.
  if pid=$(running_pid); then
    die 75 "another crawl_all.sh run is in progress (PID $pid). Wait for it, or: $SELF --stop"
  fi
  rm -f "$LOCK/pid"
  rmdir "$LOCK" 2>/dev/null
  mkdir "$LOCK" 2>/dev/null
} || die 75 "cannot take the lock $LOCK - is another run starting right now?"
echo $$ >"$LOCK/pid"

ROUND_OUT=""
cleanup() {
  [ -n "$ROUND_OUT" ] && rm -f "$ROUND_OUT"
  if [ "$(cat "$LOCK/pid" 2>/dev/null)" = "$$" ]; then
    rm -f "$LOCK/pid"
    rmdir "$LOCK" 2>/dev/null
  fi
}
stopped() {
  printf '\nStopped. Nothing is lost: start the same command again to continue where this run stopped.\n'
  exit "$1"
}
trap cleanup EXIT
trap 'stopped 130' INT
trap 'stopped 143' TERM
trap 'stopped 129' HUP

ROUND_OUT=$(mktemp "${TMPDIR:-/tmp}/crawl_all.XXXXXX") || die 73 "cannot create a temporary file"

# Keep the Mac awake while this shell lives. A closed MacBook lid still sleeps.
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -i -s -w $$ >/dev/null 2>&1 &
fi

section() { printf '\n==== %s ====\n' "$*"; }
elapsed() { printf '%dh %02dm' $((SECONDS / 3600)) $((SECONDS % 3600 / 60)); }

section "crawl_all.sh  $(date '+%Y-%m-%d %H:%M')"
echo "pages   : ${TARGETS[*]}"
echo "rounds  : up to $((RETRIES + 1)), ${PAUSE}s apart; at most $MAX_ITEMS videos per page"
echo "python  : $PY"
echo "log     : $LOG"
echo "PID     : $$"
printf '%s\n' "$CHECK"

CRAWL=(scripts/download.py --crawl --max-items "$MAX_ITEMS")
[ "$DRY_RUN" = 1 ] && CRAWL+=(--dry-run)

round=0
code=0
incomplete=""  # why the last round left work undone; empty when it did not
while :; do
  round=$((round + 1))
  section "Round $round/$((RETRIES + 1)) - download.py --crawl  ($(date '+%H:%M'))"
  "$PY" "${CRAWL[@]}" "${TARGETS[@]}" 2>&1 | tee -i "$ROUND_OUT"
  code=${PIPESTATUS[0]}
  incomplete=""
  case $code in
    0)
      # A page that failed to load hides the videos below it without failing
      # the run; the crawl summary line is the only place that says so.
      grep -Eq '^Crawl found .*[0-9]+ unreadable\)' "$ROUND_OUT" || break
      incomplete="some pages could not be read, so videos under them may be missing" ;;
    1) incomplete="some videos failed" ;;
    75) incomplete="the site could not be reached" ;;
    129 | 130 | 143) stopped "$code" ;;
    *) break ;;  # usage, configuration, missing dependency: waiting will not help
  esac
  if [ "$round" -gt "$RETRIES" ]; then
    printf '\nNo rounds left: %s.\n' "$incomplete"
    break
  fi
  printf '\n%s - next round in %ss.\n' "$incomplete" "$PAUSE"
  sleep "$PAUSE"
done

transcribe_code=""
validate_code=""
case $code in
  0 | 1 | 75)
    if [ "$DRY_RUN" = 0 ]; then
      section "Transcripts still pending"
      "$PY" scripts/transcribe.py --pending || transcribe_code=$?
      section "Staging tree check"
      "$PY" scripts/validate.py --repair-archive || validate_code=$?
    fi ;;
esac

# --- summary ----------------------------------------------------------------

section "Summary"
echo "pages   : ${TARGETS[*]}"
echo "rounds  : $round, elapsed $(elapsed)"
if grep -q '^Downloaded: ' "$ROUND_OUT"; then
  echo "last round (Skipped = staged by an earlier round or an earlier run):"
  sed -n '/^Downloaded: /,$p' "$ROUND_OUT" | sed 's/^/  /'
fi
echo "log     : $LOG"
echo

if [ "$code" = 1 ]; then
  failed=$(sed -n 's/^Failed: \([0-9][0-9]*\)$/\1/p' "$ROUND_OUT" | tail -n 1)
  incomplete="${failed:-some} video(s) failed in every round, listed above"
fi

if [ "$DRY_RUN" = 1 ]; then
  echo "Dry run: nothing was downloaded."
elif [ "$code" = 0 ] && [ -z "$incomplete" ] && [ -z "$transcribe_code" ] && [ -z "$validate_code" ]; then
  echo "OK - every video found is staged with its transcript, and the staging tree is valid."
else
  case $code in
    0 | 1 | 75)
      [ -n "$incomplete" ] &&
        echo "NOT COMPLETE - $incomplete. Run the same command later: it only does what is still missing." ;;
    *)
      echo "STOPPED - download.py ended with exit code $code (see its message above);" \
        "waiting would not help, so it was not retried." ;;
  esac
  [ -n "$transcribe_code" ] &&
    echo "Some transcripts failed - retry them with: python3 scripts/transcribe.py --pending"
  [ -n "$validate_code" ] &&
    echo "The staging tree check reported errors - see 'Staging tree check' above."
fi

if [ "$code" != 0 ]; then
  exit "$code"
elif [ -n "$incomplete" ] || [ -n "$transcribe_code" ] || [ -n "$validate_code" ]; then
  exit 1
fi
exit 0
