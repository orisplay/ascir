// ASCIR backend — Fabric Gateway connection module.
//
// Establishes a gateway connection to peer0.org1 of the test-network using
// the User1 identity, and exposes helpers to query the ASCIR chaincode.
// The crypto-material paths below point into the stock test-network tree and
// are testbed-specific; a real deployment would provision a dedicated service
// identity and read these from configuration. Uses the official
// @hyperledger/fabric-gateway SDK (supported path for Fabric 2.4+).

import * as grpc from '@grpc/grpc-js';
import { connect, hash, signers } from '@hyperledger/fabric-gateway';
import * as crypto from 'node:crypto';
import { promises as fs } from 'node:fs';
import { TextDecoder } from 'node:util';
import path from 'node:path';

const utf8Decoder = new TextDecoder();

// --- Testbed configuration (override via environment if desired) ----------
const TEST_NETWORK =
  process.env.ASCIR_TEST_NETWORK ||
  path.join(process.env.HOME, 'research/fabric-samples/test-network');

const MSP_ID = process.env.ASCIR_MSP_ID || 'Org1MSP';
const CHANNEL = process.env.ASCIR_CHANNEL || 'mychannel';
const CHAINCODE = process.env.ASCIR_CHAINCODE || 'ascir';

// Peer endpoint and the hostname its TLS certificate is issued for. We connect
// to localhost but the cert names peer0.org1.example.com, so gRPC needs the
// ssl-target-name-override channel option or it rejects the certificate.
const PEER_ENDPOINT = process.env.ASCIR_PEER_ENDPOINT || 'localhost:7051';
const PEER_HOST_ALIAS = process.env.ASCIR_PEER_HOST || 'peer0.org1.example.com';

const ORG1 = path.join(
  TEST_NETWORK, 'organizations/peerOrganizations/org1.example.com');
const CERT_PATH = path.join(
  ORG1, 'users/User1@org1.example.com/msp/signcerts/User1@org1.example.com-cert.pem');
const KEY_DIR = path.join(
  ORG1, 'users/User1@org1.example.com/msp/keystore');
const TLS_CERT_PATH = path.join(
  ORG1, 'peers/peer0.org1.example.com/tls/ca.crt');

// --- gRPC client -----------------------------------------------------------
async function newGrpcConnection() {
  const tlsRootCert = await fs.readFile(TLS_CERT_PATH);
  const tlsCredentials = grpc.credentials.createSsl(tlsRootCert);
  return new grpc.Client(PEER_ENDPOINT, tlsCredentials, {
    'grpc.ssl_target_name_override': PEER_HOST_ALIAS,
  });
}

async function newIdentity() {
  const credentials = await fs.readFile(CERT_PATH);
  return { mspId: MSP_ID, credentials };
}

async function newSigner() {
  // The keystore dir contains a single private-key file (priv_sk).
  const files = await fs.readdir(KEY_DIR);
  const keyPath = path.join(KEY_DIR, files[0]);
  const privateKeyPem = await fs.readFile(keyPath);
  const privateKey = crypto.createPrivateKey(privateKeyPem);
  return signers.newPrivateKeySigner(privateKey);
}

// --- Public API ------------------------------------------------------------

// connectGateway returns { gateway, client, contract }. Caller must close the
// gateway and client when done (see closeGateway).
export async function connectGateway() {
  const client = await newGrpcConnection();
  const gateway = connect({
    client,
    identity: await newIdentity(),
    signer: await newSigner(),
    hash: hash.sha256,
    evaluateOptions: () => ({ deadline: Date.now() + 5000 }),
    endorseOptions: () => ({ deadline: Date.now() + 15000 }),
    submitOptions: () => ({ deadline: Date.now() + 5000 }),
    commitStatusOptions: () => ({ deadline: Date.now() + 60000 }),
  });
  const network = gateway.getNetwork(CHANNEL);
  const contract = network.getContract(CHAINCODE);
  return { gateway, client, contract };
}

export function closeGateway({ gateway, client }) {
  gateway.close();
  client.close();
}

// queryStatus evaluates QueryCompromiseStatus for a manifest hash and returns
// the parsed StatusResponse object.
export async function queryStatus(contract, manifestHash) {
  const resultBytes = await contract.evaluateTransaction(
    'QueryCompromiseStatus', manifestHash);
  const resultJson = utf8Decoder.decode(resultBytes);
  return JSON.parse(resultJson);
}

export const config = {
  TEST_NETWORK, MSP_ID, CHANNEL, CHAINCODE, PEER_ENDPOINT, PEER_HOST_ALIAS,
};
