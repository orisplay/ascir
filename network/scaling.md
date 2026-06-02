# ASCIR Network Scaling: n=2 → n=3 → n=4

This document records the verified procedure for scaling the ASCIR testbed from
the BICIR-replication baseline (n=2) to the primary contribution measurement
(n=3) and the scaling extension (n=4). It is written so the topology can be
reproduced from a clean `fabric-samples/test-network`.

Sector mapping (encoded in the chaincode's `PrimaryJurisdiction`, not in Fabric
MSP names): Org1MSP = FIN (financial), Org2MSP = CI (critical infrastructure),
Org3MSP = HC (healthcare), Org4MSP = GOV (general national CERT). The MSPs keep
their generic test-network names; the sector meaning lives in the policy layer.

All commands run from `~/research/fabric-samples/test-network` unless noted.
The chaincode is deployed at version 1.1, sequence 1 (the schema-fixed build;
package-id `ascir_1.1:98a7541...`).

## n=2 — baseline (BICIR replication)

Standard test-network bring-up plus the ASCIR chaincode:

```
./network.sh up createChannel
./network.sh deployCC -ccn ascir -ccp ~/research/ascir/chaincode/ascir -ccl go -ccv 1.1 -ccs 1
```

Note `-ccs 1` (sequence 1) on a fresh channel. Use `-ccs 2` only when upgrading
an already-committed definition (e.g. the v1.0→v1.1 schema fix on an existing
ledger). Verify with a RegisterKnownGood + QueryCompromiseStatus (see
README.md).

## n=3 — add Org3 (healthcare CERT)

test-network ships `addOrg3` tooling. Add Org3 to the running channel:

```
cd addOrg3
./addOrg3.sh up -c mychannel
cd ..
```

This generates Org3 crypto, brings up peer0.org3 (port 11051), and joins it to
the channel. Then the chaincode must be installed and approved on Org3 (the
addOrg3 script does not do this for a custom chaincode):

```
# Package once (reused for org3 and org4); label must match the deployed cc
peer lifecycle chaincode package ascir.tar.gz --path ~/research/ascir/chaincode/ascir --lang golang --label ascir_1.1

# Org3 admin env
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org3MSP"
export CORE_PEER_TLS_ROOTCERT_FILE=${PWD}/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=${PWD}/organizations/peerOrganizations/org3.example.com/users/Admin@org3.example.com/msp
export CORE_PEER_ADDRESS=localhost:11051
export ORDERER_CA=${PWD}/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem

peer lifecycle chaincode install ascir.tar.gz
# (package-id should be ascir_1.1:98a7541...; identical across all orgs)
peer lifecycle chaincode approveformyorg -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --tls --cafile "$ORDERER_CA" --channelID mychannel --name ascir --version 1.1 --package-id ascir_1.1:98a7541be779744dc6a69c0aa9a8a85476366821fdd66e1d36b572c15d40aab2 --sequence 1

peer lifecycle chaincode querycommitted --channelID mychannel --name ascir
# Expect Approvals: [Org1MSP: true, Org2MSP: true, Org3MSP: true]
```

Verify n=3 routing with an HC-sector report → route; the recipient set should
be [Org3MSP] (HC maps to Org3). Note the access-control rule: ReportCompromise's
caller MSP must equal the `reporter_org` argument, so report as the org named in
reporter_org.

## n=4 — add Org4 (general national CERT)

There is no `addOrg4` in test-network; it is adapted from `addOrg3`. The files
are produced by sed-substitution from the Org3 equivalents (org3→org4, Org3→Org4,
ports 11051→13051 and 11052→13052):

```
mkdir -p addOrg4/compose/docker
sed -e 's/Org3/Org4/g' -e 's/org3/org4/g' addOrg3/org3-crypto.yaml > addOrg4/org4-crypto.yaml
sed -e 's/Org3/Org4/g' -e 's/org3/org4/g' addOrg3/configtx.yaml > addOrg4/configtx.yaml
sed -e 's/Org3/Org4/g' -e 's/org3/org4/g' -e 's/11051/13051/g' -e 's/11052/13052/g' addOrg3/compose/compose-org3.yaml > addOrg4/compose/compose-org4.yaml
sed -e 's/org3/org4/g' -e 's/Org3/Org4/g' addOrg3/compose/docker/docker-compose-org3.yaml > addOrg4/compose/docker/docker-compose-org4.yaml
cp -r addOrg3/compose/docker/peercfg addOrg4/compose/docker/peercfg
grep -rn -E 'org3|Org3|11051|11052' addOrg4/   # must be empty
```

### GOTCHA 1 — the peercfg/docker.sock overlay

`compose-org3.yaml` alone does NOT mount `/etc/hyperledger/peercfg`; that mount
(and the docker.sock mount) lives in the overlay `compose/docker/docker-compose-org3.yaml`.
A peer started without it crashes immediately with
`FABRIC_CFG_PATH /etc/hyperledger/peercfg does not exist`. Bring the peer up
with BOTH compose files, run from `addOrg4/compose/`, with DOCKER_SOCK set:

```
cd addOrg4/compose
export DOCKER_SOCK=/var/run/docker.sock
docker compose -f compose-org4.yaml -f docker/docker-compose-org4.yaml up -d
cd ../..
```

### Generate Org4 crypto and org definition

```
cryptogen generate --config=addOrg4/org4-crypto.yaml --output="organizations"

# IMPORTANT: verify the generated certs are internally consistent (see GOTCHA 2)
openssl verify -CAfile organizations/peerOrganizations/org4.example.com/msp/cacerts/ca.org4.example.com-cert.pem organizations/peerOrganizations/org4.example.com/peers/peer0.org4.example.com/msp/signcerts/*.pem
openssl verify -CAfile organizations/peerOrganizations/org4.example.com/msp/cacerts/ca.org4.example.com-cert.pem organizations/peerOrganizations/org4.example.com/users/Admin@org4.example.com/msp/signcerts/*.pem
# Both MUST print OK before proceeding.

export FABRIC_CFG_PATH=$PWD/addOrg4
configtxgen -printOrg Org4MSP > organizations/peerOrganizations/org4.example.com/org4.json
export FABRIC_CFG_PATH=$HOME/research/fabric-samples/config   # reset
```

### GOTCHA 2 — inconsistent cryptogen output

A cryptogen run can produce a `cacerts/` CA cert that does NOT match the CA that
signed the leaf (peer/admin) certs — the `openssl verify` above then fails with
`unable to get local issuer certificate`. If committed into the channel config,
the orderer rejects the org with `x509: certificate signed by unknown authority`
/ `ECDSA verification failure`, and the new peer can never pull blocks (every
deliver request returns FORBIDDEN against /Channel/Readers). Fix: delete the org
crypto and regenerate cleanly:

```
docker rm -f peer0.org4.example.com; docker volume rm compose_peer0.org4.example.com
rm -rf organizations/peerOrganizations/org4.example.com
cryptogen generate --config=addOrg4/org4-crypto.yaml --output="organizations"
# re-run both openssl verify checks → must be OK
```

### Channel config update — add Org4

Fetch config, splice Org4 in, compute delta, sign, submit. Set the Org1 admin
env first (CORE_PEER_LOCALMSPID=Org1MSP, ADDRESS=localhost:7051, ORDERER_CA set).

```
peer channel fetch config channel-artifacts/cfg.pb -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com -c mychannel --tls --cafile "$ORDERER_CA"
configtxlator proto_decode --input channel-artifacts/cfg.pb --type common.Block --output channel-artifacts/cfg.json
jq '.data.data[0].payload.data.config' channel-artifacts/cfg.json > channel-artifacts/cfg_current.json
jq -s '.[0] * {"channel_group":{"groups":{"Application":{"groups":{"Org4MSP":.[1]}}}}}' channel-artifacts/cfg_current.json organizations/peerOrganizations/org4.example.com/org4.json > channel-artifacts/cfg_added.json
configtxlator proto_encode --input channel-artifacts/cfg_current.json --type common.Config --output channel-artifacts/cfg_current.pb
configtxlator proto_encode --input channel-artifacts/cfg_added.json --type common.Config --output channel-artifacts/cfg_added.pb
configtxlator compute_update --channel_id mychannel --original channel-artifacts/cfg_current.pb --updated channel-artifacts/cfg_added.pb --output channel-artifacts/upd.pb
configtxlator proto_decode --input channel-artifacts/upd.pb --type common.ConfigUpdate --output channel-artifacts/upd.json
echo '{"payload":{"header":{"channel_header":{"channel_id":"mychannel", "type":2}},"data":{"config_update":'$(cat channel-artifacts/upd.json)'}}}' | jq . > channel-artifacts/upd_env.json
configtxlator proto_encode --input channel-artifacts/upd_env.json --type common.Envelope --output channel-artifacts/upd_env.pb
```

### GOTCHA 3 — org-membership changes require UNANIMOUS sign-off

On this channel, `/Channel/Application/Admins` evaluates to "all current orgs"
(not a bare majority) for group-membership changes. Adding Org4 at n=3 requires
ALL THREE existing orgs (Org1, Org2, Org3) to sign the update; two signatures
fail with `requires 3 of the 'Admins' sub-policies`. Sign with each org, then
submit:

```
# Org1 sign, Org2 sign, then Org3 sign-and-submit (each export sets that org's
# admin env: LOCALMSPID, TLS_ROOTCERT_FILE, MSPCONFIGPATH, ADDRESS 7051/9051/11051)
peer channel signconfigtx -f channel-artifacts/upd_env.pb   # as Org1
peer channel signconfigtx -f channel-artifacts/upd_env.pb   # as Org2
peer channel update -f channel-artifacts/upd_env.pb -c mychannel -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --tls --cafile "$ORDERER_CA"   # as Org3
```

Corollary: if a broken Org4 MSP was already committed, you cannot MODIFY it
(that needs Org4's own admin signature, which a broken org cannot provide).
Instead REMOVE Org4 (a channel-Admins action, unanimous among current orgs) then
re-ADD it fresh. Removal: `jq 'del(.channel_group.groups.Application.groups.Org4MSP)'`.

### Join Org4's peer

A newly-added org's peer is denied when fetching the genesis block directly
(FORBIDDEN). Have an existing org (Org1) fetch block 0, then Org4 joins locally
with that file (join is a local operation; the fetcher identity is irrelevant):

```
# as Org1:
peer channel fetch 0 channel-artifacts/genesis.block -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com -c mychannel --tls --cafile "$ORDERER_CA"
# as Org4 (ADDRESS=localhost:13051):
peer channel join -b channel-artifacts/genesis.block
```

Once the channel config has the CORRECT Org4 cert, the peer syncs (block height
climbs, gossip joins "4 organizations") instead of looping on FORBIDDEN.

### Install + approve chaincode on Org4

As the Org4 admin env:

```
peer lifecycle chaincode install ascir.tar.gz
peer lifecycle chaincode approveformyorg -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --tls --cafile "$ORDERER_CA" --channelID mychannel --name ascir --version 1.1 --package-id ascir_1.1:98a7541be779744dc6a69c0aa9a8a85476366821fdd66e1d36b572c15d40aab2 --sequence 1
peer lifecycle chaincode querycommitted --channelID mychannel --name ascir
# Expect Approvals: [Org1MSP: true, Org2MSP: true, Org3MSP: true, Org4MSP: true]
```

### GOTCHA 4 — endorsement count scales with n

The chaincode uses the default endorsement policy (`MAJORITY` of orgs). At n=2
and n=3, two endorsing peers satisfy it. At n=4, MAJORITY = 3, so a WRITE
(ReportCompromise, RouteCompromise) must be endorsed by THREE peers. With only
two `--peerAddresses`, the invoke returns status:200 (endorsement collected) but
the transaction is INVALIDATED at commit with reason `ENDORSEMENT_POLICY_FAILURE`
— the write silently never reaches state, and a later lookup reports the record
as not found. Always pass three `--peerAddresses` for writes at n=4:

```
peer chaincode invoke ... -C mychannel -n ascir \
  --peerAddresses localhost:7051 --tlsRootCertFiles <org1 ca.crt> \
  --peerAddresses localhost:9051 --tlsRootCertFiles <org2 ca.crt> \
  --peerAddresses localhost:11051 --tlsRootCertFiles <org3 ca.crt> \
  -c '{"function":"ReportCompromise","Args":[...]}'
```

This is a measurable property, not just an operational note: endorsement cost
(and therefore end-to-end write latency, metric M4) grows with n, since more
peer round-trips are required to satisfy the policy as the network scales.

## Verified results

All three sizes have been brought up and exercised live on Fabric 2.5.15:

- n=2: register/query/report/route; SBA rules (sector_mapping, severity_escalation, reporter_exclusion); all four statuses incl. contested.
- n=3: cross-org endorsement (Org1+Org3); HC report routes to [Org3MSP].
- n=4: cross-org endorsement incl. Org4; CI+critical report routes to
  [Org2MSP, Org4MSP] (sector_mapping CI→Org2 + severity_escalation critical→Org4),
  committed with 3-of-4 endorsement.

## Teardown

```
docker rm -f peer0.org4.example.com; docker volume rm compose_peer0.org4.example.com
cd addOrg3 && ./addOrg3.sh down -c mychannel; cd ..   # if present
./network.sh down
```

`network.sh down` removes the core network; the Org4 peer (started outside
network.sh) must be removed separately as shown.
