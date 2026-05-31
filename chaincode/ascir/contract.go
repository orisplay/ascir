package ascir

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

// ASCIRContract implements the four chaincode functions defined in the
// interface specification: RegisterKnownGood, ReportCompromise,
// QueryCompromiseStatus, and RouteCompromise.
type ASCIRContract struct {
	contractapi.Contract
}

// ---------------------------------------------------------------------------
// Response types (contract-layer outputs, not ledger records)
// ---------------------------------------------------------------------------

// RegisterResponse is returned by RegisterKnownGood.
type RegisterResponse struct {
	Status string `json:"status"` // "registered" | "already_exists"
	Key    string `json:"key"`
	TxID   string `json:"tx_id"`
}

// ReportResponse is returned by ReportCompromise.
type ReportResponse struct {
	Status   string `json:"status"` // "reported"
	ReportID string `json:"report_id"`
	Key      string `json:"key"`
	TxID     string `json:"tx_id"`
}

// StatusResponse is returned by QueryCompromiseStatus.
type StatusResponse struct {
	ManifestHash               string             `json:"manifest_hash"`
	Status                     string             `json:"status"` // unknown|known_good|compromised|contested
	KnownGoodEntry             *KnownGoodEntry    `json:"known_good_entry"`
	ActiveCompromiseReports    []CompromiseReport `json:"active_compromise_reports"`
	RetractedCompromiseReports []CompromiseReport `json:"retracted_compromise_reports"`
}

// RouteResponse is returned by RouteCompromise.
type RouteResponse struct {
	Status                string       `json:"status"` // "routed"
	DecisionID            string       `json:"decision_id"`
	Key                   string       `json:"key"`
	AuthorizedRecipients  []string     `json:"authorized_recipients"`
	ExcludedJurisdictions []string     `json:"excluded_jurisdictions"`
	PolicyTrace           []TraceEntry `json:"policy_trace"`
	TxID                  string       `json:"tx_id"`
}

// Status string constants for QueryCompromiseStatus.
const (
	StatusUnknown     = "unknown"
	StatusKnownGood   = "known_good"
	StatusCompromised = "compromised"
	StatusContested   = "contested"
)

// ---------------------------------------------------------------------------
// RegisterKnownGood (interface spec 5.1)
// ---------------------------------------------------------------------------

// RegisterKnownGood records a manifest hash as a verified legitimate
// component. Idempotent: a second call with the same hash returns
// already_exists without writing.
func (c *ASCIRContract) RegisterKnownGood(
	ctx contractapi.TransactionContextInterface,
	manifestHash string,
	componentName string,
	version string,
	signerOrg string,
	signedAt string,
) (*RegisterResponse, error) {
	if err := validateHash(manifestHash); err != nil {
		return nil, err
	}
	if err := requireCallerMSP(ctx, signerOrg); err != nil {
		return nil, err
	}

	stub := ctx.GetStub()
	key, err := stub.CreateCompositeKey(ObjKnownGood, []string{manifestHash})
	if err != nil {
		return nil, fmt.Errorf("composite key: %w", err)
	}

	existing, err := stub.GetState(key)
	if err != nil {
		return nil, fmt.Errorf("get state: %w", err)
	}
	if existing != nil {
		return &RegisterResponse{Status: "already_exists", Key: key, TxID: stub.GetTxID()}, nil
	}

	entry := KnownGoodEntry{
		ManifestHash:  manifestHash,
		ComponentName: componentName,
		Version:       version,
		SignerOrg:     signerOrg,
		SignedAt:      signedAt,
	}
	data, err := json.Marshal(entry)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}
	if err := stub.PutState(key, data); err != nil {
		return nil, fmt.Errorf("put state: %w", err)
	}

	return &RegisterResponse{Status: "registered", Key: key, TxID: stub.GetTxID()}, nil
}

// ---------------------------------------------------------------------------
// ReportCompromise (interface spec 5.2)
// ---------------------------------------------------------------------------

// ReportCompromise declares a manifest hash as a known compromise and stores
// the policy metadata used for routing. Writes a CR record and an IDX index
// record (report_id -> manifest_hash). Deterministic report_id makes the call
// idempotent under retry.
func (c *ASCIRContract) ReportCompromise(
	ctx contractapi.TransactionContextInterface,
	manifestHash string,
	componentName string,
	reporterOrg string,
	reportedAt string,
	evidenceRef string,
	meta PolicyMetadata,
) (*ReportResponse, error) {
	if err := validateHash(manifestHash); err != nil {
		return nil, err
	}
	if err := requireCallerMSP(ctx, reporterOrg); err != nil {
		return nil, err
	}
	if evidenceRef == "" {
		return nil, fmt.Errorf("evidence_ref must be non-empty")
	}
	if err := validatePolicyMetadata(meta); err != nil {
		return nil, err
	}

	reportID := deriveReportID(manifestHash, reporterOrg, reportedAt)

	stub := ctx.GetStub()
	key, err := stub.CreateCompositeKey(ObjReport, []string{manifestHash, reportID})
	if err != nil {
		return nil, fmt.Errorf("composite key: %w", err)
	}

	report := CompromiseReport{
		ManifestHash:   manifestHash,
		ComponentName:  componentName,
		ReporterOrg:    reporterOrg,
		ReportedAt:     reportedAt,
		EvidenceRef:    evidenceRef,
		PolicyMetadata: meta,
		ReportID:       reportID,
	}
	data, err := json.Marshal(report)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}
	if err := stub.PutState(key, data); err != nil {
		return nil, fmt.Errorf("put state: %w", err)
	}

	// Secondary index: report_id -> manifest_hash (DECISIONS.md D2).
	idxKey, err := stub.CreateCompositeKey(ObjIndex, []string{reportID})
	if err != nil {
		return nil, fmt.Errorf("index composite key: %w", err)
	}
	if err := stub.PutState(idxKey, []byte(manifestHash)); err != nil {
		return nil, fmt.Errorf("put index: %w", err)
	}

	return &ReportResponse{Status: "reported", ReportID: reportID, Key: key, TxID: stub.GetTxID()}, nil
}

// ---------------------------------------------------------------------------
// QueryCompromiseStatus (interface spec 5.3)
// ---------------------------------------------------------------------------

// QueryCompromiseStatus consolidates the KG, CR, and RT records for a hash
// into a single status response. Read-only.
func (c *ASCIRContract) QueryCompromiseStatus(
	ctx contractapi.TransactionContextInterface,
	manifestHash string,
) (*StatusResponse, error) {
	if err := validateHash(manifestHash); err != nil {
		return nil, err
	}
	stub := ctx.GetStub()

	// Known-good entry (single key).
	kgKey, err := stub.CreateCompositeKey(ObjKnownGood, []string{manifestHash})
	if err != nil {
		return nil, fmt.Errorf("kg composite key: %w", err)
	}
	kgData, err := stub.GetState(kgKey)
	if err != nil {
		return nil, fmt.Errorf("kg get state: %w", err)
	}
	var kgEntry *KnownGoodEntry
	if kgData != nil {
		var e KnownGoodEntry
		if err := json.Unmarshal(kgData, &e); err != nil {
			return nil, fmt.Errorf("kg unmarshal: %w", err)
		}
		kgEntry = &e
	}

	// All compromise reports for this hash (partial composite key CR~<hash>~*).
	iter, err := stub.GetStateByPartialCompositeKey(ObjReport, []string{manifestHash})
	if err != nil {
		return nil, fmt.Errorf("cr partial query: %w", err)
	}
	defer iter.Close()

	active := []CompromiseReport{}
	retracted := []CompromiseReport{}
	for iter.HasNext() {
		kv, err := iter.Next()
		if err != nil {
			return nil, fmt.Errorf("cr iterate: %w", err)
		}
		var report CompromiseReport
		if err := json.Unmarshal(kv.Value, &report); err != nil {
			return nil, fmt.Errorf("cr unmarshal: %w", err)
		}
		isRetracted, err := c.reportIsRetracted(ctx, report.ReportID)
		if err != nil {
			return nil, err
		}
		if isRetracted {
			retracted = append(retracted, report)
		} else {
			active = append(active, report)
		}
	}

	status := resolveStatus(kgEntry != nil, len(active) > 0)

	return &StatusResponse{
		ManifestHash:               manifestHash,
		Status:                     status,
		KnownGoodEntry:             kgEntry,
		ActiveCompromiseReports:    active,
		RetractedCompromiseReports: retracted,
	}, nil
}

// ---------------------------------------------------------------------------
// RouteCompromise (interface spec 5.4)
// ---------------------------------------------------------------------------

// RouteCompromise evaluates the SBA policy on a compromise report and writes
// the routing decision as a verifiable ledger record. Resolves report_id to
// the manifest hash via the IDX index, then loads the CR record.
func (c *ASCIRContract) RouteCompromise(
	ctx contractapi.TransactionContextInterface,
	reportID string,
	knownJurisdictions []string,
) (*RouteResponse, error) {
	if reportID == "" {
		return nil, fmt.Errorf("report_id must be non-empty")
	}
	stub := ctx.GetStub()

	// Resolve report_id -> manifest_hash via the secondary index.
	idxKey, err := stub.CreateCompositeKey(ObjIndex, []string{reportID})
	if err != nil {
		return nil, fmt.Errorf("index composite key: %w", err)
	}
	hashBytes, err := stub.GetState(idxKey)
	if err != nil {
		return nil, fmt.Errorf("index get state: %w", err)
	}
	if hashBytes == nil {
		return nil, fmt.Errorf("no compromise report found for report_id %s", reportID)
	}
	manifestHash := string(hashBytes)

	// Load the CR record by full composite key.
	crKey, err := stub.CreateCompositeKey(ObjReport, []string{manifestHash, reportID})
	if err != nil {
		return nil, fmt.Errorf("cr composite key: %w", err)
	}
	crData, err := stub.GetState(crKey)
	if err != nil {
		return nil, fmt.Errorf("cr get state: %w", err)
	}
	if crData == nil {
		return nil, fmt.Errorf("index pointed to missing CR record for report_id %s", reportID)
	}
	var report CompromiseReport
	if err := json.Unmarshal(crData, &report); err != nil {
		return nil, fmt.Errorf("cr unmarshal: %w", err)
	}

	// Precondition: the report must not be retracted.
	isRetracted, err := c.reportIsRetracted(ctx, reportID)
	if err != nil {
		return nil, err
	}
	if isRetracted {
		return nil, fmt.Errorf("report_id %s has been retracted; cannot route", reportID)
	}

	// Evaluate the SBA policy (pure function from policy.go).
	recipients, excluded, trace := EvaluateSBA(report.PolicyMetadata, report.ReporterOrg, knownJurisdictions)

	decisionID := deriveDecisionID(reportID, recipients)
	rdKey, err := stub.CreateCompositeKey(ObjDecision, []string{reportID, decisionID})
	if err != nil {
		return nil, fmt.Errorf("rd composite key: %w", err)
	}

	decision := RoutingDecision{
		ReportID:              reportID,
		DecisionID:            decisionID,
		AuthorizedRecipients:  recipients,
		ExcludedJurisdictions: excluded,
		PolicyTrace:           trace,
	}
	data, err := json.Marshal(decision)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}
	if err := stub.PutState(rdKey, data); err != nil {
		return nil, fmt.Errorf("put state: %w", err)
	}

	return &RouteResponse{
		Status:                "routed",
		DecisionID:            decisionID,
		Key:                   rdKey,
		AuthorizedRecipients:  recipients,
		ExcludedJurisdictions: excluded,
		PolicyTrace:           trace,
		TxID:                  stub.GetTxID(),
	}, nil
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// reportIsRetracted reports whether an RT record exists for the given report_id.
func (c *ASCIRContract) reportIsRetracted(
	ctx contractapi.TransactionContextInterface,
	reportID string,
) (bool, error) {
	stub := ctx.GetStub()
	rtKey, err := stub.CreateCompositeKey(ObjRetract, []string{reportID})
	if err != nil {
		return false, fmt.Errorf("rt composite key: %w", err)
	}
	rtData, err := stub.GetState(rtKey)
	if err != nil {
		return false, fmt.Errorf("rt get state: %w", err)
	}
	return rtData != nil, nil
}

// resolveStatus implements the status-resolution logic of spec 5.3.
func resolveStatus(hasKnownGood, hasActiveCompromise bool) string {
	switch {
	case !hasKnownGood && !hasActiveCompromise:
		return StatusUnknown
	case hasKnownGood && !hasActiveCompromise:
		return StatusKnownGood
	case !hasKnownGood && hasActiveCompromise:
		return StatusCompromised
	default: // hasKnownGood && hasActiveCompromise
		return StatusContested
	}
}

// validateHash checks that a manifest hash is a 64-char lowercase hex string.
func validateHash(h string) error {
	if len(h) != 64 {
		return fmt.Errorf("manifest_hash must be 64 hex characters, got %d", len(h))
	}
	for _, r := range h {
		if !((r >= '0' && r <= '9') || (r >= 'a' && r <= 'f')) {
			return fmt.Errorf("manifest_hash must be lowercase hexadecimal")
		}
	}
	return nil
}

// validatePolicyMetadata checks sector codes and the affected-jurisdictions
// value against the controlled vocabulary.
func validatePolicyMetadata(meta PolicyMetadata) error {
	for _, s := range meta.AffectedSectors {
		if !ValidSectors[s] {
			return fmt.Errorf("unknown sector code %q", s)
		}
	}
	return nil
}

// requireCallerMSP enforces that the transaction caller's MSP ID matches the
// claimed organization (a caller cannot act on behalf of another org).
func requireCallerMSP(ctx contractapi.TransactionContextInterface, claimedOrg string) error {
	callerMSP, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("get caller MSP: %w", err)
	}
	if callerMSP != claimedOrg {
		return fmt.Errorf("caller MSP %q does not match claimed org %q", callerMSP, claimedOrg)
	}
	return nil
}

// deriveReportID deterministically derives a UUID-like report ID from the
// report's identifying fields (spec 5.2).
func deriveReportID(manifestHash, reporterOrg, reportedAt string) string {
	sum := sha256.Sum256([]byte(manifestHash + "|" + reporterOrg + "|" + reportedAt))
	return formatUUIDLike(sum[:])
}

// deriveDecisionID deterministically derives a decision ID from the report_id
// and the computed recipient set (spec 5.4).
func deriveDecisionID(reportID string, recipients []string) string {
	h := sha256.New()
	h.Write([]byte(reportID))
	for _, r := range recipients {
		h.Write([]byte("|"))
		h.Write([]byte(r))
	}
	return formatUUIDLike(h.Sum(nil))
}

// formatUUIDLike formats the first 16 bytes of a digest into 8-4-4-4-12 form.
func formatUUIDLike(b []byte) string {
	hexStr := hex.EncodeToString(b)
	return fmt.Sprintf("%s-%s-%s-%s-%s",
		hexStr[0:8], hexStr[8:12], hexStr[12:16], hexStr[16:20], hexStr[20:32])
}
