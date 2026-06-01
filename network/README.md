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

## ReportCompromise and RouteCompromise (verified live, v1.1)

`ReportCompromise` takes five string args plus a `PolicyMetadata` struct; the
struct is passed as an escaped-JSON string in the final Arg slot. Report a
CI-sector compromise from Org1 (with the Org1 peer env set per section 3):

```bash
peer chaincode invoke -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "${PWD}/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem" \
  -C mychannel -n ascir \
  --peerAddresses localhost:7051 --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt" \
  -c '{"function":"ReportCompromise","Args":["<64-hex-hash>","<name>","Org1MSP","<rfc3339-time>","evidence://<ref>","{\"affected_sectors\":[\"CI\"],\"affected_jurisdictions\":[],\"distribution_scope\":\"single_jurisdiction\",\"severity\":\"medium\"}"]}'
```

Returns `{"status":"reported","report_id":"<uuid>", ...}`. Capture the
`report_id`.

`RouteCompromise` takes the `report_id` and a `[]string` of known
jurisdictions (also passed as an escaped-JSON string). For these validation
runs the four-org list is supplied so results match the unit-test
expectations, even though the stock test-network has only Org1/Org2 (the
routing decision is a computed record, not a transmission, so non-member MSP
IDs are reasoned over without being contacted):

```bash
peer chaincode invoke -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "${PWD}/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem" \
  -C mychannel -n ascir \
  --peerAddresses localhost:7051 --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt" \
  -c '{"function":"RouteCompromise","Args":["<report_id>","[\"Org1MSP\",\"Org2MSP\",\"Org3MSP\",\"Org4MSP\"]"]}'
```

Verified results (Fabric 2.5.15, chaincode v1.1):

- CI sector, reporter Org1, medium severity ->
  `authorized_recipients:["Org2MSP"]`; trace has one `sector_mapping` entry
  (CI -> Org2). Reporter exclusion does not appear because Org1 was never
  added.
- FIN sector, reporter Org1, medium severity ->
  `authorized_recipients:[]` (empty); trace has `sector_mapping` (FIN ->
  Org1) followed by `reporter_exclusion` (Org1 removed). The only affected
  jurisdiction is the reporter, so there is no one else to notify.

These match the mock-based unit tests (M02_CI and M01_FIN respectively).

## Schema-validation gotcha (chaincode v1.0 -> v1.1)

The first `RouteCompromise` invocation under v1.0 failed with:

```
endorsement failure ... value did not match schema: return.policy_trace.0: removed is required
```

Cause: contractapi v2 generates a return-value JSON schema from the Go
structs and, by default, marks every struct field required. `TraceEntry`
uses `omitempty` on `Added`/`Removed` (an entry sets only one), so a
`sector_mapping` entry (no `removed`) failed validation. Fix: tag both
fields `metadata:",optional"` so the schema matches the `omitempty` shape.
Committed in chaincode/ascir/model.go; redeployed as v1.1, sequence 2 via:

```bash
./network.sh deployCC -ccn ascir -ccp ~/research/ascir/chaincode/ascir -ccl go -ccv 1.1 -ccs 2
```

In-place upgrade preserves ledger state (existing reports remain routable).

## Additional verified cases: severity escalation and contested status

Two further cases complete the live validation (Fabric 2.5.15, chaincode v1.1),
covering the remaining SBA rule and the remaining status branch.

### Severity escalation (critical -> general CERT)

A CI-sector compromise reported with `severity: critical` routes to the CI
primary jurisdiction (Org2) and, by the escalation rule, also to the general
national CERT (Org4):

- Report: CI sector, reporter Org1, `severity: critical`.
- Route (4-org list) -> `authorized_recipients: ["Org2MSP","Org4MSP"]`,
  `excluded_jurisdictions: ["Org1MSP","Org3MSP"]`.
- `policy_trace`: `sector_mapping` (CI -> Org2) then `severity_escalation`
  (critical -> Org4).

Matches unit test `R03_CI_critical`. Confirms the `severity_escalation` rule
firing on the live ledger.

### Contested status (supply-chain signal)

A component registered known-good and *subsequently* reported compromised
resolves to `contested` — the supply-chain-attack signature in which a
legitimate component is compromised after registration:

- `RegisterKnownGood(hash, ...)` then `ReportCompromise(hash, ...)` for the
  same manifest hash.
- `QueryCompromiseStatus(hash)` -> `status: "contested"`, with both a
  populated `known_good_entry` and a non-empty `active_compromise_reports`.

Confirms the fourth status branch (after unknown / known_good / compromised)
on the live ledger.

### Live-validation coverage summary

All four functions, all four status values (unknown, known_good, compromised,
contested), and all three SBA routing rules (sector_mapping,
severity_escalation, reporter_exclusion) have been exercised against the live
Fabric 2.5.15 testbed, with results matching the mock-based unit tests.

Operational note: multi-line `peer` invoke commands with trailing backslashes
are fragile when pasted (a mangled continuation can cause the command to run
incorrectly or not at all). Prefer single-line invocations or a wrapper script.
