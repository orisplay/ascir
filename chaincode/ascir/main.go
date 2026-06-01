package main

import (
	"log"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

// main is the chaincode entrypoint. It bundles the ASCIRContract into a
// contractapi chaincode and starts it, so the four interface functions
// (RegisterKnownGood, ReportCompromise, QueryCompromiseStatus,
// RouteCompromise) are callable as chaincode transactions on the peer.
func main() {
	chaincode, err := contractapi.NewChaincode(&ASCIRContract{})
	if err != nil {
		log.Panicf("error creating ASCIR chaincode: %v", err)
	}
	if err := chaincode.Start(); err != nil {
		log.Panicf("error starting ASCIR chaincode: %v", err)
	}
}
