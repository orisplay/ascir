package ascir

import (
	"strings"

	"github.com/hyperledger/fabric-chaincode-go/v2/pkg/cid"
	"github.com/hyperledger/fabric-chaincode-go/v2/shim"
	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
	"github.com/hyperledger/fabric-protos-go-apiv2/ledger/queryresult"
)

// This file provides an in-memory test double for the parts of the Fabric
// transaction context that the ASCIR contract functions use. It is a _test.go
// file, so it is compiled only for tests and never ships in the chaincode.
//
// The composite-key emulation mirrors Fabric's real behavior: keys are formed
// as <sep><objectType><sep><attr><sep>... using U+0000 as the separator, and a
// partial composite query matches every key sharing the partial prefix. This
// fidelity is what makes the QueryCompromiseStatus tests meaningful rather than
// merely passing against a lenient mock.

const minUnicodeRuneValue = '\u0000' // Fabric composite-key separator

// ---------------------------------------------------------------------------
// mockStub: in-memory ChaincodeStubInterface
// ---------------------------------------------------------------------------

type mockStub struct {
	shim.ChaincodeStubInterface // embedded: unimplemented methods panic if called
	state                       map[string][]byte
	txID                        string
}

func newMockStub() *mockStub {
	return &mockStub{state: map[string][]byte{}, txID: "tx-mock-0001"}
}

func (s *mockStub) GetTxID() string { return s.txID }

func (s *mockStub) GetState(key string) ([]byte, error) {
	v, ok := s.state[key]
	if !ok {
		return nil, nil
	}
	return v, nil
}

func (s *mockStub) PutState(key string, value []byte) error {
	// Copy to avoid aliasing the caller's slice.
	b := make([]byte, len(value))
	copy(b, value)
	s.state[key] = b
	return nil
}

func (s *mockStub) DelState(key string) error {
	delete(s.state, key)
	return nil
}

// CreateCompositeKey mirrors Fabric: sep + objectType + sep + attr + sep + ...
func (s *mockStub) CreateCompositeKey(objectType string, attributes []string) (string, error) {
	var b strings.Builder
	b.WriteRune(minUnicodeRuneValue)
	b.WriteString(objectType)
	b.WriteRune(minUnicodeRuneValue)
	for _, a := range attributes {
		b.WriteString(a)
		b.WriteRune(minUnicodeRuneValue)
	}
	return b.String(), nil
}

// SplitCompositeKey mirrors Fabric's inverse of CreateCompositeKey.
func (s *mockStub) SplitCompositeKey(compositeKey string) (string, []string, error) {
	parts := strings.Split(compositeKey, string(minUnicodeRuneValue))
	// parts[0] is "" (leading sep), parts[1] is objectType, then attributes,
	// then a trailing "" from the final sep.
	if len(parts) < 2 {
		return "", nil, nil
	}
	objectType := parts[1]
	attrs := []string{}
	for _, p := range parts[2:] {
		if p != "" {
			attrs = append(attrs, p)
		}
	}
	return objectType, attrs, nil
}

// GetStateByPartialCompositeKey returns all keys whose composite prefix matches
// the given objectType + attributes prefix, mirroring Fabric's range scan.
func (s *mockStub) GetStateByPartialCompositeKey(objectType string, attributes []string) (shim.StateQueryIteratorInterface, error) {
	prefix, _ := s.CreateCompositeKey(objectType, attributes)
	// The partial key ends with a trailing separator; a matching full key
	// shares this prefix. We match on prefix (Fabric scans [prefix, prefix+max)).
	results := []*queryresult.KV{}
	for k, v := range s.state {
		if strings.HasPrefix(k, prefix) {
			results = append(results, &queryresult.KV{Key: k, Value: v})
		}
	}
	return newMockIterator(results), nil
}

// ---------------------------------------------------------------------------
// mockIterator: in-memory StateQueryIteratorInterface
// ---------------------------------------------------------------------------

type mockIterator struct {
	items []*queryresult.KV
	pos   int
}

func newMockIterator(items []*queryresult.KV) *mockIterator {
	return &mockIterator{items: items, pos: 0}
}

func (it *mockIterator) HasNext() bool { return it.pos < len(it.items) }

func (it *mockIterator) Next() (*queryresult.KV, error) {
	kv := it.items[it.pos]
	it.pos++
	return kv, nil
}

func (it *mockIterator) Close() error { return nil }

// ---------------------------------------------------------------------------
// mockClientIdentity: supplies the caller MSP ID
// ---------------------------------------------------------------------------

type mockClientIdentity struct {
	cid.ClientIdentity // embedded interface; only GetMSPID is overridden
	mspID              string
}

func (m *mockClientIdentity) GetMSPID() (string, error) { return m.mspID, nil }

// ---------------------------------------------------------------------------
// mockContext: in-memory TransactionContextInterface
// ---------------------------------------------------------------------------

type mockContext struct {
	contractapi.TransactionContextInterface // embedded: unused methods panic
	stub                                    *mockStub
	clientID                                *mockClientIdentity
}

func newMockContext(callerMSP string) *mockContext {
	return &mockContext{
		stub:     newMockStub(),
		clientID: &mockClientIdentity{mspID: callerMSP},
	}
}

func (c *mockContext) GetStub() shim.ChaincodeStubInterface { return c.stub }

func (c *mockContext) GetClientIdentity() cid.ClientIdentity { return c.clientID }
