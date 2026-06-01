package main

import (
	"reflect"
	"testing"
)

// knownFour is the four-organization channel topology used by the dataset.
var knownFour = []string{Org1MSP, Org2MSP, Org3MSP, Org4MSP}

// TestEvaluateSBA_DatasetVariants checks EvaluateSBA against the 15
// compromise-variant cases whose expected recipient sets were verified
// by hand against the interface spec in the dataset-generation phase.
// The Python reference (generator's compute_expected_sba_recipients)
// produced these same values; this test confirms the Go implementation
// agrees. Reporter is Org1MSP for all cases (the dataset's assumption).
func TestEvaluateSBA_DatasetVariants(t *testing.T) {
	cases := []struct {
		name     string
		meta     PolicyMetadata
		expected []string
	}{
		{"M01_FIN", PolicyMetadata{AffectedSectors: []string{"FIN"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityMedium}, []string{}},
		{"M02_CI", PolicyMetadata{AffectedSectors: []string{"CI"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityMedium}, []string{Org2MSP}},
		{"M03_HC", PolicyMetadata{AffectedSectors: []string{"HC"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityMedium}, []string{Org3MSP}},
		{"M04_GOV", PolicyMetadata{AffectedSectors: []string{"GOV"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityMedium}, []string{Org4MSP}},
		{"M05_FIN", PolicyMetadata{AffectedSectors: []string{"FIN"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityMedium}, []string{}},

		{"A01_FIN_CI", PolicyMetadata{AffectedSectors: []string{"FIN", "CI"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeMulti, Severity: SeverityHigh}, []string{Org2MSP}},
		{"A02_HC_GOV", PolicyMetadata{AffectedSectors: []string{"HC", "GOV"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeMulti, Severity: SeverityHigh}, []string{Org3MSP, Org4MSP}},
		{"A03_FIN_HC", PolicyMetadata{AffectedSectors: []string{"FIN", "HC"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeMulti, Severity: SeverityHigh}, []string{Org3MSP}},
		{"A04_CI_HC_GOV", PolicyMetadata{AffectedSectors: []string{"CI", "HC", "GOV"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeMulti, Severity: SeverityHigh}, []string{Org2MSP, Org3MSP, Org4MSP}},
		{"A05_all", PolicyMetadata{AffectedSectors: []string{"FIN", "CI", "HC", "GOV"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeMulti, Severity: SeverityHigh}, []string{Org2MSP, Org3MSP, Org4MSP}},

		{"R01_GOV", PolicyMetadata{AffectedSectors: []string{"GOV"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityLow}, []string{Org4MSP}},
		{"R02_HC", PolicyMetadata{AffectedSectors: []string{"HC"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityMedium}, []string{Org3MSP}},
		{"R03_CI_critical", PolicyMetadata{AffectedSectors: []string{"CI"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityCritical}, []string{Org2MSP, Org4MSP}},
		{"R04_FIN", PolicyMetadata{AffectedSectors: []string{"FIN"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeMulti, Severity: SeverityHigh}, []string{}},
		{"R05_GOV_all_critical", PolicyMetadata{AffectedSectors: []string{"GOV"}, AffectedJurisdictions: []string{"ALL"}, DistributionScope: ScopeGlobal, Severity: SeverityCritical}, []string{Org2MSP, Org3MSP, Org4MSP}},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, _, _ := EvaluateSBA(c.meta, Org1MSP, knownFour)
			if !equalStringSlices(got, c.expected) {
				t.Errorf("recipients mismatch\n  meta:     %+v\n  expected: %v\n  got:      %v",
					c.meta, c.expected, got)
			}
		})
	}
}

// TestEvaluateSBA_ReporterExclusionTrace checks that when the reporter is
// excluded, the trace records a reporter_exclusion entry, and that a
// non-excluded case does not.
func TestEvaluateSBA_ReporterExclusionTrace(t *testing.T) {
	// FIN maps to Org1MSP, which is the reporter -> exclusion fires.
	_, _, trace := EvaluateSBA(
		PolicyMetadata{AffectedSectors: []string{"FIN"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityMedium},
		Org1MSP, knownFour)
	if !traceHasRule(trace, "reporter_exclusion") {
		t.Errorf("expected reporter_exclusion in trace, got %+v", trace)
	}

	// CI maps to Org2MSP; reporter Org1MSP was never added -> no exclusion.
	_, _, trace2 := EvaluateSBA(
		PolicyMetadata{AffectedSectors: []string{"CI"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityMedium},
		Org1MSP, knownFour)
	if traceHasRule(trace2, "reporter_exclusion") {
		t.Errorf("did not expect reporter_exclusion in trace, got %+v", trace2)
	}
}

// TestEvaluateSBA_SeverityEscalationTrace checks that a critical-severity
// report records a severity_escalation entry adding Org4MSP.
func TestEvaluateSBA_SeverityEscalationTrace(t *testing.T) {
	_, _, trace := EvaluateSBA(
		PolicyMetadata{AffectedSectors: []string{"CI"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityCritical},
		Org1MSP, knownFour)
	if !traceHasRule(trace, "severity_escalation") {
		t.Errorf("expected severity_escalation in trace, got %+v", trace)
	}
}

// TestEvaluateSBA_UnknownSectorFallsBackToGOV checks that a sector code
// outside the vocabulary is treated as GOV (-> Org4MSP).
func TestEvaluateSBA_UnknownSectorFallsBackToGOV(t *testing.T) {
	got, _, _ := EvaluateSBA(
		PolicyMetadata{AffectedSectors: []string{"BANANA"}, AffectedJurisdictions: []string{}, DistributionScope: ScopeSingle, Severity: SeverityLow},
		Org1MSP, knownFour)
	expected := []string{Org4MSP}
	if !equalStringSlices(got, expected) {
		t.Errorf("unknown sector fallback: expected %v, got %v", expected, got)
	}
}

// --- helpers ---------------------------------------------------------------

func equalStringSlices(a, b []string) bool {
	// Treat nil and empty as equal for our purposes.
	if len(a) == 0 && len(b) == 0 {
		return true
	}
	return reflect.DeepEqual(a, b)
}

func traceHasRule(trace []TraceEntry, rule string) bool {
	for _, e := range trace {
		if e.Rule == rule {
			return true
		}
	}
	return false
}
