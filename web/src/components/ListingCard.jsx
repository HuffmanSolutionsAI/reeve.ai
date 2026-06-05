import React from 'react';

const fmt$ = (v) => v === null || v === undefined ? '—' : `$${Math.round(v).toLocaleString()}`;

export default function ListingCard({ payload, pending }) {
  if (!payload || payload.type !== 'listing') return null;
  const {
    unit_label, address, asking_rent, deposit, term_months, available_from,
    headline, description, amenities, channels, posted_at, listing_urls,
  } = payload;

  return (
    <div className="card listing">
      <div className="card-top">
        <div>
          <div className="card-title">{headline || `Unit ${unit_label || ''}`}</div>
          <div className="card-meta">
            {address}{unit_label ? ` · Unit ${unit_label}` : ''}
          </div>
        </div>
        <div className="verdict" data-decision={pending ? 'conditional' : 'pursue'}>
          {pending ? 'Awaiting sign-off' : posted_at ? 'Posted' : 'Draft'}
        </div>
      </div>

      <div className="loi-grid">
        <div><div className="loi-label">Rent</div><div className="loi-value">{fmt$(asking_rent)}/mo</div></div>
        <div><div className="loi-label">Deposit</div><div className="loi-value">{fmt$(deposit)}</div></div>
        <div><div className="loi-label">Term</div><div className="loi-value">{term_months || 12}mo</div></div>
        <div><div className="loi-label">Available</div><div className="loi-value">{available_from}</div></div>
        <div><div className="loi-label">Channels</div><div className="loi-value">{(channels || []).length}</div></div>
      </div>

      {description && <p className="card-note" style={{ marginTop: 12 }}>{description}</p>}

      {amenities?.length > 0 && (
        <div className="assumptions">
          {amenities.map((a, i) => <span key={i}>{a}</span>)}
        </div>
      )}

      {listing_urls && Object.keys(listing_urls).length > 0 && (
        <div className="listing-urls">
          {Object.entries(listing_urls).map(([ch, url]) => (
            <a key={ch} href={url} target="_blank" rel="noreferrer" className="listing-url">{ch}</a>
          ))}
        </div>
      )}

      {posted_at && <div className="loi-sent">Posted {new Date(posted_at).toLocaleString()}</div>}
    </div>
  );
}
