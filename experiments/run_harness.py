#!/usr/bin/env python3
"""ASCIR measurement harness: drive routing_core scenarios against the live
chaincode and capture outputs for M2/M3, or time the report->verified-query
round-trip for M4.

Shells out to the Fabric `peer` CLI. Encodes test-network paths/ports, so it is
specific to this testbed (paths are constants below, easy to adjust). Must be run
from the test-network directory context with the Fabric bin on PATH and
FABRIC_CFG_PATH set (the same shell you bring the network up in).

Modes:
  --mode capture  : for each scenario, ReportCompromise (as the scenario's
                    reporter org) -> poll until committed -> RouteCompromise;
                    record authorized_recipients. Writes a run-file for score.py.
  --mode latency  : time ReportCompromise-invoke -> QueryCompromiseStatus-returns
                    -record, N trials (default 30) after a warm-up. Writes raw
                    times + median/p95.

Endorser count follows Fabric MAJORITY = floor(n/2)+1 (2 at n=2/3, 3 at n=4);
writes that under-endorse are silently invalidated (scaling.md GOTCHA 4), so the
harness always passes the correct number of --peerAddresses for writes.

Usage:
  python run_harness.py --mode capture --n 4 --scenarios scenarios/routing_core.json \
      --out results/raw_n4.json
  python run_harness.py --mode latency --n 4 --scenarios scenarios/routing_core.json \
      --latency-scenario ci_critical --trials 30 --out results/m4_n4.json
  python run_harness.py --mode capture --n 4 ... --dry-run   # print commands, no exec
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

# --- test-network topology constants -------------------------------------
# Org -> (peer port, host MSPID dir name). TLS cert paths derived from these.
TN = "${PWD}"  # resolved by the shell when commands run; we build literal paths below.
ORG_PEER = {
    "Org1MSP": ("localhost:7051", "org1.example.com", "peer0.org1.example.com"),
    "Org2MSP": ("localhost:9051", "org2.example.com", "peer0.org2.example.com"),
    "Org3MSP": ("localhost:11051", "org3.example.com", "peer0.org3.example.com"),
    "Org4MSP": ("localhost:13051", "org4.example.com", "peer0.org4.example.com"),
}
# org order used to pick endorsers (lowest orgs first, all healthy)
ORG_ORDER = ["Org1MSP", "Org2MSP", "Org3MSP", "Org4MSP"]
ORDERER = "localhost:7050"
ORDERER_HOSTNAME = "orderer.example.com"
CHANNEL = "mychannel"
CC = "ascir"

PEERROOT = "${PWD}/organizations/peerOrganizations"
ORDERER_CA = ("${PWD}/organizations/ordererOrganizations/example.com/orderers/"
              "orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem")


def tls_root(mspid):
    dom = ORG_PEER[mspid][1]
    peer = ORG_PEER[mspid][2]
    return f"{PEERROOT}/{dom}/peers/{peer}/tls/ca.crt"


def admin_env(mspid):
    """Shell snippet to set the peer CLI identity to mspid's admin."""
    dom = ORG_PEER[mspid][1]
    peer = ORG_PEER[mspid][2]
    addr = ORG_PEER[mspid][0]
    return (
        f'export CORE_PEER_TLS_ENABLED=true; '
        f'export CORE_PEER_LOCALMSPID="{mspid}"; '
        f'export CORE_PEER_TLS_ROOTCERT_FILE={PEERROOT}/{dom}/peers/{peer}/tls/ca.crt; '
        f'export CORE_PEER_MSPCONFIGPATH={PEERROOT}/{dom}/users/Admin@{dom}/msp; '
        f'export CORE_PEER_ADDRESS={addr}; '
    )


def majority(n):
    return n // 2 + 1


def endorser_args(n):
    """--peerAddresses/--tlsRootCertFiles for the first `majority(n)` orgs."""
    parts = []
    for mspid in ORG_ORDER[:majority(n)]:
        addr = ORG_PEER[mspid][0]
        parts.append(f'--peerAddresses {addr} --tlsRootCertFiles {tls_root(mspid)}')
    return " ".join(parts)


def synth_hash(scenario_id):
    """Deterministic 64-hex manifest hash per scenario (routing only cares about
    policy_metadata, not the hash value; unique hashes keep reports independent)."""
    return hashlib.sha256(("ascir-scenario:" + scenario_id).encode()).hexdigest()


def sh(cmd, dry_run):
    """Run a shell command, return stdout. On dry-run, print and return ''. """
    if dry_run:
        print("DRYRUN $", cmd)
        return ""
    res = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(f"command failed ({res.returncode}): {cmd}\n{res.stderr}\n")
        raise RuntimeError(res.stderr.strip() or "peer command failed")
    return res.stdout


def invoke_report(scenario, n, dry_run):
    """ReportCompromise as the scenario's reporter org. Returns report_id."""
    rep = scenario["report"]
    mspid = rep["reporter_org"]
    pm = json.dumps(rep["policy_metadata"]).replace('"', '\\"')
    h = synth_hash(scenario["id"])
    ts = "2026-03-01T00:00:00Z"
    args = (f'{{"function":"ReportCompromise","Args":["{h}",'
            f'"{rep["component_name"]}","{mspid}","{ts}",'
            f'"evidence://{scenario["id"]}","{pm}"]}}')
    cmd = (admin_env(mspid) +
           f'peer chaincode invoke -o {ORDERER} --ordererTLSHostnameOverride {ORDERER_HOSTNAME} '
           f'--tls --cafile {ORDERER_CA} -C {CHANNEL} -n {CC} {endorser_args(n)} '
           f"-c '{args}'")
    out = sh(cmd, dry_run)
    if dry_run:
        return "DRYRUN-REPORT-ID", h
    # parse report_id from the invoke result payload
    for line in out.splitlines():
        if "payload:" in line:
            start = line.find('payload:"') + len('payload:"')
            payload = line[start:].rstrip('"\n ')
            payload = payload.encode().decode("unicode_escape")
            try:
                return json.loads(payload)["report_id"], h
            except Exception:
                pass
    raise RuntimeError(f"could not parse report_id from: {out}")


def poll_committed(h, dry_run, tries=10, delay=1.0):
    """Query until the report hash shows status compromised (committed)."""
    if dry_run:
        print(f"DRYRUN poll QueryCompromiseStatus {h}")
        return True
    q = (f'peer chaincode query -C {CHANNEL} -n {CC} '
         f'-c \'{{"function":"QueryCompromiseStatus","Args":["{h}"]}}\'')
    for _ in range(tries):
        out = sh(admin_env("Org1MSP") + q, False)
        try:
            if json.loads(out).get("status") == "compromised":
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def invoke_route(report_id, n, dry_run):
    juris = json.dumps(ORG_ORDER[:n]).replace('"', '\\"')
    args = f'{{"function":"RouteCompromise","Args":["{report_id}","{juris}"]}}'
    cmd = (admin_env("Org1MSP") +
           f'peer chaincode invoke -o {ORDERER} --ordererTLSHostnameOverride {ORDERER_HOSTNAME} '
           f'--tls --cafile {ORDERER_CA} -C {CHANNEL} -n {CC} {endorser_args(n)} '
           f"-c '{args}'")
    out = sh(cmd, dry_run)
    if dry_run:
        return ["DRYRUN"]
    for line in out.splitlines():
        if "payload:" in line:
            start = line.find('payload:"') + len('payload:"')
            payload = line[start:].rstrip('"\n ')
            payload = payload.encode().decode("unicode_escape")
            try:
                return json.loads(payload)["authorized_recipients"]
            except Exception:
                pass
    raise RuntimeError(f"could not parse recipients from: {out}")


def mode_capture(scenarios, n, dry_run):
    outputs = {}
    for sc in scenarios:
        sid = sc["id"]
        report_id, h = invoke_report(sc, n, dry_run)
        if not poll_committed(h, dry_run):
            raise RuntimeError(f"report for {sid} never committed (endorsement/policy?)")
        recipients = invoke_route(report_id, n, dry_run)
        outputs[sid] = {"authorized_recipients": recipients}
        if not dry_run:
            print(f"  {sid}: {recipients}")
    return outputs


def mode_latency(scenario, n, trials, dry_run):
    rep = scenario["report"]
    times_ms = []
    # warm-up
    invoke_report(scenario, n, dry_run)
    for i in range(trials):
        t0 = time.perf_counter()
        _, h = invoke_report(scenario, n, dry_run)
        poll_committed(h, dry_run, tries=30, delay=0.2)
        t1 = time.perf_counter()
        times_ms.append((t1 - t0) * 1000.0)
        if dry_run:
            break
    times_ms.sort()
    def pct(p):
        if not times_ms:
            return None
        k = int(round((p / 100.0) * (len(times_ms) - 1)))
        return round(times_ms[k], 2)
    median = pct(50)
    p95 = pct(95)
    return {"trials": len(times_ms), "median_ms": median, "p95_ms": p95,
            "raw_times_ms": [round(t, 2) for t in times_ms]}


def main():
    ap = argparse.ArgumentParser(description="ASCIR live measurement harness")
    ap.add_argument("--mode", required=True, choices=["capture", "latency"])
    ap.add_argument("--n", type=int, required=True, choices=[2, 3, 4])
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--out", help="result file (else stdout)")
    ap.add_argument("--latency-scenario", help="scenario id to time (latency mode)")
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true", help="print commands, do not execute")
    args = ap.parse_args()

    with open(args.scenarios) as f:
        sdoc = json.load(f)
    scenarios = sdoc["scenarios"]
    scenario_set = sdoc.get("set", args.scenarios)

    meta = {
        "n": args.n,
        "chaincode": {"name": "ascir", "version": "1.1", "sequence": 1},
        "fabric_version": "2.5.15",
        "endorser_count": majority(args.n),
        "scenario_set": scenario_set,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if args.mode == "capture":
        outputs = mode_capture(scenarios, args.n, args.dry_run)
        result = dict(meta, outputs=outputs)
    else:
        if not args.latency_scenario:
            ap.error("--mode latency requires --latency-scenario")
        sc = next((s for s in scenarios if s["id"] == args.latency_scenario), None)
        if sc is None:
            ap.error(f"scenario id not found: {args.latency_scenario}")
        stats = mode_latency(sc, args.n, args.trials, args.dry_run)
        result = dict(meta, metric="M4", latency_scenario=args.latency_scenario, **stats)

    if args.dry_run:
        print("\n(dry-run: no result written)")
        return
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
