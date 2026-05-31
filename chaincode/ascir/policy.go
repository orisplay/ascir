package ascir

import "sort"

// EvaluateSBA applies the Selective Broadcast Algorithm policy to a
// compromise report's metadata and returns the authorized recipient set,
// the excluded set, and the policy trace.
//
// The function is pure (chaincode-interface.md Section 7.4): it depends
// only on its arguments, consults no world state, reads no clock, and
// uses no randomness. Every peer evaluating the same inputs produces a
// byte-identical result, which Fabric's endorsement model requires.
//
// Parameters:
//   - meta: the report's policy metadata (sectors, jurisdictions, scope, severity)
//   - reporterOrg: the MSP ID of the reporting organization (excluded from recipients)
//   - knownJurisdictions: all MSP IDs on the channel (defines ALL and the excluded complement)
//
// Returns (recipients, excluded, trace), with recipients and excluded
// sorted for determinism and trace in evaluation order.
func EvaluateSBA(meta PolicyMetadata, reporterOrg string, knownJurisdictions []string) (recipients []string, excluded []string, trace []TraceEntry) {
	// The recipient set, built as a set (map) and sorted at the end.
	set := map[string]bool{}
	trace = []TraceEntry{}

	// --- Phase 1: direct sector mapping ---
	// For each affected sector, add its primary jurisdiction. A sector code
	// not in the vocabulary falls back to GOV's jurisdiction, preserving the
	// BICIR behavior under unknown inputs (Section 4.3).
	for _, sector := range meta.AffectedSectors {
		juris, ok := PrimaryJurisdiction[sector]
		if !ok {
			// Unknown sector code: treat as GOV.
			juris = PrimaryJurisdiction[SectorGOV]
		}
		if !set[juris] {
			set[juris] = true
		}
		trace = append(trace, TraceEntry{
			Rule:  "sector_mapping",
			Input: sector,
			Added: []string{juris},
		})
	}

	// --- Phase 2: explicit jurisdiction inclusion ---
	// Every listed jurisdiction is added. The literal "ALL" adds every known
	// jurisdiction on the channel.
	for _, j := range meta.AffectedJurisdictions {
		if j == JurisdictionsAll {
			added := []string{}
			for _, k := range knownJurisdictions {
				if !set[k] {
					set[k] = true
				}
				added = append(added, k)
			}
			sort.Strings(added)
			trace = append(trace, TraceEntry{
				Rule:  "explicit_jurisdiction",
				Input: JurisdictionsAll,
				Added: added,
			})
		} else {
			if !set[j] {
				set[j] = true
			}
			trace = append(trace, TraceEntry{
				Rule:  "explicit_jurisdiction",
				Input: j,
				Added: []string{j},
			})
		}
	}

	// --- Phase 3: severity escalation ---
	// A critical compromise routes to the general national CERT (Org4MSP)
	// regardless of sector.
	if meta.Severity == SeverityCritical {
		if !set[Org4MSP] {
			set[Org4MSP] = true
		}
		trace = append(trace, TraceEntry{
			Rule:  "severity_escalation",
			Input: SeverityCritical,
			Added: []string{Org4MSP},
		})
	}

	// --- Reporter exclusion ---
	// The reporting organization is never a recipient of its own report.
	// Applied after all three phases.
	if set[reporterOrg] {
		delete(set, reporterOrg)
		trace = append(trace, TraceEntry{
			Rule:    "reporter_exclusion",
			Input:   reporterOrg,
			Removed: []string{reporterOrg},
		})
	}

	// --- Build sorted outputs ---
	recipients = []string{}
	for j := range set {
		recipients = append(recipients, j)
	}
	sort.Strings(recipients)

	// Excluded = known jurisdictions not in the recipient set.
	excluded = []string{}
	for _, k := range knownJurisdictions {
		if !set[k] {
			excluded = append(excluded, k)
		}
	}
	sort.Strings(excluded)

	return recipients, excluded, trace
}
