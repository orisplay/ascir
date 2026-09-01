#!/usr/bin/env bash
# run_experiments.sh — run ASCIR experiments against a running network.
# Bring the network up first with ./rebuild.sh <n>, then run this with the same n.
#
# Usage:  ASCIR_ORGS="Org1MSP,Org2MSP,Org3MSP,Org4MSP" ./run_experiments.sh 4
set -euo pipefail
ASCIR="$HOME/research/ascir"
N="${1:-4}"
cd "$ASCIR"

echo "=== M4 staged latency (endorsement vs commit), n=$N ==="
node experiments/m4_staged.js --n "$N" --trials 30 \
  --out "experiments/results/m4_staged_n${N}.json"

echo ""
echo "M1/M2/M3 are driven by run_harness.py + score*.py — see network/scaling.md"
echo "for the per-metric commands (they depend on the chaincode being populated"
echo "with the seeded dataset first)."
