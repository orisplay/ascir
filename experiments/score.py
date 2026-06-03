#!/usr/bin/env python3
"""Score ASCIR measurement runs: compute M2 (routing precision) and M3
(broadcast overhead reduction) from captured chaincode outputs.

Per docs/metrics.md. Expected recipients are computed from the SBA reference
oracle (sba_reference.evaluate_sba), so M2 scores the chaincode against the
specification rather than against the scenario file's stored values (which are
validated to agree, but the reference is authoritative).

Inputs:
  - a scenario file (experiments/scenarios/*.json): reports + ground truth
  - a run-output file: what the chaincode actually returned per scenario
  - n: the network size at which the run was taken

Run-output file schema (JSON):
  {
    "n": 4,
    "chaincode": {"name": "ascir", "version": "1.1", "sequence": 1},
    "fabric_version": "2.5.15",
    "endorser_count": 3,
    "scenario_set": "routing_core",
    "outputs": {
      "<scenario_id>": {"authorized_recipients": ["Org2MSP", "Org4MSP"]},
      ...
    }
  }

Usage:
  # score a real run:
  python score.py --scenarios experiments/scenarios/routing_core.json \
                  --run experiments/results/raw_n4.json --metric M2 --out experiments/results/m2_n4.json

  # test the whole pipeline offline (reference stands in for the chaincode):
  python score.py --scenarios experiments/scenarios/routing_core.json \
                  --simulate --n 4 --metric M2
"""
import argparse
import json
import sys
from datetime import datetime, timezone

import sba_reference as ref


def _set(xs):
    return set(xs or [])


def score_m2(scenarios, outputs, jurisdictions):
    """Routing precision. Per scenario: precision, recall, exact_match
    (routed vs reference-expected, as sets)."""
    per = []
    for sc in scenarios:
        sid = sc["id"]
        report = sc["report"]
        expected, _ = ref.evaluate_sba(
            report["policy_metadata"], report["reporter_org"], jurisdictions
        )
        expected_s = _set(expected)
        routed_s = _set(outputs[sid]["authorized_recipients"])
        inter = expected_s & routed_s
        precision = 1.0 if not routed_s else len(inter) / len(routed_s)
        recall = 1.0 if not expected_s else len(inter) / len(expected_s)
        exact = 1 if routed_s == expected_s else 0
        per.append({
            "id": sid,
            "expected_recipients": sorted(expected_s),
            "routed_recipients": sorted(routed_s),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "exact_match": exact,
        })
    n = len(per)
    summary = {
        "mean_precision": round(sum(p["precision"] for p in per) / n, 4) if n else None,
        "mean_recall": round(sum(p["recall"] for p in per) / n, 4) if n else None,
        "exact_match_rate": round(sum(p["exact_match"] for p in per) / n, 4) if n else None,
        "scenarios": n,
    }
    return per, summary


def score_m3(scenarios, outputs, n_orgs, jurisdictions):
    """Broadcast overhead reduction (n - r)/n per scenario, plus baseline
    comparison (B-Broadcast notifies all n -> reduction 0)."""
    per = []
    for sc in scenarios:
        sid = sc["id"]
        routed = outputs[sid]["authorized_recipients"]
        r = len(_set(routed))
        reduction = (n_orgs - r) / n_orgs if n_orgs else None
        per.append({
            "id": sid,
            "r": r,
            "n": n_orgs,
            "ascir_reduction": round(reduction, 4) if reduction is not None else None,
            "broadcast_reduction": 0.0,
        })
    k = len(per)
    summary = {
        "mean_ascir_reduction": round(sum(p["ascir_reduction"] for p in per) / k, 4) if k else None,
        "mean_broadcast_reduction": 0.0,
        "scenarios": k,
        "note": "mean over the full scenario mix; single-recipient cases reduce more than escalation/multi-sector ones",
    }
    return per, summary


def build_simulated_outputs(scenarios, jurisdictions):
    """Generate a run-output dict by running the reference oracle as a stand-in
    for the chaincode. Lets the scoring pipeline be tested offline; against this
    input, M2 must score a perfect exact-match rate by construction."""
    outputs = {}
    for sc in scenarios:
        report = sc["report"]
        recipients, _ = ref.evaluate_sba(
            report["policy_metadata"], report["reporter_org"], jurisdictions
        )
        outputs[sc["id"]] = {"authorized_recipients": recipients}
    return outputs


def main():
    ap = argparse.ArgumentParser(description="Score ASCIR M2/M3 from run outputs")
    ap.add_argument("--scenarios", required=True, help="scenario file (JSON)")
    ap.add_argument("--metric", required=True, choices=["M2", "M3"])
    ap.add_argument("--run", help="run-output file (JSON); omit with --simulate")
    ap.add_argument("--simulate", action="store_true",
                    help="use the SBA reference as a stand-in for the chaincode (offline pipeline test)")
    ap.add_argument("--n", type=int, help="network size (required for --simulate or if run file lacks 'n')")
    ap.add_argument("--out", help="write result JSON to this path (else stdout)")
    args = ap.parse_args()

    with open(args.scenarios) as f:
        sdoc = json.load(f)
    scenarios = sdoc["scenarios"]
    jurisdictions = sdoc.get("jurisdictions", ref.DEFAULT_JURISDICTIONS)
    scenario_set = sdoc.get("set", args.scenarios)

    if args.simulate:
        if args.n is None:
            ap.error("--simulate requires --n")
        n_orgs = args.n
        outputs = build_simulated_outputs(scenarios, jurisdictions)
        envelope_meta = {"chaincode": {"name": "ascir", "version": "1.1", "sequence": 1},
                         "fabric_version": "simulated", "endorser_count": None}
    else:
        if not args.run:
            ap.error("provide --run or use --simulate")
        with open(args.run) as f:
            rdoc = json.load(f)
        outputs = rdoc["outputs"]
        n_orgs = args.n if args.n is not None else rdoc.get("n")
        if n_orgs is None:
            ap.error("network size unknown: pass --n or include 'n' in the run file")
        envelope_meta = {"chaincode": rdoc.get("chaincode"),
                         "fabric_version": rdoc.get("fabric_version"),
                         "endorser_count": rdoc.get("endorser_count")}

    # every scenario must have an output
    missing = [sc["id"] for sc in scenarios if sc["id"] not in outputs]
    if missing:
        ap.error(f"run outputs missing scenarios: {missing}")

    # Scope the jurisdiction list to the present orgs (first n in canonical
    # order), matching what the chaincode actually had on the channel. The
    # scenario file's jurisdictions list is the full (n=4) universe; expected
    # recipients must be computed against the orgs present at measurement time.
    scoped_juris = jurisdictions[:n_orgs]

    if args.metric == "M2":
        per, summary = score_m2(scenarios, outputs, scoped_juris)
    else:
        per, summary = score_m3(scenarios, outputs, n_orgs, scoped_juris)

    result = {
        "metric": args.metric,
        "n": n_orgs,
        "scenario_set": scenario_set,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "per_scenario": per,
        "summary": summary,
        **envelope_meta,
    }
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        print(f"wrote {args.out}")
        print(json.dumps(summary, indent=2))
    else:
        print(text)


if __name__ == "__main__":
    main()
