# ASCIR — Agentic Supply-Chain Incident Routing

A forensic framework for detecting agentic-AI supply-chain compromises at the
artifact level and disseminating compromise notifications across jurisdictions
through a permissioned blockchain.

This repository contains the design documents, chaincode, network configurations,
detection client, dataset, and experimental scripts for the ASCIR research
project. The work extends the BICIR cross-national cyber incident response model
with artifact-level compromise detection and a richer jurisdiction-aware routing
policy, evaluated on a Hyperledger Fabric testbed at network sizes n = 2, 3,
and 4.

## Status

Pre-implementation. Currently building the design specifications and reproducible
testbed structure. See `docs/` for the working design documents.

## Repository Structure

- `docs/` — Design documents (problem statement, chaincode interface, dataset spec)
- `chaincode/` — Hyperledger Fabric chaincode in Go
- `network/` — Fabric network configurations for n=2, n=3, n=4
- `backend/` — Node.js REST API wrapping chaincode invocations
- `detector/` — Python artifact-level compromise detector
- `dataset/` — Seeded agent components and ground-truth labels
- `experiments/` — Scripts to reproduce the measurement runs
- `analysis/` — JupyterLab notebooks producing the paper figures

## Reproducibility

Reproduction instructions will land in `docs/reproducibility.md` once the first
measurement run is complete. The repository is version-tagged at each major
milestone; the tag corresponding to a given paper submission will be noted in
the eventual paper.

## License

See `LICENSE`. The code is released under the MIT License; the dataset and
documentation are released under CC-BY-4.0.

## Citation

A `CITATION.cff` file will be added at first public release.

## Contact

Osayomore O. Aigbogun — Department of Computer Science, Sam Houston State
University — ooa020@shsu.edu
