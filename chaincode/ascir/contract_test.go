package ascir

import (
	"encoding/json"
	"testing"
)

// A valid 64-char lowercase hex manifest hash for tests.
const testHash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
const testHash2 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

func ciMeta() PolicyMetadata {
	return PolicyMetadata{
		AffectedSectors:       []string{SectorCI},
		AffectedJurisdictions: []string{},
		DistributionScope:     ScopeSingle,
		Severity:              SeverityMedium,
	}
}

// --- RegisterKnownGood -----------------------------------------------------

func TestRegisterKnownGood_RegistersThenIdempotent(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org1MSP)

	resp, err := c.RegisterKnownGood(ctx, testHash, "comp", "1.0", Org1MSP, "2026-01-01T00:00:00Z")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Status != "registered" {
		t.Errorf("first register: expected status registered, got %q", resp.Status)
	}

	resp2, err := c.RegisterKnownGood(ctx, testHash, "comp", "1.0", Org1MSP, "2026-01-01T00:00:00Z")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp2.Status != "already_exists" {
		t.Errorf("second register: expected already_exists, got %q", resp2.Status)
	}
}

func TestRegisterKnownGood_RejectsMSPMismatch(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org2MSP)

	_, err := c.RegisterKnownGood(ctx, testHash, "comp", "1.0", Org1MSP, "2026-01-01T00:00:00Z")
	if err == nil {
		t.Errorf("expected error when caller MSP != signer_org, got nil")
	}
}

func TestRegisterKnownGood_RejectsBadHash(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org1MSP)

	_, err := c.RegisterKnownGood(ctx, "tooshort", "comp", "1.0", Org1MSP, "2026-01-01T00:00:00Z")
	if err == nil {
		t.Errorf("expected error for malformed hash, got nil")
	}
}

// --- ReportCompromise ------------------------------------------------------

func TestReportCompromise_DeterministicAndIndexed(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org1MSP)

	resp, err := c.ReportCompromise(ctx, testHash, "comp", Org1MSP, "2026-01-02T00:00:00Z", "evid-1", ciMeta())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Status != "reported" {
		t.Errorf("expected status reported, got %q", resp.Status)
	}
	if resp.ReportID == "" {
		t.Errorf("expected non-empty report_id")
	}

	resp2, err := c.ReportCompromise(ctx, testHash, "comp", Org1MSP, "2026-01-02T00:00:00Z", "evid-1", ciMeta())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp2.ReportID != resp.ReportID {
		t.Errorf("report_id not deterministic: %q vs %q", resp.ReportID, resp2.ReportID)
	}

	idxKey, _ := ctx.stub.CreateCompositeKey(ObjIndex, []string{resp.ReportID})
	idxVal, _ := ctx.stub.GetState(idxKey)
	if string(idxVal) != testHash {
		t.Errorf("index entry wrong: expected %q, got %q", testHash, string(idxVal))
	}
}

func TestReportCompromise_RejectsEmptyEvidence(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org1MSP)

	_, err := c.ReportCompromise(ctx, testHash, "comp", Org1MSP, "2026-01-02T00:00:00Z", "", ciMeta())
	if err == nil {
		t.Errorf("expected error for empty evidence_ref, got nil")
	}
}

// --- QueryCompromiseStatus: all four statuses ------------------------------

func TestQueryStatus_Unknown(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org1MSP)

	resp, err := c.QueryCompromiseStatus(ctx, testHash)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Status != StatusUnknown {
		t.Errorf("expected unknown, got %q", resp.Status)
	}
}

func TestQueryStatus_KnownGood(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org1MSP)

	_, _ = c.RegisterKnownGood(ctx, testHash, "comp", "1.0", Org1MSP, "2026-01-01T00:00:00Z")

	resp, err := c.QueryCompromiseStatus(ctx, testHash)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Status != StatusKnownGood {
		t.Errorf("expected known_good, got %q", resp.Status)
	}
	if resp.KnownGoodEntry == nil {
		t.Errorf("expected known_good_entry to be populated")
	}
}

func TestQueryStatus_Compromised(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org1MSP)

	_, _ = c.ReportCompromise(ctx, testHash, "comp", Org1MSP, "2026-01-02T00:00:00Z", "evid-1", ciMeta())

	resp, err := c.QueryCompromiseStatus(ctx, testHash)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Status != StatusCompromised {
		t.Errorf("expected compromised, got %q", resp.Status)
	}
	if len(resp.ActiveCompromiseReports) != 1 {
		t.Errorf("expected 1 active report, got %d", len(resp.ActiveCompromiseReports))
	}
}

func TestQueryStatus_Contested(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org1MSP)

	_, _ = c.RegisterKnownGood(ctx, testHash, "comp", "1.0", Org1MSP, "2026-01-01T00:00:00Z")
	_, _ = c.ReportCompromise(ctx, testHash, "comp", Org1MSP, "2026-01-02T00:00:00Z", "evid-1", ciMeta())

	resp, err := c.QueryCompromiseStatus(ctx, testHash)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Status != StatusContested {
		t.Errorf("expected contested, got %q", resp.Status)
	}
}

// --- RouteCompromise: end-to-end through the ledger ------------------------

func TestRouteCompromise_EndToEnd(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org1MSP)

	rep, err := c.ReportCompromise(ctx, testHash, "comp", Org1MSP, "2026-01-02T00:00:00Z", "evid-1", ciMeta())
	if err != nil {
		t.Fatalf("report error: %v", err)
	}

	known := []string{Org1MSP, Org2MSP, Org3MSP, Org4MSP}
	route, err := c.RouteCompromise(ctx, rep.ReportID, known)
	if err != nil {
		t.Fatalf("route error: %v", err)
	}
	if route.Status != "routed" {
		t.Errorf("expected routed, got %q", route.Status)
	}

	if len(route.AuthorizedRecipients) != 1 || route.AuthorizedRecipients[0] != Org2MSP {
		t.Errorf("expected recipients [Org2MSP], got %v", route.AuthorizedRecipients)
	}

	rdData, _ := ctx.stub.GetState(route.Key)
	if rdData == nil {
		t.Fatalf("routing decision record not found at %q", route.Key)
	}
	var decision RoutingDecision
	if err := json.Unmarshal(rdData, &decision); err != nil {
		t.Fatalf("RD unmarshal: %v", err)
	}
	if decision.DecisionID != route.DecisionID {
		t.Errorf("RD record decision_id mismatch")
	}
}

func TestRouteCompromise_UnknownReportID(t *testing.T) {
	c := &ASCIRContract{}
	ctx := newMockContext(Org1MSP)

	_, err := c.RouteCompromise(ctx, "nonexistent-report-id", []string{Org1MSP, Org2MSP})
	if err == nil {
		t.Errorf("expected error for unknown report_id, got nil")
	}
}
