// m4_staged.js — staged latency harness (endorsement vs commit).
// Times ReportCompromise through the fabric-gateway SDK's phase boundaries,
// separating endorsement latency from commit latency. Each trial uses a unique
// synthetic manifest hash so every submit is a fresh write.
// Usage (from repo root, network up, chaincode deployed):
//   ASCIR_ORGS="Org1MSP,Org2MSP,Org3MSP,Org4MSP" node experiments/m4_staged.js --n 4 --trials 30 --out experiments/results/m4_staged_n4.json
import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { connectAll, closeAll, submitTimedReport } from '../backend/src/fabric.js';

function arg(flag, def) {
  const i = process.argv.indexOf(flag);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : def;
}
const N      = parseInt(arg('--n', '4'), 10);
const TRIALS = parseInt(arg('--trials', '30'), 10);
const WARMUP = parseInt(arg('--warmup', '5'), 10);
const OUT    = arg('--out', `experiments/results/m4_staged_n${N}.json`);

function synthHash(i) {
  return createHash('sha256').update(`m4-staged-trial-${i}-${Date.now()}`).digest('hex');
}
function pct(sorted, p) {
  if (!sorted.length) return null;
  const k = Math.round((p / 100) * (sorted.length - 1));
  return Math.round(sorted[k] * 100) / 100;
}
function summarize(vals) {
  const s = [...vals].sort((a, b) => a - b);
  return { median_ms: pct(s, 50), p95_ms: pct(s, 95),
           min_ms: Math.round(s[0]*100)/100, max_ms: Math.round(s[s.length-1]*100)/100 };
}

async function main() {
  const conns = await connectAll();
  const reporter = 'Org1MSP';
  const conn = conns.get(reporter);
  if (!conn) throw new Error(`no gateway for ${reporter}; set ASCIR_ORGS to include it`);

  const policyMetadata = {
    affected_sectors: ['CI'], affected_jurisdictions: [],
    distribution_scope: 'single_jurisdiction', severity: 'critical',
  };
  const mkArgs = (i) => ({
    manifestHash: synthHash(i),
    componentName: 'agent-ci-controller',
    reporterOrg: reporter,
    reportedAt: new Date().toISOString(),
    evidenceRef: `evidence://m4-staged/${i}`,
    policyMetadata,
  });

  console.log(`M4 staged: n=${N}, warmup=${WARMUP}, trials=${TRIALS}, reporter=${reporter}`);
  for (let i = 0; i < WARMUP; i++) {
    await submitTimedReport(conn.contract, mkArgs(`w${i}`));
    process.stdout.write('.');
  }
  console.log(' warmup done');

  const endorse = [], commit = [], total = [];
  for (let i = 0; i < TRIALS; i++) {
    const r = await submitTimedReport(conn.contract, mkArgs(i));
    endorse.push(r.endorse_ms); commit.push(r.commit_ms); total.push(r.total_ms);
    process.stdout.write(`\r  trial ${i + 1}/${TRIALS}  (endorse ${r.endorse_ms.toFixed(1)}ms, commit ${r.commit_ms.toFixed(1)}ms)   `);
  }
  console.log('\n');

  const out = {
    metric: 'M4_staged', n: N, endorser_count: Math.floor(N / 2) + 1,
    reporter_org: reporter, trials: TRIALS, warmup: WARMUP,
    fabric_version: '2.5.15', timestamp: new Date().toISOString(),
    stages: { endorsement: summarize(endorse), commit: summarize(commit), total: summarize(total) },
    raw: { endorse_ms: endorse.map(x=>Math.round(x*100)/100),
           commit_ms:  commit.map(x=>Math.round(x*100)/100),
           total_ms:   total.map(x=>Math.round(x*100)/100) },
  };
  writeFileSync(OUT, JSON.stringify(out, null, 2) + '\n');
  console.log(`endorsement  median ${out.stages.endorsement.median_ms}ms  p95 ${out.stages.endorsement.p95_ms}ms`);
  console.log(`commit       median ${out.stages.commit.median_ms}ms  p95 ${out.stages.commit.p95_ms}ms`);
  console.log(`total        median ${out.stages.total.median_ms}ms  p95 ${out.stages.total.p95_ms}ms`);
  console.log(`wrote ${OUT}`);
  closeAll(conns);
}
main().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
