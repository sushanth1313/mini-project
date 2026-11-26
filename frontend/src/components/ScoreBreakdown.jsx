export default function ScoreBreakdown({ scores, type }) {
  if (!scores || !scores.breakdown) {
    return <div className="empty-state" style={{ padding: '20px' }}><p>Detailed breakdown not available</p></div>;
  }

  const { breakdown, notes } = scores;

  return (
    <div>
      {Object.entries(breakdown).map(([key, data]) => {
        if (!data || typeof data !== 'object') return null;
        
        // Handle Price score breakdown separately (it doesn't have a out-of-max format)
        if (type === 'price') {
          return (
            <div key={key} style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: 4 }}>
                {key.replace(/_/g, ' ')}
              </div>
              <div style={{ fontSize: 16, fontWeight: 600 }}>
                {typeof data === 'number' ? `₹${data.toLocaleString('en-IN')}` : data}
              </div>
            </div>
          );
        }

        const score = data.score !== undefined ? data.score : 0;
        const max = data.max || 100;
        const pct = Math.max(0, Math.min(100, (score / max) * 100));
        let colorClass = 'ok';
        if (pct < 50) colorClass = 'danger';
        else if (pct < 70) colorClass = 'warn';

        return (
          <div key={key} className="score-bar-row">
            <div className="score-bar-label">
              {key.replace(/_/g, ' ')}
            </div>
            <div className="score-bar-track">
              <div className={`score-bar-fill ${colorClass}`} style={{ width: `${pct}%` }}></div>
            </div>
            <div className="score-bar-val">
              {score}/{max}
            </div>
          </div>
        );
      })}

      {notes && notes.length > 0 && (
        <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
          {notes.map((note, i) => (
            <div key={i} style={{ fontSize: 11.5, color: 'var(--text-3)', marginBottom: 4 }}>• {note}</div>
          ))}
        </div>
      )}
    </div>
  );
}
