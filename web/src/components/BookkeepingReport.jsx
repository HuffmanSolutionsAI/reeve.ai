import React from 'react';

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

export default function BookkeepingReport({ payload }) {
  if (!payload || payload.type !== 'bookkeeping_report') return null;
  const {
    as_of, period, reviewed, recategorized, adjusting_entries_proposed,
    category_distribution, anomalies, thesis, confidence, unverified,
  } = payload;

  const distEntries = Object.entries(category_distribution || {})
    .sort((a, b) => b[1] - a[1]);

  return (
    <div className="card bookkeeping">
      <div className="card-top">
        <div>
          <div className="card-title">Bookkeeping pass</div>
          <div className="card-meta">{period?.start} → {period?.end} · as of {as_of}</div>
        </div>
        <div className="verdict" data-decision={(adjusting_entries_proposed || 0) > 0 ? 'conditional' : 'pursue'}>
          {reviewed} reviewed · {recategorized || 0} fixed
        </div>
      </div>

      <div className="metrics">
        <Metric label="Reviewed" value={reviewed} />
        <Metric label="Recategorized" value={recategorized || 0} accent />
        <Metric label="Adjustments proposed" value={adjusting_entries_proposed || 0} />
        <Metric label="Anomalies" value={anomalies?.length || 0} />
        <Metric label="Categories" value={distEntries.length} />
      </div>

      {distEntries.length > 0 && (
        <div className="assumptions">
          {distEntries.map(([k, v]) => <span key={k}>{k} {v}</span>)}
        </div>
      )}

      {anomalies?.length > 0 && (
        <div className="highlights">
          {anomalies.map((a, i) => (
            <div key={i} className="highlight" style={{ borderLeftColor: SEV[a.severity] || 'var(--line)' }}>
              <span className="hl-kind">{a.kind}</span>
              <span className="hl-text">{a.text}</span>
              {a.amount != null && <span className="hl-amount">${Math.round(a.amount).toLocaleString()}</span>}
            </div>
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
