# ASCIR Network Runbook

One-command bring-up, teardown, and experiment runner for the ASCIR Hyperledger
Fabric testbed. These scripts reproduce the known-good build used for the paper's
evaluation (Fabric 2.5.15, chaincode v1.3, `BatchTimeout=200ms`).

## Layout assumed

- Fabric samples: `~/research/fabric-samples`
- ASCIR repo:     `~/research/ascir`
- Org4 assets:    `~/research/fabric-samples/test-network/addOrg4/`
  (`org4-crypto.yaml`, `configtx.yaml`, `compose/`)

Edit the paths at the top of `rebuild.sh` if your layout differs.

## Quick start

```bash
# bring up a 4-org network (also accepts 2 or 3)
./scripts/rebuild.sh 4

# in a second terminal: start the backend (match the org list to n)
cd ~/research/ascir/backend
ASCIR_ORGS="Org1MSP,Org2MSP,Org3MSP,Org4MSP" npm start

# optional: start the GUI (Vite) for a live demo
cd ~/research/ascir/frontend && npm run dev   # http://localhost:5173

# run the staged-latency experiment (M4)
ASCIR_ORGS="Org1MSP,Org2MSP,Org3MSP,Org4MSP" ./scripts/run_experiments.sh 4

# tear everything down when done
./scripts/teardown.sh
```

## What `rebuild.sh <n>` does

| Step | Action |
|------|--------|
| 0 | Sets `BatchTimeout=200ms` in `configtx.yaml` (so latency matches the paper) |
| 1 | Tears down any existing network + prunes stale volumes |
| 2 | Brings up n=2 with `mychannel` and CAs |
| 3 | Deploys chaincode v1.3 (auto-installs on Org1/Org2, commits seq 1) |
| 4 | (n≥3) Adds Org3 via `addOrg3.sh`, installs + approves chaincode |
| 5 | (n=4) Hand-builds Org4: crypto → config splice → unanimous sign → peer up → join → install + approve |

Ends by printing the committed-definition approvals (all orgs should read `true`).

## Tunable parameters (top of `rebuild.sh`)

- `CC_VER` / `CC_SEQ` — chaincode version and sequence (default 1.3 / 1)
- `BATCH_TIMEOUT` — orderer block-cut timeout (default `200ms`; the paper's M4
  figure assumes this — raising it inflates commit latency toward the timeout)
- `PKG_ID` — chaincode package id (stable for identical chaincode source; if you
  change the chaincode, re-package and update this)

## Known gotchas (baked into the scripts, noted here for debugging)

1. **`approveformyorg` may print `ENDORSEMENT_POLICY_FAILURE`** on Org3/Org4 when
   the sequence is already committed. This is harmless — `querycommitted` is the
   authoritative check, and the script continues past it.
2. **Org4 is hand-built** (no `addOrg4.sh` in fabric-samples). Its peer runs from
   `addOrg4/compose/` with both compose files and `DOCKER_SOCK` exported.
3. **Adding an org requires unanimous signatures** of the present orgs on the
   channel config update (Org1+Org2 sign, Org3 submits).
4. **Endorser count follows MAJORITY**: 2 endorsers at n=2 and n=3, 3 at n=4.
5. **Terminal paste-buffer corruption**: if `peer` commands start printing
   orderer help-text, open a *fresh terminal* — a stale paste buffer garbles
   input. (Not a script issue; affects manual runs.)
6. **`configtx.yaml` lives in fabric-samples**, which is not version-controlled
   here. Step 0 re-applies `BatchTimeout` on every run so results stay consistent
   even from a fresh fabric-samples clone.

## Experiments

- **M4 (staged latency)**: `run_experiments.sh <n>` runs `m4_staged.js` — 30
  trials, reports endorsement vs commit median/p95 to
  `experiments/results/m4_staged_n<n>.json`.
- **M1/M2/M3**: driven by `experiments/run_harness.py` + `score*.py` against the
  seeded dataset; see `network/scaling.md` for the per-metric invocations (they
  require the registry to be populated from `dataset/` first).

## Reproducing the dataset

```bash
python dataset/generate.py          # regenerates the 45 components + ground truth
```
Deterministic (fixed seed); asserts all 45 manifest hashes are unique before
writing.
