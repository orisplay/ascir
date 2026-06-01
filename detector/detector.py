"""ASCIR artifact-level detector.

Given a directory containing an installed agentic-AI component, the detector
computes the component's manifest hash (chaincode-interface.md Section 4.2)
using the canonical implementation shared with the dataset generator
(ascir_common.manifest_hash). The hash is the artifact-level identity that an
investigator would query against the blockchain-anchored registry to determine
compromise status.

This module implements the detection (hashing) half of that workflow, plus a
--check mode that queries the registry for a verdict. The query is currently
issued via the Fabric peer CLI as a subprocess; it requires the peer
environment (CORE_PEER_*, FABRIC_CFG_PATH, PATH) to be active in the calling
shell (see network/README.md section 3). A proper Fabric gateway backend will
replace the CLI path. The hashing modes (--component, --verify) need no
network and are fully testable offline.

Usage:
    # Compute the manifest hash of a single component directory:
    python detector/detector.py --component dataset/components/comp_001

    # Verify the detector reproduces every hash in the ground-truth file:
    python detector/detector.py --verify
    python detector/detector.py --verify --dataset-dir dataset

    # Full workflow: hash a component and query the registry for its status
    # (requires the peer env to be set and the network/chaincode up):
    python detector/detector.py --check dataset/components/comp_001
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

# Make the repo root importable so the shared ascir_common package resolves
# regardless of the current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ascir_common.manifest_hash import compute_manifest_hash


def compute(component_dir):
    """Return the manifest hash of a single component directory."""
    component_dir = Path(component_dir)
    if not component_dir.is_dir():
        raise NotADirectoryError(f"not a directory: {component_dir}")
    return compute_manifest_hash(component_dir)


def load_ground_truth(csv_path):
    """Load ground truth as a dict: component_id -> expected manifest_hash."""
    csv_path = Path(csv_path)
    expected = {}
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            expected[row["component_id"]] = row["manifest_hash"]
    return expected


def verify(dataset_dir):
    """Recompute every component's manifest hash and compare to ground truth.

    Returns (passed, failed, missing) counts and prints a per-mismatch report.
    A clean run (all hashes match) is the cross-check that the detector and the
    registry's recorded hashes agree.
    """
    dataset_dir = Path(dataset_dir)
    components_dir = dataset_dir / "components"
    csv_path = dataset_dir / "ground_truth.csv"

    expected = load_ground_truth(csv_path)

    passed = 0
    failed = 0
    missing_on_disk = 0
    mismatches = []

    for component_id, expected_hash in sorted(expected.items()):
        component_path = components_dir / component_id
        if not component_path.is_dir():
            missing_on_disk += 1
            mismatches.append(
                (component_id, "MISSING ON DISK", expected_hash, "-"))
            continue
        actual_hash = compute(component_path)
        if actual_hash == expected_hash:
            passed += 1
        else:
            failed += 1
            mismatches.append(
                (component_id, "HASH MISMATCH", expected_hash, actual_hash))

    total = len(expected)
    print(f"Verifying {total} components against {csv_path} ...")
    if mismatches:
        print("")
        for cid, kind, exp, act in mismatches:
            print(f"  [{kind}] {cid}")
            print(f"      expected: {exp}")
            print(f"      actual:   {act}")
        print("")
    print(f"  passed:           {passed}")
    print(f"  failed:           {failed}")
    print(f"  missing on disk:  {missing_on_disk}")

    ok = (failed == 0 and missing_on_disk == 0)
    print("")
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return ok


def query_status(manifest_hash, channel="mychannel", cc_name="ascir"):
    """Query the chaincode for a manifest hash's registry status.

    Issues `peer chaincode query` as a subprocess and returns the parsed
    StatusResponse dict. Requires the peer environment to be active in the
    calling shell (CORE_PEER_*, FABRIC_CFG_PATH, and `peer` on PATH); see
    network/README.md section 3. Raises RuntimeError with a clear message if
    `peer` is not found or the query fails.

    This CLI-based path is the interim integration; a Fabric gateway backend
    will replace it.
    """
    request = json.dumps({"function": "QueryCompromiseStatus",
                          "Args": [manifest_hash]})
    cmd = ["peer", "chaincode", "query", "-C", channel, "-n", cc_name,
           "-c", request]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError(
            "`peer` not found on PATH. Activate the Fabric peer environment "
            "first (see network/README.md section 3).")
    if proc.returncode != 0:
        raise RuntimeError(
            "peer chaincode query failed (is the network up and the peer env "
            f"set?):\n{proc.stderr.strip()}")
    out = proc.stdout.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError(f"could not parse query output as JSON:\n{out}")


def check(component_dir, channel="mychannel", cc_name="ascir"):
    """Full investigator workflow: hash a component, query the registry, and
    print a verdict. Returns the status string (e.g. 'known_good')."""
    h = compute(component_dir)
    resp = query_status(h, channel, cc_name)
    status = resp.get("status", "unknown")

    print(f"Component:       {component_dir}")
    print(f"Manifest hash:   {h}")
    print(f"Registry status: {status.upper()}")

    kg = resp.get("known_good_entry")
    if kg:
        print(f"  known-good:    {kg.get('component_name')} "
              f"v{kg.get('version')} (signed by {kg.get('signer_org')})")
    active = resp.get("active_compromise_reports") or []
    for r in active:
        sectors = ",".join(r.get("policy_metadata", {}).get("affected_sectors", []))
        sev = r.get("policy_metadata", {}).get("severity", "?")
        print(f"  compromise:    reported by {r.get('reporter_org')} "
              f"[sectors={sectors} severity={sev}] ref={r.get('evidence_ref')}")
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="ASCIR artifact-level detector (manifest-hash computation "
                    "and registry lookup).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--component", metavar="DIR",
        help="Compute and print the manifest hash of one component directory.")
    group.add_argument(
        "--verify", action="store_true",
        help="Recompute all components and compare against ground_truth.csv.")
    group.add_argument(
        "--check", metavar="DIR",
        help="Hash a component and query the registry for its status "
             "(requires the peer env and a running network).")
    parser.add_argument(
        "--dataset-dir", default="dataset",
        help="Path to the dataset directory (default: dataset).")
    parser.add_argument(
        "--channel", default="mychannel",
        help="Fabric channel name for --check (default: mychannel).")
    parser.add_argument(
        "--cc-name", default="ascir",
        help="Chaincode name for --check (default: ascir).")
    args = parser.parse_args(argv)

    if args.component:
        print(compute(args.component))
        return 0

    if args.verify:
        ok = verify(args.dataset_dir)
        return 0 if ok else 1

    if args.check:
        try:
            check(args.check, args.channel, args.cc_name)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
