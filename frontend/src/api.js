// All requests go to /api/* which Vite proxies to the backend on :3000.
async function post(path, body) {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({ error: 'non-JSON response' }));
  if (!res.ok) throw new Error(data.error || data.detail || `HTTP ${res.status}`);
  return data;
}

export async function getHealth() {
  const res = await fetch('/api/health');
  return res.json();
}
export const checkStatus = (manifest_hash) => post('/check', { manifest_hash });
export const registerKnownGood = (b) => post('/register', b);
export const reportCompromise = (b) => post('/report', b);
export const routeCompromise = (b) => post('/route', b);
