import React from 'react';

const fmt$ = (v) => v === null || v === undefined ? '—' : `$${Math.round(v).toLocaleString()}`;

export default function LoiDraft({ payload, pending }) {
  if (!payload || payload.type !== 'loi_draft') return null;
  const {
    address, price, earnest_money, due_diligence_days,
    financing_contingency_days, closing_days, addressee, terms, narrative, sent_at,
  } = payload;

  return (
    <div className="card loi">
      <div className="card-top">
        <div>
          <div className="card-title">Letter of intent</div>
          <div className="card-meta">{address}</div>
        </div>
        <div className="verdict" data-decision={pending ? 'conditional' : 'pursue'}>
          {pending ? 'Awaiting sign-off' : sent_at ? 'Sent' : 'Draft'}
        </div>
      </div>

      <div className="loi-grid">
        <div><div className="loi-label">Price</div><div className="loi-value">{fmt$(price)}</div></div>
        <div><div className="loi-label">Earnest money</div><div className="loi-value">{fmt$(earnest_money)}</div></div>
        <div><div className="loi-label">Due diligence</div><div className="loi-value">{due_diligence_days}d</div></div>
        <div><div className="loi-label">Financing</div><div className="loi-value">{financing_contingency_days}d</div></div>
        <div><div className="loi-label">Closing</div><div className="loi-value">{closing_days}d</div></div>
      </div>

      <div className="loi-addressee">
        <span className="loi-label">To</span>
        <span>{addressee?.name}{addressee?.role ? ` · ${addressee.role}` : ''} · <code>{addressee?.email}</code></span>
      </div>

      {terms?.length > 0 && (
        <ul className="loi-terms">
          {terms.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      )}

      {narrative && <p className="card-note">{narrative}</p>}
      {sent_at && <div className="loi-sent">Sent {new Date(sent_at).toLocaleString()}</div>}
    </div>
  );
}
