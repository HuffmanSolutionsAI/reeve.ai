import { authHeaders, clearSession } from './auth.js';

const BASE = '/api';

async function jsonOrThrow(resp, label) {
  if (resp.status === 401) {
    clearSession();
    window.location.reload();
    throw new Error('unauthorized');
  }
  if (!resp.ok) throw new Error(`${label}: ${resp.status} ${resp.statusText}`);
  return resp.json();
}

const get = (path) => fetch(`${BASE}${path}`, { headers: authHeaders() });

export async function fetchMe() {
  return jsonOrThrow(await get('/me'), 'me');
}

export async function fetchActivity(limit = 50) {
  return jsonOrThrow(await get(`/activity?limit=${limit}`), 'activity');
}

export async function fetchPipeline() {
  return jsonOrThrow(await get('/pipeline'), 'pipeline');
}

export async function fetchPortfolio() {
  return jsonOrThrow(await get('/portfolio'), 'portfolio');
}

export async function fetchMessages(conversationId) {
  return jsonOrThrow(await get(`/conversations/${conversationId}/messages`), 'messages');
}

export async function fetchArtifact(artifactId) {
  return jsonOrThrow(await get(`/artifacts/${artifactId}`), 'artifact');
}

export async function fetchProposals(status = 'pending') {
  const q = status ? `?status=${status}` : '';
  return jsonOrThrow(await get(`/proposals${q}`), 'proposals');
}

export async function decideProposal(proposalId, decision, approver = 'investor') {
  const r = await fetch(`${BASE}/proposals/${proposalId}/${decision}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ approver }),
  });
  if (r.status === 401) { clearSession(); window.location.reload(); throw new Error('unauthorized'); }
  if (!r.ok) throw new Error(`${decision}: ${r.status}`);
  return r.json();
}
