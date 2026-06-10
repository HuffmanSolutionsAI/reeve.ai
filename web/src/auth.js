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

// Pull a human-readable message out of a FastAPI error body (which may be
// {"detail": "..."} or {"detail": [{"msg": "..."}]} for validation errors).
async function errorMessage(resp, fallback) {
  try {
    const body = await resp.json();
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    /* not json */
  }
  return `${fallback} (${resp.status})`;
}

export async function login({ email, password }) {
  const r = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error(await errorMessage(r, 'login failed'));
  const body = await r.json();
  setSession(body.access_token, body.investor_id);
  return body;
}

export async function signup({ email, password, name, entity_name = null, buy_box = null, preferences = null }) {
  const r = await fetch('/api/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name, entity_name, buy_box, preferences }),
  });
  if (!r.ok) throw new Error(await errorMessage(r, 'signup failed'));
  const body = await r.json();
  setSession(body.access_token, body.investor_id);
  return body;
}
