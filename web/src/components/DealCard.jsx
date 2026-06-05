import React from 'react';
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, Tooltip } from 'recharts';

const fmtPct = (v) => v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)}%`;
const fmtMul = (v) => v === null || v === undefined ? '—' : `${v.toFixed(2)}×`;
const fmt$ = (v) => v === null || v === undefined ? '—' : `$${Math.round(v).toLocaleString()}`;

function Metric({ label, value, sub, accent }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={accent ? { color: 'var(--green-2)' } : undefined}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

export default function DealCard({ payload }) {
  if (!payload || payload.type !== 'deal_analysis') return null;
  const { address, units, ask, price_per_unit, verdict, metrics, rent_roll, assumptions, thesis, confidence, unverified } = payload;
  const data = (rent_roll || []).map(r => ({ u: r.unit, inplace: r.in_place, market: r.market }));

  return (
    <div className="card">
      <div className="card-top">
        <div>
          <div className="card-title">{address}</div>
          <div className="card-meta">
            {units} units · Asking {fmt$(ask)} · {fmt$(price_per_unit)} / unit
          </div>
        </div>
        <div className="verdict" data-decision={verdict?.decision}>{verdict?.headline || verdict?.decision}</div>
      </div>

      <div className="metrics">
        <Metric label="Cap (in-place)" value={fmtPct(metrics?.cap_in_place)} sub={`pro-forma ${fmtPct(metrics?.cap_proforma)}`} />
        <Metric label="Cash-on-cash" value={fmtPct(metrics?.coc_year1)} sub={`stab. ${fmtPct(metrics?.coc_stabilized)}`} accent />
        <Metric label="DSCR" value={fmtMul(metrics?.dscr)} sub="yr 1" />
        <Metric label="Avg rent" value={fmt$(metrics?.avg_rent_in_place)} sub={`market ${fmt$(metrics?.avg_rent_market)}`} />
        <Metric label="Rent upside" value={fmtPct(metrics?.rent_upside_pct)} sub={`${fmt$(metrics?.rent_upside_monthly)} / mo`} accent />
      </div>

      {data.length > 0 && (
        <div className="chart-wrap">
          <div className="chart-label">In-place rent vs. market — by unit</div>
          <ResponsiveContainer width="100%" height={148}>
            <BarChart data={data} barGap={3} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
              <XAxis dataKey="u" tick={{ fontSize: 10, fill: 'var(--ink-soft)', fontFamily: 'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--ink-soft)', fontFamily: 'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ fill: 'rgba(0,0,0,.04)' }}
                contentStyle={{ fontFamily: 'IBM Plex Mono', fontSize: 11, border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)' }} />
              <Bar dataKey="inplace" radius={[2, 2, 0, 0]}>
                {data.map((_, i) => <Cell key={i} fill="#C9BFA6" />)}
              </Bar>
              <Bar dataKey="market" radius={[2, 2, 0, 0]}>
                {data.map((_, i) => <Cell key={i} fill="var(--green)" />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="assumptions">
        {(assumptions || []).map((a, i) => <span key={i}>{a}</span>)}
      </div>

      {thesis && <p className="card-note">{thesis}</p>}

      {(unverified?.length || confidence) && (
        <div className="confidence">
          <span data-level={confidence}>confidence: {confidence}</span>
          {unverified?.length > 0 && <span className="unverified">unverified: {unverified.join(', ')}</span>}
        </div>
      )}
    </div>
  );
}
