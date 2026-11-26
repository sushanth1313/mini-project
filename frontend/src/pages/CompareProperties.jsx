import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getProperties } from '../api/client';
import { GitCompare, Map, Activity, CheckCircle2, AlertTriangle } from 'lucide-react';

export default function CompareProperties() {
  const [searchParams] = useSearchParams();
  const addPropId = searchParams.get('add');
  
  const [properties, setProperties] = useState([]);
  const [selectedIds, setSelectedIds] = useState(['', '', '']); // up to 3
  const [dupWarning, setDupWarning] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getProperties().then(res => {
      setProperties(res.data.properties);
      const props = res.data.properties;
      
      let ids = ['', '', ''];
      
      if (addPropId) {
        ids[0] = parseInt(addPropId);
        if (props.length > 1) {
          const otherProp = props.find(p => p.id !== parseInt(addPropId));
          if (otherProp) ids[1] = otherProp.id;
        }
      } else if (props.length >= 2) {
        ids[0] = props[0].id;
        ids[1] = props[1].id;
      }
      setSelectedIds(ids);
      
    }).finally(() => setLoading(false));
  }, [addPropId]);

  const handleSelect = (index, value) => {
    const parsed = value ? parseInt(value, 10) : '';
    if (parsed !== '' && selectedIds.some((id, idx) => idx !== index && id === parsed)) {
      setDupWarning('Duplicate property selection blocked: each comparison slot must reference a distinct evaluated property.');
      return;
    }
    setDupWarning('');
    const newIds = [...selectedIds];
    newIds[index] = parsed;
    setSelectedIds(newIds);
  };

  const activeProps = selectedIds
    .map(id => properties.find(p => p.id === id))
    .filter(Boolean);

  if (loading) return <div className="loading-state"><div className="spinner"></div>Loading...</div>;

  return (
    <div className="page-body">
      <div className="page-header fade-in">
        <div className="page-header-text">
          <h2>Compare Properties</h2>
          <p>Side-by-side evaluation and intelligence comparison.</p>
        </div>
      </div>

      <div className="card fade-in" style={{ padding: 24, animationDelay: '0.1s' }}>
        {dupWarning && (
          <div className="alert alert-warn" style={{ marginBottom: 16 }}>
            <AlertTriangle size={16} />
            <span style={{ fontSize: 13 }}>{dupWarning}</span>
          </div>
        )}
        
        {/* Selectors */}
        <div className="grid grid-3" style={{ marginBottom: 32 }}>
          {[0, 1, 2].map(i => (
            <div key={i} className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" style={{ color: 'var(--accent)' }}>Property Slot {i + 1}</label>
              <select className="form-control" value={selectedIds[i]} onChange={e => handleSelect(i, e.target.value)}>
                <option value="">-- Empty Slot --</option>
                {properties.map(p => {
                  const takenElsewhere = selectedIds.some((id, idx) => idx !== i && id === p.id);
                  return (
                    <option key={p.id} value={p.id} disabled={takenElsewhere}>
                      {p.name || `Prop #${p.id}`} ({p.village_or_locality}, {p.taluk}){takenElsewhere ? ' — Already Selected' : ''}
                    </option>
                  );
                })}
              </select>
            </div>
          ))}
        </div>

        {activeProps.length === 0 ? (
          <div className="empty-state">
            <GitCompare size={48} />
            <h3>Comparison Matrix</h3>
            <p>Select up to 3 properties above to compare their intelligence profiles.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data-table compare-table" style={{ minWidth: 800 }}>
              <thead>
                <tr>
                  <th style={{ width: 220, background: '#F0F4F1', color: '#141C17' }}>Intelligence Metric</th>
                  {activeProps.map(p => (
                    <th key={p.id} style={{ width: `${100 / activeProps.length}%`, fontSize: '14px', color: '#144D29', textAlign: 'center', background: '#F0F4F1' }}>
                      {p.name || `Property #${p.id}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr style={{ background: 'var(--surface-2)' }}><td colSpan={4} style={{ fontWeight: 600, fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--accent)' }}>Core Information</td></tr>
                <tr>
                  <td><Map size={14} style={{ display: 'inline', marginRight: 8, verticalAlign: 'middle' }}/>Location</td>
                  {activeProps.map(p => <td key={p.id} style={{ textAlign: 'center' }}>{p.village_or_locality}, {p.taluk}</td>)}
                </tr>
                <tr>
                  <td><Activity size={14} style={{ display: 'inline', marginRight: 8, verticalAlign: 'middle' }}/>Area</td>
                  {activeProps.map(p => <td key={p.id} style={{ textAlign: 'center' }}>{p.land_area_sqft} sq.ft</td>)}
                </tr>
                <tr>
                  <td>Type</td>
                  {activeProps.map(p => <td key={p.id} style={{ textAlign: 'center' }}>{p.land_type}</td>)}
                </tr>

                <tr style={{ background: 'var(--surface-2)' }}><td colSpan={4} style={{ fontWeight: 600, fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--accent)' }}>Valuation Intelligence</td></tr>
                <tr>
                  <td>Predicted Total Value</td>
                  {activeProps.map(p => (
                    <td key={p.id} style={{ fontWeight: 600, color: 'var(--accent)', textAlign: 'center', fontSize: '16px' }}>
                      {p.latest_evaluation?.predicted_total_price ? `₹${(p.latest_evaluation.predicted_total_price / 100000).toFixed(2)} L` : 'N/A'}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Predicted per sq.ft</td>
                  {activeProps.map(p => (
                    <td key={p.id} style={{ textAlign: 'center' }}>
                      {p.latest_evaluation?.predicted_price_per_sqft ? `₹${p.latest_evaluation.predicted_price_per_sqft.toLocaleString('en-IN')}` : 'N/A'}
                    </td>
                  ))}
                </tr>

                <tr style={{ background: 'var(--surface-2)' }}><td colSpan={4} style={{ fontWeight: 600, fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--accent)' }}>Evaluation Scores</td></tr>
                <tr>
                  <td style={{ fontWeight: 700, color: '#141C17' }}>OVERALL SCORE</td>
                  {activeProps.map(p => (
                    <td key={p.id} style={{ textAlign: 'center' }}>
                      {p.latest_evaluation ? (
                         <div className={`badge badge-${p.latest_evaluation.overall_score >= 70 ? 'ok' : p.latest_evaluation.overall_score >= 50 ? 'warn' : 'danger'}`} style={{ fontSize: '18px', padding: '6px 12px' }}>
                           {Number(p.latest_evaluation.overall_score).toFixed(1)}/100
                         </div>
                      ) : <span style={{ color: 'var(--text-3)' }}>N/A</span>}
                    </td>
                  ))}
                </tr>
                
                {(() => {
                  const keys = [
                    { label: 'Location (Connectivity)', type: 'location_breakdown' },
                    { label: 'Facilities (GIS)', type: 'facility_breakdown' },
                    { label: 'Infrastructure', type: 'infrastructure_breakdown' },
                    { label: 'Environment Risk', type: 'environment_breakdown' },
                  ];

                  return keys.map(k => (
                    <tr key={k.type}>
                      <td>{k.label}</td>
                      {activeProps.map(p => {
                        if (!p.latest_evaluation) return <td key={p.id} style={{ textAlign: 'center' }}>N/A</td>;
                        try {
                          const brk = typeof p.latest_evaluation[k.type] === 'string' 
                            ? JSON.parse(p.latest_evaluation[k.type]) 
                            : p.latest_evaluation[k.type];
                          return (
                            <td key={p.id} style={{ textAlign: 'center' }}>
                              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                <div style={{ fontSize: '16px', fontWeight: '600', color: brk?.score >= (brk?.max || 100)*0.7 ? 'var(--ok)' : brk?.score >= (brk?.max || 100)*0.5 ? 'var(--warn)' : 'var(--danger)' }}>
                                  {brk?.score !== null && brk?.score !== undefined ? Math.round(brk.score) : 'N/A'}
                                </div>
                                <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>/ {brk?.max || 100}</div>
                              </div>
                            </td>
                          );
                        } catch(e) {
                          return <td key={p.id} style={{ textAlign: 'center' }}>-</td>;
                        }
                      })}
                    </tr>
                  ));
                })()}

                <tr style={{ background: 'var(--surface-2)' }}><td colSpan={4} style={{ fontWeight: 600, fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--accent)' }}>Risks & Warnings</td></tr>
                <tr>
                  <td>Identified Risks</td>
                  {activeProps.map(p => {
                    if (!p.latest_evaluation) return <td key={p.id} style={{ textAlign: 'center' }}>N/A</td>;
                    try {
                      const warns = typeof p.latest_evaluation.warnings === 'string' 
                        ? JSON.parse(p.latest_evaluation.warnings) 
                        : p.latest_evaluation.warnings;
                      return (
                        <td key={p.id}>
                          {warns && warns.length > 0 ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', alignItems: 'center' }}>
                              {warns.map((w, i) => (
                                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--warn)', fontSize: '12px' }}>
                                  <AlertTriangle size={12} /> {w}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '6px', color: 'var(--ok)', fontSize: '13px', fontWeight: '600' }}>
                              <CheckCircle2 size={14} /> Clear
                            </div>
                          )}
                        </td>
                      );
                    } catch(e) { return <td key={p.id} style={{ textAlign: 'center' }}>-</td>; }
                  })}
                </tr>

              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
