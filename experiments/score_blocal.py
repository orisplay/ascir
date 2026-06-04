#!/usr/bin/env python3
"""Compute the B-Local baseline: minimal sector-only routing.

B-Local routes ONLY to the primary jurisdiction of each affected sector
(SBA Phase 1): no explicit-jurisdiction inclusion, no ALL-expansion, no
severity escalation. Reporter exclusion and presence-scoping are applied
identically to ASCIR by reusing the reference oracle's sector map and
jurisdiction list, so B-Local and ASCIR are directly comparable. Overhead
reduction is (n - r)/n per scenario, the same formula score.py uses for M3.

This isolates what ASCIR's richer policy (explicit targets, ALL, severity
escalation) contributes over naive route-to-the-affected-sector-and-stop:
B-Local under-routes on exactly those cases, so its higher mean reduction
reflects under-notification, not better behavior.
"""
import argparse, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sba_reference as ref


def evaluate_blocal(policy_metadata, reporter_org, jurisdictions):
    known = set(jurisdictions)
    recipients = []
    for sector in (policy_metadata.get("affected_sectors", []) or []):
        mapped = ref.SECTOR_TO_JURISDICTION.get(sector)
        if mapped is None:
            continue
        if mapped in known and mapped not in recipients:
            recipients.append(mapped)
    recipients = [r for r in recipients if r != reporter_org]
    return sorted(recipients)


def main():
    ap = argparse.ArgumentParser(description="Compute B-Local baseline routing + overhead reduction")
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--jurisdictions", help="JSON array; default = first n of [Org1..Org4]")
    ap.add_argument("--out")
    args = ap.parse_args()

    with open(args.scenarios) as f:
        sdoc = json.load(f)
    scenarios = sdoc["scenarios"]

    if args.jurisdictions:
        juris = json.loads(args.jurisdictions)
    else:
        juris = ref.DEFAULT_JURISDICTIONS[:args.n]

    per = []
    for sc in scenarios:
        report = sc["report"]
        recips = evaluate_blocal(report["policy_metadata"], report["reporter_org"], juris)
        r = len(recips)
        reduction = (args.n - r) / args.n if args.n else None
        per.append({
            "id": sc["id"], "r": r, "n": args.n,
            "blocal_reduction": round(reduction, 4) if reduction is not None else None,
            "blocal_recipients": recips,
        })
    k = len(per)
    summary = {
        "mean_blocal_reduction": round(sum(p["blocal_reduction"] for p in per) / k, 4) if k else None,
        "scenarios": k,
        "baseline": "B-Local (minimal sector-only routing; SBA Phase 1 only)",
    }
    result = {
        "metric": "M3-baseline-Blocal", "n": args.n,
        "jurisdictions": juris, "per_scenario": per, "summary": summary,
    }
    text = json.dumps(result, indent=2)
    if args.out:
        open(args.out, "w").write(text + "\n"); print("wrote " + args.out)
        print(json.dumps(summary, indent=2))
    else:
        print(text)


if __name__ == "__main__":
    main()
