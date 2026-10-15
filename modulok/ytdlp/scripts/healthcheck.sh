#!/usr/bin/env bash
# healthcheck.sh - is the pipeline runnable, right now, on whatever drive it
# currently sits on? Read-only: dependency check + a structural validate of
# staging/. No network, no download.
#
#   scripts/healthcheck.sh
#
# Exits 0 and prints "PIPELINE OK" when both checks pass, 1 otherwise.

set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P) || exit 1
ROOT=$(dirname "$SCRIPT_DIR")
cd "$ROOT" || exit 1

# Same interpreter-resolution order as crawl_status.sh, so this never depends
# on which venv happens to be active in the calling shell.
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

START=$(date +%s)
FAIL=0

echo "== 1/2 függőségek és útvonalak (download.py --check) =="
CHECK_OUT=$("$PY" scripts/download.py --check 2>&1)
echo "$CHECK_OUT"
if printf '%s\n' "$CHECK_OUT" | grep -q 'MISSING'; then
  FAIL=1
fi

echo
echo "== 2/2 staging/ szerkezeti ellenőrzése (validate.py) =="
if ! "$PY" scripts/validate.py; then
  FAIL=1
fi

ELAPSED=$(($(date +%s) - START))
echo
if [ "$FAIL" -eq 0 ]; then
  echo "PIPELINE OK (${ELAPSED}s, interpreter: $PY)"
  exit 0
else
  echo "PIPELINE HIBÁS (${ELAPSED}s) - lásd a fenti MISSING / hibaüzeneteket"
  exit 1
fi
