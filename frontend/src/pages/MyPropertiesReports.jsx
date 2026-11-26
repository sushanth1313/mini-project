import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  Bookmark,
  FileDown,
  FileText,
  FolderKanban,
  GitCompare,
  MapPin,
} from 'lucide-react';
import {
  downloadReportUrl,
  generateReport,
  getProperties,
  getReports,
  getSavedProperties,
  toggleSavedProperty,
} from '../api/client';
import CompareProperties from './CompareProperties';

export default function MyPropertiesReports() {
  const [tab, setTab] = useState('properties'); // properties | compare | reports
  const [properties, setProperties] = useState([]);
  const [savedIds, setSavedIds] = useState(new Set());
  const [reports, setReports] = useState([]);
  const [savedOnly, setSavedOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [talukFilter, setTalukFilter] = useState('');
  const [generatingId, setGeneratingId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const loadAll = async () => {
    setLoading(true);
    setErr('');
    try {
      const [pRes, sRes, rRes] = await Promise.all([
        getProperties(),
        getSavedProperties().catch(() => ({ data: { saved_properties: [] } })),
        getReports().catch(() => ({ data: { reports: [] } })),
      ]);
      const pList = pRes.data?.properties || [];
      const myPropIds = new Set(pList.map((p) => p.id));
      setProperties(pList);
      setSavedIds(new Set((sRes.data?.saved_properties || []).map((x) => x.id)));
      const allRpts = rRes.data?.reports || [];
      setReports(myPropIds.size > 0 ? allRpts.filter((r) => myPropIds.has(r.property_id)) : []);
    } catch (e) {
      setErr(e?.message || 'Failed to load properties and reports.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleToggleSave = async (propId) => {
    const res = await toggleSavedProperty(propId);
    setSavedIds((prev) => {
      const next = new Set(prev);
      if (res.data.saved) next.add(propId);
      else next.delete(propId);
      return next;
    });
  };

  const handleGeneratePdf = async (propId) => {
    setGeneratingId(propId);
    setErr('');
    try {
      const res = await generateReport(propId);
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Mysuru_Property_Evaluation_${propId}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
      loadAll();
    } catch (e) {
      setErr(e?.response?.data?.error || 'Could not generate evaluation PDF.');
    } finally {
      setGeneratingId(null);
    }
  };

  const visibleProps = properties.filter((p) => {
    if (savedOnly && !savedIds.has(p.id)) return false;
    if (talukFilter && (p.taluk || '').toLowerCase() !== talukFilter.toLowerCase()) return false;
    const q = searchQuery.trim().toLowerCase();
    if (!q) return true;
    return (
      String(p.name || '').toLowerCase().includes(q) ||
      String(p.village_or_locality || '').toLowerCase().includes(q) ||
      String(p.taluk || '').toLowerCase().includes(q) ||
      String(p.id).includes(q)
    );
  });
  const talukOptions = [...new Set(properties.map((p) => p.taluk).filter(Boolean))];

  if (loading) return <div className="loading-state"><div className="spinner" />Loading My Properties &amp; Reports...</div>;

  return (
    <div className="page-body fade-in">
      <div className="page-header">
        <div className="page-header-text">
          <h2>My Properties &amp; Reports</h2>
          <p>Review saved &amp; evaluated parcels, compare up to 3 properties side-by-side, and download PDF reports.</p>
        </div>
        <Link to="/student/evaluate" className="btn btn-primary btn-sm">Evaluate New Property</Link>
      </div>

      {/* Sub-view Switcher */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '22px' }}>
        <button type="button" onClick={() => setTab('properties')} className={`btn btn-sm ${tab === 'properties' ? 'btn-primary' : 'btn-secondary'}`}>
          <FolderKanban size={14} /> Evaluations &amp; Saved ({properties.length})
        </button>
        <button type="button" onClick={() => setTab('compare')} className={`btn btn-sm ${tab === 'compare' ? 'btn-primary' : 'btn-secondary'}`}>
          <GitCompare size={14} /> Compare Saved Properties
        </button>
        <button type="button" onClick={() => setTab('reports')} className={`btn btn-sm ${tab === 'reports' ? 'btn-primary' : 'btn-secondary'}`}>
          <FileDown size={14} /> Downloaded Reports ({reports.length})
        </button>
      </div>

      {err && (
        <div className="alert alert-danger" style={{ marginBottom: 16 }}>
          <AlertTriangle size={16} /> {err}
        </div>
      )}

      {tab === 'properties' && (
        <div className="space-y-4">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px', marginBottom: '14px' }}>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
              <input
                type="text"
                className="form-control"
                style={{ width: 230, paddingBlock: 6, fontSize: 13 }}
                placeholder="Search property, locality, ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <select
                className="form-control"
                style={{ width: 'auto', paddingBlock: 6, fontSize: 13 }}
                value={talukFilter}
                onChange={(e) => setTalukFilter(e.target.value)}
              >
                <option value="">All Taluks</option>
                {talukOptions.map((t) => (
                  <option key={t} value={t}>{t} Taluk</option>
                ))}
              </select>
            </div>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--text-2)', cursor: 'pointer' }}>
              <input type="checkbox" checked={savedOnly} onChange={(e) => setSavedOnly(e.target.checked)} />
              Show bookmarked / saved shortlist only ({savedIds.size})
            </label>
          </div>

          {visibleProps.length === 0 ? (
            <div className="empty-state">
              <Bookmark size={36} />
              <h4>No properties found</h4>
              <p>Run a property evaluation or uncheck saved-only filter to view your evaluated parcels.</p>
              <Link to="/student/evaluate" className="btn btn-primary" style={{ marginTop: 12 }}>Evaluate Property</Link>
            </div>
          ) : (
            <div className="grid grid-3" style={{ gap: '18px' }}>
              {visibleProps.map((p) => {
                const ev = p.latest_evaluation;
                const isSaved = savedIds.has(p.id);
                return (
                  <div key={p.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '15px', color: 'var(--text-primary)' }}>{p.name || p.village_or_locality}</div>
                        <div style={{ fontSize: '12px', color: 'var(--text-3)' }}>
                          <MapPin size={12} style={{ display: 'inline', marginRight: 4 }} />
                          {p.village_or_locality} · {p.taluk} Taluk
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleToggleSave(p.id)}
                        style={{
                          background: isSaved ? '#E7F5EC' : '#F6F8F6',
                          border: `1px solid ${isSaved ? '#144D29' : '#E3E8E4'}`,
                          borderRadius: '6px',
                          padding: '5px 7px',
                          cursor: 'pointer',
                          color: isSaved ? '#144D29' : '#6E7B73',
                        }}
                      >
                        <Bookmark size={14} fill={isSaved ? 'currentColor' : 'none'} />
                      </button>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                      Area: <strong>{p.land_area_sqft?.toLocaleString()} sq.ft</strong> · Type: <strong>{p.land_type}</strong>
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>
                      Evaluated: {ev?.created_at ? new Date(ev.created_at).toLocaleDateString() : 'Pending'} · Status: <strong>{ev ? 'Completed' : 'Pending'}</strong>
                    </div>
                    {ev && (
                      <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--accent)' }}>
                        ₹{ev.predicted_total_price ? (ev.predicted_total_price / 100000).toFixed(2) : '--'} L
                        <span style={{ fontSize: '11px', color: 'var(--text-3)', fontWeight: 400, marginLeft: 8 }}>
                          Score {ev.overall_score ?? '--'}/100
                        </span>
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: 'auto' }}>
                      <Link to={`/student/map?property_id=${p.id}`} className="btn btn-secondary btn-sm" style={{ flex: 1, justifyContent: 'center' }}>
                        Open Analysis
                      </Link>
                      <button
                        type="button"
                        disabled={!ev || generatingId === p.id}
                        onClick={() => handleGeneratePdf(p.id)}
                        className="btn btn-primary btn-sm"
                        style={{ flex: 1, justifyContent: 'center' }}
                      >
                        <FileDown size={13} /> {generatingId === p.id ? 'Generating...' : 'PDF'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {tab === 'compare' && (
        <div style={{ margin: '-20px' }}>
          <CompareProperties />
        </div>
      )}

      {tab === 'reports' && (
        <div className="card">
          {reports.length === 0 ? (
            <div className="empty-state">
              <FileText size={36} />
              <h4>No PDF Reports Generated Yet</h4>
              <p>Open any evaluated property and click PDF to create a 12-section A4 report.</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Report File</th>
                    <th>Property ID</th>
                    <th>Generated</th>
                    <th>Size</th>
                    <th>Download</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((r) => (
                    <tr key={r.id}>
                      <td style={{ fontWeight: 600 }}>{r.filename}</td>
                      <td>#{r.property_id}</td>
                      <td>{r.generated_at ? new Date(r.generated_at).toLocaleString() : '—'}</td>
                      <td>{r.file_size_bytes ? `${Math.round(r.file_size_bytes / 1024)} KB` : '—'}</td>
                      <td>
                        <a href={downloadReportUrl(r.id)} className="btn btn-primary btn-sm" target="_blank" rel="noreferrer">
                          <FileDown size={13} /> Download PDF
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
