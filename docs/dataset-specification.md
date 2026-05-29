# ASCIR Seeded Component Dataset Specification

*Agentic Supply-Chain Incident Routing — Design Document 3 of N*

*Draft v0.1 — Working Document*

---

## 1. Purpose and Scope

This document specifies the seeded component dataset used to evaluate the ASCIR system. The dataset is the answer key against which detection accuracy (M1) and routing precision (M2) are computed. Without a documented dataset, the headline metrics are unverifiable; with one, they become reproducible measurements.

The dataset consists of two parts: a set of simulated agent components representing legitimate software, and a set of seeded compromise variants derived from those components. Each entry carries a ground-truth label that the chaincode and detector are expected to produce. The dataset is version-controlled as `dataset_v1`; any change to its content or structure requires a version bump rather than silent mutation.

The dataset is deliberately not derived from any real-world agent software. Components are mock packages constructed for the experimental design, with names chosen to resemble plausible entries in an agentic-AI package ecosystem without referencing or imitating any actual real-world package. This choice is intentional: the research contribution is detection of supply-chain compromises at the artifact level, not the analysis or discovery of specific malicious real-world packages.

## 2. Component Structure

A single mock agent component is a directory containing a small set of Python files organized as a minimal package. The structure is deliberately uniform across the dataset so that manifest-hash computation is consistent and the detector can be exercised against a controlled, predictable layout.

### 2.1 Required Files

Every component contains at minimum the following files:

- `__init__.py` — package initialization, declares the component's public symbols
- `manifest.json` — component metadata (name, version, declared dependencies, author)
- A primary implementation file named after the component's role (e.g., `memory_store.py`, `tool_runner.py`)

### 2.2 Optional Files

Depending on the component's role, the directory may also contain:

- One or two additional `.py` modules (helpers, utilities, internal interfaces)
- A `README.md` documenting the component's purpose
- A `requirements.txt` listing declared dependencies

Component sizes range from 3 to 7 files. The variation is deliberate: a uniform file count would make compromise detection trivially identifiable by file count alone, which is not the realistic case.

### 2.3 File Contents

Component file contents are plausible but minimal Python — function definitions with docstrings, a few imports, and small bodies that do not need to execute correctly. The components are never run during the experiments; they exist only as on-disk artifacts whose manifest hashes are computed.

Total component size ranges from approximately 800 to 2,500 bytes. This size range is small enough that the entire dataset fits comfortably in version control, large enough that manifest hashes are statistically robust.

### 2.4 Manifest Hash Computation

The manifest hash for a component is computed exactly as specified in the chaincode interface specification (Section 4.2):

1. Walk the component directory recursively
2. Produce a sorted list of `(relative_path, file_sha256)` pairs for every file
3. Concatenate the sorted list as a deterministic string
4. Compute SHA-256 of that string; the result is the component's manifest hash

The hash is independent of file modification times, inode numbers, and any filesystem metadata. Two filesystems that contain the same files with the same contents at the same relative paths produce the same manifest hash, which is the reproducibility property the dataset depends on.

## 3. Baseline Component Inventory

The dataset contains 30 baseline components representing legitimate, known-good agent ecosystem packages. Each is identified by a stable `component_id` of the form `comp_XXX`. Component names follow a `agent-<role>-<descriptor>` pattern to mirror conventions in real package ecosystems without imitating any specific real package.

| ID | Component name | Role |
|---|---|---|
| comp_001 | agent-memory-store | Persistent memory storage interface |
| comp_002 | agent-tool-runner | Local tool execution wrapper |
| comp_003 | agent-llm-bridge | Language-model API adapter |
| comp_004 | agent-file-reader | File-system read operations |
| comp_005 | agent-file-writer | File-system write operations |
| comp_006 | agent-scheduler | Task scheduling and queue management |
| comp_007 | agent-prompt-builder | Prompt construction helpers |
| comp_008 | agent-token-counter | Token counting and budget tracking |
| comp_009 | agent-rate-limiter | API rate limiting middleware |
| comp_010 | agent-retry-policy | Failure retry and backoff logic |
| comp_011 | agent-context-window | Context window management |
| comp_012 | agent-embedding-cache | Embedding vector caching |
| comp_013 | agent-vector-search | Vector similarity search |
| comp_014 | agent-session-manager | User session state tracking |
| comp_015 | agent-event-logger | Structured event logging |
| comp_016 | agent-config-loader | Configuration file loader |
| comp_017 | agent-secret-vault | Local secrets storage |
| comp_018 | agent-http-client | Outbound HTTP client wrapper |
| comp_019 | agent-websocket-client | WebSocket client wrapper |
| comp_020 | agent-stream-parser | Streaming response parser |
| comp_021 | agent-markdown-renderer | Markdown to plain-text rendering |
| comp_022 | agent-code-executor | Sandboxed code execution |
| comp_023 | agent-shell-wrapper | Shell command wrapper |
| comp_024 | agent-clipboard-bridge | Clipboard read/write bridge |
| comp_025 | agent-screenshot-capture | Screen capture interface |
| comp_026 | agent-notification-sender | Notification dispatch |
| comp_027 | agent-permission-checker | Action permission verification |
| comp_028 | agent-output-sanitizer | Output sanitization |
| comp_029 | agent-error-handler | Error capture and routing |
| comp_030 | agent-telemetry-emitter | Telemetry event emission |

Each baseline component is constructed by the generator script with a fixed random seed, ensuring that the manifest hashes are deterministic and reproducible across machines.

## 4. Compromise Variant Categories

Fifteen compromised variants are derived from a subset of the baseline components (one variant per parent component, drawn from `comp_001` through `comp_015`). The variants are partitioned into three categories based on how the file set changes relative to the parent:

- **Modification** (5 variants) — file count unchanged, one or more file contents differ
- **Addition** (5 variants) — file count increases; legitimate files are unchanged
- **Removal** (5 variants) — file count decreases; remaining legitimate files are unchanged

This three-way partition is chosen because each category produces a structurally distinct change in the manifest-hash inputs: modifications change individual entries in the sorted hash list, additions extend the list, and removals shorten it. Per-category detection rates can therefore be reported independently, which strengthens the M1 breakdown in the eventual paper.

### 4.1 Modification Variants

| ID | Parent | Description |
|---|---|---|
| comp_M01 | comp_001 | Single-byte modification in `__init__.py` |
| comp_M02 | comp_002 | Single-function replacement in primary implementation file |
| comp_M03 | comp_003 | Modification of `manifest.json` version field only |
| comp_M04 | comp_004 | Multi-file modification: changes to two helper modules |
| comp_M05 | comp_005 | Inserted suspicious import in a helper module |

Modification variants test whether the detector identifies compromises that preserve the file-list shape and differ only in content.

### 4.2 Addition Variants

| ID | Parent | Description |
|---|---|---|
| comp_A01 | comp_006 | Single added file: `_loader.py` containing exfiltration code |
| comp_A02 | comp_007 | Single added file: `.config.cache` (dotfile, easily overlooked) |
| comp_A03 | comp_008 | Single added file: nested at deeper path `utils/_internal.py` |
| comp_A04 | comp_009 | Two added files: `helpers.py` and `_init_helper.py` |
| comp_A05 | comp_010 | Added file with name closely resembling existing file |

Addition variants test whether the detector identifies compromises that inject new files alongside legitimate ones.

### 4.3 Removal Variants

| ID | Parent | Description |
|---|---|---|
| comp_R01 | comp_011 | Single file removed: `README.md` (documentation deletion) |
| comp_R02 | comp_012 | Single file removed: optional helper module |
| comp_R03 | comp_013 | Single file removed: `requirements.txt` (dependency declaration) |
| comp_R04 | comp_014 | Two files removed: both optional helpers |
| comp_R05 | comp_015 | Single file removed: a critical implementation file |

Removal variants test whether the detector identifies compromises that disable functionality by removing files (for example, removing a security check or a dependency declaration that would otherwise raise alarms).

### 4.4 Per-Variant Policy Metadata

Each variant carries policy metadata that determines its expected SBA routing. The metadata is assigned at dataset construction time and recorded in the ground-truth file. The assignment is designed to exercise the full range of policy paths:

- Variants `comp_M01` through `comp_M05` are assigned a single primary sector each, cycling through FIN, CI, HC, GOV, and FIN again
- Variants `comp_A01` through `comp_A05` are assigned multiple affected sectors to exercise multi-sector routing
- Variants `comp_R01` through `comp_R05` include at least one with `severity: critical` to exercise severity escalation, and at least one with `affected_jurisdictions: ALL` to exercise the ALL routing path

This distribution ensures the SBA policy logic in chaincode-interface Section 7 is exercised across all its rule branches by the dataset alone, without requiring additional test cases.

## 5. Ground-Truth File Format

The dataset is documented in two files: `ground_truth.csv` for human review and `ground_truth.json` for machine consumption. Both files are generated from the same Python source by the dataset generator script, guaranteeing consistency between the two formats by construction.

### 5.1 CSV Schema

The CSV is the primary reviewer-facing artifact. It contains one row per component (baseline and variant alike) with the following columns:

| Column | Type | Description |
|---|---|---|
| component_id | string | Stable identifier (e.g., `comp_001`, `comp_M03`) |
| component_name | string | Human-readable name |
| variant_type | string | `baseline`, `modification`, `addition`, or `removal` |
| parent_id | string | For variants, the baseline `component_id` they derive from; empty for baselines |
| manifest_hash | string | 64-char hex SHA-256 of the deterministic file-list representation |
| file_count | integer | Number of files in the component directory |
| total_size_bytes | integer | Sum of all file sizes |
| ground_truth_label | string | `known_good` (for baselines) or `compromised` (for variants) |
| affected_sectors | string | Comma-separated sector codes, or empty for baselines |
| affected_jurisdictions | string | Comma-separated MSP IDs or the literal `ALL`, or empty for baselines |
| distribution_scope | string | `single_jurisdiction`, `multi_jurisdiction`, `global`, or empty |
| severity | string | `low`, `medium`, `high`, `critical`, or empty |
| expected_sba_recipients | string | Comma-separated MSP IDs expected to receive the SBA-routed notification |

Example baseline row:

    comp_001,agent-memory-store,baseline,,a3f2c1...,5,1840,known_good,,,,,

Example variant row:

    comp_M01,agent-memory-store-MOD01,modification,comp_001,b4e9d2...,5,1841,compromised,FIN,,single_jurisdiction,medium,Org1MSP

### 5.2 JSON Schema

The JSON is the canonical machine-readable form. It preserves the nested structure of `policy_metadata` exactly as it would be passed to `ReportCompromise`. Top-level structure:

    {
      "dataset_version": "1",
      "generated_at": "<RFC3339 timestamp>",
      "generator_seed": "<integer>",
      "components": [
        {
          "component_id": "comp_001",
          "component_name": "agent-memory-store",
          "variant_type": "baseline",
          "parent_id": null,
          "manifest_hash": "a3f2c1...",
          "file_count": 5,
          "total_size_bytes": 1840,
          "ground_truth_label": "known_good",
          "policy_metadata": null,
          "expected_sba_recipients": []
        },
        {
          "component_id": "comp_M01",
          "component_name": "agent-memory-store-MOD01",
          "variant_type": "modification",
          "parent_id": "comp_001",
          "manifest_hash": "b4e9d2...",
          "file_count": 5,
          "total_size_bytes": 1841,
          "ground_truth_label": "compromised",
          "policy_metadata": {
            "affected_sectors": ["FIN"],
            "affected_jurisdictions": [],
            "distribution_scope": "single_jurisdiction",
            "severity": "medium"
          },
          "expected_sba_recipients": ["Org1MSP"]
        }
      ]
    }

The `expected_sba_recipients` field is the answer key for the M2 routing-precision metric. It is computed at dataset construction time by applying the SBA policy logic (chaincode-interface Section 7) to each variant's `policy_metadata` under the four-organization topology. Lower-`n` configurations recompute this field at runtime by restricting the recipient set to organizations present on the channel.

## 6. Reproducibility Requirements

The dataset must be reproducible from the generator script alone. Specifically:

- **Fixed random seed.** The generator accepts a seed parameter (default `42`); the same seed produces the same dataset on any machine.
- **Deterministic file generation.** Component file contents are generated from templates parameterized by component name and seed; no random calls during file content generation.
- **Stable file ordering.** File walking uses sorted relative paths, so manifest hashes do not depend on filesystem traversal order.
- **Idempotent execution.** Running the generator twice (with the same seed, same output directory) produces byte-identical output. The script may either refuse to overwrite an existing dataset or first remove it; either behavior must be documented and consistent.
- **Versioned output.** The dataset is `dataset_v1`. Any change to the structure, component count, variant categories, or generator logic produces `dataset_v2` rather than mutating v1. The version is recorded in both `ground_truth.csv` (as a header comment) and `ground_truth.json` (in the `dataset_version` field).

The generator script itself is part of the repository under `dataset/generate.py`. The script's behavior is the operational definition of this specification: if the script and this document ever disagree, the script defines the dataset and the document is updated to match.

## 7. Explicitly Out of Scope

The following are deliberately not part of the dataset and will not be added at this stage. Each was considered and rejected; the rationale is preserved here so the choices can be revisited later if needed.

- **File-replacement variants** (rename + replace). At the manifest-hash level, file replacement is structurally equivalent to "removal + addition" — the file count remains constant only because one path leaves the sorted list and a different path enters it. Including this as a fourth category would not exercise novel detection logic and would muddy the per-category M1 breakdown, since the detector cannot distinguish replacement from independent removal+addition by manifest hash alone.

- **Multi-variant attacks on a single component.** The current design assigns one compromise variant per baseline component, so each compromised hash has a single known-good counterpart. Real supply-chain attacks may produce multiple compromised versions of the same component over time. Modeling this is a meaningful extension but adds bookkeeping complexity (multiple `parent_id` references per baseline) that is not needed to demonstrate the core M1 and M2 measurements.

- **Adversarial near-collisions.** Components engineered to have manifest hashes that differ only in unlikely positions, designed to stress hash-collision detection. SHA-256 is not vulnerable to constructed collisions at the scale relevant here, so engineering near-collisions adds complexity without strengthening the contribution.

- **Time-varying compromise.** Components whose compromise status changes during the experimental run (e.g., a component reported as compromised, then retracted, then re-reported). The retraction logic is specified in chaincode-interface Section 6.2 and can be exercised in the test suite directly; building it into the dataset would conflate dataset content with experimental dynamics.

- **Real-world malicious package samples.** Drawing variants from actual published malicious packages (e.g., from PyPI advisory databases) would compromise the dataset's reproducibility — public databases mutate and entries are removed — and would conflate this work with software-security research, which is explicitly out of scope per the problem statement.

## 8. Next Steps

With the dataset specified, the design phase is complete. The next phase is implementation, and it proceeds in the following order:

1. **Implement the dataset generator.** Write `dataset/generate.py` per the specification above. Verify it produces 45 components (30 baseline + 15 variant), the expected file structure, and the two ground-truth files in matching content. Run twice with the same seed and confirm byte-identical output.

2. **Implement the chaincode.** Write the four functions specified in `chaincode-interface.md` in Go. Test each function against the seeded dataset via the chaincode's local test harness (no Fabric network required for unit tests). Verify the SBA policy produces the `expected_sba_recipients` field from each variant's `policy_metadata`.

3. **Implement the detector.** Write `detector/detector.py` to compute manifest hashes per Section 2.4 and query the chaincode (via the backend API) for compromise status. Verify against the seeded dataset that the detector produces the correct `ground_truth_label` for every component.

4. **Stand up the Fabric networks incrementally.** Reproduce the BICIR n=2 configuration as the known-good baseline; then add Org3 and Org4 one at a time.

5. **Collect metrics.** Run the four M1–M4 measurements across n=2, n=3, n=4.

Each implementation step is itself a focused work session with its own checkpoints and its own tag. The design documents in `docs/` are the source of truth that the implementation honors; if implementation reveals a problem with a design decision, the design document is updated first, then implementation follows.



