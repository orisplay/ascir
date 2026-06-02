"""ASCIR artifact-level detector.

Given a directory containing an installed agentic-AI component, the detector
computes the component's manifest hash (chaincode-interface.md Section 4.2)
using the canonical implementation shared with the dataset generator
(ascir_common.manifest_hash). The hash is the artifact-level identity that an
investigator would query against the blockchain-anchored registry to determine
compromise status.

The detector can query the registry two ways:
  --check     issues the query via the Fabric peer CLI (interim path; requires
              the peer environment to be active in the calling shell).
  --check-api posts the hash to the ASCIR backend's HTTP API (the production
              path; requires the backend running, which holds the Fabric
              gateway connection). See backend/ and network/README.md.

The hashing modes (--component, --verify) need no network and are fully
testable offline.

Usage:
    python detector/detector.py --component dataset/components/comp_001
    python detector/detector.py --verify
    python detector/detector.py --check dataset/components/comp_001
    python detector/detector.py --check-api dataset/components/comp_001
    python detector/detector.py --check-api dataset/components/comp_001 \\
        --backend-url http://localhost:3000
"""

import argparse
import csv
import json
import subprocess
import sys
import urllib.error
import urllib.request
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


def query_status_cli(manifest_hash, channel="mychannel", cc_name="ascir"):
    """Query the chaincode for a manifest hash's status via the peer CLI.

    Issues `peer chaincode query` as a subprocess and returns the parsed
    StatusResponse dict. Requires the peer environment to be active in the
    calling shell (CORE_PEER_*, FABRIC_CFG_PATH, and `peer` on PATH); see
    network/README.md section 3. Raises RuntimeError on failure.

    This CLI path predates the gateway backend and is kept as a fallback.
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


def query_status_api(manifest_hash, backend_url="http://localhost:3000"):
    """Query the registry for a manifest hash's status via the backend HTTP API.

    POSTs {"manifest_hash": ...} to <backend_url>/check and returns the parsed
    StatusResponse dict. Requires the ASCIR backend to be running (it holds the
    Fabric gateway connection). Raises RuntimeError on failure. Uses only the
    standard library so the detector has no third-party dependencies.
    """
    url = backend_url.rstrip("/") + "/check"
    payload = json.dumps({"manifest_hash": manifest_hash}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"backend returned HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"could not reach backend at {url} (is it running?): {e.reason}")
    except json.JSONDecodeError:
        raise RuntimeError("could not parse backend response as JSON")


def _print_verdict(component_dir, manifest_hash, resp):
    """Print a human-readable verdict from a StatusResponse dict."""
    status = resp.get("status", "unknown")
    print(f"Component:       {component_dir}")
    print(f"Manifest hash:   {manifest_hash}")
    print(f"Registry status: {status.upper()}")

    kg = resp.get("known_good_entry")
    if kg:
        print(f"  known-good:    {kg.get('component_name')} "
              f"v{kg.get('version')} (signed by {kg.get('signer_org')})")
    active = resp.get("active_compromise_reports") or []
    for r in active:
        sectors = ",".join(
            r.get("policy_metadata", {}).get("affected_sectors", []))
        sev = r.get("policy_metadata", {}).get("severity", "?")
        print(f"  compromise:    reported by {r.get('reporter_org')} "
              f"[sectors={sectors} severity={sev}] ref={r.get('evidence_ref')}")
    return status


def check(component_dir, channel="mychannel", cc_name="ascir"):
    """Investigator workflow via the peer CLI: hash, query, print a verdict."""
    h = compute(component_dir)
    resp = query_status_cli(h, channel, cc_name)
    return _print_verdict(component_dir, h, resp)


def check_api(component_dir, backend_url="http://localhost:3000"):
    """Investigator workflow via the backend HTTP API: hash, query, verdict."""
    h = compute(component_dir)
    resp = query_status_api(h, backend_url)
    return _print_verdict(component_dir, h, resp)


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
        help="Hash a component and query the registry via the peer CLI "
             "(requires the peer env and a running network).")
    group.add_argument(
        "--check-api", metavar="DIR",
        help="Hash a component and query the registry via the backend HTTP "
             "API (requires the backend running).")
    parser.add_argument(
        "--dataset-dir", default="dataset",
        help="Path to the dataset directory (default: dataset).")
    parser.add_argument(
        "--channel", default="mychannel",
        help="Fabric channel name for --check (default: mychannel).")
    parser.add_argument(
        "--cc-name", default="ascir",
        help="Chaincode name for --check (default: ascir).")
    parser.add_argument(
        "--backend-url", default="http://localhost:3000",
        help="Backend base URL for --check-api (default: http://localhost:3000).")
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

    if args.check_api:
        try:
            check_api(args.check_api, args.backend_url)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
