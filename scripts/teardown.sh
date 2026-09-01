#!/usr/bin/env bash
# teardown.sh — fully tear down the ASCIR Fabric network (all orgs + volumes).
set -uo pipefail
FABRIC="$HOME/research/fabric-samples"
TN="$FABRIC/test-network"
export PATH="$PATH:$FABRIC/bin"
echo "=== removing Org4 peer + volume (hand-built, outside network.sh) ==="
docker rm -f peer0.org4.example.com 2>/dev/null || true
docker volume rm compose_peer0.org4.example.com 2>/dev/null || true
echo "=== network.sh down ==="
cd "$TN"
./network.sh down
docker volume prune -f
echo "=== verify clean ==="
docker ps -a --format '{{.Names}}' | grep -E 'peer|orderer|ca_' || echo "all clean"
