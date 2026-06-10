import React from 'react';
import BookkeepingReport from './BookkeepingReport.jsx';
import DealCard from './DealCard.jsx';
import ListingCard from './ListingCard.jsx';
import LoiDraft from './LoiDraft.jsx';
import MorningBrief from './MorningBrief.jsx';
import SourcingSummary from './SourcingSummary.jsx';
import TaxMemo from './TaxMemo.jsx';
import TenantMessage from './TenantMessage.jsx';
import ValueAddAnalysis from './ValueAddAnalysis.jsx';
import WorkOrder from './WorkOrder.jsx';

// Switch on payload.type — new artifact types add a case here.
export default function ArtifactCard({ payload, pending }) {
  if (!payload) return null;
  switch (payload.type) {
    case 'deal_analysis': return <DealCard payload={payload} />;
    case 'value_add_analysis': return <ValueAddAnalysis payload={payload} />;
    case 'morning_brief': return <MorningBrief payload={payload} />;
    case 'sourcing_summary': return <SourcingSummary payload={payload} />;
    case 'bookkeeping_report': return <BookkeepingReport payload={payload} />;
    case 'loi_draft': return <LoiDraft payload={payload} pending={pending} />;
    case 'tenant_message': return <TenantMessage payload={payload} pending={pending} />;
    case 'work_order': return <WorkOrder payload={payload} pending={pending} />;
    case 'listing': return <ListingCard payload={payload} pending={pending} />;
    case 'tax_memo': return <TaxMemo payload={payload} />;
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
