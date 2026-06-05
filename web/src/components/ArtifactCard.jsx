import React from 'react';
import DealCard from './DealCard.jsx';
import MorningBrief from './MorningBrief.jsx';

// Switch on payload.type — new artifact types add a case here.
export default function ArtifactCard({ payload }) {
  if (!payload) return null;
  switch (payload.type) {
    case 'deal_analysis': return <DealCard payload={payload} />;
    case 'morning_brief': return <MorningBrief payload={payload} />;
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
