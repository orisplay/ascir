# ASCIR — Agentic Supply-Chain Incident Routing

A forensic framework for detecting agentic-AI supply-chain compromises at the
artifact level and disseminating compromise notifications across jurisdictions
through a permissioned blockchain.

This repository contains the chaincode, network configurations, backend API,
investigator console, dataset, and experimental scripts for the ASCIR research
project. The work extends the BICIR cross-national cyber incident response model
with artifact-level compromise detection and a jurisdiction-aware routing policy
scoped to the organizations present on the channel, evaluated on a Hyperledger
Fabric 2.5.15 testbed at network sizes n = 2, 3, and 4.

## Status

Implemented and evaluated. The system runs end-to-end (investigator console →
multi-organization backend → four-organization Fabric network), and the four
reported metrics (detection accuracy, routing precision, broadcast-overhead
reduction, staged latency) have been measured on the testbed. A manuscript based
on this work is in preparation.

## Repository Structure

* `chaincode/` — Hyperledger Fabric chaincode in Go (registry, detection, SBA routing, enumeration)
* `backend/` — Node.js REST API wrapping chaincode invocations, one Fabric gateway per organization
* `frontend/` — React/Vite investigator console (check, register, report, route, registry browser)
* `dataset/` — Deterministic generator for the 45-component dataset + ground truth
* `experiments/` — Measurement harnesses (M1–M4) and the independent routing oracle
* `network/` — Network build notes (`scaling.md`) for n=2, n=3, n=4
* `scripts/` — One-command network build, teardown, experiment runner, and demo guide
* `analysis/` — Notebooks producing the paper figures

## Reproducing the testbed

The network build is automated:

    ./scripts/rebuild.sh 4        # bring up a 4-org network (also accepts 2 or 3)

See `scripts/RUNBOOK.md` for prerequisites, tunable parameters (chaincode
version, orderer batch timeout), and known gotchas, and `scripts/DEMO.md` for a
step-by-step end-to-end demo (network → backend → frontend → GUI walk-through).
The 45-component dataset is regenerated deterministically:

    python dataset/generate.py

**Note:** the build depends on Hyperledger `fabric-samples` (v2.5.15) and the
hand-built `addOrg4/` assets under `fabric-samples/test-network/`; see
`scripts/RUNBOOK.md` for the expected layout.

## License

See `LICENSE`. The code is released under the MIT License; the dataset and
documentation are released under CC-BY-4.0.

## Citation

A `CITATION.cff` file will be added at first public release.

## Contact

Osayomore O. Aigbogun — Department of Computer Science, Sam Houston State
University — ooa020@shsu.edu
