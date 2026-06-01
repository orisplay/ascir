// ASCIR backend HTTP server.
//
// Exposes a small HTTP API over the Fabric Gateway connection so that clients
// (e.g. the detector) can query the ASCIR registry without speaking Fabric
// directly. The gateway connection is opened once at startup and reused across
// requests (gateway connections are designed to be long-lived).
//
// Endpoints:
//   GET  /health           -> { status: "ok", fabric: {...config} }
//   POST /check {manifest_hash} -> the chaincode StatusResponse JSON
//
// Run with: npm start   (requires the Fabric network up and the chaincode
// deployed; see network/README.md).

import express from 'express';
import { connectGateway, closeGateway, queryStatus, config } from './fabric.js';

const PORT = process.env.ASCIR_BACKEND_PORT || 3000;
const HEX64 = /^[0-9a-f]{64}$/;

const app = express();
app.use(express.json());

// Opened at startup, reused across requests, closed on shutdown.
let conn = null;

app.get('/health', (req, res) => {
  res.json({
    status: conn ? 'ok' : 'starting',
    fabric: {
      mspId: config.MSP_ID,
      channel: config.CHANNEL,
      chaincode: config.CHAINCODE,
      peer: config.PEER_ENDPOINT,
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
  if (!conn) {
    return res.status(503).json({ error: 'gateway not connected yet' });
  }
  try {
    const status = await queryStatus(conn.contract, manifestHash);
    return res.json(status);
  } catch (err) {
    return res.status(502).json({
      error: 'chaincode query failed',
      detail: err.message || String(err),
    });
  }
});

async function start() {
  conn = await connectGateway();
  const server = app.listen(PORT, () => {
    console.log(`ASCIR backend listening on http://localhost:${PORT}`);
    console.log(`  fabric: ${config.MSP_ID} @ ${config.PEER_ENDPOINT}, `
      + `channel ${config.CHANNEL}, chaincode ${config.CHAINCODE}`);
  });

  const shutdown = () => {
    console.log('\nShutting down...');
    server.close(() => {
      if (conn) closeGateway(conn);
      process.exit(0);
    });
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

start().catch((err) => {
  console.error('Failed to start backend:', err.message || err);
  process.exit(1);
});
