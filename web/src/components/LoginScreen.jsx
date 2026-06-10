import React, { useState } from 'react';
import { login } from '../auth.js';

export default function LoginScreen({ onLoggedIn, onSwitchToSignup }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (busy || !email.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      await login({ email: email.trim(), password });
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
          <label className="login-label">Email</label>
          <input className="login-input" type="email" value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com" autoFocus disabled={busy} autoComplete="email" />
          <label className="login-label" style={{ marginTop: 14 }}>Password</label>
          <input className="login-input" type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••" disabled={busy} autoComplete="current-password" />
          <button className="login-submit" type="submit" disabled={busy || !email.trim() || !password}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        {error && <div className="login-error">{error}</div>}

        <div className="login-note">
          New here? <a className="login-link" onClick={onSwitchToSignup}>Create an account</a>.
        </div>
      </div>
    </div>
  );
}
