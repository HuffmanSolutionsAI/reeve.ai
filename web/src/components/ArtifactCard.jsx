import React from 'react';
import BookkeepingReport from './BookkeepingReport.jsx';
import DealCard from './DealCard.jsx';
import LoiDraft from './LoiDraft.jsx';
import MorningBrief from './MorningBrief.jsx';
import SourcingSummary from './SourcingSummary.jsx';
import TenantMessage from './TenantMessage.jsx';

// Switch on payload.type — new artifact types add a case here.
export default function ArtifactCard({ payload, pending }) {
  if (!payload) return null;
  switch (payload.type) {
    case 'deal_analysis': return <DealCard payload={payload} />;
    case 'morning_brief': return <MorningBrief payload={payload} />;
    case 'sourcing_summary': return <SourcingSummary payload={payload} />;
    case 'bookkeeping_report': return <BookkeepingReport payload={payload} />;
    case 'loi_draft': return <LoiDraft payload={payload} pending={pending} />;
    case 'tenant_message': return <TenantMessage payload={payload} pending={pending} />;
    default:
      return (
        <div className="card">
          <div className="card-title">Artifact: {payload.type}</div>
          <pre style={{ fontSize: 11, marginTop: 8, overflow: 'auto' }}>
            {JSON.stringify(payload, null, 2)}
          </pre>
        </div>
      );
  }
}
