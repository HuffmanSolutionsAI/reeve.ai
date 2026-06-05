import React, { useState } from 'react';
import { signup } from '../auth.js';

// Builds the buy_box payload from the form. Returns null if the user left
// every field blank — passes the API's "buy_box is optional" semantics.
function collectBuyBox(f) {
  const bb = {};
  if (f.capFloor) bb.cap_floor = parseFloat(f.capFloor) / 100;
  if (f.minDscr) bb.min_dscr = parseFloat(f.minDscr);
  if (f.targetCoc) bb.target_coc = parseFloat(f.targetCoc) / 100;
  if (f.markets.trim()) {
    bb.markets = f.markets.split(',').map((s) => s.trim()).filter(Boolean);
  }
  if (f.minUnits && f.maxUnits) {
    bb.unit_range = [parseInt(f.minUnits, 10), parseInt(f.maxUnits, 10)];
  }
  if (f.minPrice && f.maxPrice) {
    bb.price_range = [parseFloat(f.minPrice), parseFloat(f.maxPrice)];
  }
  return Object.keys(bb).length ? bb : null;
}

export default function SignupScreen({ onSignedUp, onSwitchToLogin }) {
  const [f, setF] = useState({
    name: '', entityName: '',
    capFloor: '7', minDscr: '1.20', targetCoc: '8',
    markets: '',
    minUnits: '', maxUnits: '',
    minPrice: '', maxPrice: '',
  });
  const set = (k) => (e) => setF((prev) => ({ ...prev, [k]: e.target.value }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!f.name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await signup({
        name: f.name.trim(),
        entity_name: f.entityName.trim() || null,
        buy_box: collectBuyBox(f),
      });
      onSignedUp();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="login-root">
      <div className="login-card signup-card">
        <div className="login-brand">Reeve</div>
        <div className="login-tagline">Create your account.</div>

        <form onSubmit={submit}>
          <div className="signup-section">
            <label className="login-label">Your name</label>
            <input className="login-input" value={f.name} onChange={set('name')}
              placeholder="James Madison" autoFocus disabled={busy} required />
            <label className="login-label" style={{ marginTop: 14 }}>Entity (optional)</label>
            <input className="login-input" value={f.entityName} onChange={set('entityName')}
              placeholder="Oakwood Holdings LLC" disabled={busy} />
          </div>

          <div className="signup-section">
            <div className="signup-section-head">Buy-box (all optional — edit later in Settings)</div>
            <div className="signup-grid-3">
              <div>
                <label className="login-label">Cap floor</label>
                <div className="input-suffix">
                  <input className="login-input" value={f.capFloor} onChange={set('capFloor')}
                    inputMode="decimal" placeholder="7" disabled={busy} />
                  <span>%</span>
                </div>
              </div>
              <div>
                <label className="login-label">Min DSCR</label>
                <input className="login-input" value={f.minDscr} onChange={set('minDscr')}
                  inputMode="decimal" placeholder="1.20" disabled={busy} />
              </div>
              <div>
                <label className="login-label">Target CoC</label>
                <div className="input-suffix">
                  <input className="login-input" value={f.targetCoc} onChange={set('targetCoc')}
                    inputMode="decimal" placeholder="8" disabled={busy} />
                  <span>%</span>
                </div>
              </div>
            </div>

            <label className="login-label" style={{ marginTop: 14 }}>Markets (comma-separated)</label>
            <input className="login-input" value={f.markets} onChange={set('markets')}
              placeholder="Westfield, NJ; Columbus, OH" disabled={busy} />

            <div className="signup-grid-2" style={{ marginTop: 14 }}>
              <div>
                <label className="login-label">Unit range</label>
                <div className="input-pair">
                  <input className="login-input" value={f.minUnits} onChange={set('minUnits')}
                    inputMode="numeric" placeholder="min" disabled={busy} />
                  <span>–</span>
                  <input className="login-input" value={f.maxUnits} onChange={set('maxUnits')}
                    inputMode="numeric" placeholder="max" disabled={busy} />
                </div>
              </div>
              <div>
                <label className="login-label">Price range</label>
                <div className="input-pair">
                  <input className="login-input" value={f.minPrice} onChange={set('minPrice')}
                    inputMode="numeric" placeholder="500000" disabled={busy} />
                  <span>–</span>
                  <input className="login-input" value={f.maxPrice} onChange={set('maxPrice')}
                    inputMode="numeric" placeholder="2000000" disabled={busy} />
                </div>
              </div>
            </div>
          </div>

          <button className="login-submit" type="submit" disabled={busy || !f.name.trim()}>
            {busy ? 'Creating…' : 'Create account'}
          </button>
        </form>

        {error && <div className="login-error">{error}</div>}

        <div className="login-note">
          Already have an investor id? <a className="login-link" onClick={onSwitchToLogin}>Sign in</a>.
        </div>
      </div>
    </div>
  );
}
