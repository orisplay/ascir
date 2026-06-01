// Standalone test of the Fabric Gateway connection: connect, query one
// manifest hash, print the result, disconnect. Proves the gateway wiring
// (identity, TLS override, contract evaluation) before the HTTP layer is
// added. Run with: npm run query -- <manifest_hash>
// Defaults to comp_001's known hash if no argument is given.

import { connectGateway, closeGateway, queryStatus, config } from './fabric.js';

const DEFAULT_HASH =
  'dd6a60da439db0d0e20d318b33ccf762e3cb13ab7379e4f34cf53ca697b4abe8';

async function main() {
  const manifestHash = process.argv[2] || DEFAULT_HASH;
  console.log('Connecting to', config.PEER_ENDPOINT,
    '(as', config.MSP_ID + ', channel', config.CHANNEL + ',',
    'chaincode', config.CHAINCODE + ')');
  const conn = await connectGateway();
  try {
    console.log('Querying status for hash:', manifestHash);
    const status = await queryStatus(conn.contract, manifestHash);
    console.log('Result:');
    console.log(JSON.stringify(status, null, 2));
  } finally {
    closeGateway(conn);
  }
}

main().catch((err) => {
  console.error('ERROR:', err.message || err);
  process.exit(1);
});
