// Package ascir implements the chaincode for Agentic Supply-Chain
// Incident Routing. This file defines the data model: the record types
// stored on the ledger and the controlled vocabularies they use.
//
// model.go and policy.go deliberately import nothing outside the Go
// standard library, so the core logic compiles and is unit-testable
// without a running Fabric network. The Fabric-facing contract
// functions live in contract.go (added in a later stage).
package main

// ---------------------------------------------------------------------------
// Controlled vocabularies (chaincode-interface.md Sections 4.3, 4.4)
// ---------------------------------------------------------------------------

// Sector codes. GOV is the default/fallback sector.
const (
	SectorFIN = "FIN" // Financial services
	SectorCI  = "CI"  // Critical infrastructure
	SectorHC  = "HC"  // Healthcare
	SectorGOV = "GOV" // General government / default
)

// ValidSectors is the set of recognized sector codes. A sector code not
// in this set is treated as GOV by the policy logic.
var ValidSectors = map[string]bool{
	SectorFIN: true,
	SectorCI:  true,
	SectorHC:  true,
	SectorGOV: true,
}

// MSP IDs for the four-organization testbed topology.
const (
	Org1MSP = "Org1MSP" // financial-sector CERT
	Org2MSP = "Org2MSP" // critical-infrastructure CERT
	Org3MSP = "Org3MSP" // healthcare-sector CERT
	Org4MSP = "Org4MSP" // general national CERT
)

// PrimaryJurisdiction maps each sector code to the MSP ID of the CERT
// responsible for it by default. This is policy configuration, not data
// model, but it lives here as a constant the policy logic consults.
var PrimaryJurisdiction = map[string]string{
	SectorFIN: Org1MSP,
	SectorCI:  Org2MSP,
	SectorHC:  Org3MSP,
	SectorGOV: Org4MSP,
}

// Distribution-scope values.
const (
	ScopeSingle = "single_jurisdiction"
	ScopeMulti  = "multi_jurisdiction"
	ScopeGlobal = "global"
)

// Severity values.
const (
	SeverityLow      = "low"
	SeverityMedium   = "medium"
	SeverityHigh     = "high"
	SeverityCritical = "critical"
)

// JurisdictionsAll is the literal value affected_jurisdictions may take
// to mean "every known jurisdiction on the channel".
const JurisdictionsAll = "ALL"

// ---------------------------------------------------------------------------
// Policy metadata (chaincode-interface.md Section 5.2, 6.3)
// ---------------------------------------------------------------------------

// PolicyMetadata is the structured routing metadata attached to a
// compromise report. AffectedJurisdictions is modeled as []string; the
// literal "ALL" is represented as a single-element slice {"ALL"} at this
// layer and interpreted by the policy logic. (The wire form may be either
// an array or the bare string "ALL"; the contract layer normalizes it.)
type PolicyMetadata struct {
	AffectedSectors       []string `json:"affected_sectors"`
	AffectedJurisdictions []string `json:"affected_jurisdictions"`
	DistributionScope     string   `json:"distribution_scope"`
	Severity              string   `json:"severity"`
}

// ---------------------------------------------------------------------------
// Ledger record types (chaincode-interface.md Section 4.1)
// ---------------------------------------------------------------------------

// KnownGoodEntry records a manifest hash as a verified legitimate
// component. Stored under key KG~<manifest_hash>.
type KnownGoodEntry struct {
	ManifestHash  string `json:"manifest_hash"`
	ComponentName string `json:"component_name"`
	Version       string `json:"version"`
	SignerOrg     string `json:"signer_org"`
	SignedAt      string `json:"signed_at"` // RFC3339
}

// CompromiseReport declares a manifest hash as a known compromise.
// Stored under key CR~<manifest_hash>~<report_id>.
type CompromiseReport struct {
	ManifestHash   string         `json:"manifest_hash"`
	ComponentName  string         `json:"component_name"`
	ReporterOrg    string         `json:"reporter_org"`
	ReportedAt     string         `json:"reported_at"` // RFC3339
	EvidenceRef    string         `json:"evidence_ref"`
	PolicyMetadata PolicyMetadata `json:"policy_metadata"`
	ReportID       string         `json:"report_id"`
}

// RetractionRecord marks a prior compromise report as withdrawn.
// Stored under key RT~<report_id>. It does not delete the original CR
// record; QueryCompromiseStatus treats a CR as inactive when a matching
// RT exists.
type RetractionRecord struct {
	ReportID    string `json:"report_id"`
	RetractedBy string `json:"retracted_by"` // MSP ID of original reporter
	RetractedAt string `json:"retracted_at"` // RFC3339
	Reason      string `json:"reason"`
}

// TraceEntry is one step of an SBA policy evaluation. Each entry names the
// rule that fired, the input that triggered it, and the jurisdictions it
// added or removed. An entry sets either Added or Removed, never both;
// the empty one is omitted from JSON.
type TraceEntry struct {
	Rule    string   `json:"rule"`
	Input   string   `json:"input"`
	Added   []string `json:"added,omitempty" metadata:",optional"`
	Removed []string `json:"removed,omitempty" metadata:",optional"`
}

// RoutingDecision is the audit record produced by RouteCompromise.
// Stored under key RD~<report_id>~<decision_id>.
type RoutingDecision struct {
	ReportID              string       `json:"report_id"`
	DecisionID            string       `json:"decision_id"`
	AuthorizedRecipients  []string     `json:"authorized_recipients"`
	ExcludedJurisdictions []string     `json:"excluded_jurisdictions"`
	PolicyTrace           []TraceEntry `json:"policy_trace"`
}

// ReportSummary is a compromise report annotated with its retraction status,
// returned by ListReports so callers can browse all reports without a per-hash
// query.
type ReportSummary struct {
	Report    CompromiseReport `json:"report"`
	Retracted bool             `json:"retracted"`
}

// ---------------------------------------------------------------------------
// Composite-key object types (see DECISIONS.md D2)
// ---------------------------------------------------------------------------

// Object-type prefixes for Fabric composite keys. The interface spec's tilde
// notation (KG~, CR~, RT~, RD~) denotes logical key structure; on the ledger
// these are the objectType argument to CreateCompositeKey. ObjIndex backs the
// report_id -> manifest_hash secondary index used by RouteCompromise.
const (
	ObjKnownGood = "KG"  // KG~<manifest_hash>
	ObjReport    = "CR"  // CR~<manifest_hash>~<report_id>
	ObjRetract   = "RT"  // RT~<report_id>
	ObjDecision  = "RD"  // RD~<report_id>~<decision_id>
	ObjIndex     = "IDX" // IDX~<report_id>  (value: manifest_hash)
)
