import React, { useState, useEffect } from 'react';
import { getHealth, getKnownGood, getReports, checkStatus, registerKnownGood, reportCompromise, routeCompromise } from './api.js';

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

// A prominent banner interpreting a write result's status, so duplicate
// handling is visible rather than buried in the JSON.
function WriteBanner({ data }) {
  if (!data || !data.status) return null;
  const map = {
    registered:    { cls: 'ok',   text: '✓ Registered on the ledger' },
    already_exists:{ cls: 'warn', text: '⚠ Already registered — existing entry left unchanged' },
    reported:      { cls: 'ok',   text: '✓ Compromise report recorded' },
    routed:        { cls: 'ok',   text: '✓ Routed' },
  };
  const m = map[data.status] || { cls: 'warn', text: data.status };
  return <div className={`write-banner ${m.cls}`}>{m.text}{data.report_id ? ` · report ${data.report_id.slice(0,13)}…` : ''}</div>;
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

function CheckCard({ presetHash, onConsumePreset }) {
  const [hash, setHash] = useState('');
  useEffect(() => { if (presetHash) { setHash(presetHash); onConsumePreset && onConsumePreset(); } }, [presetHash]);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError(null); setData(null);
    try { const d = await checkStatus(hash.trim()); setData(d); setHash(''); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const statusColor = data && {
    known_good: '#1a7f37', unknown: '#9a6700',
    compromised: '#cf222e', contested: '#bc4c00',
  }[data.status];

  return (
    <section className="card" id="card-check">
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

function RegisterCard({ org, onWrote }) {
  const [f, setF] = useState({ manifest_hash: '', component_name: '', version: '1.0' });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function run() {
    setBusy(true); setError(null); setData(null);
    try {
      const d = await registerKnownGood({
        ...f, manifest_hash: f.manifest_hash.trim(),
        signer_org: org, signed_at: nowISO(),
      });
      setData(d);
      if (d && d.status === 'registered') { setF({ manifest_hash: '', component_name: '', version: '1.0' }); onWrote && onWrote(); }
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <section className="card">
      <h2>Register Known-Good</h2>
      <p className="hint">Record a trusted component, signed as <b>{org}</b>.</p>
      <Field label="Manifest hash (64-hex)">
        <input value={f.manifest_hash} onChange={set('manifest_hash')} onKeyDown={enterKey(run, !busy && !!f.manifest_hash.trim() && !!f.component_name)} spellCheck={false} />
      </Field>
      <Field label="Component name">
        <input value={f.component_name} onChange={set('component_name')} onKeyDown={enterKey(run, !busy && !!f.manifest_hash.trim() && !!f.component_name)} placeholder="agent-memory-store" />
      </Field>
      <Field label="Version">
        <input value={f.version} onChange={set('version')} onKeyDown={enterKey(run, !busy && !!f.manifest_hash.trim() && !!f.component_name)} />
      </Field>
      <button onClick={run} disabled={busy || !f.manifest_hash.trim() || !f.component_name}>
        {busy ? 'Registering…' : 'Register'}
      </button>
      <WriteBanner data={data} />
      <Result data={data} error={error} />
    </section>
  );
}

function ReportCard({ org, onWrote }) {
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
      const d = await reportCompromise({
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
      });
      setData(d);
      if (d && d.status === 'reported') {
        setF({ manifest_hash: '', component_name: '', evidence_ref: '', severity: 'high', distribution_scope: 'single_jurisdiction' });
        setSectors(['CI']);
        onWrote && onWrote();
      }
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <section className="card">
      <h2>Report Compromise</h2>
      <p className="hint">File a compromise report, as reporter <b>{org}</b>.</p>
      <Field label="Manifest hash (64-hex)">
        <input value={f.manifest_hash} onChange={set('manifest_hash')} onKeyDown={enterKey(run, !busy && !!f.manifest_hash.trim() && !!f.component_name && !!sectors.length)} spellCheck={false} />
      </Field>
      <Field label="Component name">
        <input value={f.component_name} onChange={set('component_name')} onKeyDown={enterKey(run, !busy && !!f.manifest_hash.trim() && !!f.component_name && !!sectors.length)} />
      </Field>
      <Field label="Evidence reference">
        <input value={f.evidence_ref} onChange={set('evidence_ref')} onKeyDown={enterKey(run, !busy && !!f.manifest_hash.trim() && !!f.component_name && !!sectors.length)} placeholder="evidence://case/123" />
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
      <WriteBanner data={data} />
      <Result data={data} error={error} />
    </section>
  );
}

function RouteCard({ org, presetReportId, onConsumePreset, onWrote }) {
  const [reportId, setReportId] = useState('');
  useEffect(() => { if (presetReportId) { setReportId(presetReportId); onConsumePreset && onConsumePreset(); } }, [presetReportId]);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError(null); setData(null);
    try { const d = await routeCompromise({ report_id: reportId.trim(), as_org: org }); setData(d); setReportId(''); onWrote && onWrote(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <section className="card" id="card-route">
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

function BrowseCard({ refreshKey, onPickHash, onPickReport }) {
  const [kg, setKg] = useState([]);
  const [reports, setReports] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true); setError(null);
    try {
      const [k, r] = await Promise.all([getKnownGood(), getReports()]);
      setKg(Array.isArray(k) ? k : []);
      setReports(Array.isArray(r) ? r : []);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  useEffect(() => { load(); }, [refreshKey]);

  return (
    <section className="card browse">
      <h2>Registry Browser</h2>
      <p className="hint">Everything currently on the ledger. Click a hash to load it into Check, or a report ID into Route.</p>
      <button onClick={load} disabled={busy}>{busy ? 'Loading…' : 'Refresh'}</button>
      {error && <pre className="result error">{error}</pre>}

      <h3>Known-Good Components ({kg.length})</h3>
      {kg.length === 0 ? <p className="empty">none registered</p> : (
        <table className="trace">
          <thead><tr><th>Component</th><th>Ver</th><th>Signer</th><th>Hash</th></tr></thead>
          <tbody>
            {kg.map((e) => (
              <tr key={e.manifest_hash}>
                <td>{e.component_name}</td><td>{e.version}</td><td>{e.signer_org}</td>
                <td><code className="clickable" title="use in Check" onClick={() => onPickHash(e.manifest_hash)}>{e.manifest_hash.slice(0, 12)}…</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Compromise Reports ({reports.length})</h3>
      {reports.length === 0 ? <p className="empty">none filed</p> : (
        <table className="trace">
          <thead><tr><th>Component</th><th>Sectors</th><th>Sev</th><th>Report ID</th></tr></thead>
          <tbody>
            {reports.map((rs) => (
              <tr key={rs.report.report_id} className={rs.retracted ? 'retracted' : ''}>
                <td>{rs.report.component_name}</td>
                <td>{(rs.report.policy_metadata.affected_sectors || []).join(', ')}</td>
                <td>{rs.report.policy_metadata.severity}</td>
                <td><code className="clickable" title="use in Route" onClick={() => onPickReport(rs.report.report_id)}>{rs.report.report_id.slice(0, 13)}…</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export default function App() {
  const [org, setOrg] = useState('Org1MSP');
  const [health, setHealth] = useState(null);
  const [presetHash, setPresetHash] = useState('');
  const [presetReportId, setPresetReportId] = useState('');
  const [refreshTick, setRefreshTick] = useState(0);
  const bumpRefresh = () => setRefreshTick((t) => t + 1);

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
        <CheckCard presetHash={presetHash} onConsumePreset={() => setPresetHash('')} />
        <RegisterCard org={org} onWrote={bumpRefresh} />
        <ReportCard org={org} onWrote={bumpRefresh} />
        <RouteCard org={org} presetReportId={presetReportId} onConsumePreset={() => setPresetReportId('')} onWrote={bumpRefresh} />
      </main>
      <BrowseCard refreshKey={refreshTick}
        onPickHash={(h) => { setPresetHash(h); document.getElementById('card-check')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }}
        onPickReport={(r) => { setPresetReportId(r); document.getElementById('card-route')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }} />
      <footer>ASCIR investigator console · drives the multi-org Fabric backend over its HTTP API</footer>
    </div>
  );
}
