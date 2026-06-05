import React, { useState, useEffect } from 'react';
import { getHealth, checkStatus, registerKnownGood, reportCompromise, routeCompromise } from './api.js';

const SECTORS = ['FIN', 'CI', 'HC', 'GOV'];
const SEVERITIES = ['low', 'medium', 'high', 'critical'];
const SCOPES = ['single_jurisdiction', 'multi_jurisdiction', 'global'];

function Field({ label, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

function Result({ data, error }) {
  if (error) return <pre className="result error">{error}</pre>;
  if (!data) return null;
  return <pre className="result">{JSON.stringify(data, null, 2)}</pre>;
}

function nowISO() {
  return new Date().toISOString();
}

// Call `fn` when Enter is pressed in a field, unless the field is disabled.
function enterKey(fn, enabled = true) {
  return (e) => {
    if (e.key === 'Enter' && enabled) { e.preventDefault(); fn(); }
  };
}

function CheckCard() {
  const [hash, setHash] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError(null); setData(null);
    try { setData(await checkStatus(hash.trim())); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const statusColor = data && {
    known_good: '#1a7f37', unknown: '#9a6700',
    compromised: '#cf222e', contested: '#bc4c00',
  }[data.status];

  return (
    <section className="card">
      <h2>Check Component Status</h2>
      <p className="hint">Query a manifest hash against the on-chain registry.</p>
      <Field label="Manifest hash (64-hex)">
        <input value={hash} onChange={(e) => setHash(e.target.value)}
               onKeyDown={enterKey(run, !busy && !!hash.trim())}
               placeholder="dd6a60da...b4abe8" spellCheck={false} />
      </Field>
      <button onClick={run} disabled={busy || !hash.trim()}>
        {busy ? 'Checking…' : 'Check'}
      </button>
      {data && (
        <div className="status-badge" style={{ background: statusColor }}>
          {data.status}
        </div>
      )}
      <Result data={data} error={error} />
    </section>
  );
}

function RegisterCard({ org }) {
  const [f, setF] = useState({ manifest_hash: '', component_name: '', version: '1.0' });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function run() {
    setBusy(true); setError(null); setData(null);
    try {
      setData(await registerKnownGood({
        ...f, manifest_hash: f.manifest_hash.trim(),
        signer_org: org, signed_at: nowISO(),
      }));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <section className="card">
      <h2>Register Known-Good</h2>
      <p className="hint">Record a trusted component, signed as <b>{org}</b>.</p>
      <Field label="Manifest hash (64-hex)">
        <input value={f.manifest_hash} onChange={set('manifest_hash')} spellCheck={false} />
      </Field>
      <Field label="Component name">
        <input value={f.component_name} onChange={set('component_name')} placeholder="agent-memory-store" />
      </Field>
      <Field label="Version">
        <input value={f.version} onChange={set('version')}
               onKeyDown={enterKey(run, !busy && !!f.manifest_hash.trim() && !!f.component_name)} />
      </Field>
      <button onClick={run} disabled={busy || !f.manifest_hash.trim() || !f.component_name}>
        {busy ? 'Registering…' : 'Register'}
      </button>
      <Result data={data} error={error} />
    </section>
  );
}

function ReportCard({ org }) {
  const [f, setF] = useState({
    manifest_hash: '', component_name: '', evidence_ref: '',
    severity: 'high', distribution_scope: 'single_jurisdiction',
  });
  const [sectors, setSectors] = useState(['CI']);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const toggleSector = (s) =>
    setSectors(sectors.includes(s) ? sectors.filter((x) => x !== s) : [...sectors, s]);

  async function run() {
    setBusy(true); setError(null); setData(null);
    try {
      setData(await reportCompromise({
        manifest_hash: f.manifest_hash.trim(),
        component_name: f.component_name,
        reporter_org: org,
        reported_at: nowISO(),
        evidence_ref: f.evidence_ref || 'evidence://unspecified',
        policy_metadata: {
          affected_sectors: sectors,
          affected_jurisdictions: [],
          distribution_scope: f.distribution_scope,
          severity: f.severity,
        },
      }));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <section className="card">
      <h2>Report Compromise</h2>
      <p className="hint">File a compromise report, as reporter <b>{org}</b>.</p>
      <Field label="Manifest hash (64-hex)">
        <input value={f.manifest_hash} onChange={set('manifest_hash')} spellCheck={false} />
      </Field>
      <Field label="Component name">
        <input value={f.component_name} onChange={set('component_name')} />
      </Field>
      <Field label="Evidence reference">
        <input value={f.evidence_ref} onChange={set('evidence_ref')} placeholder="evidence://case/123" />
      </Field>
      <Field label="Affected sectors">
        <div className="checkbox-row">
          {SECTORS.map((s) => (
            <label key={s} className={`chip ${sectors.includes(s) ? 'on' : ''}`}>
              <input type="checkbox" checked={sectors.includes(s)} onChange={() => toggleSector(s)} />
              {s}
            </label>
          ))}
        </div>
      </Field>
      <div className="row">
        <Field label="Severity">
          <select value={f.severity} onChange={set('severity')}>
            {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="Distribution scope">
          <select value={f.distribution_scope} onChange={set('distribution_scope')}>
            {SCOPES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </Field>
      </div>
      <button onClick={run} disabled={busy || !f.manifest_hash.trim() || !f.component_name || !sectors.length}>
        {busy ? 'Reporting…' : 'Report'}
      </button>
      <Result data={data} error={error} />
    </section>
  );
}

function RouteCard({ org }) {
  const [reportId, setReportId] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError(null); setData(null);
    try { setData(await routeCompromise({ report_id: reportId.trim(), as_org: org })); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <section className="card">
      <h2>Route Compromise</h2>
      <p className="hint">Run the Selective Broadcast Algorithm for a report.</p>
      <Field label="Report ID">
        <input value={reportId} onChange={(e) => setReportId(e.target.value)}
               onKeyDown={enterKey(run, !busy && !!reportId.trim())}
               placeholder="ca694b06-..." spellCheck={false} />
      </Field>
      <button onClick={run} disabled={busy || !reportId.trim()}>
        {busy ? 'Routing…' : 'Route'}
      </button>
      {data && data.authorized_recipients && (
        <div className="route-summary">
          <div><span className="tag recipients">Recipients</span> {data.authorized_recipients.join(', ') || '(none)'}</div>
          <div><span className="tag excluded">Excluded</span> {(data.excluded_jurisdictions || []).join(', ') || '(none)'}</div>
          {data.policy_trace && (
            <table className="trace">
              <thead><tr><th>Rule</th><th>Input</th><th>Added</th></tr></thead>
              <tbody>
                {data.policy_trace.map((t, i) => (
                  <tr key={i}><td>{t.rule}</td><td>{t.input}</td><td>{(t.added || []).join(', ')}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <Result data={data} error={error} />
    </section>
  );
}

export default function App() {
  const [org, setOrg] = useState('Org1MSP');
  const [health, setHealth] = useState(null);

  useEffect(() => { getHealth().then(setHealth).catch(() => setHealth({ status: 'unreachable' })); }, []);
  const orgs = (health && health.fabric && health.fabric.orgs) || ['Org1MSP', 'Org2MSP', 'Org3MSP', 'Org4MSP'];

  return (
    <div className="app">
      <header>
        <h1>ASCIR</h1>
        <p className="subtitle">Agentic Supply-Chain Incident Routing</p>
        <div className="topbar">
          <label className="org-select">
            Acting as&nbsp;
            <select value={org} onChange={(e) => setOrg(e.target.value)}>
              {orgs.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <span className={`health ${health && health.status === 'ok' ? 'ok' : 'bad'}`}>
            {health ? `backend: ${health.status}` : 'connecting…'}
            {health && health.fabric && ` · ${orgs.length} orgs · ${health.fabric.channel}`}
          </span>
        </div>
      </header>
      <main className="grid">
        <CheckCard />
        <RegisterCard org={org} />
        <ReportCard org={org} />
        <RouteCard org={org} />
      </main>
      <footer>ASCIR investigator console · drives the multi-org Fabric backend over its HTTP API</footer>
    </div>
  );
}
