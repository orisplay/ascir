#!/usr/bin/env bash
# rebuild.sh — bring up the ASCIR Fabric network at n=2, 3, or 4 organizations.
#
# Reproduces the known-good build sequence: teardown -> up (n=2) -> deployCC v1.3
# -> addOrg3 -> addOrg4, installing and approving the chaincode on each org.
# Applies BatchTimeout=200ms so latency (M4) matches the paper's configuration.
#
# Usage:
#   ./rebuild.sh 2       # two-org network
#   ./rebuild.sh 3       # three-org network
#   ./rebuild.sh 4       # four-org network (default)
#
# Prerequisites: Fabric 2.5.15 samples at $FABRIC, ASCIR repo at $ASCIR,
# addOrg4 assets under $FABRIC/test-network/addOrg4/.
set -euo pipefail

# ---- paths (edit if your layout differs) ----------------------------------
FABRIC="$HOME/research/fabric-samples"
ASCIR="$HOME/research/ascir"
CC_PATH="$ASCIR/chaincode/ascir"
CC_NAME="ascir"
CC_VER="1.3"
CC_SEQ="1"
CHANNEL="mychannel"
PKG_ID="ascir_1.3:c267277527610827d9b7fc97970c6d0fb3b74a050063f75fb3f2e4ee6a7e3991"
BATCH_TIMEOUT="200ms"

N="${1:-4}"
if [[ "$N" != "2" && "$N" != "3" && "$N" != "4" ]]; then
  echo "ERROR: org count must be 2, 3, or 4 (got '$N')"; exit 1
fi

TN="$FABRIC/test-network"
export PATH="$PATH:$FABRIC/bin"
export FABRIC_CFG_PATH="$FABRIC/config"
ORDERER_CA="$TN/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem"

say() { echo -e "\n=== $* ==="; }

# ---- org env helper -------------------------------------------------------
set_org() {
  local msp="$1" port="$2" org="$3"
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_LOCALMSPID="$msp"
  export CORE_PEER_TLS_ROOTCERT_FILE="$TN/organizations/peerOrganizations/$org.example.com/peers/peer0.$org.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="$TN/organizations/peerOrganizations/$org.example.com/users/Admin@$org.example.com/msp"
  export CORE_PEER_ADDRESS="localhost:$port"
}

install_approve() {  # $1=msp $2=port $3=org
  set_org "$1" "$2" "$3"
  peer lifecycle chaincode install "$TN/ascir.tar.gz"
  peer lifecycle chaincode approveformyorg -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com --tls --cafile "$ORDERER_CA" \
    --channelID "$CHANNEL" --name "$CC_NAME" --version "$CC_VER" \
    --package-id "$PKG_ID" --sequence "$CC_SEQ" || \
    echo "  (approve returned non-zero — harmless if already committed; querycommitted is authoritative)"
}

# ===========================================================================
say "STEP 0  set BatchTimeout=$BATCH_TIMEOUT"
sed -i "s/BatchTimeout: [0-9a-z]*/BatchTimeout: $BATCH_TIMEOUT/" "$TN/configtx/configtx.yaml"
grep -n "BatchTimeout" "$TN/configtx/configtx.yaml"

say "STEP 1  teardown"
cd "$TN"
./network.sh down
docker volume prune -f

say "STEP 2  bring up n=2 with channel"
./network.sh up createChannel -c "$CHANNEL" -ca

say "STEP 3  deploy chaincode v$CC_VER"
./network.sh deployCC -ccn "$CC_NAME" -ccp "$CC_PATH" -ccl go -ccv "$CC_VER" -ccs "$CC_SEQ"

if [[ "$N" == "2" ]]; then
  say "DONE — n=2 network up, chaincode committed."
  peer lifecycle chaincode querycommitted --channelID "$CHANNEL" --name "$CC_NAME" --output json | grep -A4 approvals
  exit 0
fi

say "STEP 4  add Org3"
cd "$TN/addOrg3"
./addOrg3.sh up -c "$CHANNEL"
cd "$TN"
install_approve "Org3MSP" 11051 "org3"

if [[ "$N" == "3" ]]; then
  say "DONE — n=3 network up."
  peer lifecycle chaincode querycommitted --channelID "$CHANNEL" --name "$CC_NAME" --output json | grep -A5 approvals
  exit 0
fi

say "STEP 5  add Org4 (hand-built)"
cd "$TN"
# Stage Org4 source assets from the repo so a clean clone can build n=4.
cp -n "$ASCIR/network/addOrg4/org4-crypto.yaml" "$TN/addOrg4/" 2>/dev/null || true
cp -n "$ASCIR/network/addOrg4/configtx.yaml"    "$TN/addOrg4/" 2>/dev/null || true
cp -rn "$ASCIR/network/addOrg4/compose"         "$TN/addOrg4/" 2>/dev/null || true
# 5a crypto
cryptogen generate --config=addOrg4/org4-crypto.yaml --output=organizations
# 5b org def + fetch config + splice
FABRIC_CFG_PATH="$TN/addOrg4" configtxgen -printOrg Org4MSP \
  > organizations/peerOrganizations/org4.example.com/org4.json
export FABRIC_CFG_PATH="$FABRIC/config"
mkdir -p addOrg4/channel-artifacts
set_org "Org1MSP" 7051 "org1"
peer channel fetch config addOrg4/channel-artifacts/config_block.pb -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com -c "$CHANNEL" --tls --cafile "$ORDERER_CA"
configtxlator proto_decode --input addOrg4/channel-artifacts/config_block.pb --type common.Block \
  --output addOrg4/channel-artifacts/config_block.json
jq '.data.data[0].payload.data.config' addOrg4/channel-artifacts/config_block.json \
  > addOrg4/channel-artifacts/config.json
jq -s '.[0] * {"channel_group":{"groups":{"Application":{"groups":{"Org4MSP":.[1]}}}}}' \
  addOrg4/channel-artifacts/config.json organizations/peerOrganizations/org4.example.com/org4.json \
  > addOrg4/channel-artifacts/modified_config.json
configtxlator proto_encode --input addOrg4/channel-artifacts/config.json --type common.Config \
  --output addOrg4/channel-artifacts/config.pb
configtxlator proto_encode --input addOrg4/channel-artifacts/modified_config.json --type common.Config \
  --output addOrg4/channel-artifacts/modified_config.pb
configtxlator compute_update --channel_id "$CHANNEL" \
  --original addOrg4/channel-artifacts/config.pb --updated addOrg4/channel-artifacts/modified_config.pb \
  --output addOrg4/channel-artifacts/org4_update.pb
configtxlator proto_decode --input addOrg4/channel-artifacts/org4_update.pb --type common.ConfigUpdate \
  --output addOrg4/channel-artifacts/org4_update.json
echo '{"payload":{"header":{"channel_header":{"channel_id":"'"$CHANNEL"'", "type":2}},"data":{"config_update":'"$(cat addOrg4/channel-artifacts/org4_update.json)"'}}}' \
  | jq . > addOrg4/channel-artifacts/org4_update_in_envelope.json
configtxlator proto_encode --input addOrg4/channel-artifacts/org4_update_in_envelope.json \
  --type common.Envelope --output addOrg4/channel-artifacts/org4_update_in_envelope.pb
# 5c sign (Org1, Org2) + submit (Org3)
ENV=addOrg4/channel-artifacts/org4_update_in_envelope.pb
set_org "Org1MSP" 7051 "org1"; peer channel signconfigtx -f "$ENV"
set_org "Org2MSP" 9051 "org2"; peer channel signconfigtx -f "$ENV"
set_org "Org3MSP" 11051 "org3"
peer channel update -f "$ENV" -c "$CHANNEL" -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com --tls --cafile "$ORDERER_CA"
# 5d bring up Org4 peer
( cd addOrg4/compose && export DOCKER_SOCK=/var/run/docker.sock && \
  docker compose -f compose-org4.yaml -f docker/docker-compose-org4.yaml up -d )
sleep 3
# 5e genesis fetch, join, install, approve
set_org "Org1MSP" 7051 "org1"
peer channel fetch 0 addOrg4/channel-artifacts/mychannel_genesis.block -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com -c "$CHANNEL" --tls --cafile "$ORDERER_CA"
set_org "Org4MSP" 13051 "org4"
peer channel join -b addOrg4/channel-artifacts/mychannel_genesis.block
install_approve "Org4MSP" 13051 "org4"

say "DONE — n=4 network up."
peer lifecycle chaincode querycommitted --channelID "$CHANNEL" --name "$CC_NAME" --output json | grep -A6 approvals
