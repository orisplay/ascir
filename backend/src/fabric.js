// ASCIR backend — Fabric Gateway connection module (multi-organization).
//
// Establishes gateway connections to one or more organizations' peers using
// each org's User1 identity, and exposes helpers to query and submit to the
// ASCIR chaincode. Multiple identities are supported so that write operations
// (RegisterKnownGood, ReportCompromise) can be submitted under the MSP the
// chaincode requires of the caller (requireCallerMSP). The crypto-material
// paths point into the stock test-network tree and are testbed-specific; a
// real deployment would provision dedicated service identities from config.
// Uses the official @hyperledger/fabric-gateway SDK (Fabric 2.4+).

import * as grpc from '@grpc/grpc-js';
import { connect, hash, signers } from '@hyperledger/fabric-gateway';
import * as crypto from 'node:crypto';
import { promises as fs } from 'node:fs';
import { TextDecoder } from 'node:util';
import path from 'node:path';

const utf8Decoder = new TextDecoder();

const TEST_NETWORK =
  process.env.ASCIR_TEST_NETWORK ||
  path.join(process.env.HOME, 'research/fabric-samples/test-network');

const CHANNEL = process.env.ASCIR_CHANNEL || 'mychannel';
const CHAINCODE = process.env.ASCIR_CHAINCODE || 'ascir';

// Per-organization profile. test-network peer0 ports: Org1 7051, Org2 9051,
// Org3 11051, Org4 13051. TLS certs name peer0.orgN.example.com, so gRPC needs
// ssl-target-name-override since we dial localhost.
const ORG_PROFILES = {
  Org1MSP: { num: 1, port: 7051 },
  Org2MSP: { num: 2, port: 9051 },
  Org3MSP: { num: 3, port: 11051 },
  Org4MSP: { num: 4, port: 13051 },
};

function orgPaths(mspId) {
  const p = ORG_PROFILES[mspId];
  if (!p) throw new Error(`unknown MSP: ${mspId}`);
  const domain = `org${p.num}.example.com`;
  const base = path.join(TEST_NETWORK, 'organizations/peerOrganizations', domain);
  return {
    mspId,
    peerEndpoint: `localhost:${p.port}`,
    peerHostAlias: `peer0.${domain}`,
    certPath: path.join(base,
      `users/User1@${domain}/msp/signcerts/cert.pem`),
    keyDir: path.join(base, `users/User1@${domain}/msp/keystore`),
    tlsCertPath: path.join(base, `peers/peer0.${domain}/tls/ca.crt`),
  };
}

function configuredOrgs() {
  const env = process.env.ASCIR_ORGS;
  if (env) return env.split(',').map((s) => s.trim()).filter(Boolean);
  return Object.keys(ORG_PROFILES);
}

async function newGrpcConnection(cfg) {
  const tlsRootCert = await fs.readFile(cfg.tlsCertPath);
  const tlsCredentials = grpc.credentials.createSsl(tlsRootCert);
  return new grpc.Client(cfg.peerEndpoint, tlsCredentials, {
    'grpc.ssl_target_name_override': cfg.peerHostAlias,
  });
}

async function newIdentity(cfg) {
  const credentials = await fs.readFile(cfg.certPath);
  return { mspId: cfg.mspId, credentials };
}

async function newSigner(cfg) {
  const files = await fs.readdir(cfg.keyDir);
  const keyPath = path.join(cfg.keyDir, files[0]);
  const privateKeyPem = await fs.readFile(keyPath);
  const privateKey = crypto.createPrivateKey(privateKeyPem);
  return signers.newPrivateKeySigner(privateKey);
}

async function connectOrg(mspId) {
  const cfg = orgPaths(mspId);
  const client = await newGrpcConnection(cfg);
  const gateway = connect({
    client,
    identity: await newIdentity(cfg),
    signer: await newSigner(cfg),
    hash: hash.sha256,
    evaluateOptions: () => ({ deadline: Date.now() + 5000 }),
    endorseOptions: () => ({ deadline: Date.now() + 15000 }),
    submitOptions: () => ({ deadline: Date.now() + 5000 }),
    commitStatusOptions: () => ({ deadline: Date.now() + 60000 }),
  });
  const network = gateway.getNetwork(CHANNEL);
  const contract = network.getContract(CHAINCODE);
  return { mspId, gateway, client, contract };
}

// connectAll opens a gateway per configured org. Returns Map mspId -> conn.
export async function connectAll() {
  const orgs = configuredOrgs();
  const conns = new Map();
  for (const mspId of orgs) {
    conns.set(mspId, await connectOrg(mspId));
  }
  return conns;
}

export function closeAll(conns) {
  for (const { gateway, client } of conns.values()) {
    try { gateway.close(); client.close(); } catch (_) { /* ignore */ }
  }
}

export function connFor(conns, mspId) {
  const c = conns.get(mspId);
  if (!c) throw new Error(
    `no gateway connected for ${mspId} (configured: ${[...conns.keys()].join(', ')})`);
  return c;
}

export async function queryStatus(contract, manifestHash) {
  const resultBytes = await contract.evaluateTransaction(
    'QueryCompromiseStatus', manifestHash);
  return JSON.parse(utf8Decoder.decode(resultBytes));
}

export async function registerKnownGood(contract, args) {
  const { manifestHash, componentName, version, signerOrg, signedAt } = args;
  const resultBytes = await contract.submitTransaction(
    'RegisterKnownGood', manifestHash, componentName, version, signerOrg, signedAt);
  return JSON.parse(utf8Decoder.decode(resultBytes));
}

export async function reportCompromise(contract, args) {
  const { manifestHash, componentName, reporterOrg, reportedAt,
          evidenceRef, policyMetadata } = args;
  const resultBytes = await contract.submitTransaction(
    'ReportCompromise', manifestHash, componentName, reporterOrg, reportedAt,
    evidenceRef, JSON.stringify(policyMetadata));
  return JSON.parse(utf8Decoder.decode(resultBytes));
}

export async function routeCompromise(contract, reportId, knownJurisdictions) {
  // RouteCompromise(reportID string, knownJurisdictions []string). The slice
  // argument is passed as a JSON-encoded string, matching how the contract API
  // unmarshals []string parameters.
  const resultBytes = await contract.submitTransaction(
    'RouteCompromise', reportId, JSON.stringify(knownJurisdictions));
  return JSON.parse(utf8Decoder.decode(resultBytes));
}

export const config = {
  TEST_NETWORK, CHANNEL, CHAINCODE, orgs: configuredOrgs(),
};
