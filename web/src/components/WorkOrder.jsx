import React from 'react';

const PRIORITY_COLOR = {
  emergency: 'var(--clay)',
  urgent: 'var(--brass)',
  standard: 'var(--green-2)',
  low: 'var(--ink-soft)',
};

const fmt$ = (v) => v === null || v === undefined ? '—' : `$${Math.round(v).toLocaleString()}`;

export default function WorkOrder({ payload, pending }) {
  if (!payload || payload.type !== 'work_order') return null;
  const { vendor_name, building_address, unit_label, trade, scope, priority, max_spend, dispatched_at, contact } = payload;

  return (
    <div className="card work-order">
      <div className="card-top">
        <div>
          <div className="card-title">Work order · {trade}</div>
          <div className="card-meta">
            {vendor_name || 'Vendor'} → {building_address || 'building'}{unit_label ? ` · Unit ${unit_label}` : ''}
          </div>
        </div>
        <div className="verdict" style={{ background: PRIORITY_COLOR[priority] || 'var(--green-2)' }}>
          {priority}
        </div>
      </div>

      <p className="card-note" style={{ marginTop: 12 }}>{scope}</p>

      <div className="wo-row">
        {max_spend != null && <span>cap {fmt$(max_spend)}</span>}
        {contact?.email && <span><code>{contact.email}</code></span>}
        {contact?.phone && <span><code>{contact.phone}</code></span>}
        {dispatched_at && <span className="loi-sent">dispatched {new Date(dispatched_at).toLocaleString()}</span>}
        {pending && <span style={{ color: 'var(--brass)' }}>awaiting sign-off</span>}
      </div>
    </div>
  );
}
