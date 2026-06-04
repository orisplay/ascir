// ASCIR backend HTTP server (multi-organization).
//
// Exposes an HTTP API over per-organization Fabric Gateway connections so that
// clients can drive the ASCIR chaincode without speaking Fabric directly.
// Read operations (/check) use any connected org's gateway; write operations
// (/register, /report, /route) are submitted under the MSP the chaincode
// requires of the caller, selected from the request body.
//
// Endpoints:
//   GET  /health
//   POST /check    {manifest_hash}
//   POST /register {manifest_hash, component_name, version, signer_org, signed_at}
//   POST /report   {manifest_hash, component_name, reporter_org, reported_at,
//                   evidence_ref, policy_metadata}
//   POST /route    {report_id, as_org?}
//
// Run with: npm start  (requires the Fabric network up and chaincode deployed).

import express from 'express';
import {
  connectAll, closeAll, connFor, queryStatus,
  registerKnownGood, reportCompromise, routeCompromise, config,
} from './fabric.js';

const PORT = process.env.ASCIR_BACKEND_PORT || 3000;
const HEX64 = /^[0-9a-f]{64}$/;

const app = express();
app.use(express.json());

let conns = null;

function anyContract() {
  const first = conns && conns.values().next().value;
  return first ? first.contract : null;
}

function msg(err) { return (err && err.message) ? err.message : String(err); }

app.get('/health', (req, res) => {
  res.json({
    status: conns ? 'ok' : 'starting',
    fabric: {
      channel: config.CHANNEL,
      chaincode: config.CHAINCODE,
      orgs: conns ? [...conns.keys()] : config.orgs,
    },
  });
});

app.post('/check', async (req, res) => {
  const manifestHash = req.body && req.body.manifest_hash;
  if (typeof manifestHash !== 'string' || !HEX64.test(manifestHash)) {
    return res.status(400).json({
      error: 'manifest_hash must be a 64-character lowercase hex string',
    });
  }
  const contract = anyContract();
  if (!contract) return res.status(503).json({ error: 'no gateway connected yet' });
  try {
    return res.json(await queryStatus(contract, manifestHash));
  } catch (err) {
    return res.status(502).json({ error: 'chaincode query failed', detail: msg(err) });
  }
});

app.post('/register', async (req, res) => {
  const b = req.body || {};
  const required = ['manifest_hash', 'component_name', 'version', 'signer_org', 'signed_at'];
  const missing = required.filter((k) => typeof b[k] !== 'string' || !b[k]);
  if (missing.length) return res.status(400).json({ error: `missing/invalid: ${missing.join(', ')}` });
  if (!HEX64.test(b.manifest_hash)) return res.status(400).json({ error: 'manifest_hash must be 64-hex' });

  let conn;
  try { conn = connFor(conns, b.signer_org); }
  catch (e) { return res.status(400).json({ error: msg(e) }); }
  try {
    const result = await registerKnownGood(conn.contract, {
      manifestHash: b.manifest_hash, componentName: b.component_name,
      version: b.version, signerOrg: b.signer_org, signedAt: b.signed_at,
    });
    return res.json(result);
  } catch (err) {
    return res.status(502).json({ error: 'RegisterKnownGood failed', detail: msg(err) });
  }
});

app.post('/report', async (req, res) => {
  const b = req.body || {};
  const required = ['manifest_hash', 'component_name', 'reporter_org', 'reported_at', 'evidence_ref'];
  const missing = required.filter((k) => typeof b[k] !== 'string' || !b[k]);
  if (missing.length) return res.status(400).json({ error: `missing/invalid: ${missing.join(', ')}` });
  if (!HEX64.test(b.manifest_hash)) return res.status(400).json({ error: 'manifest_hash must be 64-hex' });
  if (typeof b.policy_metadata !== 'object' || b.policy_metadata === null) {
    return res.status(400).json({ error: 'policy_metadata must be an object' });
  }

  let conn;
  try { conn = connFor(conns, b.reporter_org); }
  catch (e) { return res.status(400).json({ error: msg(e) }); }
  try {
    const result = await reportCompromise(conn.contract, {
      manifestHash: b.manifest_hash, componentName: b.component_name,
      reporterOrg: b.reporter_org, reportedAt: b.reported_at,
      evidenceRef: b.evidence_ref, policyMetadata: b.policy_metadata,
    });
    return res.json(result);
  } catch (err) {
    return res.status(502).json({ error: 'ReportCompromise failed', detail: msg(err) });
  }
});

app.post('/route', async (req, res) => {
  const b = req.body || {};
  if (typeof b.report_id !== 'string' || !b.report_id) {
    return res.status(400).json({ error: 'report_id is required' });
  }
  const asOrg = (typeof b.as_org === 'string' && b.as_org) ? b.as_org : [...conns.keys()][0];
  let conn;
  try { conn = connFor(conns, asOrg); }
  catch (e) { return res.status(400).json({ error: msg(e) }); }
  // The scoped SBA needs the set of jurisdictions present on the channel.
  // Default to the orgs the backend is connected to; allow an explicit override
  // via known_jurisdictions in the request body.
  const known = Array.isArray(b.known_jurisdictions) && b.known_jurisdictions.length
    ? b.known_jurisdictions
    : [...conns.keys()];
  try {
    return res.json(await routeCompromise(conn.contract, b.report_id, known));
  } catch (err) {
    return res.status(502).json({ error: 'RouteCompromise failed', detail: msg(err) });
  }
});

async function start() {
  conns = await connectAll();
  const server = app.listen(PORT, () => {
    console.log(`ASCIR backend listening on http://localhost:${PORT}`);
    console.log(`  channel ${config.CHANNEL}, chaincode ${config.CHAINCODE}`);
    console.log(`  connected orgs: ${[...conns.keys()].join(', ')}`);
  });
  const shutdown = () => {
    console.log('\nShutting down...');
    server.close(() => { if (conns) closeAll(conns); process.exit(0); });
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

start().catch((err) => {
  console.error('Failed to start backend:', msg(err));
  process.exit(1);
});
