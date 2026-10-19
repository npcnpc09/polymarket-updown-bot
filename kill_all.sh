#!/bin/bash
# Stop all sims started by run_all.sh
pkill -f "ws_paper_executor.py" 2>/dev/null
pkill -f "ws_arb_observer.py" 2>/dev/null
pkill -f "arb_scanner_observe.py" 2>/dev/null
pkill -f "v8_mirror_sim.py" 2>/dev/null
echo "all sims stopped"
