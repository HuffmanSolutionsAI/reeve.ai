import React from 'react';

const PURPOSE_LABEL = {
  renewal_notice: 'Renewal notice',
  rent_reminder: 'Rent reminder',
  maintenance_update: 'Maintenance update',
  compliance: 'Compliance',
  general: 'General',
};

export default function TenantMessage({ payload, pending }) {
  if (!payload || payload.type !== 'tenant_message') return null;
  const { tenant_name, tenant_id, channel, to, subject, body, purpose, sent_at } = payload;

  return (
    <div className="card tenant-msg">
      <div className="card-top">
        <div>
          <div className="card-title">{PURPOSE_LABEL[purpose] || 'Tenant message'}</div>
          <div className="card-meta">
            via {channel} · to {tenant_name || tenant_id}{to ? ` <${to}>` : ''}
          </div>
        </div>
        <div className="verdict" data-decision={pending ? 'conditional' : 'pursue'}>
          {pending ? 'Awaiting sign-off' : sent_at ? 'Sent' : 'Draft'}
        </div>
      </div>

      <div className="msg-subject">{subject}</div>
      <pre className="msg-body">{body}</pre>

      {sent_at && <div className="loi-sent">Sent {new Date(sent_at).toLocaleString()}</div>}
    </div>
  );
}
