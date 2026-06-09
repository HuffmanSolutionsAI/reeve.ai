import React, { useState } from 'react';
import { devLogin, login } from '../auth.js';

export default function LoginScreen({ onLoggedIn, onSwitchToSignup }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [devMode, setDevMode] = useState(false);
  const [investorId, setInvestorId] = useState(import.meta.env.VITE_INVESTOR_ID || '');

  const submit = async (e) => {
    e?.preventDefault?.();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (devMode) {
        if (!investorId.trim()) { setBusy(false); return; }
        await devLogin(investorId.trim());
      } else {
        if (!email.trim() || !password) { setBusy(false); return; }
        await login({ email: email.trim(), password });
      }
      onLoggedIn();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="login-root">
      <div className="login-card">
        <div className="login-brand">Reeve</div>
        <div className="login-tagline">Chief of staff for your portfolio.</div>

        <form onSubmit={submit}>
          {devMode ? (
            <>
              <label className="login-label">Investor id</label>
              <input className="login-input" type="text" value={investorId}
                onChange={(e) => setInvestorId(e.target.value)}
                placeholder="Paste investor _id" autoFocus disabled={busy} />
            </>
          ) : (
            <>
              <label className="login-label">Email</label>
              <input className="login-input" type="email" value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com" autoFocus disabled={busy} autoComplete="email" />
              <label className="login-label" style={{ marginTop: 14 }}>Password</label>
              <input className="login-input" type="password" value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••" disabled={busy} autoComplete="current-password" />
            </>
          )}
          <button className="login-submit" type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        {error && <div className="login-error">{error}</div>}

        <div className="login-note">
          New here? <a className="login-link" onClick={onSwitchToSignup}>Create an account</a>.
          <br />
          <a className="login-link" onClick={() => { setDevMode(!devMode); setError(null); }}>
            {devMode ? 'Back to email sign-in' : 'Dev: sign in by investor id'}
          </a>
        </div>
      </div>
    </div>
  );
}
