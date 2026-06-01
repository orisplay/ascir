# ASCIR Design Decisions

An append-only log of significant design and tooling decisions, with the
reasoning preserved so that choices can be revisited if later evidence
requires it. Newest entries are added at the end.

---

## D1 — Fabric contract API: target the v2 line; choose the Fabric version forward

**Date:** 2026-05-31
**Status:** Adopted
**Context:** The chaincode needs the `fabric-contract-api-go` library to
provide the transaction-context interface its functions are written
against. Two questions had to be resolved: (a) which Fabric version the
testbed targets, and (b) which version of the contract API to depend on.

**Decision:**

1. **The exact Fabric version used by the prior BICIR network is not
   recoverable.** That network was built on a different machine, and no
   Fabric version number was recorded in the BICIR paper or in the ASCIR
   project notes. Rather than block on an unrecoverable value, ASCIR
   chooses a current Fabric release going forward. This is consistent with
   the project's framing: the n = 2 run replicates the BICIR two-organization
   *topology and routing behavior*, not a specific Fabric patch version.

2. **The chaincode targets the v2 line of `fabric-contract-api-go`**
   (which depends on `fabric-chaincode-go/v2` and `fabric-protos-go-apiv2`).
   The v2 line is the current path for a new project on Go 1.26: it resolves
   a protobuf namespace conflict present in the older `fabric-protos-go`
   dependency (advisory GO-2024-2687). The published COMPATIBILITY.md table
   still reflects the older v1.0 packages and is treated as stale.

3. **This choice does not need to be finalized against a running network
   yet.** The contract functions are developed and unit-tested against an
   in-memory mock of the transaction context. The dependency only needs to
   compile and provide the contract-API interface. The exact Fabric *peer*
   version is finalized later, when the network is stood up, and recorded as
   a follow-up decision at that time.

**Consequences:** The chaincode module gains a dependency on the v2 contract
API. The first non-trivial network bring-up (Section 5.5, n = 2) will pin a
specific Fabric peer release; until then, the version is intentionally left
open and the mock-based tests are network-independent.

---

## D2 — Composite keys via Fabric API; report_id→hash secondary index

**Date:** 2026-05-31
**Status:** Adopted
**Context:** The interface spec (Section 4.1) describes ledger keys using a
tilde notation, e.g. `KG~<manifest_hash>` and `CR~<manifest_hash>~<report_id>`,
and states that `~` is "the standard Hyperledger Fabric composite-key
separator." In the v2 chaincode shim, composite keys are constructed with
`stub.CreateCompositeKey(objectType, attributes)`, which uses an internal
`U+0000` separator, not a literal `~`. Separately, `RouteCompromise` takes
only a `report_id`, but the compromise-report key places `report_id` as the
*second* attribute; Fabric's `GetStateByPartialCompositeKey` matches only a
left-to-right prefix of attributes, so a record cannot be queried by its
second attribute directly.

**Decision:**

1. **Use Fabric's composite-key API rather than literal `~`-joined strings.**
   Keys are created with `CreateCompositeKey(objectType, attributes)` using
   object types `KG`, `CR`, `RT`, `RD`, and `IDX`. The tilde notation in the
   interface spec is treated as a description of the *logical* key structure
   (object type plus ordered attributes), not as the literal on-ledger byte
   separator. This is the idiomatic approach and makes partial-key range
   queries (e.g. all CR records for a hash) straightforward via
   `GetStateByPartialCompositeKey`.

2. **Maintain a `report_id -> manifest_hash` secondary index.** Each call to
   `ReportCompromise` writes, in addition to the `CR` record, an index record
   with object type `IDX` keyed on `report_id`, whose value is the
   manifest hash. `RouteCompromise` resolves its `report_id` argument to the
   manifest hash via this index, then loads the full `CR` record by complete
   composite key. This avoids scanning all `CR` records and respects the
   left-prefix limitation of partial composite-key queries.

**Consequences:** One additional ledger record type (the `IDX` index entry)
is written per compromise report. The index is append-only like every other
record and is covered by the contract unit tests. The logical key structure
in the interface spec remains the reference; the composite-key encoding is
an implementation detail reconciled here.

---

## D3 — Fabric platform version: 2.5.x LTS (2.5.15)

**Date:** 2026-05-31
**Status:** Adopted
**Context:** D1 deferred the exact Fabric peer version to network bring-up,
choosing to target a current release rather than the unrecoverable BICIR
version. The network is now being stood up, so the version is pinned here.

**Decision:** ASCIR targets **Hyperledger Fabric v2.5.x LTS**, installed at
**v2.5.15** (peer/orderer/ccenv images and CLI binaries; Fabric CA from the
same install). Chosen over the newer v3.x line for several project-specific
reasons:

1. v2.5 is the long-term-support line: stable, security-maintained, and the
   most thoroughly documented Fabric setup, which minimizes risk during the
   most config-heavy phase of the project.
2. It matches the chaincode's dependency stack (fabric-contract-api-go v2 /
   fabric-chaincode-go v2), already implemented and tested under D1.
3. It keeps the n = 2 "replication of BICIR" baseline as clean as possible:
   BICIR was a 2.x-era deployment, so replicating its topology and routing
   behavior on 2.5.x differs from the original only at the patch level rather
   than across a major version.
4. v3's headline feature (SmartBFT Byzantine-fault-tolerant ordering) is not
   needed for ASCIR's metrics (detection accuracy, routing precision,
   overhead reduction, latency); a Raft orderer is sufficient. Choosing v3
   would mean adopting the newer, less-documented line without using the
   capability that distinguishes it.

**Consequences:** The testbed runs Fabric 2.5.15 with a Raft ordering service.
Migrating to v3.x and evaluating a BFT orderer remain available as future
work; nothing in this choice precludes them. The exact toolchain: Fabric
v2.5.15 (peer commit 83c7930, built with Go 1.26.0), installed via the
official install-fabric.sh into ~/research/fabric-samples (kept outside the
repository as upstream tooling).
