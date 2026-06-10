import React, { useState } from 'react';

const fmt$ = (v) => (v === null || v === undefined ? '—' : `$${Math.round(v).toLocaleString()}`);
const fmtPct = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)}%`);
const fmtPct2 = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(2)}%`);

const STATUS_COLOR = { pass: 'var(--green-2)', warn: 'var(--brass)', fail: 'var(--clay)' };
const SEV_COLOR = { blocking: 'var(--clay)', watch: 'var(--brass)' };

function NOITable({ panel }) {
  const states = [
    ['In-place', panel.in_place],
    ['Stabilized', panel.stabilized],
    ['+ Ancillary', panel.stabilized_plus_ancillary],
  ];
  const rows = [
    ['GPI', (s) => fmt$(s.gross_potential_income)],
    ['Vacancy', (s) => fmt$(-s.vacancy_loss)],
    ['Credit loss', (s) => fmt$(-s.credit_loss)],
    ['Other income', (s) => fmt$(s.other_income)],
    ['EGI', (s) => fmt$(s.effective_gross_income)],
    ['OpEx', (s) => fmt$(-s.opex_total)],
    ['NOI', (s) => fmt$(s.noi)],
  ];
  return (
    <table className="va-table">
      <thead>
        <tr><th /><th>In-place</th><th>Stabilized</th><th>+ Ancillary</th></tr>
      </thead>
      <tbody>
        {rows.map(([label, fn]) => (
          <tr key={label} className={label === 'NOI' ? 'va-noi-row' : ''}>
            <td>{label}</td>
            {states.map(([name, s]) => <td key={name}>{fn(s)}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SensitivityGrid({ sensitivity }) {
  const cells = sensitivity?.cells || [];
  if (!cells.length) return null;
  const rentDeltas = [...new Set(cells.map((c) => c.target_rent_delta_pct))].sort((a, b) => a - b);
  const capDeltas = [...new Set(cells.map((c) => c.exit_cap_delta_bps))].sort((a, b) => a - b);
  const byKey = {};
  cells.forEach((c) => { byKey[`${c.target_rent_delta_pct}:${c.exit_cap_delta_bps}`] = c; });
  return (
    <div>
      <div className="va-swing">
        Max offer swings <strong>{fmt$(sensitivity.swing)}</strong> across the grid
      </div>
      <table className="va-table va-grid">
        <thead>
          <tr>
            <th>rent \ cap</th>
            {capDeltas.map((d) => <th key={d}>{d > 0 ? `+${d}` : d}bps</th>)}
          </tr>
        </thead>
        <tbody>
          {rentDeltas.map((r) => (
            <tr key={r}>
              <td>{r > 0 ? `+${(r * 100).toFixed(0)}` : (r * 100).toFixed(0)}%</td>
              {capDeltas.map((cDelta) => {
                const cell = byKey[`${r}:${cDelta}`];
                const center = r === 0 && cDelta === 0;
                return (
                  <td key={cDelta} className={center ? 'va-grid-center' : ''}>
                    {cell ? fmt$(cell.max_offer) : '—'}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ValueAddAnalysis({ payload }) {
  const [showGrid, setShowGrid] = useState(false);
  if (!payload || payload.type !== 'value_add_analysis') return null;
  const {
    address, units, noi_panel, valuation_panel, sources_and_uses: su,
    returns, cross_checks, sensitivity, risk_register, flags,
    verdict, confidence, thesis,
  } = payload;
  const ladder = valuation_panel?.bid_ladder || {};
  const blocking = (flags || []).filter((f) => f.severity === 'blocking');
  const loadBearing = (risk_register || [])[0];

  return (
    <div className="card va-card">
      <div className="card-top">
        <div>
          <div className="card-title">{address}</div>
          <div className="card-meta">{units} units · value-add underwrite</div>
        </div>
        <div className="verdict" data-decision={verdict?.decision}>
          {verdict?.headline || verdict?.decision}
        </div>
      </div>

      {/* Valuation band + bid ladder */}
      <div className="metrics" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <div className="metric">
          <div className="metric-label">Floor (in-place)</div>
          <div className="metric-value">{fmt$(valuation_panel?.floor_value)}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Stabilized value</div>
          <div className="metric-value">{fmt$(valuation_panel?.stabilized_value)}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Ceiling (max offer)</div>
          <div className="metric-value" style={{ color: 'var(--green-2)' }}>{fmt$(valuation_panel?.ceiling_max_offer)}</div>
        </div>
      </div>
      <div className="va-ladder">
        <span>open {fmt$(ladder.opening)}</span>
        <span className="va-ladder-arrow">→</span>
        <span>target {fmt$(ladder.target_bid)}</span>
        <span className="va-ladder-arrow">→</span>
        <span>walk away {fmt$(ladder.walk_away)}</span>
      </div>

      {/* NOI states */}
      <div className="chart-label" style={{ marginTop: 14 }}>NOI by state (annual)</div>
      <NOITable panel={noi_panel} />
      {noi_panel?.broker_proforma_diff?.length > 0 && (
        <div className="va-broker-diff">
          {noi_panel.broker_proforma_diff.map((d, i) => (
            <span key={i}>
              broker {d.line}: {fmt$(d.broker)} vs engine {fmt$(d.engine)}
              {d.delta != null && <em> ({d.delta > 0 ? '+' : ''}{fmt$(d.delta)} rosier)</em>}
            </span>
          ))}
        </div>
      )}

      {/* Cost to stabilize + financing */}
      <div className="va-two-col">
        <div>
          <div className="chart-label">Sources &amp; uses</div>
          <div className="va-kv">
            <span>Bridge basis</span><span>{fmt$(su?.bridge_basis)}</span>
            <span>Bridge proceeds</span><span>{fmt$(su?.bridge_proceeds)}</span>
            <span>Equity in</span><span>{fmt$(su?.bridge_equity_in)}</span>
            <span>Perm loan</span><span>{fmt$(su?.perm_loan)}</span>
            <span>Equity recapture</span><span>{fmt$(su?.equity_recapture)}</span>
            <span>Residual equity</span><span>{fmt$(su?.residual_equity)}</span>
          </div>
          <div className="va-structure">
            structure: <code>{su?.structure}</code>
            {su?.perm_first_qualifies === false && (
              <span className="va-gate-warn">
                · below {fmtPct(su?.occupancy_gate_pct)} agency gate
              </span>
            )}
          </div>
        </div>
        <div>
          <div className="chart-label">Returns + checks</div>
          <div className="va-kv">
            <span>Stabilized CoC</span><span>{fmtPct2(returns?.stabilized_cash_on_cash)}</span>
            <span>DSCR @ perm</span><span>{returns?.perm_dscr_at_stabilized?.toFixed?.(2) ?? '—'}×</span>
          </div>
          <div className="va-checks">
            {(cross_checks || []).map((c, i) => (
              <div key={i} className="va-check" style={{ borderLeftColor: STATUS_COLOR[c.status] }}>
                <span className="va-check-name">{c.name.replace(/_/g, ' ')}</span>
                <span className="va-check-val">
                  {c.name.includes('cap') || c.name.includes('yoc') ? fmtPct2(c.value)
                    : c.name === 'grm' || c.name.includes('dscr') ? c.value.toFixed(2)
                    : fmt$(c.value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Load-bearing assumption + risk register */}
      {loadBearing && (
        <div className="va-load-bearing">
          Load-bearing assumption: <strong>{loadBearing.input.replace(/_/g, ' ')}</strong>
          {' '}(swing {fmt$(loadBearing.swing_dollars)} on the max offer
          {loadBearing.provenance !== 'verified' && `, ${loadBearing.provenance}`})
          {loadBearing.verification_action && (
            <div className="va-verify-action">→ {loadBearing.verification_action}</div>
          )}
        </div>
      )}

      {/* Flags */}
      {(flags || []).length > 0 && (
        <div className="highlights">
          {flags.map((f, i) => (
            <div key={i} className="highlight" style={{ borderLeftColor: SEV_COLOR[f.severity] }}>
              <span className="hl-kind">{f.severity}</span>
              <span className="hl-text">
                {f.text}
                {f.unblock_action && <em className="va-unblock"> Unblock: {f.unblock_action}</em>}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Sensitivity (collapsible) */}
      <button className="va-toggle" onClick={() => setShowGrid(!showGrid)}>
        {showGrid ? 'Hide' : 'Show'} sensitivity grid (swing {fmt$(sensitivity?.swing)})
      </button>
      {showGrid && <SensitivityGrid sensitivity={sensitivity} />}

      {thesis && <p className="card-note">{thesis}</p>}

      <div className="confidence">
        <span data-level={confidence}>confidence: {confidence}</span>
        {blocking.length > 0 && (
          <span className="unverified">{blocking.length} blocking flag{blocking.length !== 1 ? 's' : ''} open</span>
        )}
      </div>
    </div>
  );
}
