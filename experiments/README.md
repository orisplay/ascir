# ASCIR Experiments

Measurement runs for metrics M1–M4 (defined in `docs/metrics.md`). This
directory holds the scenario sets, the run protocol, and the recorded results.

## Layout

- `scenarios/` — fixed scenario sets (JSON), one file per scenario group. Each
  scenario specifies the report inputs and the expected outcome derived from the
  SBA spec (independent of the chaincode). Fixing these makes M2/M3 reproducible.
- `results/` — one JSON file per metric per network size, named
  `<metric>_n<size>.json` (e.g. `m3_n4.json`). Schema below.

## Run protocol

1. Bring up the network at size n per `network/scaling.md`; deploy chaincode
   v1.1 (sequence 1).
2. For M1: establish the registry state (register baselines known-good; report
   the designated compromise variants) — record the exact registration commands.
3. For each scenario in the chosen set, invoke the chaincode (using the correct
   endorser count for n — three peers at n=4, see scaling.md GOTCHA 4) and
   capture the raw outputs.
4. Compute metric values and write the result JSON.
5. Tear down per scaling.md.

The expected recipient set for M2 is computed from the SBA spec, never read
back from the chaincode (see docs/metrics.md).

## Result file schema

```json
{
  "metric": "M3",
  "n": 4,
  "chaincode": {"name": "ascir", "version": "1.1", "sequence": 1},
  "fabric_version": "2.5.15",
  "endorser_count": 3,
  "scenario_set": "scenarios/routing_core.json",
  "timestamp": "ISO-8601",
  "per_scenario": [
    {
      "id": "ci_critical",
      "inputs": {"affected_sectors": ["CI"], "severity": "critical", "reporter": "Org1MSP"},
      "expected_recipients": ["Org2MSP", "Org4MSP"],
      "routed_recipients": ["Org2MSP", "Org4MSP"],
      "r": 2,
      "metric_values": {"reduction": 0.5, "exact_match": 1}
    }
  ],
  "summary": {"mean_reduction": 0.5, "notes": "single-recipient cases avg higher"}
}
```

Fields vary by metric (M1 carries a confusion matrix; M2 precision/recall/
exact-match; M3 reduction; M4 median/p95 and a `raw_times_ms` array), but every
file carries the `metric`, `n`, `chaincode`, `fabric_version`, `endorser_count`,
`scenario_set`, and `timestamp` envelope so results are self-describing and
reproducible.

## Scenario file schema

```json
{
  "set": "routing_core",
  "description": "core SBA routing cases exercising each rule",
  "scenarios": [
    {
      "id": "hc_high",
      "report": {
        "component_name": "clinical-data-agent",
        "reporter_org": "Org1MSP",
        "policy_metadata": {
          "affected_sectors": ["HC"],
          "affected_jurisdictions": [],
          "distribution_scope": "single_jurisdiction",
          "severity": "high"
        }
      },
      "expected_recipients": ["Org3MSP"],
      "exercises": ["sector_mapping"]
    }
  ]
}
```

The `expected_recipients` and `exercises` fields are the ground truth; they are
authored from the SBA spec (chaincode-interface.md §7), reviewed independently of
the chaincode, and are what M2 scores against.
