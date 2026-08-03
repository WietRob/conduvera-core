#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Hermes Buildroom Autopilot Runner
# Runs buildroom_loop.py --project peekxd in ticks until:
#   - a worker task is running (WAITING)
#   - a hard gate blocks (BLOCKED_*)
#   - cycle is complete (PROOF_COMPLETE / STOPPED_AFTER_*)
#   - max ticks reached
# ============================================================

export PYTHONPATH="$HOME/.hermes/scripts"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/bin:/usr/local/bin:$PATH"
PROJECT="peekxd"
LOOP="$HOME/.hermes/scripts/buildroom_loop.py"
STATE="$HOME/.hermes/research-vault/ops/peekxd-buildroom-v09/orchestrator-state.json"
LOCK="$HOME/.hermes/run/buildroom-autopilot.lock"
LOGDIR="$HOME/.hermes/logs/buildroom-autopilot"
mkdir -p "$(dirname "$LOCK")" "$LOGDIR"

# Lock: only one runner at a time
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -Is) SKIP: autopilot runner already active (lock held)"
  exit 0
fi

echo "$(date -Is) START buildroom autopilot ticker"

MAX_TICKS=10
SLEEP_SECONDS=30

for i in $(seq 1 "$MAX_TICKS"); do
  echo "$(date -Is) TICK $i/$MAX_TICKS"

  # Read current state BEFORE tick
  PHASE_BEFORE=$(python3 -c "import json; print(json.load(open('$STATE')).get('phase',''))" 2>/dev/null || echo "UNKNOWN")
  STATUS_BEFORE=$(python3 -c "import json; print(json.load(open('$STATE')).get('status',''))" 2>/dev/null || echo "UNKNOWN")

  echo "  before: phase=$PHASE_BEFORE status=$STATUS_BEFORE"

  # Run one tick
  python3 "$LOOP" --project "$PROJECT" 2>&1 || {
    rc=$?
    echo "$(date -Is) LOOP_ERROR exit_code=$rc"
    exit 0  # Don't retry on error — let next cron invocation handle it
  }

  # Read state AFTER tick
  PHASE=$(python3 -c "import json; print(json.load(open('$STATE')).get('phase',''))" 2>/dev/null)
  STATUS=$(python3 -c "import json; print(json.load(open('$STATE')).get('status',''))" 2>/dev/null)
  CYCLE=$(python3 -c "import json; print(json.load(open('$STATE')).get('cycle',''))" 2>/dev/null)
  PR=$(python3 -c "import json; print(json.load(open('$STATE')).get('pr_open',''))" 2>/dev/null)

  echo "  after:  cycle=$CYCLE phase=$PHASE status=$STATUS pr=$PR"

  # STOP conditions
  if [[ "$STATUS" == WAITING ]]; then
    echo "$(date -Is) STOP: waiting for active worker task ($PHASE)"
    exit 0
  fi

  if [[ "$STATUS" == HOLD_FOR_BOSS ]]; then
    echo "$(date -Is) STOP: terminal hold (${PHASE}: ${STATUS})"
    exit 0
  fi

  if [[ "$STATUS" == BLOCKED* ]]; then
    echo "$(date -Is) STOP: blocked ($STATUS)"
    exit 0
  fi

  if [[ "$STATUS" == PROOF_COMPLETE || "$PHASE" == STOPPED_AFTER_REPORTER ]]; then
    echo "$(date -Is) STOP: cycle $CYCLE complete"
    exit 0
  fi

  if [[ "$PHASE" == "$PHASE_BEFORE" && "$STATUS" == "$STATUS_BEFORE" ]]; then
    echo "  (no state change this tick — continuing)"
  fi

  sleep "$SLEEP_SECONDS"
done

echo "$(date -Is) STOP: max ticks ($MAX_TICKS) reached"
exit 0
