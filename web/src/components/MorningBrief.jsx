import React from 'react';

const fmt$ = (v) => v === null || v === undefined ? '—' : `$${Math.round(v).toLocaleString()}`;
const fmtPct = (v) => v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)}%`;

const SEV = { info: 'var(--ink-soft)', watch: 'var(--brass)', action: 'var(--clay)' };

function Metric({ label, value, sub, accent }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={accent ? { color: 'var(--green-2)' } : undefined}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

export default function MorningBrief({ payload }) {
  if (!payload || payload.type !== 'morning_brief') return null;
  const { as_of, period, portfolio, month_to_date: mtd, cash_position, highlights, thesis, confidence, unverified } = payload;

  return (
    <div className="card brief">
      <div className="card-top">
        <div>
          <div className="card-title">Morning brief</div>
          <div className="card-meta">
            as of {as_of} · {period?.start} → {period?.end}
          </div>
        </div>
        <div className="verdict brief-pill">{portfolio?.buildings || 0} bldgs · {portfolio?.units || 0} units</div>
      </div>

      <div className="metrics">
        <Metric label="MTD revenue" value={fmt$(mtd?.revenue)} />
        <Metric label="MTD expenses" value={fmt$(mtd?.expenses)} />
        <Metric label="MTD NOI" value={fmt$(mtd?.noi)} accent />
        <Metric label="Expense ratio" value={fmtPct(mtd?.expense_ratio)} />
        <Metric label="Occupancy" value={fmtPct(portfolio?.occupancy)} sub={`${portfolio?.occupied || 0}/${portfolio?.units || 0}`} />
      </div>

      {cash_position && (cash_position.operating || cash_position.reserves) && (
        <div className="cash-row">
          <span>operating {fmt$(cash_position.operating)}</span>
          {cash_position.reserves != null && <span>reserves {fmt$(cash_position.reserves)}</span>}
          {cash_position.total != null && <span>total {fmt$(cash_position.total)}</span>}
        </div>
      )}

      {highlights?.length > 0 && (
        <div className="highlights">
          {highlights.map((h, i) => (
            <div key={i} className="highlight" style={{ borderLeftColor: SEV[h.severity] || 'var(--line)' }}>
              <span className="hl-kind">{h.kind}</span>
              <span className="hl-text">{h.text}</span>
              {h.amount != null && <span className="hl-amount">{fmt$(h.amount)}</span>}
            </div>
          ))}
        </div>
      )}

      {mtd?.by_category && (
        <div className="assumptions">
          {Object.entries(mtd.by_category).map(([k, v]) => (
            <span key={k}>{k} {fmt$(v)}</span>
          ))}
        </div>
      )}

      {thesis && <p className="card-note">{thesis}</p>}

      <div className="confidence">
        <span data-level={confidence}>confidence: {confidence}</span>
        {unverified?.length > 0 && <span className="unverified">unverified: {unverified.join(', ')}</span>}
      </div>
    </div>
  );
}
