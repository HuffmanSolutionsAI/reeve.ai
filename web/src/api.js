const BASE = '/api';

async function jsonOrThrow(resp, label) {
  if (!resp.ok) throw new Error(`${label}: ${resp.status} ${resp.statusText}`);
  return resp.json();
}

export async function fetchInvestor(investorId) {
  return jsonOrThrow(await fetch(`${BASE}/investors/${investorId}`), 'investor');
}

export async function fetchActivity(investorId, limit = 50) {
  return jsonOrThrow(
    await fetch(`${BASE}/activity?investor_id=${investorId}&limit=${limit}`),
    'activity',
  );
}

export async function fetchPipeline(investorId) {
  return jsonOrThrow(
    await fetch(`${BASE}/pipeline?investor_id=${investorId}`),
    'pipeline',
  );
}

export async function fetchPortfolio(investorId) {
  return jsonOrThrow(
    await fetch(`${BASE}/portfolio?investor_id=${investorId}`),
    'portfolio',
  );
}

export async function fetchMessages(conversationId) {
  return jsonOrThrow(
    await fetch(`${BASE}/conversations/${conversationId}/messages`),
    'messages',
  );
}

export async function fetchArtifact(artifactId) {
  return jsonOrThrow(
    await fetch(`${BASE}/artifacts/${artifactId}`),
    'artifact',
  );
}

export async function fetchProposals(investorId, status = 'pending') {
  const q = status ? `&status=${status}` : '';
  return jsonOrThrow(
    await fetch(`${BASE}/proposals?investor_id=${investorId}${q}`),
    'proposals',
  );
}

export async function decideProposal(proposalId, decision, approver = 'investor') {
  // decision: 'approve' | 'reject'
  const r = await fetch(`${BASE}/proposals/${proposalId}/${decision}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approver }),
  });
  if (!r.ok) throw new Error(`${decision}: ${r.status}`);
  return r.json();
}
