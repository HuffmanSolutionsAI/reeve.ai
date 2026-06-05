import React from 'react';

const SEV = { info: 'var(--ink-soft)', watch: 'var(--brass)', action: 'var(--clay)' };
const fmt$ = (v) => v === null || v === undefined ? '—' : `$${Math.round(v).toLocaleString()}`;
const fmtPct = (v) => v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)}%`;

function Metric({ label, value, sub, accent }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={accent ? { color: 'var(--green-2)' } : undefined}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

export default function TaxMemo({ payload }) {
  if (!payload || payload.type !== 'tax_memo') return null;
  const {
    as_of, tax_year, estimate, by_building, strategy_flags,
    filing_due, assumptions, thesis, confidence, unverified,
  } = payload;

  return (
    <div className="card tax-memo">
      <div className="card-top">
        <div>
          <div className="card-title">Tax memo · {tax_year}</div>
          <div className="card-meta">as of {as_of}{filing_due ? ` · due ${filing_due}` : ''}</div>
        </div>
        <div className="verdict" data-decision="pursue">
          Est. {fmt$(estimate?.total_liability)}
        </div>
      </div>

      <div className="metrics">
        <Metric label="Gross income" value={fmt$(estimate?.gross_rental_income)} />
        <Metric label="OpEx" value={fmt$(estimate?.operating_expenses)} />
        <Metric label="Depreciation" value={fmt$(estimate?.depreciation)} />
        <Metric label="Federal" value={fmt$(estimate?.federal_liability)} sub={fmtPct(estimate?.federal_rate)} />
        <Metric label="State" value={fmt$(estimate?.state_liability)} sub={fmtPct(estimate?.state_rate)} accent />
      </div>

      {by_building?.length > 0 && (
        <div className="tax-by-building">
          <div className="chart-label">By building</div>
          {by_building.map((b, i) => (
            <div key={i} className="tax-row">
              <span>{b.address}</span>
              <span>{fmt$(b.net_rental_income)}</span>
            </div>
          ))}
        </div>
      )}

      {strategy_flags?.length > 0 && (
        <div className="highlights">
          {strategy_flags.map((f, i) => (
            <div key={i} className="highlight" style={{ borderLeftColor: SEV[f.severity] || 'var(--line)' }}>
              <span className="hl-kind">{f.kind.replace(/_/g, ' ')}</span>
              <span className="hl-text">{f.text}</span>
              {f.estimated_value != null && <span className="hl-amount">~{fmt$(f.estimated_value)}</span>}
            </div>
          ))}
        </div>
      )}

      {assumptions?.length > 0 && (
        <div className="assumptions">
          {assumptions.map((a, i) => <span key={i}>{a}</span>)}
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
