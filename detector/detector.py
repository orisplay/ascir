"""ASCIR artifact-level detector.

Given a directory containing an installed agentic-AI component, the detector
computes the component's manifest hash (chaincode-interface.md Section 4.2)
using the canonical implementation shared with the dataset generator
(ascir_common.manifest_hash). The hash is the artifact-level identity that an
investigator would query against the blockchain-anchored registry to determine
compromise status.

This module implements the detection (hashing) half of that workflow. Querying
the registry for status is performed against the Fabric network via the backend
API and is added once the network is stood up; it is intentionally not part of
this file, which is fully testable with no network.

Usage:
    # Compute the manifest hash of a single component directory:
    python detector/detector.py --component dataset/components/comp_001

    # Verify the detector reproduces every hash in the ground-truth file:
    python detector/detector.py --verify
    python detector/detector.py --verify --dataset-dir dataset
"""

import argparse
import csv
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="ASCIR artifact-level detector (manifest-hash computation).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--component", metavar="DIR",
        help="Compute and print the manifest hash of one component directory.")
    group.add_argument(
        "--verify", action="store_true",
        help="Recompute all components and compare against ground_truth.csv.")
    parser.add_argument(
        "--dataset-dir", default="dataset",
        help="Path to the dataset directory (default: dataset).")
    args = parser.parse_args(argv)

    if args.component:
        print(compute(args.component))
        return 0

    if args.verify:
        ok = verify(args.dataset_dir)
        return 0 if ok else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
