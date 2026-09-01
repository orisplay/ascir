# ASCIR Demo Guide

Follow this top to bottom for a live end-to-end demo (UI -> backend -> 4-org
Fabric). Assumes the network is already up via `./scripts/rebuild.sh 4`.

Each GUI step tells the same story as the paper: **register -> detect ->
report -> contest -> route -> browse.**

---

---

## Part 0 — Bring up the network

From the repo root, build the Fabric network (this does teardown, channel
creation, chaincode deploy, and adds all orgs). Takes a few minutes.

```bash
cd ~/research/ascir
./scripts/rebuild.sh 4        # 4-org network (also accepts 2 or 3)
```

**Confirm:** it ends with
```
=== DONE — n=4 network up. ===
        "approvals": {
                "Org1MSP": true,
                "Org2MSP": true,
                "Org3MSP": true,
                "Org4MSP": true
        }
```
All four orgs must read `true`. The network containers now run in the
background — leave them; do NOT run teardown until you are finished.

## Part 1 — Start the services

You need TWO terminals open and running at the same time (leave both open).

### Terminal A — backend
```bash
cd ~/research/ascir/backend
ASCIR_ORGS="Org1MSP,Org2MSP,Org3MSP,Org4MSP" npm start
```
Wait for:
```
ASCIR backend listening on http://localhost:3000
  connected orgs: Org1MSP, Org2MSP, Org3MSP, Org4MSP
```
Leave it running.

### Terminal B — frontend
```bash
cd ~/research/ascir/frontend
npm run dev
```
Wait for `Local: http://localhost:5173/`, then open that URL in the browser.

### Confirm
Top of the page should show:  **backend: ok · 4 orgs · mychannel**  (green).
The "Acting as" dropdown should list Org1MSP–Org4MSP.

---

## Part 2 — The demo flow

Use this manifest hash throughout (a valid 64-hex string):
```
aa11bb22cc33dd44ee55ff6677889900aabbccddeeff00112233445566778899
```

### Step 1 — Register a known-good component
*Card: Register Known-Good. Acting as: **Org1MSP**.*
- Manifest hash: `aa11bb22cc33dd44ee55ff6677889900aabbccddeeff00112233445566778899`
- Component name: `agent-ci-controller`
- Version: `1.0`
- Click **Register**

**Confirm:** green "✓ Registered on the ledger" banner + JSON with a `tx_id`.
*Say: "A trusted component is now on the shared ledger, signed by Org1."*

### Step 2 — Check it (status = known_good)
*Card: Check Component Status.*
- Manifest hash: (same as above)
- Click **Check**

**Confirm:** a **KNOWN_GOOD** badge. This proves the register persisted to the
ledger — Check queries the chain, not the UI.
*Say: "Any organization can independently verify a component's status."*

### Step 3 — Report it compromised
*Card: Report Compromise. Acting as: **Org1MSP**.*
- Manifest hash: (same)
- Component name: `agent-ci-controller`
- Evidence ref: `evidence://case/ci-001`
- Affected sectors: check **CI** (uncheck others)
- Severity: `critical`
- Distribution scope: `global`
- Click **Report**

**Confirm:** green "recorded" banner + a **report_id** in the JSON.
**COPY THE report_id** — you need it in Step 5.
*Say: "An investigator finds the component compromised on a device."*

### Step 4 — Check again (status = contested)
*Card: Check Component Status.*
- Manifest hash: (same)
- Click **Check**

**Confirm:** an orange **CONTESTED** badge, with both `known_good_entry` and
`active_compromise_reports` shown.
*Say: "The system flags the conflict — trusted by one org, reported malicious.
This is the four-status detection model."*

### Step 5 — Route the compromise (the headline)
*Card: Route Compromise.*
- Report ID: paste the report_id from Step 3
  *(or open the Registry Browser and click the report row to load it)*
- Click **Route**

**Confirm:** Recipients **Org2MSP, Org4MSP**; Excluded **Org1MSP, Org3MSP**;
plus a policy-trace table (sector_mapping CI->Org2MSP, severity_escalation
critical->Org4MSP).
*Say: "Only the affected authorities are notified — the CI sector team plus the
national CERT for the critical severity — and the decision is recorded on-chain
with its full reasoning."*

### Step 6 — Registry Browser
*Panel: Registry Browser (bottom of page). Click **Refresh** if needed.*
- Shows the known-good component and the compromise report as rows.
- Click a hash -> loads it into Check. Click a report ID -> loads it into Route.

*Say: "Everything is auditable and browsable — no need to memorize 64-character
hashes."*

---

## Part 3 — Optional: prove no superimposition

Re-register the SAME hash under a different name/org:
- Acting as: **Org2MSP**, hash: (same), name: `something-else`, version `2.0` ->
  **Register**

**Confirm:** an amber "already exists — existing entry left unchanged" banner.
*Say: "The manifest hash IS the identity — you cannot overwrite or spoof an
existing entry."*

---

## Part 4 — Tear down when done
```bash
# Ctrl-C in Terminal A (backend) and Terminal B (frontend), then:
cd ~/research/ascir
./scripts/teardown.sh
```

---

## Talking points / FAQ during the demo

- **The brief pause on a write (~250ms)** is the four organizations reaching
  consensus and committing to the ledger.
- **Why Org2 and Org4** for a critical CI report: CI maps to Org2 (sector
  authority); critical severity escalates to Org4 (national CERT).
- **The tx_id on every write** is a real Fabric transaction — tamper-evident and
  auditable after the fact.
- **"Acting as"** switches which organization's identity signs the write; the
  chaincode enforces that the caller's MSP matches the claimed org.
