import React, { useEffect, useState } from 'react';
import * as api from '../api.js';
import { clearSession } from '../auth.js';

function fmtPct(v) {
  if (v === null || v === undefined) return '';
  return (v * 100).toFixed(2).replace(/\.?0+$/, '');
}

function Row({ label, value, onEdit }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">{label}</div>
      <div className="settings-row-value">{value || <span className="settings-empty">—</span>}</div>
      {onEdit && <button className="settings-edit" onClick={onEdit}>edit</button>}
    </div>
  );
}

export default function SettingsView({ onChanged }) {
  const [me, setMe] = useState(null);
  const [flash, setFlash] = useState(null);
  const [editing, setEditing] = useState(null);   // 'profile' | 'buy_box' | null
  const [pending, setPending] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const refresh = () => api.fetchMe().then(setMe).catch(() => {});
  useEffect(() => { refresh(); }, []);

  const saveProfile = async (patch) => {
    setPending(true);
    try {
      const next = await api.updateMe(patch);
      setMe(next);
      setEditing(null);
      setFlash('Profile updated.');
      onChanged?.();
    } catch (e) {
      setFlash(`Error: ${e.message}`);
    } finally {
      setPending(false);
    }
  };

  const saveBuyBox = async (patch) => {
    setPending(true);
    try {
      const next = await api.updateBuyBox(patch);
      setMe(next);
      setEditing(null);
      setFlash('Buy-box updated.');
      onChanged?.();
    } catch (e) {
      setFlash(`Error: ${e.message}`);
    } finally {
      setPending(false);
    }
  };

  const reset = async () => {
    setPending(true);
    try {
      const r = await api.deleteMe();
      clearSession();
      window.alert(
        `Wiped ${r.counts.investors} investor, ${r.counts.portfolios} portfolios, ` +
        `${r.counts.buildings} buildings, ${r.counts.units} units, ` +
        `${r.counts.deals} deals, ${r.counts.transactions} transactions.\n\n` +
        `You'll be returned to the login screen.`,
      );
      window.location.reload();
    } catch (e) {
      setFlash(`Error: ${e.message}`);
      setPending(false);
    }
  };

  if (!me) return <main className="chat" style={{ padding: 24 }}>Loading…</main>;
  const bb = me.buy_box || {};

  return (
    <main className="chat" style={{ padding: '24px 28px', overflowY: 'auto' }}>
      <h2 style={{ fontFamily: 'Fraunces, serif', marginBottom: 18 }}>Settings</h2>
      {flash && <div className="flash">{flash}</div>}

      {/* ----- Profile ------------------------------------------------- */}
      <div className="settings-block">
        <div className="settings-block-head">Profile</div>
        {editing === 'profile' ? (
          <ProfileForm me={me} pending={pending}
            onCancel={() => setEditing(null)} onSave={saveProfile} />
        ) : (
          <>
            <Row label="Name" value={me.name} onEdit={() => setEditing('profile')} />
            <Row label="Entity" value={me.entity_name} onEdit={() => setEditing('profile')} />
            <Row label="Investor id" value={<code>{me._id}</code>} />
          </>
        )}
      </div>

      {/* ----- Buy-box ------------------------------------------------- */}
      <div className="settings-block">
        <div className="settings-block-head">Buy-box</div>
        {editing === 'buy_box' ? (
          <BuyBoxForm bb={bb} pending={pending}
            onCancel={() => setEditing(null)} onSave={saveBuyBox} />
        ) : (
          <>
            <Row label="Cap floor" value={bb.cap_floor != null ? `${fmtPct(bb.cap_floor)}%` : ''} onEdit={() => setEditing('buy_box')} />
            <Row label="Min DSCR" value={bb.min_dscr != null ? bb.min_dscr : ''} onEdit={() => setEditing('buy_box')} />
            <Row label="Target CoC" value={bb.target_coc != null ? `${fmtPct(bb.target_coc)}%` : ''} onEdit={() => setEditing('buy_box')} />
            <Row label="Markets" value={(bb.markets || []).join(', ')} onEdit={() => setEditing('buy_box')} />
            <Row label="Unit range" value={bb.unit_range ? `${bb.unit_range[0]}–${bb.unit_range[1]}` : ''} onEdit={() => setEditing('buy_box')} />
            <Row label="Price range" value={bb.price_range ? `$${bb.price_range[0].toLocaleString()}–$${bb.price_range[1].toLocaleString()}` : ''} onEdit={() => setEditing('buy_box')} />
          </>
        )}
      </div>

      {/* ----- Danger zone -------------------------------------------- */}
      <div className="settings-block danger">
        <div className="settings-block-head">Reset</div>
        <p style={{ fontSize: 13, color: 'var(--ink-soft)', marginBottom: 12 }}>
          Deletes this account and every portfolio, building, deal, transaction,
          conversation, and audit row scoped to it. Cannot be undone.
        </p>
        {!confirmDelete ? (
          <button className="btn-reject" onClick={() => setConfirmDelete(true)}>Wipe account</button>
        ) : (
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-reject" disabled={pending} onClick={reset}>
              {pending ? 'Wiping…' : 'Yes, wipe everything'}
            </button>
            <button className="btn-approve" disabled={pending} onClick={() => setConfirmDelete(false)} style={{ background: 'var(--ink-soft)' }}>
              Cancel
            </button>
          </div>
        )}
      </div>
    </main>
  );
}

function ProfileForm({ me, pending, onSave, onCancel }) {
  const [name, setName] = useState(me.name || '');
  const [entity, setEntity] = useState(me.entity_name || '');
  return (
    <form className="settings-form" onSubmit={(e) => { e.preventDefault(); onSave({ name, entity_name: entity || null }); }}>
      <label className="login-label">Name</label>
      <input className="login-input" value={name} onChange={(e) => setName(e.target.value)} required />
      <label className="login-label" style={{ marginTop: 14 }}>Entity</label>
      <input className="login-input" value={entity} onChange={(e) => setEntity(e.target.value)} />
      <div className="settings-form-actions">
        <button className="btn-approve" type="submit" disabled={pending || !name.trim()}>Save</button>
        <button className="btn-reject" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function BuyBoxForm({ bb, pending, onSave, onCancel }) {
  const [f, setF] = useState({
    capFloor: bb.cap_floor != null ? (bb.cap_floor * 100).toString() : '',
    minDscr: bb.min_dscr != null ? bb.min_dscr.toString() : '',
    targetCoc: bb.target_coc != null ? (bb.target_coc * 100).toString() : '',
    markets: (bb.markets || []).join(', '),
    minUnits: bb.unit_range ? bb.unit_range[0].toString() : '',
    maxUnits: bb.unit_range ? bb.unit_range[1].toString() : '',
    minPrice: bb.price_range ? bb.price_range[0].toString() : '',
    maxPrice: bb.price_range ? bb.price_range[1].toString() : '',
  });
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    const patch = {};
    if (f.capFloor !== '') patch.cap_floor = parseFloat(f.capFloor) / 100;
    if (f.minDscr !== '') patch.min_dscr = parseFloat(f.minDscr);
    if (f.targetCoc !== '') patch.target_coc = parseFloat(f.targetCoc) / 100;
    // Markets: empty string clears nothing (we'd need a separate "clear" flow).
    // To replace, send the full list. To leave alone, omit the field — pass
    // null here means "don't include in patch".
    if (f.markets.trim() !== (bb.markets || []).join(', ').trim()) {
      patch.markets = f.markets.split(',').map((s) => s.trim()).filter(Boolean);
    }
    if (f.minUnits && f.maxUnits) {
      patch.unit_range = [parseInt(f.minUnits, 10), parseInt(f.maxUnits, 10)];
    }
    if (f.minPrice && f.maxPrice) {
      patch.price_range = [parseFloat(f.minPrice), parseFloat(f.maxPrice)];
    }
    if (Object.keys(patch).length === 0) return;
    onSave(patch);
  };

  return (
    <form className="settings-form" onSubmit={submit}>
      <div className="signup-grid-3">
        <div>
          <label className="login-label">Cap floor</label>
          <div className="input-suffix"><input className="login-input" value={f.capFloor} onChange={set('capFloor')} inputMode="decimal" /><span>%</span></div>
        </div>
        <div>
          <label className="login-label">Min DSCR</label>
          <input className="login-input" value={f.minDscr} onChange={set('minDscr')} inputMode="decimal" />
        </div>
        <div>
          <label className="login-label">Target CoC</label>
          <div className="input-suffix"><input className="login-input" value={f.targetCoc} onChange={set('targetCoc')} inputMode="decimal" /><span>%</span></div>
        </div>
      </div>
      <label className="login-label" style={{ marginTop: 14 }}>Markets (comma-separated; full list replaces)</label>
      <input className="login-input" value={f.markets} onChange={set('markets')} />
      <div className="signup-grid-2" style={{ marginTop: 14 }}>
        <div>
          <label className="login-label">Unit range</label>
          <div className="input-pair">
            <input className="login-input" value={f.minUnits} onChange={set('minUnits')} inputMode="numeric" placeholder="min" />
            <span>–</span>
            <input className="login-input" value={f.maxUnits} onChange={set('maxUnits')} inputMode="numeric" placeholder="max" />
          </div>
        </div>
        <div>
          <label className="login-label">Price range</label>
          <div className="input-pair">
            <input className="login-input" value={f.minPrice} onChange={set('minPrice')} inputMode="numeric" placeholder="min" />
            <span>–</span>
            <input className="login-input" value={f.maxPrice} onChange={set('maxPrice')} inputMode="numeric" placeholder="max" />
          </div>
        </div>
      </div>
      <div className="settings-form-actions">
        <button className="btn-approve" type="submit" disabled={pending}>Save</button>
        <button className="btn-reject" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
