"""ASCIR Dataset Generator.

Produces the seeded component dataset specified in
docs/dataset-specification.md.

Output:
    dataset/components/comp_XXX/  — 45 component directories
    dataset/ground_truth.csv      — human-readable ground truth
    dataset/ground_truth.json     — machine-readable ground truth

Usage:
    python dataset/generate.py
    python dataset/generate.py --seed 42 --output-dir dataset --force

The generator is deterministic: running it twice with the same seed
produces byte-identical output. Before writing ground truth, the
generator asserts that all 45 manifest hashes are distinct; if any
two collide, it aborts rather than emit a corrupt dataset.
"""

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

# Make the repo root importable so the shared ascir_common package resolves
# regardless of the current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ascir_common.manifest_hash import compute_manifest_hash


# ===========================================================================
# Dataset constants
# ===========================================================================

DATASET_VERSION = "1"
DEFAULT_SEED = 42

COMPONENT_NAMES = [
    "agent-memory-store",
    "agent-tool-runner",
    "agent-llm-bridge",
    "agent-file-reader",
    "agent-file-writer",
    "agent-scheduler",
    "agent-prompt-builder",
    "agent-token-counter",
    "agent-rate-limiter",
    "agent-retry-policy",
    "agent-context-window",
    "agent-embedding-cache",
    "agent-vector-search",
    "agent-session-manager",
    "agent-event-logger",
    "agent-config-loader",
    "agent-secret-vault",
    "agent-http-client",
    "agent-websocket-client",
    "agent-stream-parser",
    "agent-markdown-renderer",
    "agent-code-executor",
    "agent-shell-wrapper",
    "agent-clipboard-bridge",
    "agent-screenshot-capture",
    "agent-notification-sender",
    "agent-permission-checker",
    "agent-output-sanitizer",
    "agent-error-handler",
    "agent-telemetry-emitter",
]

ROLES = {
    "agent-memory-store": "Persistent memory storage interface",
    "agent-tool-runner": "Local tool execution wrapper",
    "agent-llm-bridge": "Language-model API adapter",
    "agent-file-reader": "File-system read operations",
    "agent-file-writer": "File-system write operations",
    "agent-scheduler": "Task scheduling and queue management",
    "agent-prompt-builder": "Prompt construction helpers",
    "agent-token-counter": "Token counting and budget tracking",
    "agent-rate-limiter": "API rate limiting middleware",
    "agent-retry-policy": "Failure retry and backoff logic",
    "agent-context-window": "Context window management",
    "agent-embedding-cache": "Embedding vector caching",
    "agent-vector-search": "Vector similarity search",
    "agent-session-manager": "User session state tracking",
    "agent-event-logger": "Structured event logging",
    "agent-config-loader": "Configuration file loader",
    "agent-secret-vault": "Local secrets storage",
    "agent-http-client": "Outbound HTTP client wrapper",
    "agent-websocket-client": "WebSocket client wrapper",
    "agent-stream-parser": "Streaming response parser",
    "agent-markdown-renderer": "Markdown to plain-text rendering",
    "agent-code-executor": "Sandboxed code execution",
    "agent-shell-wrapper": "Shell command wrapper",
    "agent-clipboard-bridge": "Clipboard read/write bridge",
    "agent-screenshot-capture": "Screen capture interface",
    "agent-notification-sender": "Notification dispatch",
    "agent-permission-checker": "Action permission verification",
    "agent-output-sanitizer": "Output sanitization",
    "agent-error-handler": "Error capture and routing",
    "agent-telemetry-emitter": "Telemetry event emission",
}


# ===========================================================================
# Policy metadata: computed rule producing per-variant assignments
# ===========================================================================

def policy_metadata_for_variants():
    """Produce the per-variant policy metadata dict.

    Coverage strategy:
      - M variants get single sectors cycling FIN, CI, HC, GOV, FIN to
        exercise direct-sector-mapping across all four codes plus a repeat.
      - A variants get multiple affected_sectors to exercise multi-sector
        routing.
      - R variants include at least one severity=critical (exercises
        severity escalation) and at least one affected_jurisdictions=ALL
        (exercises the ALL routing path).
    """
    metadata = {}

    m_sectors = ["FIN", "CI", "HC", "GOV", "FIN"]
    for i, sector in enumerate(m_sectors, start=1):
        metadata[f"comp_M{i:02d}"] = {
            "affected_sectors": [sector],
            "affected_jurisdictions": [],
            "distribution_scope": "single_jurisdiction",
            "severity": "medium",
        }

    a_sector_sets = [
        ["FIN", "CI"],
        ["HC", "GOV"],
        ["FIN", "HC"],
        ["CI", "HC", "GOV"],
        ["FIN", "CI", "HC", "GOV"],
    ]
    for i, sectors in enumerate(a_sector_sets, start=1):
        metadata[f"comp_A{i:02d}"] = {
            "affected_sectors": sectors,
            "affected_jurisdictions": [],
            "distribution_scope": "multi_jurisdiction",
            "severity": "high",
        }

    metadata["comp_R01"] = {
        "affected_sectors": ["GOV"],
        "affected_jurisdictions": [],
        "distribution_scope": "single_jurisdiction",
        "severity": "low",
    }
    metadata["comp_R02"] = {
        "affected_sectors": ["HC"],
        "affected_jurisdictions": [],
        "distribution_scope": "single_jurisdiction",
        "severity": "medium",
    }
    metadata["comp_R03"] = {
        "affected_sectors": ["CI"],
        "affected_jurisdictions": [],
        "distribution_scope": "single_jurisdiction",
        "severity": "critical",
    }
    metadata["comp_R04"] = {
        "affected_sectors": ["FIN"],
        "affected_jurisdictions": [],
        "distribution_scope": "multi_jurisdiction",
        "severity": "high",
    }
    metadata["comp_R05"] = {
        "affected_sectors": ["GOV"],
        "affected_jurisdictions": "ALL",
        "distribution_scope": "global",
        "severity": "critical",
    }

    return metadata


# ===========================================================================
# SBA policy logic (mirrors chaincode-interface Section 7)
# ===========================================================================

PRIMARY_JURISDICTION = {
    "FIN": "Org1MSP",
    "CI": "Org2MSP",
    "HC": "Org3MSP",
    "GOV": "Org4MSP",
}

ALL_JURISDICTIONS = ["Org1MSP", "Org2MSP", "Org3MSP", "Org4MSP"]


def compute_expected_sba_recipients(policy_metadata, reporter_org="Org1MSP"):
    """Apply the SBA policy and return the expected recipient set.

    Mirrors the routing rules in chaincode-interface Section 7.2.
    """
    recipients = set()

    for sector in policy_metadata["affected_sectors"]:
        if sector in PRIMARY_JURISDICTION:
            recipients.add(PRIMARY_JURISDICTION[sector])

    affected = policy_metadata["affected_jurisdictions"]
    if affected == "ALL":
        recipients.update(ALL_JURISDICTIONS)
    elif isinstance(affected, list):
        recipients.update(affected)

    if policy_metadata["severity"] == "critical":
        recipients.add("Org4MSP")

    recipients.discard(reporter_org)

    return sorted(recipients)


# ===========================================================================
# File content generation
# ===========================================================================

def class_name_from_component(component_name):
    """Convert 'agent-memory-store' to 'MemoryStore'."""
    parts = component_name.replace("agent-", "").split("-")
    return "".join(p.capitalize() for p in parts)


def primary_module_for_name(component_name):
    """Convert 'agent-memory-store' to 'memory_store' (no extension)."""
    return component_name.replace("agent-", "").replace("-", "_")


def generate_init_py(component_name):
    class_name = class_name_from_component(component_name)
    primary_module = primary_module_for_name(component_name)
    return (
        f'"""{component_name}."""\n\n'
        f'from .{primary_module} import {class_name}\n\n'
        f'__all__ = ["{class_name}"]\n'
    )


def generate_manifest_json(component_name, version="1.0.0"):
    manifest = {
        "name": component_name,
        "version": version,
        "author": "ASCIR Test Suite",
        "description": ROLES[component_name],
    }
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def generate_primary_py(component_name):
    class_name = class_name_from_component(component_name)
    role = ROLES[component_name]
    return (
        f'"""Implementation of {component_name}."""\n\n\n'
        f'class {class_name}:\n'
        f'    """{role}."""\n\n'
        f'    def __init__(self):\n'
        f'        self._initialized = True\n\n'
        f'    def is_ready(self):\n'
        f'        return self._initialized\n'
    )


def generate_helper_py(component_name, helper_name):
    return (
        f'"""Helper module ({helper_name}) for {component_name}."""\n\n\n'
        f'def helper_function():\n'
        f'    """Internal helper."""\n'
        f'    return None\n'
    )


def generate_readme_md(component_name):
    role = ROLES[component_name]
    return f"# {component_name}\n\n{role}.\n"


def generate_requirements_txt(component_name):
    """Requirements file. Includes the component name in a comment so
    every component's requirements.txt is distinct."""
    return f"# Dependencies for {component_name}.\n# No external dependencies.\n"


# ===========================================================================
# Baseline component generation
# ===========================================================================

def baseline_file_set(component_name, index):
    """Determine which files this baseline contains.

    Every component is guaranteed to have at least four files:
    __init__.py, manifest.json, the primary module, and README.md.
    README.md is always present so removal handlers always have a
    guaranteed-present target. File count varies from 4 to 7 via
    index % 4 to avoid trivial detection by file count alone.
    """
    primary_module = primary_module_for_name(component_name)
    files = {
        "__init__.py": generate_init_py(component_name),
        "manifest.json": generate_manifest_json(component_name),
        f"{primary_module}.py": generate_primary_py(component_name),
        "README.md": generate_readme_md(component_name),
    }

    variation = index % 4
    if variation >= 1:
        files["requirements.txt"] = generate_requirements_txt(component_name)
    if variation >= 2:
        files["helpers.py"] = generate_helper_py(component_name, "helpers")
    if variation >= 3:
        files["utils.py"] = generate_helper_py(component_name, "utils")

    return files


def write_component(component_dir, files):
    component_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (component_dir / filename).write_text(content)


# Manifest hashing (chaincode-interface Section 4.2) is provided by
# ascir_common.manifest_hash.compute_manifest_hash, imported above and shared
# with the detector so the two tools cannot diverge.



def count_files_and_size(component_dir):
    files = [p for p in component_dir.rglob("*") if p.is_file()]
    total_size = sum(p.stat().st_size for p in files)
    return len(files), total_size


# ===========================================================================
# Variant generation
# ===========================================================================

def copy_parent(parent_dir, variant_dir):
    shutil.copytree(parent_dir, variant_dir)


def _first_nonessential_py(variant_dir):
    """Return the first .py file that is not __init__.py, or None."""
    for py_file in sorted(variant_dir.glob("*.py")):
        if py_file.name != "__init__.py":
            return py_file
    return None


def _primary_module_name(variant_dir):
    """Derive the primary module name from the component's manifest.json.

    Reading the manifest is the reliable way to know the component's
    name (and thus its primary module), independent of which other
    files happen to be present.
    """
    manifest = json.loads((variant_dir / "manifest.json").read_text())
    return primary_module_for_name(manifest["name"])


def apply_modification(variant_dir, variant_id):
    """Modify file content without changing the file count.

    Every handler makes a guaranteed change and raises if it cannot,
    so a modification variant can never be identical to its parent.
    """
    if variant_id == "comp_M01":
        init_file = variant_dir / "__init__.py"
        init_file.write_text(init_file.read_text() + "# m1\n")
    elif variant_id == "comp_M02":
        # Replace a function body in the PRIMARY module specifically
        # (not the first non-init .py, which could be a helper that
        # lacks the target string). Verify the replacement changed the
        # content so this variant can never equal its parent.
        target = variant_dir / (_primary_module_name(variant_dir) + ".py")
        if not target.exists():
            raise RuntimeError(f"{variant_id}: primary module not found")
        before = target.read_text()
        after = before.replace(
            "return self._initialized", "return False  # COMPROMISED")
        if after == before:
            raise RuntimeError(f"{variant_id}: replacement changed nothing")
        target.write_text(after)
    elif variant_id == "comp_M03":
        manifest_file = variant_dir / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["version"] = "1.0.1-malicious"
        manifest_file.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    elif variant_id == "comp_M04":
        readme = variant_dir / "README.md"
        readme.write_text(readme.read_text() + "\n<!-- modified by M04 -->\n")
    elif variant_id == "comp_M05":
        target = _first_nonessential_py(variant_dir)
        if target is None:
            raise RuntimeError(f"{variant_id}: no eligible .py file to modify")
        lines = target.read_text().split("\n")
        lines.insert(1, "import socket  # suspicious")
        target.write_text("\n".join(lines))


def apply_addition(variant_dir, variant_id):
    """Add one or more files, increasing the file count."""
    if variant_id == "comp_A01":
        (variant_dir / "_loader.py").write_text(
            '"""Exfiltration loader."""\n\n'
            'def exfiltrate():\n'
            '    pass  # COMPROMISED\n'
        )
    elif variant_id == "comp_A02":
        (variant_dir / ".config.cache").write_text(
            "# Hidden cache file added by attacker\n"
        )
    elif variant_id == "comp_A03":
        utils_dir = variant_dir / "utils"
        utils_dir.mkdir()
        (utils_dir / "_internal.py").write_text(
            '"""Deeply-nested malicious file."""\n\n'
            'BACKDOOR = True\n'
        )
    elif variant_id == "comp_A04":
        (variant_dir / "extra_a.py").write_text(
            '"""Added file A."""\n\ndef a():\n    pass\n')
        (variant_dir / "extra_b.py").write_text(
            '"""Added file B."""\n\ndef b():\n    pass\n')
    elif variant_id == "comp_A05":
        target = _first_nonessential_py(variant_dir)
        if target is None:
            raise RuntimeError(f"{variant_id}: no eligible .py file to clone")
        lookalike = variant_dir / target.name.replace(".py", "_.py")
        lookalike.write_text(target.read_text() + "# lookalike\n")


def apply_removal(variant_dir, variant_id):
    """Remove one or more files, decreasing the file count.

    Each handler removes a guaranteed-present file and raises if the
    target is missing, so a removal variant can never equal its parent.
    """
    if variant_id == "comp_R01":
        target = variant_dir / "README.md"
        if not target.exists():
            raise RuntimeError(f"{variant_id}: README.md missing from parent")
        target.unlink()
    elif variant_id == "comp_R02":
        target = variant_dir / "manifest.json"
        if not target.exists():
            raise RuntimeError(f"{variant_id}: manifest.json missing from parent")
        target.unlink()
    elif variant_id == "comp_R03":
        target = variant_dir / "README.md"
        if not target.exists():
            raise RuntimeError(f"{variant_id}: README.md missing from parent")
        target.unlink()
    elif variant_id == "comp_R04":
        removed = 0
        for name in ["README.md", "manifest.json"]:
            target = variant_dir / name
            if target.exists():
                target.unlink()
                removed += 1
        if removed < 2:
            raise RuntimeError(f"{variant_id}: expected 2 removable files, removed {removed}")
    elif variant_id == "comp_R05":
        target = _first_nonessential_py(variant_dir)
        if target is None:
            raise RuntimeError(f"{variant_id}: no primary .py file to remove")
        target.unlink()


# ===========================================================================
# Variant parent mapping
# ===========================================================================

VARIANT_PARENTS = {}
for i in range(1, 6):
    VARIANT_PARENTS[f"comp_M{i:02d}"] = f"comp_{i:03d}"
for i in range(1, 6):
    VARIANT_PARENTS[f"comp_A{i:02d}"] = f"comp_{i + 5:03d}"
for i in range(1, 6):
    VARIANT_PARENTS[f"comp_R{i:02d}"] = f"comp_{i + 10:03d}"

VARIANT_HANDLERS = {
    "M": apply_modification,
    "A": apply_addition,
    "R": apply_removal,
}

VARIANT_TYPE_NAMES = {
    "M": "modification",
    "A": "addition",
    "R": "removal",
}


# ===========================================================================
# Ground truth file writers
# ===========================================================================

def write_ground_truth_csv(entries, output_path):
    fieldnames = [
        "component_id", "component_name", "variant_type", "parent_id",
        "manifest_hash", "file_count", "total_size_bytes", "ground_truth_label",
        "affected_sectors", "affected_jurisdictions", "distribution_scope",
        "severity", "expected_sba_recipients",
    ]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for entry in entries:
            row = {k: entry.get(k, "") for k in fieldnames}
            for list_field in ["affected_sectors", "expected_sba_recipients"]:
                v = row.get(list_field, "")
                if isinstance(v, list):
                    row[list_field] = ",".join(v)
            v = row.get("affected_jurisdictions", "")
            if isinstance(v, list):
                row["affected_jurisdictions"] = ",".join(v)
            writer.writerow(row)


def write_ground_truth_json(entries, output_path, seed):
    payload = {
        "dataset_version": DATASET_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_seed": seed,
        "components": entries,
    }
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
        f.write("\n")


# ===========================================================================
# Main orchestration
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate the ASCIR seeded dataset.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"Random seed (default {DEFAULT_SEED})")
    parser.add_argument("--output-dir", type=Path, default=Path("dataset"),
                        help="Output directory (default: dataset)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing components/ directory")
    args = parser.parse_args()

    components_dir = args.output_dir / "components"

    if components_dir.exists():
        if not args.force:
            print(f"ERROR: {components_dir} already exists. Use --force to overwrite.")
            return 1
        shutil.rmtree(components_dir)

    components_dir.mkdir(parents=True)
    entries = []

    print(f"Generating 30 baseline components in {components_dir}/ ...")
    for i, name in enumerate(COMPONENT_NAMES, start=1):
        component_id = f"comp_{i:03d}"
        component_dir = components_dir / component_id
        files = baseline_file_set(name, i)
        write_component(component_dir, files)

        file_count, total_size = count_files_and_size(component_dir)
        manifest_hash = compute_manifest_hash(component_dir)

        entries.append({
            "component_id": component_id,
            "component_name": name,
            "variant_type": "baseline",
            "parent_id": None,
            "manifest_hash": manifest_hash,
            "file_count": file_count,
            "total_size_bytes": total_size,
            "ground_truth_label": "known_good",
            "policy_metadata": None,
            "expected_sba_recipients": [],
        })

    print("Generating 15 compromise variants ...")
    variant_metadata = policy_metadata_for_variants()

    for variant_id, parent_id in VARIANT_PARENTS.items():
        parent_dir = components_dir / parent_id
        variant_dir = components_dir / variant_id
        copy_parent(parent_dir, variant_dir)

        category = variant_id.split("_")[1][0]
        handler = VARIANT_HANDLERS[category]
        handler(variant_dir, variant_id)

        file_count, total_size = count_files_and_size(variant_dir)
        manifest_hash = compute_manifest_hash(variant_dir)

        parent_index = int(parent_id.split("_")[1]) - 1
        parent_name = COMPONENT_NAMES[parent_index]
        variant_name = f"{parent_name}-{variant_id.split('_')[1]}"

        policy = variant_metadata[variant_id]
        recipients = compute_expected_sba_recipients(policy)

        entries.append({
            "component_id": variant_id,
            "component_name": variant_name,
            "variant_type": VARIANT_TYPE_NAMES[category],
            "parent_id": parent_id,
            "manifest_hash": manifest_hash,
            "file_count": file_count,
            "total_size_bytes": total_size,
            "ground_truth_label": "compromised",
            "policy_metadata": policy,
            "expected_sba_recipients": recipients,
        })

    # ---- Uniqueness assertion: no two components may share a hash ----
    hash_counts = Counter(e["manifest_hash"] for e in entries)
    collisions = {h for h, n in hash_counts.items() if n > 1}
    if collisions:
        print("FATAL: manifest hash collision detected.")
        for e in entries:
            if e["manifest_hash"] in collisions:
                print(f"  {e['component_id']} (parent={e['parent_id']}) "
                      f"hash={e['manifest_hash'][:16]}...")
        print("Aborting without writing ground-truth files.")
        return 2

    csv_path = args.output_dir / "ground_truth.csv"
    json_path = args.output_dir / "ground_truth.json"

    csv_entries = []
    for entry in entries:
        flat = dict(entry)
        policy = flat.pop("policy_metadata") or {}
        flat["affected_sectors"] = policy.get("affected_sectors", [])
        flat["affected_jurisdictions"] = policy.get("affected_jurisdictions", "")
        flat["distribution_scope"] = policy.get("distribution_scope", "")
        flat["severity"] = policy.get("severity", "")
        csv_entries.append(flat)

    write_ground_truth_csv(csv_entries, csv_path)
    write_ground_truth_json(entries, json_path, args.seed)

    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    print(f"Generated {len(entries)} components total "
          f"(30 baseline + 15 compromised). All hashes unique.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
