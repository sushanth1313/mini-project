import { useState, useEffect } from 'react';
import { getDataSources } from '../api/client';
import { Database, ShieldCheck, ShieldAlert, CheckCircle2, AlertTriangle, Link as LinkIcon } from 'lucide-react';

export default function DataSources() {
  const [sources, setSources] = useState([]);
  const [liveStatus, setLiveStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDataSources().then(res => {
      setSources(res.data.data_sources);
      setLiveStatus(res.data.live_status);
    }).finally(() => setLoading(false));
  }, []);

  if (loading || !liveStatus) return <div className="loading-state"><div className="spinner"></div>Loading Data Sources...</div>;

  return (
    <div className="page-body">
      <div className="page-header fade-in">
        <div className="page-header-text">
          <h2>Data Sources & Provenance</h2>
          <p>Transparency regarding the data powering the evaluation models.</p>
        </div>
      </div>

      <div className="grid grid-2">
        
        {/* OPENSTREETMAP */}
        <div className="card fade-in" style={{ animationDelay: '0.1s' }}>
          <div className="card-header" style={{ marginBottom: 12, paddingBottom: 12 }}>
            <div className="card-title" style={{ fontSize: 16, color: 'var(--accent)' }}>
              <Database size={18} /> OpenStreetMap / Overpass
            </div>
            <div className={`badge badge-${liveStatus.osm?.status === 'CONNECTED' ? 'ok' : 'danger'}`}>
              {liveStatus.osm?.status || 'UNKNOWN'}
            </div>
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-2)', marginBottom: '16px' }}>
            <strong>Used for:</strong> Primary GIS source for facilities (schools, hospitals, banks) and road mapped accessibility.
          </div>
          <div className="kv-grid" style={{ marginBottom: '16px' }}>
            <div className="kv-key">Status Message</div>
            <div className="kv-val">{liveStatus.osm?.message || "Running"}</div>
            <div className="kv-key">Confidence</div>
            <div className="kv-val" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ShieldCheck size={14} color="var(--ok)" /> High
            </div>
          </div>
        </div>

        {/* GOOGLE PLACES */}
        <div className="card fade-in" style={{ animationDelay: '0.2s' }}>
          <div className="card-header" style={{ marginBottom: 12, paddingBottom: 12 }}>
            <div className="card-title" style={{ fontSize: 16, color: 'var(--accent)' }}>
              <Database size={18} /> Google Places API
            </div>
            <div className={`badge badge-${liveStatus.google?.status === 'CONNECTED' ? 'ok' : (liveStatus.google?.status === 'NOT_CONFIGURED' ? 'neutral' : 'danger')}`}>
              {liveStatus.google?.status || 'UNKNOWN'}
            </div>
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-2)', marginBottom: '16px' }}>
            <strong>Used for:</strong> Secondary authoritative GIS source for places and distances.
          </div>
          <div className="kv-grid" style={{ marginBottom: '16px' }}>
            <div className="kv-key">Status Message</div>
            <div className="kv-val">{liveStatus.google?.message || "Running"}</div>
            <div className="kv-key">Confidence</div>
            <div className="kv-val" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ShieldCheck size={14} color="var(--ok)" /> High
            </div>
          </div>
        </div>

        {/* WEB CORROBORATION */}
        <div className="card fade-in" style={{ animationDelay: '0.3s' }}>
          <div className="card-header" style={{ marginBottom: 12, paddingBottom: 12 }}>
            <div className="card-title" style={{ fontSize: 16, color: 'var(--accent)' }}>
              <LinkIcon size={18} /> Property Web Sources
            </div>
            <div className={`badge badge-${liveStatus.web?.status === 'CONNECTED' ? 'ok' : 'danger'}`}>
              {liveStatus.web?.status || 'UNKNOWN'}
            </div>
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-2)', marginBottom: '16px' }}>
            <strong>Used for:</strong> Corroboration using property platforms like Housing.com, MagicBricks, etc.
          </div>
          <div className="kv-grid" style={{ marginBottom: '16px' }}>
            <div className="kv-key">Status Message</div>
            <div className="kv-val">{liveStatus.web?.message || "Available"}</div>
            <div className="kv-key">Confidence</div>
            <div className="kv-val" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ShieldAlert size={14} color="var(--warn)" /> Moderate
            </div>
          </div>
          <div style={{ padding: '12px', background: 'var(--warn-bg)', borderLeft: '3px solid var(--warn)', fontSize: '12px', color: 'var(--text)' }}>
            <strong>Note:</strong> Used only as secondary evidence. Distances are source-reported, not exact GIS calculation.
          </div>
        </div>

        {/* NOMINATIM */}
        <div className="card fade-in" style={{ animationDelay: '0.4s' }}>
          <div className="card-header" style={{ marginBottom: 12, paddingBottom: 12 }}>
            <div className="card-title" style={{ fontSize: 16, color: 'var(--accent)' }}>
              <Database size={18} /> Nominatim API
            </div>
            <div className="badge badge-ok">CONNECTED</div>
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-2)', marginBottom: '16px' }}>
            <strong>Used for:</strong> Locality geocoding when exact coordinates are unavailable.
          </div>
          <div className="kv-grid" style={{ marginBottom: '16px' }}>
            <div className="kv-key">Confidence</div>
            <div className="kv-val" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ShieldCheck size={14} color="var(--ok)" /> High
            </div>
          </div>
          <div style={{ padding: '12px', background: 'var(--warn-bg)', borderLeft: '3px solid var(--warn)', fontSize: '12px', color: 'var(--text)' }}>
            <strong>Limitations:</strong> Returns the center point of a locality, not exact property boundaries.
          </div>
        </div>

      </div>
    </div>
  );
}
