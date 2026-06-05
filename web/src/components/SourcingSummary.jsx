import React from 'react';

const fmt$ = (v) => v === null || v === undefined ? '—' : `$${Math.round(v).toLocaleString()}`;
const fmtScore = (v) => `${Math.round(v * 100)}`;

export default function SourcingSummary({ payload }) {
  if (!payload || payload.type !== 'sourcing_summary') return null;
  const { as_of, filters, scanned, surfaced, duplicates, candidates, thesis, confidence, unverified } = payload;
  const sorted = [...(candidates || [])].sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0));

  return (
    <div className="card sourcing">
      <div className="card-top">
        <div>
          <div className="card-title">Sourcing summary</div>
          <div className="card-meta">as of {as_of} · {Object.entries(filters || {}).map(([k, v]) => `${k}=${v}`).join(' · ') || 'no filters'}</div>
        </div>
        <div className="verdict" data-decision="pursue">
          {surfaced} surfaced · {duplicates} dup · {scanned} scanned
        </div>
      </div>

      {sorted.length === 0 && <div className="empty" style={{ padding: '12px 0' }}>Nothing fits the buy-box this pass.</div>}

      <div className="sourcing-rows">
        {sorted.map((c, i) => (
          <div key={i} className={`sourcing-row ${c.duplicate ? 'dup' : ''}`}>
            <div className="src-score">
              <span className="src-score-num">{fmtScore(c.fit_score)}</span>
              <span className="src-score-label">fit</span>
            </div>
            <div className="src-body">
              <div className="src-head">
                <strong>{c.address}</strong>
                <span className="src-stats">{c.units}u · {fmt$(c.ask)} · {fmt$((c.ask || 0) / Math.max(c.units || 1, 1))}/unit</span>
              </div>
              <div className="src-meta">{c.city ? `${c.city}, ${c.state || ''}` : ''}{c.distress_signal ? ` · ${c.distress_signal}` : ''}</div>
              <div className="src-rationale">{c.rationale}</div>
              {c.duplicate && <div className="src-dup">already in your pipeline</div>}
            </div>
          </div>
        ))}
      </div>

      {thesis && <p className="card-note">{thesis}</p>}

      <div className="confidence">
        <span data-level={confidence}>confidence: {confidence}</span>
        {unverified?.length > 0 && <span className="unverified">unverified: {unverified.join(', ')}</span>}
      </div>
    </div>
  );
}
