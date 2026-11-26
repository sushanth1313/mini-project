import { useState, useEffect } from 'react';
import { getReports, generateReport, getProperties, downloadReportUrl } from '../api/client';
import { FileDown, RefreshCw, AlertTriangle, FileText, CheckCircle2 } from 'lucide-react';

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [properties, setProperties] = useState([]);
  const [selectedProp, setSelectedProp] = useState('');
  const [generating, setGenerating] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getReports(), getProperties()]).then(([repRes, propRes]) => {
      setReports(repRes.data.reports);
      setProperties(propRes.data.properties);
    }).finally(() => setLoading(false));
  }, []);

  const handleGenerate = async () => {
    if (!selectedProp) return;
    setGenerating(true);
    try {
      const response = await generateReport(selectedProp);
      
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      const contentDisposition = response.headers['content-disposition'];
      let filename = 'evaluation_report.pdf';
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?([^"]+)"?/);
        if (match && match[1]) {
          filename = match[1];
        }
      }
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => window.URL.revokeObjectURL(url), 100);

      const repRes = await getReports();
      setReports(repRes.data.reports);
      setSelectedProp('');
    } catch (err) {
      console.error(err);
      let errMsg = 'Unknown error';
      if (err.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          const json = JSON.parse(text);
          errMsg = json.error || errMsg;
        } catch (e) {
          errMsg = 'Server error';
        }
      } else if (err.response?.data?.error) {
        errMsg = err.response.data.error;
      } else {
        errMsg = err.message;
      }
      alert(`PDF generation failed: ${errMsg}`);
    } finally {
      setGenerating(false);
    }
  };

  if (loading) return <div className="loading-state"><div className="spinner"></div>Loading Reports...</div>;

  return (
    <div className="page-body">
      <div className="page-header fade-in">
        <div className="page-header-text">
          <h2>Evaluation Reports</h2>
          <p>Generate and download consolidated PDF reports.</p>
        </div>
      </div>

      <div className="card fade-in" style={{ marginBottom: 32, animationDelay: '0.1s' }}>
        <div className="card-header"><div className="card-title">Generate New Report</div></div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ marginBottom: 0, flex: 1, minWidth: '250px' }}>
            <label className="form-label">Select Evaluated Property</label>
            <select className="form-control" value={selectedProp} onChange={e => setSelectedProp(e.target.value)}>
              <option value="">-- Choose Property --</option>
              {properties.filter(p => p.evaluations?.length > 0).map(p => (
                <option key={p.id} value={p.id}>{p.name || `Property #${p.id}`} ({p.village_or_locality})</option>
              ))}
            </select>
          </div>
          <button className="btn btn-primary btn-lg" onClick={handleGenerate} disabled={!selectedProp || generating}>
            {generating ? <><RefreshCw size={18} className="spinner" style={{ animation: 'spin 1s linear infinite' }} /> Generating PDF...</> : <><FileDown size={18} /> Generate PDF Report</>}
          </button>
        </div>
        <div style={{ marginTop: '16px', display: 'flex', gap: '8px', fontSize: '13px', color: 'var(--text-3)' }}>
          <AlertTriangle size={16} color="var(--warn)" />
          PDF reports contain all historical scores and document status snapshots. They are permanently saved upon generation.
        </div>
      </div>

      <div className="card fade-in" style={{ animationDelay: '0.2s' }}>
        <div className="card-header"><div className="card-title">Generated Reports Archive</div></div>
        
        {reports.length === 0 ? (
          <div className="empty-state">
            <FileText size={48} />
            <h3>No Reports Found</h3>
            <p>Generate your first PDF report to view it here.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date Generated</th>
                  <th>Property Details</th>
                  <th>File Info</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {reports.map(r => {
                  const prop = properties.find(p => p.id === r.property_id);
                  return (
                    <tr key={r.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{new Date(r.generated_at).toLocaleDateString()}</div>
                        <div style={{ fontSize: '12px', color: 'var(--text-3)' }}>{new Date(r.generated_at).toLocaleTimeString()}</div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 600, color: '#141C17' }}>{prop ? prop.village_or_locality : `Prop #${r.property_id}`}</div>
                        <div style={{ fontSize: '12px', color: 'var(--text-3)' }}>ID: {r.property_id}</div>
                      </td>
                      <td>
                        <div style={{ fontFamily: 'monospace', fontSize: '12px', color: 'var(--accent)' }}>{r.filename}</div>
                        <div style={{ fontSize: '12px', color: 'var(--text-3)' }}>{(r.file_size_bytes / 1024).toFixed(1)} KB</div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--ok)', fontSize: '13px', fontWeight: '600' }}>
                          <CheckCircle2 size={16} /> Ready
                        </div>
                      </td>
                      <td>
                        <a href={downloadReportUrl(r.id)} className="btn btn-secondary btn-sm" download target="_blank" rel="noreferrer">
                          <FileDown size={14} /> Download
                        </a>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
