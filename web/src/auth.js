// Token management. Stored in localStorage so a reload keeps the session.
// Dev login goes through /api/auth/dev-token — replace with real auth in prod.

const TOKEN_KEY = 'reeve:token';
const INVESTOR_KEY = 'reeve:investor_id';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getInvestorId() {
  return localStorage.getItem(INVESTOR_KEY);
}

export function setSession(token, investorId) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(INVESTOR_KEY, investorId);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(INVESTOR_KEY);
}

export function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export async function login(investorId) {
  const r = await fetch('/api/auth/dev-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ investor_id: investorId }),
  });
  if (!r.ok) {
    const detail = await r.text().catch(() => '');
    throw new Error(`login failed: ${r.status}${detail ? ` — ${detail}` : ''}`);
  }
  const body = await r.json();
  setSession(body.access_token, body.investor_id);
  return body;
}
