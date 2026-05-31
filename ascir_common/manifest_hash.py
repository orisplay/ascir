"""Canonical manifest-hash computation (chaincode-interface.md Section 4.2).

A manifest hash uniquely identifies a specific version of a specific
agentic-AI component. It is the SHA-256 of a deterministic representation
of the component's installed file set: a sorted list of
(relative_path, file_sha256) pairs, each formatted as "<relpath>:<filehash>",
joined by newlines, UTF-8 encoded, and hashed with SHA-256.

This single implementation is imported by both the dataset generator and
the detector so that the two tools cannot diverge. The detector
additionally verifies its output against the independently generated
ground-truth file (see detector/detector.py --verify).
"""

import hashlib
from pathlib import Path


def compute_manifest_hash(component_dir):
    """SHA-256 of the concatenated sorted list of
    (relative_path, file_sha256) pairs."""
    component_dir = Path(component_dir)
    pairs = []
    for path in sorted(component_dir.rglob("*")):
        if path.is_file():
            rel_path = path.relative_to(component_dir).as_posix()
            file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            pairs.append(f"{rel_path}:{file_hash}")
    concatenated = "\n".join(pairs).encode("utf-8")
    return hashlib.sha256(concatenated).hexdigest()
