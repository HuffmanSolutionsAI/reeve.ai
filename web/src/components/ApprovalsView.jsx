import React, { useEffect, useState } from 'react';
import * as api from '../api.js';
import ArtifactCard from './ArtifactCard.jsx';

export default function ApprovalsView({ investorId, onChanged }) {
  const [pending, setPending] = useState([]);
  const [busy, setBusy] = useState(null);  // proposal id currently being acted on
  const [flash, setFlash] = useState(null);

  const refresh = () =>
    api.fetchProposals(investorId, 'pending').then(r => setPending(r.proposals)).catch(() => {});

  useEffect(() => { refresh(); }, [investorId]);

  const act = async (id, kind) => {
    setBusy(id);
    setFlash(null);
    try {
      const body = await api.decideProposal(id, kind, 'investor');
      setFlash(
        kind === 'approve' && body.executed
          ? `Sent — ${body.result?.recipient?.email || 'done'}`
          : kind === 'approve' && !body.executed
            ? `Approved but execution failed: ${body.error}`
            : `Rejected`,
      );
    } catch (e) {
      setFlash(`Error: ${e.message}`);
    } finally {
      setBusy(null);
      refresh();
      onChanged && onChanged();
    }
  };

  return (
    <main className="chat" style={{ padding: '24px 28px', overflowY: 'auto' }}>
      <h2 style={{ fontFamily: 'Fraunces, serif', marginBottom: 18 }}>Approvals</h2>
      {flash && <div className="flash">{flash}</div>}
      {pending.length === 0 && <div className="empty">Nothing waiting on you.</div>}
      {pending.map(p => (
        <div key={p._id} className="approval">
          <div className="approval-head">
            <div>
              <div className="approval-action">
                <strong>{p.agent}</strong> wants to <code>{p.action}</code>
              </div>
              <div className="approval-summary">{p.summary}</div>
              <div className="approval-meta">queued {new Date(p.created_at).toLocaleString()}</div>
            </div>
            <div className="approval-buttons">
              <button className="btn-approve" disabled={busy === p._id} onClick={() => act(p._id, 'approve')}>
                {busy === p._id ? '…' : 'Approve & send'}
              </button>
              <button className="btn-reject" disabled={busy === p._id} onClick={() => act(p._id, 'reject')}>
                Reject
              </button>
            </div>
          </div>
          {p.action === 'send_loi' && (
            <ArtifactCard payload={{ type: 'loi_draft', ...p.payload }} pending />
          )}
        </div>
      ))}
    </main>
  );
}
