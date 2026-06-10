import React, { useEffect, useState } from 'react';
import * as api from '../api.js';
import ArtifactCard from './ArtifactCard.jsx';

const fmt$ = (v) => (v === null || v === undefined ? '—' : `$${Math.round(v).toLocaleString()}`);
const fmtPct = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)}%`);

function ValidationChecks({ validation }) {
  const checks = validation?.checks || [];
  if (!checks.length) return null;
  const failed = checks.filter((c) => !c.passed);
  return (
    <div className="doc-checks">
      {checks.map((c, i) => (
        <div key={i} className={`doc-check ${c.passed ? 'ok' : 'failed'}`}>
          <span className="doc-check-mark">{c.passed ? '✓' : '✗'}</span>
          <span className="doc-check-name">{c.name.replace(/_/g, ' ')}</span>
          {!c.passed && c.detail && <span className="doc-check-detail">{c.detail}</span>}
        </div>
      ))}
      {failed.length > 0 && (
        <div className="doc-check-warning">
          {failed.length} check{failed.length !== 1 ? 's' : ''} failed — review the source
          document before confirming.
        </div>
      )}
    </div>
  );
}

function RentRollReview({ doc, busy, onConfirm }) {
  const d = doc.derived || {};
  const ach = d.achieved_renovated || {};
  return (
    <div className="approval">
      <div className="approval-head">
        <div>
          <div className="approval-action">
            Rent roll for <strong>{doc.deal_address || doc.deal_id}</strong>
          </div>
          <div className="approval-summary">
            as of {doc.as_of} · {d.units_total ?? '?'} units ·
            occupancy {fmtPct(d.physical_occupancy)} ·
            GSR {fmt$(d.gross_scheduled_rent_monthly)}/mo
            {ach.n > 0 && <> · achieved-renovated n={ach.n} @ {fmt$(ach.mean)}</>}
          </div>
          <div className="approval-meta">
            ingested {new Date(doc.created_at).toLocaleString()}
            {doc.source?.extraction_method ? ` · via ${doc.source.extraction_method}` : ''}
          </div>
        </div>
        <div className="approval-buttons">
          <button className="btn-approve" disabled={busy} onClick={onConfirm}>
            {busy ? '…' : 'Confirm & activate'}
          </button>
        </div>
      </div>
      <ValidationChecks validation={doc.validation} />
    </div>
  );
}

function OperatingStatementReview({ doc, busy, onConfirm }) {
  return (
    <div className="approval">
      <div className="approval-head">
        <div>
          <div className="approval-action">
            T-12 for <strong>{doc.deal_address || doc.deal_id}</strong>
          </div>
          <div className="approval-summary">
            {doc.period?.start} → {doc.period?.end} ·
            {' '}{doc.line_count} lines · {fmt$(doc.annual_total)}/yr
          </div>
          <div className="approval-meta">
            ingested {new Date(doc.created_at).toLocaleString()}
            {doc.source?.extraction_method ? ` · via ${doc.source.extraction_method}` : ''}
          </div>
        </div>
        <div className="approval-buttons">
          <button className="btn-approve" disabled={busy} onClick={onConfirm}>
            {busy ? '…' : 'Confirm & activate'}
          </button>
        </div>
      </div>
      <ValidationChecks validation={doc.validation} />
    </div>
  );
}

export default function ApprovalsView({ onChanged }) {
  const [pending, setPending] = useState([]);
  const [docs, setDocs] = useState({ rent_rolls: [], operating_statements: [] });
  const [busy, setBusy] = useState(null);
  const [flash, setFlash] = useState(null);

  const refresh = () => {
    api.fetchProposals('pending').then(r => setPending(r.proposals)).catch(() => {});
    api.fetchPendingDocuments().then(setDocs).catch(() => {});
  };

  useEffect(() => { refresh(); }, []);

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

  const confirmDoc = async (kind, id, label) => {
    setBusy(id);
    setFlash(null);
    try {
      await api.confirmDocument(kind, id);
      setFlash(`${label} confirmed — now active for underwriting.`);
    } catch (e) {
      setFlash(`Error: ${e.message}`);
    } finally {
      setBusy(null);
      refresh();
      onChanged && onChanged();
    }
  };

  const docCount = (docs.rent_rolls?.length || 0) + (docs.operating_statements?.length || 0);
  const nothing = pending.length === 0 && docCount === 0;

  return (
    <main className="chat" style={{ padding: '24px 28px', overflowY: 'auto' }}>
      <h2 style={{ fontFamily: 'Fraunces, serif', marginBottom: 18 }}>Approvals</h2>
      {flash && <div className="flash">{flash}</div>}
      {nothing && <div className="empty">Nothing waiting on you.</div>}

      {docCount > 0 && (
        <>
          <div className="approvals-section-head">Documents awaiting review</div>
          {(docs.rent_rolls || []).map((d) => (
            <RentRollReview key={d.id} doc={d} busy={busy === d.id}
              onConfirm={() => confirmDoc('rent-rolls', d.id, 'Rent roll')} />
          ))}
          {(docs.operating_statements || []).map((d) => (
            <OperatingStatementReview key={d.id} doc={d} busy={busy === d.id}
              onConfirm={() => confirmDoc('operating-statements', d.id, 'T-12')} />
          ))}
        </>
      )}

      {pending.length > 0 && (
        <>
          {docCount > 0 && <div className="approvals-section-head">Proposed actions</div>}
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
        </>
      )}
    </main>
  );
}
