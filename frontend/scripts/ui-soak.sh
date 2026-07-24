#!/usr/bin/env bash
# UI soak: loop the exploratory clickpath crawl (explore.spec.ts) with a fresh seed
# each iteration until a deadline, catching runtime errors across varied clickpaths.
# Passing runs' artifacts are discarded; failures are kept + their clickpath logged.
#   Usage: bash scripts/ui-soak.sh [duration_seconds]   (default 21600 = 6h)
set -u
cd "$(dirname "$0")/.." || exit 1

DURATION=${1:-21600}
END=$(( $(date +%s) + DURATION ))
SOAK=tests/e2e/soak
mkdir -p "$SOAK"
LOG="$SOAK/soak.log"
FINDINGS="$SOAK/findings.log"
: > "$LOG"; : > "$FINDINGS"

i=0; pass=0; fail=0
echo "SOAK start $(date '+%F %T') — running ${DURATION}s (until epoch $END)" | tee -a "$LOG"

while [ "$(date +%s)" -lt "$END" ]; do
  i=$((i+1))
  seed=$(( (RANDOM * 32768 + RANDOM) % 1000000 ))
  out=$(SEED="$seed" npx playwright test explore.spec.ts --reporter=line 2>&1)
  ts=$(date '+%T')
  if echo "$out" | grep -qE '^\s*1 passed'; then
    pass=$((pass+1))
    hyd=$(echo "$out" | grep -c 'hydration' || true)
    echo "$ts iter $i seed $seed: pass  [tot ${pass}ok/${fail}fail]" >> "$LOG"
    rm -rf test-results/* 2>/dev/null
  else
    fail=$((fail+1))
    echo "$ts iter $i seed $seed: FAIL  [tot ${pass}ok/${fail}fail]" >> "$LOG"
    {
      echo "=== $ts  iter $i  seed $seed  FAIL ==="
      echo "$out" | grep -A8 -iE 'uncaught error|5xx\.|Error:|clickpath:' | head -16
      echo ""
    } >> "$FINDINGS"
    # preserve the failing artifacts (screenshot + trace) for this seed
    mv test-results/explore-* "$SOAK/fail-i${i}-seed${seed}" 2>/dev/null
  fi
done

echo "SOAK done $(date '+%F %T'): $i iterations, $pass pass, $fail fail" | tee -a "$LOG"
