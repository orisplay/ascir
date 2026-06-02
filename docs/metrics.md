# ASCIR Evaluation Metrics: Operational Definitions

This document operationalizes the four metrics (M1–M4) and the comparison
baselines defined in `problem-statement.md` §5 into precise, reproducible
measurement procedures. It does not redefine the metrics; it specifies exactly
how each is computed, what data a run records, and what each result is compared
against, so that the measurement runs are mechanical and the numbers are
defensible.

All measurements use the testbed and procedure in `network/scaling.md` at the
relevant network size (n = 2, 3, 4). The chaincode is v1.1 (sequence 1).

## Definitions and conventions

- **Scenario**: a single evaluation case. For routing/overhead/latency, a
  scenario is one compromise report with fully specified `policy_metadata`
  (affected_sectors, affected_jurisdictions, distribution_scope, severity) and a
  named reporter org, plus the expected outcome derived independently from the
  SBA specification (chaincode-interface.md §7). For detection, a scenario is one
  dataset component with its ground-truth label.
- **n**: number of organizations on the channel at measurement time (2, 3, 4).
- **r**: number of authorized recipients a routing decision produces for a
  scenario (the length of `authorized_recipients`).
- **Expected recipient set**: the recipient set computed from the SBA spec by a
  reference (the ground-truth table in this document / the dataset's
  ground-truth files), NOT read back from the chaincode. M2 tests the chaincode
  against the specification, never against itself.
- Sector→jurisdiction mapping (per the policy layer): FIN→Org1MSP, CI→Org2MSP,
  HC→Org3MSP, GOV→Org4MSP; severity=critical escalates to Org4MSP; the reporter
  org is always excluded from its own notification.

## M1 — Detection Accuracy

**Question.** Are compromised components correctly identified against the
known-good registry, and clean components correctly cleared?

**Procedure.** With a known registry state (see below), run the detector over
all 45 dataset components (`detector.py --check-api <component>` for each, or the
`--verify` cross-check for the hashing half). Record each component's
ground-truth label and the detector's resolved registry status.

**Registry state under test.** M1 requires a defined registry before the run:
the 30 baseline components are registered known-good; the 15 compromise variants
are NOT registered as known-good (their altered manifests yield hashes absent
from the registry) and a subset are additionally reported compromised to
exercise the COMPROMISED/CONTESTED paths. The exact registration script is
recorded with the run so the state is reproducible.

**Scoring (binary detection view).** Map the four registry statuses to a binary
"compromise flagged" decision:
- KNOWN_GOOD → not flagged (clean)
- UNKNOWN → flagged (artifact not in the trusted registry — treated as suspect)
- COMPROMISED, CONTESTED → flagged
Then against ground truth:
- TP: a compromise-variant component is flagged
- TN: a baseline (clean, registered) component is not flagged
- FP: a clean component is flagged
- FN: a compromise variant is not flagged

**Reported.** Confusion matrix (TP/FP/TN/FN), accuracy = (TP+TN)/total,
precision, recall. The hash-level cross-check (`--verify` = 45/45) is reported
separately as evidence the detector reproduces the registry's recorded hashes.

**Note on UNKNOWN.** Treating UNKNOWN as "flagged/suspect" is a policy choice
appropriate to a supply-chain setting (an unrecognized artifact warrants
review). The run records raw statuses too, so an alternative scoring (UNKNOWN as
a separate "indeterminate" class) can be computed without re-running.

## M2 — Routing Precision

**Question.** Do compromise notifications go only to the jurisdictions the SBA
policy says they should?

**Procedure.** For each routing scenario: (1) determine the **expected**
recipient set from the SBA spec independently of the chaincode; (2) submit
ReportCompromise then RouteCompromise on the live network (passing the full
n-org jurisdiction list); (3) read the chaincode's `authorized_recipients`.

**Per-scenario metrics.** With routed = chaincode recipients, expected = spec
recipients:
- precision = |routed ∩ expected| / |routed|   (1.0 if routed is empty and expected is empty)
- recall    = |routed ∩ expected| / |expected| (1.0 if expected is empty)
- exact_match = 1 if routed == expected else 0

**Reported.** Mean precision, mean recall, and exact-match rate across the
scenario set, per network size. The headline figure is exact-match rate (the
strict "correct subset" measure the problem statement asks for); precision and
recall localize any disagreement. Edge cases (empty recipient set from
reporter-exclusion, e.g. FIN reporter on a FIN-only report) are included
explicitly because they exercise the exclusion rule.

## M3 — Broadcast Overhead Reduction

**Question.** How much unnecessary cross-org notification does selective routing
avoid versus a global broadcast, and does it follow (n − r)/n as n grows?

**Procedure.** For each scenario at each network size, record r =
|authorized_recipients| and compute reduction = (n − r)/n. A global-broadcast
baseline (B-Broadcast) notifies all n orgs (r = n → reduction 0); ASCIR notifies
only authorized recipients.

**Reported.** Per-scenario (n − r)/n, and the mean over a fixed, documented
scenario mix per n. Because r varies by scenario (a single-sector report → r=1;
a CI+critical report → r=2 via escalation), the averaged figure depends on the
mix, so the scenario mix is fixed in `experiments/scenarios/` and reported
alongside the number. Expected averaged values track the projections: ~50% at
n=2, ~66.7% at n=3, ~75% at n=4 for single-recipient cases; escalation/multi-
sector cases reduce the average and are reported separately so the curve is
interpretable.

**Baseline comparison.** Reduction is reported for each baseline (B-None,
B-Local, B-Broadcast, ASCIR) so the contribution is contextualized, per §5.4.

## M4 — End-to-End Detection Latency

**Question.** How long from detection to verified cross-jurisdiction
notification, and how does it scale with n?

**Procedure.** Wall-clock time from the `ReportCompromise` chaincode invocation
to `QueryCompromiseStatus` returning the verified record at a peer (per the
problem statement's definition). The report must be committed before the query
observes it, so the measured interval includes endorsement collection, ordering,
and commit — the consensus overhead that grows with n.

**Trials and statistics.** At each network size, run the timed scenario N times
(default N = 30) after a warm-up invocation. Report median and p95 (latency
distributions are right-skewed; mean alone is misleading). Record each trial's
raw time so distributions can be re-analyzed.

**Endorsement note (from testbed findings).** Writes must satisfy the
MAJORITY endorsement policy: 2 endorsing peers at n=2/3, but 3 at n=4. The M4
runs therefore use the correct endorser count per size (see scaling.md GOTCHA 4);
the increase in required endorsements is part of what M4 is measuring as n grows,
not an artifact to be controlled away.

## Comparison baselines (per problem-statement §5.4)

- **B-None**: no dissemination (detection only). Lower bound; r undefined / 0.
- **B-Local**: notify only the reporter's own jurisdiction. Minimal sharing.
- **B-Broadcast**: notify all n organizations (global broadcast). r = n,
  overhead reduction 0; the comparison point for M3.
- **ASCIR**: SBA selective routing (the contribution).

Each metric, where comparative, is reported across these baselines so the
selective-routing benefit is quantified rather than asserted.

## What a run records

Every run writes, into `experiments/results/`:
- the network size n and the chaincode version/sequence,
- the scenario set used (referenced by file under `experiments/scenarios/`),
- per-scenario raw outputs (recipients, statuses, timings),
- the computed metric values,
- enough environment detail (Fabric version, endorser count) to reproduce.

Result files are JSON (one per metric per network size) with a schema fixed in
`experiments/README.md`, so aggregation and plotting are mechanical.
