import React, { useState } from 'react';
import { login } from '../auth.js';

export default function LoginScreen({ onLoggedIn }) {
  const [investorId, setInvestorId] = useState(
    import.meta.env.VITE_INVESTOR_ID || '',
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!investorId.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await login(investorId.trim());
      onLoggedIn();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-root">
      <div className="login-card">
        <div className="login-brand">Reeve</div>
        <div className="login-tagline">Chief of staff for your portfolio.</div>
        <form onSubmit={submit}>
          <label className="login-label">Investor id</label>
          <input
            className="login-input"
            type="text"
            value={investorId}
            onChange={(e) => setInvestorId(e.target.value)}
            placeholder="Paste investor _id (from scripts/seed_dev.py)"
            autoFocus
            disabled={busy}
          />
          <button className="login-submit" type="submit" disabled={busy || !investorId.trim()}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        {error && <div className="login-error">{error}</div>}
        <div className="login-note">
          Dev login. Replace with real auth before production. Seed an investor with
          {' '}<code>python scripts/seed_dev.py</code> and paste the printed id above.
        </div>
      </div>
    </div>
  );
}
