package main

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
// Every jurisdiction added by any phase must be a known jurisdiction on the
// channel: a notification cannot be routed to a CERT that is not part of the
// federation. A rule may therefore fire (appear in the trace) yet contribute
// no recipient when its target jurisdiction is not currently present. This is
// what makes the recipient set, and hence the overhead-reduction metric,
// depend on the network size n.
//
// Parameters:
//   - meta: the report's policy metadata (sectors, jurisdictions, scope, severity)
//   - reporterOrg: the MSP ID of the reporting organization (excluded from recipients)
//   - knownJurisdictions: all MSP IDs on the channel (defines presence, ALL, and the excluded complement)
//
// Returns (recipients, excluded, trace), with recipients and excluded
// sorted for determinism and trace in evaluation order.
func EvaluateSBA(meta PolicyMetadata, reporterOrg string, knownJurisdictions []string) (recipients []string, excluded []string, trace []TraceEntry) {
	// The recipient set, built as a set (map) and sorted at the end.
	set := map[string]bool{}
	trace = []TraceEntry{}

	// Membership lookup: a jurisdiction is eligible to be a recipient only if
	// it is present on the channel.
	known := map[string]bool{}
	for _, k := range knownJurisdictions {
		known[k] = true
	}

	// addIfKnown adds juris to the recipient set only when it is a known
	// jurisdiction. It returns the slice to record as the rule's Added field:
	// the singleton when present, or empty when the target is absent.
	addIfKnown := func(juris string) []string {
		if !known[juris] {
			return []string{}
		}
		set[juris] = true
		return []string{juris}
	}

	// --- Phase 1: direct sector mapping ---
	// For each affected sector, add its primary jurisdiction if that
	// jurisdiction is present on the channel. A sector code not in the
	// vocabulary falls back to GOV's jurisdiction (Section 4.3).
	for _, sector := range meta.AffectedSectors {
		juris, ok := PrimaryJurisdiction[sector]
		if !ok {
			juris = PrimaryJurisdiction[SectorGOV]
		}
		trace = append(trace, TraceEntry{
			Rule:  "sector_mapping",
			Input: sector,
			Added: addIfKnown(juris),
		})
	}

	// --- Phase 2: explicit jurisdiction inclusion ---
	// Every listed jurisdiction is added if present. The literal "ALL" adds
	// every known jurisdiction on the channel (inherently scoped).
	for _, j := range meta.AffectedJurisdictions {
		if j == JurisdictionsAll {
			added := []string{}
			for _, k := range knownJurisdictions {
				set[k] = true
				added = append(added, k)
			}
			sort.Strings(added)
			trace = append(trace, TraceEntry{
				Rule:  "explicit_jurisdiction",
				Input: JurisdictionsAll,
				Added: added,
			})
		} else {
			trace = append(trace, TraceEntry{
				Rule:  "explicit_jurisdiction",
				Input: j,
				Added: addIfKnown(j),
			})
		}
	}

	// --- Phase 3: severity escalation ---
	// A critical compromise routes to the general national CERT (Org4MSP)
	// regardless of sector, when that CERT is present on the channel.
	if meta.Severity == SeverityCritical {
		trace = append(trace, TraceEntry{
			Rule:  "severity_escalation",
			Input: SeverityCritical,
			Added: addIfKnown(Org4MSP),
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
