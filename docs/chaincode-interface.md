# ASCIR Chaincode Interface Specification

*Agentic Supply-Chain Incident Routing — Design Document 2 of N*

*Draft v0.1 — Working Document*

---

## 1. Purpose and Scope

This document specifies the interface contract for the ASCIR chaincode deployed on the Hyperledger Fabric testbed. It defines four functions — `RegisterKnownGood`, `ReportCompromise`, `QueryCompromiseStatus`, and `RouteCompromise` — together with the data model they operate over, the access-control rules that govern them, and the policy-evaluation logic of the Selective Broadcast Algorithm extension.

The document is an interface specification, not an implementation guide. It defines the contract that the chaincode honors: what each function takes in, what it returns, what world state it produces, and what guarantees it makes. The Go implementation follows from this document; if the specification is sufficiently precise, two independent implementations should be functionally interchangeable.

Three design choices are explicitly argued rather than assumed: the authorization model for known-good registration (Section 6.1), the revocability of compromise reports (Section 6.2), and the structure of policy metadata (Section 6.3). Each is resolved with a recommendation, but the reasoning is preserved so that the trade-offs can be revisited if the experimental results require it.

## 2. Design Principles

Five principles guide the interface design. Each addresses a property that the eventual paper will need to defend.

- **Tamper-evidence over confidentiality.** The chaincode produces a verifiable record of what was reported and what was routed. It does not attempt to encrypt the underlying data; that is the responsibility of the layer above. Confidentiality is enforced by selective routing (only authorized organizations receive the record), not by cryptographic concealment of an otherwise-broadcast record.

- **Deterministic routing.** Given the same compromise report and the same policy metadata, `RouteCompromise` must produce the same recipient set on every peer that executes it. Non-determinism in chaincode breaks Fabric's endorsement model and cannot be tolerated; the SBA evaluation logic is therefore expressed as pure functions over the input metadata.

- **Append-only world state.** No function deletes a record. Retractions, corrections, and updates are expressed as new records that reference the originals. This preserves the forensic audit trail and aligns with the tamper-evidence claim made in the problem statement.

- **Minimal surface area.** Four functions are sufficient for the experimental design. Additional functions (e.g., bulk-query, statistics) are explicitly out of scope; they can be added later if the implementation phase reveals a need, but the interface contract should remain small enough that every function can be tested exhaustively against the seeded dataset.

- **Inputs that are forensically meaningful.** Every input field that affects routing or admissibility must be one that a real investigator could plausibly produce. The interface should not require fields that exist only because the chaincode wants them; if a field cannot be derived from a forensic acquisition or a verified upstream source, it does not belong in the schema.

## 3. Function Summary

Table 1 lists the four functions, their purpose, the expected caller, and whether they mutate the ledger. Detailed schemas follow in Section 5.

| Function | Purpose | Caller | Mutates ledger? |
|---|---|---|---|
| `RegisterKnownGood` | Records a manifest hash as a verified legitimate component | Registry maintainer | Yes (write) |
| `ReportCompromise` | Declares a manifest hash as a known compromise with policy metadata | Any participating org | Yes (write) |
| `QueryCompromiseStatus` | Returns the registry status of a given manifest hash | Any participating org | No (read) |
| `RouteCompromise` | Evaluates SBA policy on a compromise report and records the routing decision | Any participating org | Yes (write) |

## 4. Data Model

All four functions operate over a common data model. Three record types live on the ledger: known-good entries, compromise reports, and routing decisions. A fourth type, the retraction record, is introduced in Section 6.2 as part of the revocability discussion. World state is keyed by composite keys with type-prefix tags so that range queries by record type remain efficient.

### 4.1 Composite Key Structure

| Record type | Key format | Notes |
|---|---|---|
| Known-good entry | `KG~<manifest_hash>` | One entry per registered known-good component version |
| Compromise report | `CR~<manifest_hash>~<report_id>` | Multiple reports may exist for the same hash from different orgs |
| Retraction record | `RT~<report_id>` | Points back to a prior compromise report; does not delete it |
| Routing decision | `RD~<report_id>~<decision_id>` | Audit record produced by `RouteCompromise` |

The tilde character (`~`) is the standard Hyperledger Fabric composite-key separator and is reserved across the schema. The manifest hash is included in the keys for known-good and compromise records to permit efficient lookup by hash via `GetState` rather than a full state scan.

### 4.2 Manifest Hash

A manifest hash uniquely identifies a specific version of a specific agentic-AI component. For the experimental design, manifests are generated by hashing a deterministic representation of the component's installed file set: a sorted list of `(relative_path, file_sha256)` pairs, concatenated and hashed with SHA-256.

This definition deliberately excludes mutable state such as log files, cached data, and configuration that the user is expected to modify. It includes only the files that constitute the component as installed. The choice is conservative: a known-good hash will match a legitimate installation regardless of user activity, but will differ if any component file is altered. This is the same property that the OpenClaw paper's `component_manifest_hash` recommendation requires.

The hash is treated as an opaque 64-character hexadecimal string at the chaincode level. The chaincode does not recompute hashes; it stores and queries the values supplied by the calling client.

### 4.3 Sector Vocabulary

Sectors are a controlled vocabulary of four codes. The vocabulary is small intentionally: a larger set would create proliferating edge cases in the SBA policy logic without adding experimental value at the n=4 testbed scale.

| Sector code | Definition |
|---|---|
| `FIN` | Financial services (banking, payments, trading) |
| `CI` | Critical infrastructure (energy, water, transportation) |
| `HC` | Healthcare (clinical systems, patient data, medical devices) |
| `GOV` | General government and any sector not otherwise covered (default routing target) |

`GOV` is the default sector and serves as the fallback when a compromise report contains a sector code not in the vocabulary, preserving the routing behavior of the original BICIR algorithm under unknown inputs.

### 4.4 Jurisdiction Identifiers

Jurisdictions are identified by Fabric organization MSP IDs. For the four-organization testbed: `Org1MSP` (financial-sector CERT), `Org2MSP` (critical-infrastructure CERT), `Org3MSP` (healthcare-sector CERT), and `Org4MSP` (general national CERT). The mapping from sector code to default jurisdiction is part of the SBA policy logic, not the data model, so that the same chaincode can be deployed against different organizational topologies for the n=2 and n=3 measurement runs.

## 5. Function Specifications

Each function is specified by its input schema, output schema, preconditions, postconditions, and access-control rules. Schemas are presented in JSON-style notation for clarity; the Go implementation will use struct tags to enforce them.

### 5.1 RegisterKnownGood

Records a manifest hash as a verified legitimate component. The presence of a known-good entry means that an investigator querying this hash should treat it as legitimate unless a compromise report subsequently overrides this status.

#### Input

    {
      "manifest_hash": "<64-char hex>",
      "component_name": "<string>",
      "version": "<string>",
      "signer_org": "<MSP ID of the registering organization>",
      "signed_at": "<RFC3339 timestamp>"
    }

#### Output

    {
      "status": "registered" | "already_exists",
      "key": "KG~<manifest_hash>",
      "tx_id": "<Fabric transaction ID>"
    }

#### Preconditions

- The `manifest_hash` is a 64-character lowercase hexadecimal string.
- The caller's MSP ID matches `signer_org` (a caller cannot register on behalf of another organization).
- The caller is authorized to register known-good entries per the policy in Section 6.1.

#### Postconditions

- If no prior known-good entry exists for this hash, the entry is written and `status` is `registered`.
- If an entry already exists, no write occurs and `status` is `already_exists`. The function is idempotent under repeated calls with identical inputs.
- The registration does not delete or override any prior compromise report for the same hash; both records co-exist, and `QueryCompromiseStatus` resolves the conflict per Section 5.3.

### 5.2 ReportCompromise

Declares a manifest hash as a known compromise and supplies the policy metadata that the SBA will use to route the resulting notification. Multiple reports may exist for the same hash, from the same or different reporting organizations; each becomes a distinct record.

#### Input

    {
      "manifest_hash": "<64-char hex>",
      "component_name": "<string>",
      "reporter_org": "<MSP ID of the reporting organization>",
      "reported_at": "<RFC3339 timestamp>",
      "evidence_ref": "<string referencing forensic evidence>",
      "policy_metadata": {
        "affected_sectors": ["FIN" | "CI" | "HC" | "GOV", ...],
        "affected_jurisdictions": ["<MSP ID>", ...] | "ALL",
        "distribution_scope": "single_jurisdiction" | "multi_jurisdiction" | "global",
        "severity": "low" | "medium" | "high" | "critical"
      }
    }

#### Output

    {
      "status": "reported",
      "report_id": "<deterministic UUID>",
      "key": "CR~<manifest_hash>~<report_id>",
      "tx_id": "<Fabric transaction ID>"
    }

#### Preconditions

- The `manifest_hash` is well-formed.
- All sector codes in `affected_sectors` are members of the vocabulary in Section 4.3.
- All MSP IDs in `affected_jurisdictions` correspond to organizations on the channel, or the value is the literal string `ALL`.
- The caller's MSP ID matches `reporter_org`.
- `evidence_ref` is a non-empty string. The chaincode does not validate that the reference resolves to actual evidence; that is the investigator's responsibility, recorded in the chain-of-custody documentation.

#### Postconditions

- A new compromise report record is written under key `CR~<manifest_hash>~<report_id>`.
- The `report_id` is deterministically derived from the input (e.g., SHA-256 of `manifest_hash + reporter_org + reported_at`, truncated to a UUID-like form) so that the same input produces the same key. This makes the function idempotent under retry.
- No prior records (known-good or compromise) are modified. The new report co-exists with them.

### 5.3 QueryCompromiseStatus

Returns the registry status of a given manifest hash. The function consolidates known-good, compromise, and retraction records for the hash into a single status response. It is read-only and may be called by any participating organization.

#### Input

    {
      "manifest_hash": "<64-char hex>"
    }

#### Output

    {
      "manifest_hash": "<64-char hex>",
      "status": "unknown" | "known_good" | "compromised" | "contested",
      "known_good_entry": <KG record or null>,
      "active_compromise_reports": [<CR record>, ...],
      "retracted_compromise_reports": [<CR record>, ...]
    }

#### Status Resolution Logic

The `status` field is derived from the records present according to the following rules, evaluated in order:

1. If no KG record and no active CR records exist for the hash: `status` is `unknown`.
2. If a KG record exists and no active CR records exist: `status` is `known_good`.
3. If one or more active CR records exist and no KG record exists: `status` is `compromised`.
4. If a KG record exists AND one or more active CR records exist: `status` is `contested`. This explicitly surfaces the supply-chain attack case in which a legitimate component has been compromised after registration.

A CR record is considered active if no corresponding RT (retraction) record exists pointing to its `report_id`.

### 5.4 RouteCompromise

Evaluates the SBA policy on a compromise report and records the routing decision as a verifiable ledger entry. This function is the contribution point: it is where the jurisdiction-aware dissemination logic lives and where the tamper-evident audit record is produced.

#### Input

    {
      "report_id": "<deterministic UUID from a prior ReportCompromise>"
    }

#### Output

    {
      "status": "routed",
      "decision_id": "<deterministic UUID>",
      "key": "RD~<report_id>~<decision_id>",
      "authorized_recipients": ["<MSP ID>", ...],
      "excluded_jurisdictions": ["<MSP ID>", ...],
      "policy_trace": [<step>, ...],
      "tx_id": "<Fabric transaction ID>"
    }

#### Preconditions

- A CR record exists under any key matching `CR~*~<report_id>`.
- The CR record has not been retracted (no RT record points to it).

#### Postconditions

- A routing decision record is written under key `RD~<report_id>~<decision_id>`, containing the authorized recipients, the excluded jurisdictions, and the policy trace (Section 7.3).
- The `decision_id` is deterministic over the `report_id` and the policy state at the time of evaluation, so that re-evaluating the same report under the same policy produces the same `decision_id`.
- The function does not actually transmit anything to the listed recipients. Transmission is the responsibility of the application layer; the chaincode produces only the verifiable record of the routing decision.

#### Why Routing is a Separate Function

`ReportCompromise` and `RouteCompromise` are intentionally split. Reporting is the assertion that a compromise has occurred; routing is the assertion about who should be told. Separating them lets the routing decision be re-evaluated if the SBA policy is updated, preserves the original report unchanged, and produces two distinct audit records — one for the original assertion of fact and one for the policy-driven dissemination decision.

## 6. Open Design Questions

Three design decisions were left open in the problem statement. Each is resolved here with a recommendation and a record of the reasoning. The trade-offs are preserved so that the choice can be revisited if experimental results expose a problem with the recommended option.

### 6.1 Who May Call RegisterKnownGood?

The question is whether any participating organization can declare a manifest hash as legitimate, or whether registration authority is restricted.

#### Option A — Any participating organization

Decentralized trust: any org may register a hash as known-good. Reflects the federated nature of cross-national CERT cooperation; no single party holds the truth.

- **Advantages:** no single point of failure; aligns with the problem statement's framing that no single jurisdiction is authoritative; simpler chaincode logic.
- **Disadvantages:** a malicious or compromised organization could register a compromised hash as known-good, weakening the registry's evidentiary value. The chaincode cannot distinguish a legitimate registration from a malicious one.

#### Option B — Designated registry-maintainer organization

Only one organization (e.g., `Org4MSP` acting as the national CERT) may call `RegisterKnownGood`. Other organizations submit registration requests off-chain.

- **Advantages:** single accountable party; mirrors the structure of real-world certificate authorities and CVE registries; simplifies the question of what the registry means.
- **Disadvantages:** creates a centralization that the rest of the architecture explicitly avoids; the registry maintainer becomes a single point of trust, undermining the federated framing.

#### Option C — Multi-signature registration

Any organization may propose a known-good registration, but the entry is only written after N peer endorsements from distinct organizations. N is configurable; N=2 is the minimum meaningful value at n=4.

- **Advantages:** no single party can poison the registry; aligns with Fabric's native endorsement-policy machinery; preserves the federated framing while raising the bar for malicious entries.
- **Disadvantages:** more complex chaincode and endorsement policy; harder to test exhaustively at small n; adds a coordination cost at registration time that does not exist in the problem-statement scenario.

#### Recommendation

**Adopt Option C (multi-signature registration) with N=2 for the n=3 and n=4 experimental configurations, and Option A (single-org registration) for the n=2 replication baseline.**

Rationale: at n=2, two-of-two endorsement collapses to all-of-network endorsement, which is not a meaningful test of the multi-signature property and would unnecessarily complicate the BICIR replication step. From n=3 onward, N=2 produces a non-trivial endorsement requirement (two of three or two of four orgs must agree) that demonstrates the federated trust property without making the testbed unwieldy. This choice is made at the channel endorsement-policy level rather than in the chaincode itself, so the chaincode interface remains identical across the three measurement runs.

### 6.2 Should ReportCompromise Be Revocable?

The question is whether a compromise report can be withdrawn after submission — for instance, if a subsequent investigation determines that the original report was a false positive.

#### Option A — Immutable, with a separate retraction record

The original CR record is never modified or deleted. A new RT (retraction) record is written under a key that points back to the original `report_id`. `QueryCompromiseStatus` treats a CR record as inactive when a corresponding RT record exists, but both records remain on the ledger for audit purposes.

- **Advantages:** preserves the full audit trail (the original report is still verifiable evidence that someone, at some time, asserted a compromise); aligns with the append-only design principle; supports forensic reconstruction of when the false positive was discovered.
- **Disadvantages:** marginally more complex query logic, since `QueryCompromiseStatus` must check for retractions; world state grows monotonically (acceptable at testbed scale, but a real deployment would eventually require archival).

#### Option B — Direct revocation (mutate or delete the original)

The original CR record is updated in place or removed when retracted.

- **Advantages:** simpler queries; world state size remains bounded.
- **Disadvantages:** violates the append-only principle; destroys forensic evidence that a compromise was once reported; creates an attack surface where an organization could retract a true-positive report to suppress evidence.

#### Recommendation

**Adopt Option A (immutable with retraction record).** The retraction record is itself an audit artifact; an investigator who finds an RT record knows both that a compromise was reported AND that the reporting organization later believed the report to be incorrect. This is more forensically useful than a clean retraction would be.

A retraction may only be issued by the original reporting organization (the caller's MSP ID must match the `reporter_org` of the CR record). A retraction is itself final: there is no un-retraction. If the original assessment is again deemed correct, a new compromise report must be filed.

### 6.3 Policy Metadata Structure

The question is whether policy metadata should be a flat key-value structure (sector, jurisdiction, severity as scalar fields) or a richer object with controlled vocabularies and explicit cardinality.

#### Option A — Flat key-value (BICIR-style)

Three scalar fields: `sector`, `jurisdiction`, `severity`. Matches the BICIR keyword-routing approach closely.

- **Advantages:** minimal change from BICIR; small attack surface; trivially serializable; trivially testable.
- **Disadvantages:** cannot express the supply-chain reality where a single compromise affects multiple sectors and multiple jurisdictions simultaneously. Forces unnatural choices like "pick the primary sector" when in fact a compromised agent component may legitimately affect all of finance, healthcare, and infrastructure at once.

#### Option B — Structured object with controlled vocabularies

An object with: `affected_sectors` (array of sector codes), `affected_jurisdictions` (array of MSP IDs or the literal `ALL`), `distribution_scope` (`single_jurisdiction`, `multi_jurisdiction`, or `global`), and `severity` (enum).

- **Advantages:** expresses the cross-cutting nature of supply-chain compromises; supports richer SBA policies (e.g., "a high-severity multi-jurisdiction compromise routes to all affected sectors plus the general CERT"); makes the contribution beyond BICIR concrete — flat metadata could not produce the routing decisions described in the problem statement.
- **Disadvantages:** larger schema; more validation logic in the chaincode; more potential failure modes that must be exercised in the test design.

#### Recommendation

**Adopt Option B (structured object with controlled vocabularies).** The flat structure would make ASCIR an incremental BICIR variant rather than a meaningful extension. The structured object is what enables the SBA policy logic in Section 7 to produce routing decisions that are not reducible to a single keyword match, which is the technical contribution claim.

The schema is fixed at this version. Future extensions (e.g., a temporal field, a confidence score, a reference-CVE field) are explicitly out of scope and would require a versioned schema with a corresponding chaincode upgrade procedure.

## 7. Selective Broadcast Algorithm — Policy Logic

The SBA policy is a deterministic function from a compromise report's `policy_metadata` to an authorized recipient set. This section defines that function. The implementation in Section 7.3 is what `RouteCompromise` executes; the policy trace it produces is the forensic audit record.

### 7.1 Policy Inputs

The policy operates over four inputs derived from the CR record's `policy_metadata` field: the affected sectors, the affected jurisdictions, the distribution scope, and the severity. It additionally consults a static configuration mapping each sector code to its primary jurisdiction (the CERT responsible for that sector by default) and a list of all known jurisdictions on the channel.

### 7.2 Routing Rules

The recipient set is computed in three phases, with each phase potentially adding jurisdictions to the set:

1. **Direct sector mapping.** For each sector in `affected_sectors`, the corresponding primary jurisdiction is added to the recipient set. This is the BICIR behavior: a finance-affected compromise routes to the finance CERT.

2. **Explicit jurisdiction inclusion.** Every jurisdiction listed in `affected_jurisdictions` is added to the recipient set. If the value is the literal `ALL`, all known jurisdictions are added. This handles cases where a compromise affects a jurisdiction outside its primary sector (for example, a healthcare compromise that also affects a finance organization's healthcare-data systems).

3. **Severity escalation.** If `severity` is `critical`, the general national CERT (`Org4MSP` in the four-org topology) is added to the recipient set regardless of sector. This reflects the operational reality that critical compromises require national-level visibility independent of sector-specific routing.

The excluded set is the complement of the recipient set within the list of known jurisdictions on the channel. The recipient set never includes the reporting organization (a CR record is not routed back to its own reporter), since the reporter already has the information; this exclusion is applied after all three phases.

### 7.3 Policy Trace

`RouteCompromise` records its policy evaluation as an explicit trace within the routing decision. Each step of the evaluation produces a trace entry naming the rule that fired and the jurisdiction(s) it contributed to the recipient set. The trace is itself part of the ledger record and is therefore tamper-evident.

    policy_trace: [
      { "rule": "sector_mapping",        "input": "FIN",      "added": ["Org1MSP"] },
      { "rule": "explicit_jurisdiction", "input": "Org3MSP",  "added": ["Org3MSP"] },
      { "rule": "severity_escalation",   "input": "critical", "added": ["Org4MSP"] },
      { "rule": "reporter_exclusion",    "input": "Org1MSP",  "removed": ["Org1MSP"] }
    ]

The trace serves three forensic purposes. First, it makes the routing decision auditable after the fact: an investigator who queries an RD record can see not only the recipient set but the rules that produced it. Second, it allows the routing decision to be defended in adversarial contexts (a recipient claiming they should not have received a notification can be shown the rule that included them). Third, it supports the broader tamper-evidence claim: if the policy logic itself is ever amended, the historical trace of decisions made under the prior policy remains on the ledger and remains verifiable.

### 7.4 Determinism

The policy function is pure: it depends only on its inputs and the static jurisdiction configuration. It does not consult the world state at evaluation time, does not call external services, and does not depend on clock readings or random values. This guarantees that every peer executing `RouteCompromise` on the same input produces the same output, which is required for Fabric's endorsement model to accept the transaction.

## 8. Explicitly Out of Scope

The following are deliberately not part of this interface and will not be added at the implementation stage. Each was considered and rejected; the rationale is preserved here so that the choices can be revisited later if needed.

- **Bulk operations.** No `BulkRegisterKnownGood`, no `BulkQuery`. The seeded experimental dataset is small enough that per-call invocations are sufficient; bulk operations would optimize a path that is not measured.

- **Cross-channel routing.** All four functions operate within a single Fabric channel. Multi-channel deployments are a real-world concern but are not part of the testbed.

- **Private data collections.** All records are written to the channel ledger and are visible to all channel members. The confidentiality property comes from selective routing at the application layer, not from chaincode-level privacy. Adding private data collections is a meaningful extension but would obscure the SBA evaluation step, which is the contribution.

- **Statistics, dashboards, aggregate queries.** These belong in the API layer (Node.js / Express, reusing the BICIR backend pattern), not in chaincode. The chaincode is the contract; the API is the convenience.

- **Schema versioning.** The interface defined here is v1. Any change to the input or output schema requires a chaincode upgrade and is treated as a new version. The testbed runs entirely on v1; schema migration is a deployment concern that is not part of the research contribution.

## 9. Next Document

With the interface specified, the next document in the sequence is the seeded component dataset specification. That document will define the set of simulated agent components used in the evaluation, their known-good manifest hashes, the seeded compromise variants, and the ground-truth labels needed for the detection-accuracy metric (M1).

After the dataset is specified, the implementation phase has a clear and testable target: a four-organization Fabric network running the chaincode defined here against the components defined there, with experimental runs at n = 2, 3, and 4 producing the measured scaling curve described in the problem statement.
