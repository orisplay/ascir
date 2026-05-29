# ASCIR: Agentic Supply-Chain Incident Routing

*Problem Statement and Scoping Document*

*Draft v0.1 — Working Document*

---

## 1. Background and Motivation

Two recent research directions intersect at a problem that neither has fully addressed. First, blockchain-based interoperability frameworks for cross-national cyber incident response, such as the BICIR model, have demonstrated that jurisdiction-aware routing of incident data can be enforced at the smart-contract level, with measurable reductions in unnecessary broadcast overhead. Second, recent forensic analyses of agentic AI systems, exemplified by the OpenClaw responsible-AI assessment, have shown that autonomous, always-on agents introduce non-deterministic evidence states and attribution ambiguity at the artifact level, particularly when supply-chain compromises seed malicious components into agent ecosystems.

The ClawHavoc incident, in which approximately 900 malicious packages were introduced into an agentic-AI marketplace, illustrates a class of attack that is cross-national by construction: a single compromised component is distributed simultaneously to deployments across many jurisdictions. Existing supply-chain detection work treats this as a software-security problem at the registry level, and existing threat-intelligence sharing frameworks such as STIX/TAXII focus on indicator dissemination without forensic anchoring. What is missing is a forensic framing that links artifact-level evidence of compromise on a specific device to jurisdiction-aware, tamper-evident notification across borders.

## 2. Problem Statement

Current forensic and incident-response practice cannot answer the following question with verifiable, cross-jurisdictional evidence: *given a forensic image of a device on which an agentic AI was installed, can we determine whether that device was running a known-compromised component at the time of the incident, and can the resulting evidence be shared with affected national CERTs in a way that is both tamper-evident and selectively routed only to jurisdictions authorized to receive it?*

Three sub-problems follow from this question:

- **Detection at the artifact level.** Standard forensic tooling does not extract or verify the cryptographic identity of agentic-AI components from acquired images, and where it does, there is no canonical registry of known-good or known-compromised manifests against which to compare.

- **Cross-jurisdictional dissemination.** When a compromise is detected, there is no mechanism that disseminates evidence of the compromise across borders while respecting jurisdictional, sectoral, and data-sovereignty constraints, and no mechanism that produces a verifiable record of which jurisdictions were notified and when.

- **Evidentiary linkage.** Because supply-chain compromises produce artifact signatures that are identical to legitimate component behavior under standard acquisition methods, attribution to a known compromise depends entirely on whether a trusted, tamper-evident reference exists at the time the evidence is examined.

The contribution claimed by this work is therefore narrow and operational: a forensic procedure, an artifact-level detection method, and a jurisdiction-aware dissemination layer that together close the chain from on-device compromise detection to cross-border evidentiary notification.

## 3. Concrete Scenario

To keep the scope tractable and the evaluation defensible, the work targets a single, well-bounded scenario:

1. A malicious component is introduced into the package ecosystem of an agentic AI framework. The component is functionally indistinguishable from its legitimate counterpart under standard acquisition methods, but its manifest hash differs from the known-good reference.

2. The component is distributed to deployments across multiple jurisdictions. For experimental purposes, four simulated jurisdictions are modeled, corresponding to four organizations on the permissioned blockchain network: a financial-sector CERT, a critical-infrastructure CERT, a healthcare-sector CERT, and a general national CERT. Measurement is performed at n = 2 (replication of prior BICIR baseline), n = 3 (primary contribution), and n = 4 (scaling extension).

3. An incident occurs on a device in one of the jurisdictions. A forensic acquisition is performed using the suspension protocol from prior work, producing a verified image of the post-installation state of the agent.

4. The detection component examines the image, extracts the manifest hashes of installed agentic-AI components, and queries the blockchain-anchored registry to determine compromise status.

5. On detection of a compromise, a `ReportCompromise` transaction is issued with policy metadata describing the sector, jurisdiction, and distribution scope of the compromised component. The Selective Broadcast Algorithm determines which subset of organizations is authorized to receive the report, and the routing decision is itself written to the ledger as a verifiable record.

All steps are reproducible on a single research machine using a Hyperledger Fabric testbed, a controlled set of simulated agent components with seeded manifest hashes, and forensic imaging of a virtualized acquisition target. The testbed is configured for up to four organizations, with experimental runs at n = 2, 3, and 4 to produce a measured scaling curve rather than a single endpoint.

## 4. Research Questions

The following research questions are intentionally tight, each producing a measurable answer from the experimental design described in Section 5.

1. Can artifact-level manifest-hash extraction reliably identify compromised agentic-AI components in a forensic image, and at what rates of false positives and false negatives?

2. Can a jurisdiction-aware Selective Broadcast Algorithm deliver compromise notifications to the correct subset of organizations, and does the measured overhead reduction at n = 2, 3, and 4 organizations follow the projected (n − r)/n behavior from prior work?

3. Does anchoring the compromise registry to a permissioned blockchain produce a verifiable, tamper-evident record of cross-jurisdictional notification suitable as supporting evidence under standard forensic procedure?

4. What is the end-to-end latency from artifact-level detection to verified notification at a receiving jurisdiction, and how does it scale across the measured network sizes (n = 2, 3, 4)?

## 5. Scope and Evaluation Plan

### 5.1 In Scope

- Artifact-level extraction of manifest hashes from forensic images of devices with installed agentic-AI components
- Hyperledger Fabric chaincode for a compromise registry: `RegisterKnownGood`, `ReportCompromise`, `QueryCompromiseStatus`, and `RouteCompromise`
- Extension of the Selective Broadcast Algorithm to handle compromise notifications, including jurisdiction, sector, and distribution-scope metadata
- Controlled evaluation on a four-organization testbed, with experimental runs at n = 2, 3, and 4 to produce a measured scaling curve. Metrics are defined in Table 1 below.
- A forensic procedure document describing how an investigator uses the system in a real case, expressed at a level suitable for inclusion in the methodology section of the paper

### 5.2 Out of Scope

- Discovering or analyzing real-world malicious packages, which is a software-security problem rather than a forensic one
- Legal admissibility arguments for any specific jurisdiction; the work claims tamper-evidence at the technical level, not legal sufficiency
- Real CERT or government partnerships; the evaluation is on a simulated network with simulated jurisdiction policies
- Performance benchmarking against production blockchain deployments; the testbed is a research configuration

### 5.3 Evaluation Metrics

The following metrics operationalize the research questions. Each is measurable on a local four-organization testbed with no external dependencies.

| Metric | What it measures | How it is computed |
|---|---|---|
| M1: Detection Accuracy | Whether compromised components installed in the agent are correctly identified against the known-good registry | True positive, false positive, true negative, false negative rates against a seeded ground-truth set of compromised and clean components |
| M2: Routing Precision | Whether compromise notifications are delivered only to jurisdictions affected by the compromise per policy metadata | Percentage of routed notifications that match the expected recipient set defined by the SBA policy rules for sector and jurisdiction |
| M3: Broadcast Overhead Reduction | Reduction in unnecessary cross-organizational notifications relative to a global broadcast baseline, measured across multiple network sizes to produce an empirical scaling curve | (n − r)/n where n is the total number of organizations and r is the number of authorized recipients, measured at n = 2, 3, and 4 (rather than projected from a single endpoint) |
| M4: End-to-End Detection Latency | Time from artifact-level detection to verified notification at the receiving jurisdiction, measured across network sizes to characterize consensus and routing overhead as n grows | Wall-clock time from chaincode invocation of `ReportCompromise` to `QueryCompromiseStatus` returning the verified record at a peer node, measured at n = 2, 3, and 4 |

### 5.4 Comparison Baselines

The proposed system is compared against three baselines to isolate the contribution of each architectural element.

| Baseline | Detection | Dissemination |
|---|---|---|
| B-None | No artifact-level checking | No cross-jurisdictional notification |
| B-Local | Local manifest-hash comparison against a local list | No cross-jurisdictional notification |
| B-Broadcast | Local manifest-hash comparison against a blockchain-anchored registry | Global broadcast to all participating organizations |
| ASCIR (proposed) | Local manifest-hash comparison against a blockchain-anchored registry | SBA-routed notification to authorized jurisdictions only, based on policy metadata |

Comparing ASCIR against B-Local isolates the contribution of the blockchain-anchored registry; comparing against B-Broadcast isolates the contribution of the SBA routing layer; comparing against B-None establishes the absolute detection benefit.

### 5.5 Network-Size Measurement Strategy

Each metric is measured across three network sizes to distinguish empirical results from formula-based projection. The choice of measurement points is deliberate and corresponds to three distinct evaluation roles:

- **n = 2 (replication baseline).** Reproduces the BICIR two-organization configuration to confirm that the ASCIR implementation matches prior measured results (100% routing accuracy on policy-matched cases and 50% overhead reduction) before introducing additional organizations. This step validates the implementation rather than the contribution.

- **n = 3 (primary contribution measurement).** Provides the first measured data point beyond prior work. Detection accuracy, routing precision, and the introduction of richer jurisdiction policies are evaluated here. Expected overhead reduction is 66.7% per the (n − r)/n formula, and the measurement tests whether this projection holds in practice.

- **n = 4 (scaling extension).** Doubles the testbed size relative to prior work. Tests whether the projected scaling continues (expected overhead reduction of 75%) and provides the first non-trivial consensus configuration where endorsement-policy and ordering-service behavior begin to influence end-to-end latency.

This three-point structure produces a measured curve rather than a single endpoint, which is the empirical pattern stronger forensic venues expect for scaling claims. n = 4 is selected as the upper bound because it is the largest configuration that fits comfortably on a single research machine while still producing meaningful consensus behavior; further scaling is identified as future work in Section 7.

## 6. Anticipated Contributions

The paper is expected to contribute four items, each tied to a specific section of the eventual manuscript:

- **A forensic procedure for agentic-AI supply-chain compromises** that specifies, at the investigator-action level, how artifact-level manifest extraction integrates with cross-jurisdictional notification.

- **An artifact-level detection method** with measured detection accuracy on a controlled set of seeded compromised and clean components.

- **A jurisdiction-aware dissemination layer** extending the Selective Broadcast Algorithm to handle compromise notifications, with empirical routing precision and a measured (rather than projected) overhead-reduction curve at n = 2, 3, and 4 organizations.

- **A reproducible testbed and dataset** consisting of the Hyperledger Fabric configuration, the chaincode, the seeded component manifests, and the forensic acquisition workflow, suitable for replication and extension.

## 7. Risks and Mitigations

- **Scope creep into software-security territory.** Mitigation: the detection method is treated as signature comparison against a registry; the question of what makes a package compromised is explicitly delegated to upstream sources.

- **Insufficient empirical rigor for a stronger forensics venue.** Mitigation: the evaluation includes four metrics with quantitative ground truth, three baseline comparisons, and an explicit projection table for scaling behavior, matching the empirical pattern that current DFRWS-tier forensic papers expect.

- **Overclaiming on legal or evidentiary admissibility.** Mitigation: the contribution is stated as tamper-evidence at the technical level, with explicit acknowledgement that legal sufficiency is a separate determination outside the scope of the paper.

- **Testbed too small to be convincing.** Mitigation: scale from two organizations in prior work to four organizations, with measurement at n = 2, 3, and 4 rather than at a single endpoint. This produces an empirical scaling curve in place of the formula-based projection used in prior work, while framing the testbed explicitly as a proof-of-concept rather than a deployment evaluation.

- **Configuration complexity of a four-organization Fabric network.** Mitigation: build incrementally, validating each network size before scaling to the next. The n = 2 configuration replicates BICIR and serves as a known-good reference; subsequent additions of Org3 and Org4 are made one at a time with channel-membership and endorsement-policy verification at each step.

## 8. Immediate Next Steps

Three concrete tasks follow from this problem statement and are sequenced to validate the design before significant implementation effort is committed.

1. Finalize the chaincode interface. Specify the input and output schemas of `RegisterKnownGood`, `ReportCompromise`, `QueryCompromiseStatus`, and `RouteCompromise`, including the policy metadata structure used by the SBA. *(Completed; see `docs/chaincode-interface.md`.)*

2. Design the seeded component dataset. Define the set of simulated agent components, their known-good manifest hashes, and the seeded compromise variants, with a clear ground-truth label for each entry.

3. Stand up the four-organization Fabric network incrementally. Begin by reproducing the BICIR two-organization configuration as a known-good baseline; then add Org3 (a healthcare-sector CERT) and Org4 (a general national CERT) one at a time, verifying channel membership, endorsement-policy behavior, and baseline routing at each step before introducing the compromise-detection chaincode.

Once these three tasks complete, the implementation phase has a stable target and the evaluation phase has a defined ground truth. Subsequent work proceeds with detection-method implementation, end-to-end integration, and metric collection.
