#!/usr/bin/env python3
"""ASCIR M1 detection-accuracy harness (live, at network size n).

Establishes the M1 registry state and sweeps all 45 dataset components:
  1. Register the 30 baseline components known-good (RegisterKnownGood).
  2. Report the 15 compromise variants (ReportCompromise) -> 'compromised'.
  3. Query every component's manifest hash and record the resolved status.

Reuses run_harness.py (admin_env, endorser_args, majority, sh) so the invoke
path, endorser count (floor(n/2)+1), and caller-identity rules match the M2/M3
runs. At n=4 the N=2 multi-sig registration requirement is satisfied by the
endorsement policy (majority peers on the write), not special chaincode logic.

Run from the test-network dir with the peer env active.
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.expanduser("~/research/ascir/experiments"))
import run_harness as rh


def load_rows(dataset_dir):
    csv_path = os.path.join(dataset_dir, "ground_truth.csv")
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def register_known_good(row, n, dry_run, signer="Org1MSP"):
    h = row["manifest_hash"]
    name = row["component_name"]
    ts = "2026-03-01T00:00:00Z"
    args = ('{"function":"RegisterKnownGood","Args":'
            '["%s","%s","1.0","%s","%s"]}' % (h, name, signer, ts))
    cmd = (rh.admin_env(signer) +
           "peer chaincode invoke -o %s --ordererTLSHostnameOverride %s "
           "--tls --cafile %s -C %s -n %s %s -c '%s'"
           % (rh.ORDERER, rh.ORDERER_HOSTNAME, rh.ORDERER_CA, rh.CHANNEL,
              rh.CC, rh.endorser_args(n), args))
    rh.sh(cmd, dry_run)
    return h


def report_variant(row, n, dry_run, reporter="Org1MSP"):
    h = row["manifest_hash"]
    name = row["component_name"]
    sectors = [s for s in (row.get("affected_sectors") or "").split(",") if s]
    juris = [j for j in (row.get("affected_jurisdictions") or "").split(",") if j]
    scope = row.get("distribution_scope") or "single_jurisdiction"
    sev = row.get("severity") or "medium"
    pm = json.dumps({
        "affected_sectors": sectors,
        "affected_jurisdictions": juris,
        "distribution_scope": scope,
        "severity": sev,
    }).replace('"', '\\"')
    ts = "2026-03-01T00:00:00Z"
    args = ('{"function":"ReportCompromise","Args":'
            '["%s","%s","%s","%s","evidence://m1/%s","%s"]}'
            % (h, name, reporter, ts, row["component_id"], pm))
    cmd = (rh.admin_env(reporter) +
           "peer chaincode invoke -o %s --ordererTLSHostnameOverride %s "
           "--tls --cafile %s -C %s -n %s %s -c '%s'"
           % (rh.ORDERER, rh.ORDERER_HOSTNAME, rh.ORDERER_CA, rh.CHANNEL,
              rh.CC, rh.endorser_args(n), args))
    rh.sh(cmd, dry_run)
    return h


def query_status(h, dry_run):
    if dry_run:
        return "DRYRUN"
    q = ("peer chaincode query -C %s -n %s "
         "-c '{\"function\":\"QueryCompromiseStatus\",\"Args\":[\"%s\"]}'"
         % (rh.CHANNEL, rh.CC, h))
    out = rh.sh(rh.admin_env("Org1MSP") + q, False)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line).get("status", "parse_error")
            except Exception:
                pass
    raise RuntimeError("could not parse status from: %s" % out)


def poll_status_committed(h, want, dry_run, tries=10, delay=1.0):
    if dry_run:
        return True
    for _ in range(tries):
        if query_status(h, False) == want:
            return True
        time.sleep(delay)
    return False


def main():
    ap = argparse.ArgumentParser(description="ASCIR M1 detection harness")
    ap.add_argument("--n", type=int, required=True, choices=[2, 3, 4])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", help="raw run-file (else stdout)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = load_rows(args.dataset)
    baselines = [r for r in rows if r["ground_truth_label"] == "known_good"]
    variants = [r for r in rows if r["ground_truth_label"] == "compromised"]
    print("dataset: %d components (%d baseline, %d variant)"
          % (len(rows), len(baselines), len(variants)))

    print("registering baselines known-good ...")
    for r in baselines:
        h = register_known_good(r, args.n, args.dry_run)
        if not args.dry_run and not poll_status_committed(h, "known_good", args.dry_run):
            raise RuntimeError("baseline %s did not reach known_good" % r["component_id"])
        if not args.dry_run:
            print("  KG %s" % r["component_id"])

    print("reporting variants compromised ...")
    for r in variants:
        h = report_variant(r, args.n, args.dry_run)
        if not args.dry_run and not poll_status_committed(h, "compromised", args.dry_run):
            raise RuntimeError("variant %s did not reach compromised" % r["component_id"])
        if not args.dry_run:
            print("  CR %s" % r["component_id"])

    print("sweeping all components ...")
    records = []
    for r in rows:
        status = query_status(r["manifest_hash"], args.dry_run)
        records.append({
            "component_id": r["component_id"],
            "ground_truth_label": r["ground_truth_label"],
            "manifest_hash": r["manifest_hash"],
            "status": status,
        })

    result = {
        "metric": "M1",
        "n": args.n,
        "chaincode": {"name": "ascir", "version": "1.2", "sequence": 1},
        "fabric_version": "2.5.15",
        "endorser_count": rh.majority(args.n),
        "dataset": os.path.abspath(args.dataset),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "records": records,
    }
    if args.dry_run:
        print("\n(dry-run: no result written)")
        return
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        print("wrote " + args.out)
    else:
        print(text)


if __name__ == "__main__":
    main()
