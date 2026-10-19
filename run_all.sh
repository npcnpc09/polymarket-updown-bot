#!/bin/bash
# Start all 4 sims in parallel.
# Requires: POLY_PK and POLY_PROXY env vars set.

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Load .env if exists
if [ -f "$ROOT/.env" ]; then
    set -a
    source "$ROOT/.env"
    set +a
fi

# Check credentials
if [ -z "$POLY_PK" ] || [ -z "$POLY_PROXY" ]; then
    echo "ERROR: POLY_PK and POLY_PROXY env vars not set."
    echo "Copy .env.example to .env, fill it, and re-run."
    exit 1
fi

mkdir -p "$ROOT/data"
cd "$ROOT/data"

echo "=== Starting 4 sims ==="

python "$ROOT/scripts/ws_paper_executor.py" > ws_paper_executor.log 2>&1 &
echo "  ws_paper_executor    PID $!"

python "$ROOT/scripts/ws_arb_observer.py" > ws_observer.log 2>&1 &
echo "  ws_arb_observer      PID $!"

python "$ROOT/scripts/arb_scanner_observe.py" --interval 8 > arb_scanner.log 2>&1 &
echo "  arb_scanner_observe  PID $!"

python "$ROOT/scripts/v8_mirror_sim.py" --interval 10 > v8_mirror.log 2>&1 &
echo "  v8_mirror_sim        PID $!"

echo ""
echo "Monitor with:  tail -F data/ws_paper_executor.log | grep -E 'PAIR|SETTLE|STAT'"
echo "Stop all:      ./kill_all.sh"
