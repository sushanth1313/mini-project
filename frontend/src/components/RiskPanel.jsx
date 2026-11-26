import { AlertTriangle, Info, CheckCircle2 } from 'lucide-react';

export default function RiskPanel({ warnings = [], environmentScore }) {
  const risks = [];
  
  if (warnings) {
    try {
      const parsed = typeof warnings === 'string' ? JSON.parse(warnings) : warnings;
      if (Array.isArray(parsed)) {
        parsed.forEach(w => risks.push({ type: 'warning', text: w }));
      }
    } catch (e) {
      // ignore
    }
  }

  // Parse environment notes
  if (environmentScore && environmentScore.notes) {
    environmentScore.notes.forEach(note => {
      if (note.includes('No penalty') || note.includes('Score')) return;
      risks.push({ type: note.includes('WARNING') ? 'danger' : 'warning', text: note });
    });
  }

  if (risks.length === 0) {
    return (
      <div className="alert alert-ok">
        <CheckCircle2 size={16} />
        <div>
          <strong>No immediate risks identified based on provided data.</strong>
          <div style={{ fontSize: 11, marginTop: 4 }}>Note: Complete physical inspection and legal verification are still strictly required.</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {risks.map((risk, i) => (
        <div key={i} className={`alert alert-${risk.type === 'danger' ? 'danger' : 'warn'}`} style={{ marginBottom: 0 }}>
          <AlertTriangle size={16} />
          <div>{risk.text}</div>
        </div>
      ))}
      <div className="disclaimer-box" style={{ marginTop: 8 }}>
        <Info size={16} />
        <div>
          <strong>Disclaimer:</strong> Risk indicators are algorithmically generated based on available data and map approximations. They do not constitute legal advice or formal environmental surveys.
        </div>
      </div>
    </div>
  );
}
