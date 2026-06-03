#!/usr/bin/env python3
"""Reference implementation of the ASCIR Selective Broadcast Algorithm.

This is an independent oracle for the SBA policy, implemented directly from the
specification in docs/chaincode-interface.md S7. It deliberately shares no code
with the Go chaincode: agreement between this reference and the chaincode is the
M2 routing-precision measurement, and agreement between this reference and the
hand-authored expected_recipients in the scenario files validates the ground
truth. It is a pure function of its inputs and a static jurisdiction config.

Usage:
  python sba_reference.py --validate experiments/scenarios/routing_core.json
  python sba_reference.py --route '{"affected_sectors":["CI"],"severity":"critical",...}' --reporter Org1MSP
"""
import argparse
import json
import sys

# Static configuration (the policy layer's sector -> primary jurisdiction map).
# Per docs/chaincode-interface.md S7.1 and the project sector taxonomy:
#   FIN -> Org1MSP, CI -> Org2MSP, HC -> Org3MSP, GOV -> Org4MSP.
SECTOR_TO_JURISDICTION = {
    "FIN": "Org1MSP",
    "CI": "Org2MSP",
    "HC": "Org3MSP",
    "GOV": "Org4MSP",
}

# The general national CERT, used as the severity-escalation target (S7.2 phase 3).
NATIONAL_CERT = "Org4MSP"

DEFAULT_JURISDICTIONS = ["Org1MSP", "Org2MSP", "Org3MSP", "Org4MSP"]


def evaluate_sba(policy_metadata, reporter_org, jurisdictions=None):
    """Compute the authorized recipient set from a report's policy_metadata.

    Implements the three-phase policy of S7.2 followed by reporter exclusion.
    Returns (recipients_sorted, trace) where trace mirrors the chaincode's
    policy_trace structure for auditability.

    The recipient set has set semantics (a jurisdiction added twice appears
    once); ordering of the returned list is deterministic (sorted) so that
    comparisons are stable. The chaincode preserves insertion order in its own
    output, so callers comparing to the chaincode should compare as sets.
    """
    if jurisdictions is None:
        jurisdictions = list(DEFAULT_JURISDICTIONS)

    recipients = []  # preserve insertion order; dedup on add
    trace = []

    known = set(jurisdictions)

    def add(jurisdiction, rule, input_value):
        if jurisdiction not in known:
            # Rule fired but its target is not present on the channel: add nothing.
            trace.append({"rule": rule, "input": input_value, "added": []})
        elif jurisdiction not in recipients:
            recipients.append(jurisdiction)
            trace.append({"rule": rule, "input": input_value, "added": [jurisdiction]})
        else:
            trace.append({"rule": rule, "input": input_value, "added": []})

    sectors = policy_metadata.get("affected_sectors", []) or []
    explicit = policy_metadata.get("affected_jurisdictions", []) or []
    severity = policy_metadata.get("severity", "")

    # Phase 1: direct sector mapping.
    for sector in sectors:
        mapped = SECTOR_TO_JURISDICTION.get(sector)
        if mapped is None:
            # Unknown sector code: the spec's static map has no entry; skip it.
            # (The controlled vocabulary is FIN/CI/HC/GOV; anything else is a
            # data error and contributes no recipient.)
            trace.append({"rule": "sector_mapping", "input": sector, "added": [], "note": "unknown_sector"})
            continue
        add(mapped, "sector_mapping", sector)

    # Phase 2: explicit jurisdiction inclusion, with ALL expansion.
    for j in explicit:
        if j == "ALL":
            for known in jurisdictions:
                add(known, "explicit_jurisdiction", "ALL")
        else:
            add(j, "explicit_jurisdiction", j)

    # Phase 3: severity escalation.
    if severity == "critical":
        add(NATIONAL_CERT, "severity_escalation", "critical")

    # Reporter exclusion, applied after all three phases (S7.2).
    if reporter_org in recipients:
        recipients = [r for r in recipients if r != reporter_org]
        trace.append({"rule": "reporter_exclusion", "input": reporter_org, "removed": [reporter_org]})

    return sorted(recipients), trace


def validate_scenarios(path):
    """Run the reference over a scenario file and check expected_recipients."""
    with open(path) as f:
        doc = json.load(f)
    jurisdictions = doc.get("jurisdictions", DEFAULT_JURISDICTIONS)
    scenarios = doc["scenarios"]
    passed = 0
    failures = []
    for sc in scenarios:
        report = sc["report"]
        computed, _ = evaluate_sba(
            report["policy_metadata"], report["reporter_org"], jurisdictions
        )
        expected = sorted(sc["expected_recipients"])
        if computed == expected:
            passed += 1
        else:
            failures.append((sc["id"], expected, computed))
    print(f"{path}: {passed}/{len(scenarios)} scenarios match the reference")
    if failures:
        print("\nMISMATCHES (expected vs reference-computed):")
        for sid, exp, got in failures:
            print(f"  {sid}: expected {exp}  !=  computed {got}")
        return False
    print("All scenario ground-truth recipients agree with the SBA reference.")
    return True


def main():
    ap = argparse.ArgumentParser(description="ASCIR SBA reference oracle")
    ap.add_argument("--validate", metavar="SCENARIO_JSON",
                    help="validate a scenario file's expected_recipients against the reference")
    ap.add_argument("--route", metavar="POLICY_METADATA_JSON",
                    help="compute recipients for one policy_metadata blob")
    ap.add_argument("--reporter", default="Org1MSP",
                    help="reporter org for --route (default Org1MSP)")
    ap.add_argument("--jurisdictions", metavar="JSON_LIST",
                    help="override the known-jurisdiction list (JSON array)")
    args = ap.parse_args()

    juris = json.loads(args.jurisdictions) if args.jurisdictions else None

    if args.validate:
        ok = validate_scenarios(args.validate)
        sys.exit(0 if ok else 1)
    elif args.route:
        pm = json.loads(args.route)
        recipients, trace = evaluate_sba(pm, args.reporter, juris)
        print(json.dumps({"authorized_recipients": recipients, "policy_trace": trace}, indent=2))
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
