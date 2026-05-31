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
