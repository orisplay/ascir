# ASCIR Network — Deployment and Invocation (n = 2, proof of concept)

This document records the verified procedure for deploying the ASCIR
chaincode to a Hyperledger Fabric test network and invoking its functions.
It corresponds to the n = 2 configuration (the BICIR replication baseline):
the stock Fabric `test-network` with two peer organisations (Org1MSP,
Org2MSP) and a single channel `mychannel`.

Platform: Hyperledger Fabric v2.5.15 (decision D3). The chaincode is the
`package main` program in `chaincode/ascir` (module
`github.com/orisplay/ascir/chaincode`).

## Prerequisites (one-time, already done on the dev machine)

- Docker Engine (running; user in the `docker` group)
- `jq` (`sudo apt-get install -y jq`) — required by the test-network scripts
- Fabric 2.5.15 binaries and images, installed via `install-fabric.sh` into
  `~/research/fabric-samples`, with `~/research/fabric-samples/bin` on PATH
- Go 1.26.x (for local `go build`/`go test` of the chaincode)

## 1. Bring up the network with a channel

```bash
cd ~/research/fabric-samples/test-network
./network.sh up createChannel
```

Brings up orderer + peer0.org1 + peer0.org2, creates channel `mychannel`,
joins both peers, and sets anchor peers. Success ends with
`Channel 'mychannel' joined`.

## 2. Deploy the ASCIR chaincode

```bash
cd ~/research/fabric-samples/test-network
./network.sh deployCC -ccn ascir -ccp ~/research/ascir/chaincode/ascir -ccl go
```

Packages, builds (in the ccenv container), installs on both peers, approves
for both orgs, and commits the definition. Success ends with
`Committed chaincode definition for chaincode 'ascir' on channel 'mychannel'`
and `Approvals: [Org1MSP: true, Org2MSP: true]`.

If the in-container Go build fails fetching modules, vendor first:
`cd ~/research/ascir/chaincode/ascir && go mod vendor` then re-run deployCC.
(Not needed on the verified run; recorded for resilience.)

## 3. Set the peer environment (act as Org1 admin)

```bash
cd ~/research/fabric-samples/test-network
export PATH=${PWD}/../bin:$PATH
export FABRIC_CFG_PATH=$PWD/../config/
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_TLS_ROOTCERT_FILE=${PWD}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=${PWD}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp
export CORE_PEER_ADDRESS=localhost:7051
```

## 4. Invoke (write) and query (read)

Register a known-good component (transaction; endorsed by both peers).
`signer_org` must equal the caller MSP (Org1MSP here):

```bash
peer chaincode invoke -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "${PWD}/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem" \
  -C mychannel -n ascir \
  --peerAddresses localhost:7051 --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt" \
  -C mychannel -n ascir \
  -c '{"function":"RegisterKnownGood","Args":["<64-hex-hash>","<name>","<version>","Org1MSP","<rfc3339-time>"]}'
```

Query status (read-only; no orderer/endorsement flags):

```bash
peer chaincode query -C mychannel -n ascir \
  -c '{"function":"QueryCompromiseStatus","Args":["<64-hex-hash>"]}'
```

## 5. Tear down

```bash
cd ~/research/fabric-samples/test-network
./network.sh down
```

## Verified behaviour (2026-05-31, Fabric 2.5.15)

Against `mychannel` with chaincode `ascir`, a single known-good registration
reproduced the mock-tested behaviour on the live ledger:

- `RegisterKnownGood(...)` -> `{"status":"registered", ...}`
- re-invoking the same registration -> `{"status":"already_exists", ...}`
- `QueryCompromiseStatus(hash)` -> `{"status":"known_good", "known_good_entry":{...}}`

The on-ledger key is a Fabric composite key (object type `KG`, U+0000
separators), consistent with decision D2.

## Notes

- `fabric-samples` lives outside this repository (upstream tooling); only the
  chaincode in `chaincode/ascir` and this procedure are part of ASCIR.
- This is the n = 2 stock topology. Adapting org naming/roles to the ASCIR
  sector model (FIN/CI/HC/GOV CERTs) and scaling to n = 3, 4 is subsequent work.
