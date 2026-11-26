import { useState, useEffect } from 'react';
import { useSearchParams, Link, useNavigate } from 'react-router-dom';
import {
  MapPin, AlertTriangle, GitCompare, FileText, FileDown,
  Activity, Map, Database, Loader2, Bookmark, Search
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { getProperty, generateReport, toggleSavedProperty } from '../api/client';
import PropertyMap from '../components/PropertyMap';
import { EmptyState, LoadingState, PageHeader, SectionCard, StatusBadge } from '../components/ui';

/** Compute data coverage % from a list of {score, weight} items where score may be null */
function calcDataCoverage(ev) {
  const components = [
    { key: 'price_score', weight: ev.price_weight ?? 30 },
    { key: 'location_score', weight: ev.location_weight ?? 25 },
    { key: 'facility_score', weight: ev.facility_weight ?? 0 },
    { key: 'environment_score', weight: ev.environment_weight ?? 10 },
    { key: 'infrastructure_score', weight: ev.infrastructure_weight ?? 20 },
    { key: 'utility_score', weight: ev.utility_weight ?? 15 },
  ];
  const totalWeight = components.reduce((s, c) => s + c.weight, 0);
  const availWeight = components
    .filter(c => ev[c.key] !== null && ev[c.key] !== undefined)
    .reduce((s, c) => s + c.weight, 0);
  return totalWeight > 0 ? Math.round((availWeight / totalWeight) * 100) : 0;
}

/** Derive GIS status label from facilities_detail */
function calcGISStatus(facilities) {
  if (!facilities || Object.keys(facilities).length === 0) return { label: 'UNAVAILABLE', color: 'var(--danger)' };
  const statuses = Object.values(facilities).map(f => f.status || 'UNKNOWN');
  if (statuses.every(s => s === 'SOURCE_UNAVAILABLE')) return { label: 'UNAVAILABLE', color: 'var(--danger)' };
  if (statuses.some(s => s === 'PARTIAL' || s === 'SOURCE_UNAVAILABLE')) return { label: 'PARTIAL', color: 'var(--warn)' };
  if (statuses.every(s => s === 'SUCCESS')) return { label: 'COMPLETE', color: 'var(--ok)' };
  if (statuses.some(s => s === 'SUCCESS')) return { label: 'COMPLETED (SPARSE OSM)', color: 'var(--warn)' };
  return { label: 'NO DATA', color: 'var(--text-3)' };
}

/** Format a score value — null → 'N/A', number → 1 decimal (matching API/PDF) */
function fmtScore(val) {
  if (val === null || val === undefined) return null;
  return Number(Number(val).toFixed(1));
}

export default function MapAnalysis() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const propertyId = searchParams.get('property_id');
  
  const [property, setProperty] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pdfGenerating, setPdfGenerating] = useState(false);
  const [pdfError, setPdfError] = useState(null);
  const [shortlistMsg, setShortlistMsg] = useState(null);
  const [facilityFilter, setFacilityFilter] = useState('');
  const [facilityStatusFilter, setFacilityStatusFilter] = useState('ALL');

  useEffect(() => {
    async function load() {
      if (!propertyId) return;
      setLoading(true);
      setError(null);
      try {
        const res = await getProperty(propertyId);
        setProperty(res.data);
      } catch (err) {
        setError(err.response?.data?.error || err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [propertyId]);

  const handleGeneratePDF = async () => {
    setPdfGenerating(true);
    setPdfError(null);
    try {
      const response = await generateReport(propertyId);

      // Verify we got actual PDF bytes, not an error JSON
      const contentType = response.headers['content-type'] || '';
      if (!contentType.includes('application/pdf')) {
        // Probably got an error response as text/JSON
        let errMsg = 'Server did not return a PDF.';
        try {
          const text = await response.data.text?.();
          const parsed = JSON.parse(text);
          errMsg = parsed.error || errMsg;
        } catch (_) {}
        throw new Error(errMsg);
      }

      if (!response.data || response.data.size === 0) {
        throw new Error('Generated PDF is empty.');
      }

      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;

      const contentDisposition = response.headers['content-disposition'] || '';
      let filename = `evaluation_report_${propertyId}.pdf`;
      const match = contentDisposition.match(/filename[^;=\n]*=([^;\n]*)/);
      if (match && match[1]) {
        filename = match[1].replace(/['"]/g, '').trim();
      }

      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (err) {
      let msg = err.message || 'PDF generation failed.';
      if (err.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          const json = JSON.parse(text);
          msg = json.error || msg;
        } catch (_) {}
      } else if (err.response?.data?.error) {
        msg = err.response.data.error;
      }
      setPdfError(msg);
    } finally {
      setPdfGenerating(false);
    }
  };

  if (!propertyId) {
    return (
      <div className="page-body">
        <div className="empty-state">
          <Map size={48} />
          <h3>No Property Selected</h3>
          <p>Please select a property from your Dashboard.</p>
          <Link to="/student" className="btn btn-primary" style={{ marginTop: 16 }}>Go to Dashboard</Link>
        </div>
      </div>
    );
  }

  if (loading) return <div className="loading-state"><div className="spinner"></div>Loading Results...</div>;

  if (error || !property) {
    return (
      <div className="page-body">
        <div className="error-state">
          <AlertTriangle size={24} />
          <h3>Analysis Unavailable</h3>
          <p>{error || 'Property not found.'}</p>
        </div>
      </div>
    );
  }

  const ev = property.evaluations?.[0];
  if (!ev) {
    return (
      <div className="page-body">
        <div className="empty-state">
          <p>No evaluation data found for this property.</p>
          <Link to="/student/evaluate" className="btn btn-primary" style={{ marginTop: 12 }}>Run Evaluation</Link>
        </div>
      </div>
    );
  }

  // Parse facilities_detail — may be in the eval dict or as a serialised JSON string
  const facilities = typeof ev.facilities_detail === 'string'
    ? JSON.parse(ev.facilities_detail)
    : ev.facilities_detail || {};

  const coordStat = (property.coordinate_status || 'LOCALITY_CENTROID').toUpperCase();
  const isExactCoords = ['SURVEY_GPS', 'SURVEYED', 'EXACT', 'EXACT_PARCEL', 'DGPS'].includes(coordStat);
  const isMapPin = coordStat === 'MAP_SELECTED';
  const isUserEntered = coordStat === 'USER_ENTERED';
  const isBrowserGps = coordStat === 'DEVICE_GPS' || coordStat === 'BROWSER_GPS';
  const isGeocoded = coordStat === 'GEOCODED' || coordStat === 'LOCALITY_GEOCODE';
  const dataCoverage = calcDataCoverage(ev);
  const gisStatus = calcGISStatus(facilities);

  // Sub-scores from real API data
  const subScores = [
    { label: 'PRICE', score: fmtScore(ev.price_score) },
    { label: 'LOCATION', score: fmtScore(ev.location_score) },
    { label: 'FACILITIES', score: fmtScore(ev.facility_score) },
    { label: 'ENVIRONMENT', score: fmtScore(ev.environment_score) },
    { label: 'INFRASTRUCTURE', score: fmtScore(ev.infrastructure_score) },
    { label: 'UTILITIES', score: fmtScore(ev.utility_score) },
  ];

  // Warnings from backend
  const warnings = Array.isArray(ev.warnings) ? ev.warnings : [];
  let locAudit = null;
  try {
    locAudit = typeof ev.location_audit === 'string' ? JSON.parse(ev.location_audit) : (ev.location_audit || null);
  } catch {
    locAudit = null;
  }
  const hasLocCorrection = Boolean(
    locAudit && (locAudit.mismatch_detected || locAudit.resolution_status === 'MINOR_SPELLING_NORMALIZED')
  );

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      <PageHeader
        eyebrow="Property Valuation & Geospatial Intelligence Report"
        breadcrumbs={['Workspace', 'Property Analysis', `${property.village_or_locality}`]}
        title={`${property.village_or_locality}, ${property.taluk}`}
        subtitle={`${property.name ? `${property.name} · ` : ''}${property.land_area_sqft?.toLocaleString()} sq.ft · ${property.land_type} · ${property.listing_type}`}
        icon={MapPin}
        actions={
          <>
            <Link to={`/student/compare?add=${property.id}`} className="btn btn-secondary btn-sm">
              <GitCompare size={14} /> Compare
            </Link>
            <Link to={`/student/documents?property_id=${property.id}`} className="btn btn-secondary btn-sm">
              <FileText size={14} /> Documents
            </Link>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleGeneratePDF}
              disabled={pdfGenerating}
            >
              {pdfGenerating
                ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Generating...</>
                : <><FileDown size={14} /> Export PDF Report</>}
            </button>
          </>
        }
      />

      {(hasLocCorrection || (property.entered_locality && property.entered_locality !== property.village_or_locality)) && (
        <div className="alert alert-warn" style={{ marginBottom: 0 }}>
          <AlertTriangle size={16} />
          <div style={{ fontSize: 13 }}>
            Location Audit: Entered <strong>{property.entered_locality || '—'}</strong> ({property.entered_taluk || property.taluk}) {'→'} Canonical Evaluation Location: <strong>{property.village_or_locality}</strong> ({property.taluk}).
          </div>
        </div>
      )}

      {/* Backend warnings */}
      {warnings.length > 0 && (
        <div className="alert alert-warn fade-in" style={{ marginBottom: 24 }}>
          <AlertTriangle size={16} />
          <div>
            {warnings.map((w, i) => <div key={i} style={{ fontSize: 13 }}>{w}</div>)}
          </div>
        </div>
      )}

      {/* PDF error */}
      {pdfError && (
        <div className="alert alert-danger fade-in" style={{ marginBottom: 24 }}>
          <AlertTriangle size={16} /> PDF generation failed: {pdfError}
        </div>
      )}

      {/* CORE RESULTS */}
      <div className="grid grid-2" style={{ marginBottom: '32px' }}>
        
        {/* VALUE PANEL */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px 24px', background: 'linear-gradient(135deg, #FFFFFF, #ECF5EE)', border: '1px solid #CBE3D1' }}>
          <div style={{ fontSize: '12px', fontWeight: 700, letterSpacing: '0.1em', color: '#4A5750', marginBottom: '12px' }}>INDICATIVE MARKET VALUE</div>
          <div style={{ fontSize: '44px', fontWeight: '800', color: '#144D29', marginBottom: '8px', lineHeight: 1, fontFamily: 'var(--font-display)' }}>
            ₹{ev.predicted_total_price ? (ev.predicted_total_price / 100000).toFixed(2) : '--'} L
          </div>
          <div style={{ fontSize: '16px', fontWeight: 600, color: '#141C17', marginBottom: '10px' }}>
            ₹{ev.predicted_price_per_sqft?.toLocaleString(undefined, { maximumFractionDigits: 2 }) || '--'} / sq.ft
          </div>
          {ev.locality_median_psf && (
            <div style={{ fontSize: '12px', color: '#4A5750', marginBottom: '12px', textAlign: 'center' }}>
              Dataset Reference: ₹{ev.locality_median_psf.toLocaleString()} / sq.ft ({ev.comparable_records_count || 0} training record(s))
            </div>
          )}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center', marginTop: 'auto' }}>
            <StatusBadge status="INFO">
              {ev.reliability_indicator?.tier ? `${ev.reliability_indicator.tier} Reliability` : `${ev.confidence_level || 'Moderate'} Confidence`}
            </StatusBadge>
            {ev.model_used && (
              <StatusBadge status="ACTIVE">{ev.model_used}</StatusBadge>
            )}
          </div>
          {ev.uncertainty_explanation && (
            <div style={{ fontSize: '11px', color: 'var(--text-3)', marginTop: '10px', textAlign: 'center', maxWidth: '420px', lineHeight: 1.45 }}>
              {ev.uncertainty_explanation}
            </div>
          )}
          {ev.reliability_indicator?.explanation && (
            <div style={{ fontSize: '12px', color: 'var(--text-3)', marginTop: '8px', textAlign: 'center', maxWidth: '420px', lineHeight: 1.5 }}>
              {ev.reliability_indicator.explanation}
            </div>
          )}
          {ev.reliability_indicator?.deviation_note && (
            <div style={{ fontSize: '12px', color: 'var(--warn)', marginTop: '8px', textAlign: 'center', maxWidth: '420px', lineHeight: 1.5 }}>
              {ev.reliability_indicator.deviation_note}
            </div>
          )}
        </div>

        {/* SCORE PANEL */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '48px 24px' }}>
          <div className="score-ring" style={{ width: '160px', height: '160px', marginBottom: '24px' }}>
            <svg viewBox="0 0 36 36" style={{ width: '100%', height: '100%' }}>
              <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--surface-2)" strokeWidth="2.5" />
              <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--ok)" strokeWidth="2.5" strokeDasharray={`${Math.max(0, Math.min(100, ev.overall_score ?? 0))}, 100`} />
            </svg>
            <div className="score-ring-label">
              <div style={{ fontSize: '36px', fontWeight: '700', color: 'var(--text-primary)' }}>{ev.overall_score !== null && ev.overall_score !== undefined ? Number(ev.overall_score).toFixed(1) : '—'}</div>
              <div style={{ fontSize: '14px', color: 'var(--text-3)' }}>/ 100</div>
            </div>
          </div>
          <div style={{ fontSize: '16px', fontWeight: '600', letterSpacing: '0.1em', color: 'var(--text)' }}>OVERALL EVALUATION</div>
          {dataCoverage < 100 && (
            <div style={{ fontSize: '12px', color: 'var(--warn)', marginTop: 8 }}>
              Based on {dataCoverage}% data coverage
            </div>
          )}
        </div>
      </div>

      {/* SUB SCORES — Chart + Metric Cards (all from real API) */}
      <div className="grid grid-2" style={{ marginBottom: '20px', alignItems: 'stretch' }}>
        <SectionCard title="Component Score Visualization" subtitle="Relative contribution of each non-null score factor">
          <div style={{ width: '100%', height: 210 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={subScores.filter((s) => s.score !== null).map((s) => ({ name: s.label, score: s.score }))}
                margin={{ top: 8, right: 12, left: -12, bottom: 4 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#E3E8E4" vertical={false} />
                <XAxis dataKey="name" stroke="#4A5750" fontSize={10} tickLine={false} />
                <YAxis domain={[0, 100]} stroke="#4A5750" fontSize={10} tickLine={false} />
                <Tooltip contentStyle={{ background: '#FFFFFF', borderColor: '#BCE0C8', borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="score" fill="#1B6336" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <div className="grid grid-2" style={{ gap: '12px' }}>
          {subScores.map((s) => (
            <div key={s.label} className="card" style={{ padding: '16px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 0 }}>
              <div style={{ fontSize: '12px', fontWeight: '700', letterSpacing: '0.06em', color: '#4A5750' }}>{s.label}</div>
              <div style={{
                fontSize: '22px', fontWeight: '800', fontFamily: 'var(--font-display)',
                color: s.score === null ? '#6E7B73' : s.score >= 70 ? '#14532D' : s.score >= 50 ? '#85520E' : '#8C2D23'
              }}>
                {s.score !== null ? s.score : 'N/A'}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* EVALUATION SCORES & WEIGHTAGES BREAKDOWN TABLE */}
      <SectionCard
        title="Evaluation Scores & Weightages"
        subtitle="Proportional scoring formula: Overall = Σ(weight × score) / Σ(available weights); missing data excluded rather than zeroed"
      >
        {(() => {
          const scoreRows = [
            { key: 'price', label: 'Price Affordability', score: ev.price_score, weight: ev.price_weight ?? 30 },
            { key: 'location', label: 'Location Quality', score: ev.location_score, weight: ev.location_weight ?? 25 },
            { key: 'facility', label: 'Nearby Facilities', score: ev.facility_score, weight: 0, informational: true },
            { key: 'environment', label: 'Environmental Safety', score: ev.environment_score, weight: ev.environment_weight ?? 10 },
            { key: 'infrastructure', label: 'Infrastructure', score: ev.infrastructure_score, weight: ev.infrastructure_weight ?? 20 },
            { key: 'utility', label: 'Utilities', score: ev.utility_score, weight: ev.utility_weight ?? 15 },
          ];
          const availW = scoreRows.filter((r) => !r.informational && r.score !== null && r.score !== undefined).reduce((s, r) => s + Number(r.weight || 0), 0);
          return (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Dimension</th>
                    <th>Score (0–100)</th>
                    <th>Weight</th>
                    <th>Weighted Contribution</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {scoreRows.map((r) => {
                    const hasScore = r.score !== null && r.score !== undefined;
                    const contrib = !r.informational && hasScore ? (Number(r.score) * Number(r.weight)) / 100 : null;
                    return (
                      <tr key={r.key}>
                        <td style={{ fontWeight: 600 }}>{r.label}</td>
                        <td style={{ fontFamily: 'monospace', fontWeight: 700 }}>{hasScore ? Number(r.score).toFixed(1) : 'N/A'}</td>
                        <td style={{ fontFamily: 'monospace' }}>{r.informational ? '0% (Info Only)' : `${Number(r.weight).toFixed(0)}%`}</td>
                        <td style={{ fontFamily: 'monospace' }}>{contrib !== null ? contrib.toFixed(2) : '—'}</td>
                        <td>
                          {r.informational ? (
                            <span style={{ color: 'var(--text-3)', fontSize: 12 }}>Informational Only</span>
                          ) : hasScore ? (
                            <span style={{ color: 'var(--ok)', fontWeight: 600, fontSize: 12 }}>Evaluated</span>
                          ) : (
                            <span style={{ color: 'var(--warn)', fontWeight: 600, fontSize: 12 }}>Missing Data (Excluded)</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div style={{ fontSize: 12, color: 'var(--text-2)', padding: '10px 14px', borderTop: '1px solid var(--border)' }}>
                <strong>Overall Score:</strong> {ev.overall_score !== null && ev.overall_score !== undefined ? `${Number(ev.overall_score).toFixed(1)} / 100` : 'N/A'}
                {' · '}
                <strong>Available Weight:</strong> {availW}%
              </div>
            </div>
          );
        })()}
      </SectionCard>

      {/* STATUS STRIP — computed from real data */}
      <div className="card" style={{ display: 'flex', justifyContent: 'space-around', alignItems: 'center', padding: '24px', marginBottom: '32px' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-3)', letterSpacing: '0.1em', marginBottom: '8px' }}>DATA COVERAGE</div>
          <div style={{ fontSize: '20px', fontWeight: '700', color: dataCoverage >= 80 ? 'var(--ok)' : 'var(--warn)', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
            <Database size={20} color="var(--info)" /> {dataCoverage}%
          </div>
        </div>
        <div style={{ width: '1px', height: '40px', background: 'var(--border)' }}></div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-3)', letterSpacing: '0.1em', marginBottom: '8px' }}>GIS STATUS</div>
          <div style={{ fontSize: '16px', fontWeight: '600', color: gisStatus.color, display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
            <Activity size={18} /> {gisStatus.label}
          </div>
        </div>
        <div style={{ width: '1px', height: '40px', background: 'var(--border)' }}></div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-3)', letterSpacing: '0.1em', marginBottom: '8px' }}>COORDINATE TYPE</div>
          <div style={{ fontSize: '16px', fontWeight: '600', color: isExactCoords ? 'var(--ok)' : (isMapPin || isUserEntered) ? 'var(--info)' : 'var(--warn)', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
            <MapPin size={18} /> {isExactCoords ? 'SURVEYED' : isMapPin ? 'MAP PIN' : isUserEntered ? 'USER COORDS' : isBrowserGps ? 'DEVICE GPS' : 'APPROXIMATE'}
          </div>
        </div>
      </div>

      {/* LOCAL MARKET ANALYSIS */}
      {ev.market_comparison && (
        <div className="card fade-in" style={{ marginBottom: 32 }}>
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
            <div className="card-title">Local Real Estate Market Analysis</div>
            <div className={`badge badge-${ev.market_comparison.status === 'SUCCESS' ? 'ok' : ev.market_comparison.status === 'PARTIAL' ? 'warn' : 'neutral'}`}>
              {ev.market_comparison.status || 'UNKNOWN'}
            </div>
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 16 }}>
            Sources: <strong>{(ev.market_comparison.sources || []).join(', ') || 'None'}</strong>
            {' | '}Comparables: <strong>{ev.market_comparison.total_count || 0}</strong> ({ev.market_comparison.live_count || 0} live, {ev.market_comparison.historical_count || 0} historical)
            {ev.market_comparison.market_benchmark?.market_benchmark_psf && (
              <>
                {' | '}Market Median: <strong style={{ color: 'var(--accent)' }}>₹{ev.market_comparison.market_benchmark.market_benchmark_psf.toLocaleString()}/sq.ft</strong>
                {ev.market_comparison.ml_vs_market_pct !== undefined && ev.market_comparison.ml_vs_market_pct !== null && (
                  <> ({ev.market_comparison.ml_vs_market_pct > 0 ? '+' : ''}{ev.market_comparison.ml_vs_market_pct}% vs ML)</>
                )}
              </>
            )}
          </div>
          {ev.valuation_summary && (
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '12px',
              marginBottom: '16px', padding: '12px', borderRadius: '8px', background: '#F6F8F6', border: '1px solid var(--border)',
            }}>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-3)', textTransform: 'uppercase' }}>ML Model Estimate</div>
                <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--accent)' }}>
                  ₹{ev.valuation_summary.ml_estimate?.price_per_sqft?.toLocaleString() || '--'}/sq.ft
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>
                  {ev.valuation_summary.ml_estimate?.uncertainty_basis || 'Model spread'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-3)', textTransform: 'uppercase' }}>Comparable Asking Median</div>
                <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {ev.valuation_summary.market_comparables?.benchmark_median_psf
                    ? `₹${ev.valuation_summary.market_comparables.benchmark_median_psf.toLocaleString()}/sq.ft`
                    : 'No benchmark'}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>
                  {ev.valuation_summary.differences?.ml_vs_market_pct !== null && ev.valuation_summary.differences?.ml_vs_market_pct !== undefined
                    ? `ML is ${ev.valuation_summary.differences.ml_vs_market_pct > 0 ? '+' : ''}${ev.valuation_summary.differences.ml_vs_market_pct}% vs market`
                    : `${ev.valuation_summary.market_comparables?.total_count || 0} comparable(s)`}
                </div>
              </div>
              {ev.valuation_summary.user_asking && (
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-3)', textTransform: 'uppercase' }}>User Asking Price</div>
                  <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--warn)' }}>
                    ₹{ev.valuation_summary.user_asking.price_per_sqft?.toLocaleString()}/sq.ft
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>
                    ₹{(ev.valuation_summary.user_asking.total_price_inr / 100000).toFixed(2)} L total
                    {ev.valuation_summary.differences?.asking_vs_market_pct !== null && ev.valuation_summary.differences?.asking_vs_market_pct !== undefined
                      ? ` (${ev.valuation_summary.differences.asking_vs_market_pct > 0 ? '+' : ''}${ev.valuation_summary.differences.asking_vs_market_pct}% vs market)`
                      : ''}
                  </div>
                </div>
              )}
            </div>
          )}
          {ev.valuation_summary?.ml_estimate?.top_drivers?.length > 0 && (
            <div style={{ marginBottom: 14, display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Top SHAP Drivers:</span>
              {ev.valuation_summary.ml_estimate.top_drivers.slice(0, 4).map((d, idx) => (
                <span key={idx} className="badge" style={{
                  fontSize: 11,
                  background: (d.impact_psf || 0) >= 0 ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)',
                  color: (d.impact_psf || 0) >= 0 ? 'var(--ok)' : 'var(--warn)',
                  border: `1px solid ${(d.impact_psf || 0) >= 0 ? 'rgba(16,185,129,0.28)' : 'rgba(245,158,11,0.28)'}`,
                }}>
                  {d.feature}: {(d.impact_psf || 0) >= 0 ? '+' : ''}₹{Number(d.impact_psf || 0).toLocaleString()}/sq.ft
                </span>
              ))}
            </div>
          )}
          {(ev.market_comparison?.dataset_comparison_tier || ev.market_comparison?.market_benchmark?.dataset_comparison_tier) && (
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10 }}>
              Comparable Matching Tier: <strong>{(ev.market_comparison.dataset_comparison_tier || ev.market_comparison.market_benchmark.dataset_comparison_tier).replace(/_/g, ' ')}</strong>
              {(ev.market_comparison.market_benchmark?.note || '') ? ` — ${ev.market_comparison.market_benchmark.note}` : ''}
            </div>
          )}
          {ev.valuation_summary?.difference_explanation && (
            <div style={{ fontSize: '12px', color: '#4A5750', marginBottom: 14, lineHeight: 1.5, padding: '10px 12px', borderRadius: 8, background: '#F6F8F6', border: '1px solid #E3E8E4' }}>
              <strong style={{ color: '#141C17' }}>Why They Differ:</strong> {ev.valuation_summary.difference_explanation}
            </div>
          )}
          {ev.market_comparison.ml_substantially_above_market && (
            <div className="alert alert-warn" style={{ marginBottom: 16 }}>
              <AlertTriangle size={16} />
              <div style={{ fontSize: 13 }}>
                ML estimate is substantially above local comparable asking prices. Independent market verification advised.
              </div>
            </div>
          )}
          {Array.isArray(ev.market_comparison.listings) && ev.market_comparison.listings.length > 0 && (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Locality</th>
                    <th>Type</th>
                    <th>Area (sq.ft)</th>
                    <th>Rate (₹/sq.ft)</th>
                    <th>Asking Price</th>
                  </tr>
                </thead>
                <tbody>
                  {ev.market_comparison.listings.slice(0, 8).map((lst, idx) => (
                    <tr key={idx}>
                      <td>
                        {lst.source_url
                          ? <a href={lst.source_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)', textDecoration: 'underline' }}>{lst.source}</a>
                          : lst.source}
                      </td>
                      <td>{lst.locality}</td>
                      <td>{lst.listing_type}</td>
                      <td>{lst.land_area_sqft ? Number(lst.land_area_sqft).toLocaleString() : '—'}</td>
                      <td style={{ fontWeight: 600 }}>₹{lst.price_per_sqft ? Number(lst.price_per_sqft).toLocaleString() : '—'}</td>
                      <td>{lst.total_price_inr ? `₹${(lst.total_price_inr / 100000).toFixed(2)} L` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 10 }}>
            {ev.market_comparison.disclaimer}
          </div>
        </div>
      )}

      {/* PROPERTY JURISDICTION & CLASSIFICATION */}
      {(ev.property_classification || ev.infrastructure_breakdown?.property_classification) && (() => {
        const pc = ev.property_classification || ev.infrastructure_breakdown?.property_classification;
        const hobliDisp = pc.hobli || locAudit?.hobli || 'Requires KGIS / Revenue Verification';
        const distDisp = pc.district || property.district || 'Mysuru';
        const wardDisp = pc.ward_display || (
          locAudit?.ward_number || locAudit?.ward_name
            ? `Ward ${locAudit?.ward_number || '—'}${locAudit?.ward_name ? ` — ${locAudit.ward_name}` : ''}`
            : 'Outside Urban Municipal Ward (Rural / Gram Panchayat)'
        );
        const revConv = pc.revenue_classification_and_conversion || 'Land conversion & revenue classification require Bhoomi / RTC / DC Order verification.';
        const docStatus = pc.document_verification_status || 'Not Independently Verified — Obtain and verify the official approval document.';
        const outstanding = Array.isArray(pc.outstanding_checks) ? pc.outstanding_checks : [];
        return (
          <div className="card fade-in" style={{ marginBottom: 32 }}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div className="card-title">Property Jurisdiction &amp; Classification</div>
              <span className="badge badge-warn">{pc.overall_status || 'Not Independently Verified'}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginBottom: 14 }}>
              <div style={{ padding: '10px 12px', borderRadius: 8, background: '#F6F8F6', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase' }}>Locality, Taluk &amp; Hobli</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{pc.locality_or_village || property.village_or_locality}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                  {pc.taluk || property.taluk} Taluk · Hobli: {hobliDisp} · {distDisp} District
                </div>
              </div>
              <div style={{ padding: '10px 12px', borderRadius: 8, background: '#F6F8F6', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase' }}>Local Body &amp; Municipal Ward (KGIS)</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{pc.local_body}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{wardDisp}</div>
              </div>
              <div style={{ padding: '10px 12px', borderRadius: 8, background: '#F6F8F6', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase' }}>Planning Authority</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{pc.jurisdictional_planning_authority}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>Status: {docStatus}</div>
              </div>
              <div style={{ padding: '10px 12px', borderRadius: 8, background: '#F6F8F6', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase' }}>Land, Layout &amp; Conversion Status</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{pc.land_use_classification || pc.property_type}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{pc.layout_approval_category || 'Not Independently Verified'}</div>
                <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 4 }}>{revConv}</div>
              </div>
            </div>
            {outstanding.length > 0 && (
              <div style={{ fontSize: 12, color: 'var(--warn)', marginBottom: 8, lineHeight: 1.5 }}>
                <strong>Outstanding Legal Verification Requirements:</strong> {outstanding.join(' | ')}
              </div>
            )}
            <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>
              <strong>Notice:</strong> {pc.khata_disclaimer} Administrative jurisdiction is separate from legal layout sanction; neither coordinates nor KGIS boundaries establish official layout approval.
            </div>
          </div>
        );
      })()}

      {/* 5. ESSENTIAL INFRASTRUCTURE & CONNECTIVITY (4 CATEGORIES ONLY) */}
      {(ev.utility_assessment || ev.infrastructure_breakdown?.utility_assessment) && (() => {
        const ua = ev.utility_assessment || ev.infrastructure_breakdown?.utility_assessment;
        const cats = ua?.categories || [];
        if (!cats.length) return null;
        return (
          <div className="card fade-in" style={{ marginBottom: 32 }}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div className="card-title">Essential Infrastructure &amp; Connectivity</div>
              <span className="badge" style={{ background: 'rgba(16,185,129,0.12)', color: 'var(--ok)', border: '1px solid rgba(16,185,129,0.28)' }}>
                GIS Coverage: {ua.coverage_pct ?? 0}%
              </span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 14, lineHeight: 1.5, padding: '10px 12px', borderRadius: 6, background: '#F6F8F6', border: '1px solid var(--border)' }}>
              GIS infrastructure mapping indicates nearby mapped facilities only. It does not independently confirm property-level utility connections or legal road access. Unanswered user fields stay <em>Not Confirmed</em>.
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Detected Information</th>
                    <th>Distance</th>
                    <th>Status</th>
                    <th>User Reported</th>
                  </tr>
                </thead>
                <tbody>
                  {cats.map((cat, idx) => {
                    const st = cat.status || 'Unknown / Insufficient Data';
                    const stLabel = st.includes('Available') ? 'Mapped' : st.includes('Not Found') ? 'Not Found' : 'Unknown';
                    const stColor = stLabel === 'Mapped' ? 'var(--ok)' : stLabel === 'Not Found' ? 'var(--text-3)' : 'var(--warn)';
                    const uc = cat.user_confirmation || 'Not Confirmed';
                    const ucColor = uc.includes('Available') && !uc.includes('Not Available')
                      ? 'var(--ok)'
                      : uc.includes('Not Available')
                        ? 'var(--danger)'
                        : 'var(--text-3)';
                    return (
                      <tr key={cat.key || idx}>
                        <td style={{ fontWeight: 600 }}>{cat.infrastructure}</td>
                        <td style={{ fontSize: 13 }}>
                          <div style={{ fontWeight: 500, color: 'var(--text-1)' }}>{cat.system_finding}</div>
                          <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{cat.evidence}</div>
                        </td>
                        <td style={{ fontFamily: 'monospace' }}>
                          {cat.nearest_distance_km !== null && cat.nearest_distance_km !== undefined
                            ? `${Number(cat.nearest_distance_km).toFixed(2)} km`
                            : '—'}
                        </td>
                        <td><span style={{ color: stColor, fontWeight: 600, fontSize: 12 }}>{stLabel}</span></td>
                        <td><span style={{ color: ucColor, fontWeight: 600, fontSize: 12 }}>{uc}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '8px 16px' }}>
                Source: {ua.data_source || 'OpenStreetMap (Overpass API) + GIS Facility Layer'}
                {ua.retrieved_at ? ` | Retrieved: ${String(ua.retrieved_at).slice(0, 19).replace('T', ' ')} UTC` : ''}
              </div>
            </div>
          </div>
        );
      })()}

      {/* 6. NEARBY FACILITIES (INFORMATIONAL REFERENCE ONLY — 14 CATEGORIES) */}
      {(() => {
        const FACILITY_SPEC_14 = [
          { key: 'school', label: 'Schools' },
          { key: 'hospital', label: 'Hospitals' },
          { key: 'clinic', label: 'Clinics and health centres' },
          { key: 'supermarket', label: 'Supermarkets' },
          { key: 'market', label: 'Markets and bazaars' },
          { key: 'pharmacy', label: 'Pharmacies' },
          { key: 'bus_stop', label: 'Bus stops' },
          { key: 'railway_station', label: 'Railway stations' },
          { key: 'bank', label: 'Bank branches' },
          { key: 'police', label: 'Police stations' },
          { key: 'atm', label: 'ATMs' },
          { key: 'park', label: 'Parks and gardens' },
          { key: 'waterbody', label: 'Waterbodies and lakes' },
          { key: 'canal', label: 'Irrigation canals' },
        ];
        const hasAnyFacilitiesObj = Boolean(facilities && Object.keys(facilities).length > 0);
        const resolveStatus = (key) => {
          const fd = facilities?.[key];
          if (!fd) return hasAnyFacilitiesObj ? 'NOT_IN_SNAPSHOT' : 'SOURCE_UNAVAILABLE';
          return String(fd.status || 'NO_DATA').toUpperCase();
        };
        const formatCount = (val, allowZeroFallback = false) => {
          if (val !== null && val !== undefined) return val;
          return allowZeroFallback ? 0 : 'N/A';
        };
        const filteredRows = FACILITY_SPEC_14.filter(({ key, label }) => {
          const fd = facilities?.[key] || {};
          const st = resolveStatus(key);
          if (facilityStatusFilter !== 'ALL' && st !== facilityStatusFilter) return false;
          const q = facilityFilter.trim().toLowerCase();
          if (!q) return true;
          const near = String(fd.nearest?.name || fd.name || '').toLowerCase();
          return label.toLowerCase().includes(q) || near.includes(q);
        });
        const anyOutside3km = FACILITY_SPEC_14.some(({ key }) => {
          const d = facilities?.[key]?.nearest_distance_km ?? facilities?.[key]?.distance_km;
          return d !== null && d !== undefined && Number(d) > 3.0;
        });
        return (
          <div className="card fade-in" style={{ marginBottom: 32 }}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div className="card-title">Nearby Facilities (Informational Reference)</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <Search size={13} style={{ position: 'absolute', left: 9, color: '#6E7B73', pointerEvents: 'none' }} />
                  <input
                    type="text"
                    value={facilityFilter}
                    onChange={(e) => setFacilityFilter(e.target.value)}
                    placeholder="Filter facility or place..."
                    className="form-control"
                    style={{ paddingLeft: 28, paddingBlock: 5, fontSize: 12, width: 190 }}
                  />
                </div>
                <select
                  value={facilityStatusFilter}
                  onChange={(e) => setFacilityStatusFilter(e.target.value)}
                  className="form-control"
                  style={{ paddingBlock: 5, fontSize: 12, width: 'auto' }}
                >
                  <option value="ALL">All Statuses</option>
                  <option value="SUCCESS">Success Only</option>
                  <option value="PARTIAL">Partial Lookup</option>
                  <option value="NO_DATA">No Mapped Data</option>
                  <option value="SOURCE_UNAVAILABLE">Unavailable</option>
                </select>
                <span className="badge badge-neutral">Informational Only · Excluded from Valuation</span>
              </div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 14, lineHeight: 1.5, padding: '10px 12px', borderRadius: 8, background: '#F6F8F6', border: '1px solid #E3E8E4' }}>
              Retrieved from OpenStreetMap &amp; GIS reference layers solely as neighborhood context. These counts do not affect ML price estimates or Infrastructure / Overall scores.
              &nbsp;<strong>No mapped data</strong> means zero mapped OSM features in the search buffer (not proof of absence); <strong>Unavailable</strong> means the source could not be reached.
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Nearest Mapped Place</th>
                    <th>Distance (km)</th>
                    <th>≤ 1 km</th>
                    <th>≤ 3 km</th>
                    <th>≤ 5 km</th>
                    <th>Data Source</th>
                    <th>Retrieval Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-3)', padding: '20px 12px' }}>
                        No nearby facility categories match the active filter.{' '}
                        <button
                          type="button"
                          onClick={() => { setFacilityFilter(''); setFacilityStatusFilter('ALL'); }}
                          style={{ background: 'none', border: 'none', color: 'var(--accent)', fontWeight: 600, cursor: 'pointer', textDecoration: 'underline' }}
                        >
                          Reset filters
                        </button>
                      </td>
                    </tr>
                  ) : filteredRows.map(({ key, label }) => {
                    const fd = facilities?.[key] || {};
                    const st = resolveStatus(key);
                    const nearName = String(fd.nearest?.name || fd.name || '').trim();
                    const nearDist = fd.nearest_distance_km ?? fd.distance_km;
                    const c1 = fd.count_within_1km;
                    const c3 = fd.count_within_3km;
                    const c5 = fd.count_within_5km;
                    const src = st === 'SOURCE_UNAVAILABLE' || st === 'NOT_IN_SNAPSHOT' ? '—' : (fd.source || 'OpenStreetMap');
                    const outsideRadius = nearDist !== null && nearDist !== undefined && Number(nearDist) > 3.0;

                    let stBadge = { text: 'No Mapped Data', color: 'var(--text-3)' };
                    if (st === 'SUCCESS') stBadge = { text: 'Success', color: 'var(--ok)' };
                    else if (st === 'PARTIAL') stBadge = { text: 'Partial', color: 'var(--warn)' };
                    else if (st === 'SOURCE_UNAVAILABLE') stBadge = { text: 'Unavailable', color: 'var(--danger)' };
                    else if (st === 'NOT_IN_SNAPSHOT') stBadge = { text: 'Not Queried', color: 'var(--text-3)' };

                    return (
                      <tr key={key}>
                        <td style={{ fontWeight: 600 }}>{label}</td>
                        <td>
                          {st === 'SOURCE_UNAVAILABLE' ? (
                            <span style={{ color: 'var(--text-3)', fontStyle: 'italic' }}>Source unavailable</span>
                          ) : st === 'NOT_IN_SNAPSHOT' ? (
                            <span style={{ color: 'var(--text-3)', fontStyle: 'italic' }}>Not in evaluation snapshot</span>
                          ) : st === 'PARTIAL' ? (
                            nearName || (nearDist !== null && nearDist !== undefined
                              ? 'Unnamed mapped feature'
                              : <span style={{ color: 'var(--text-3)' }}>Partial / incomplete lookup</span>)
                          ) : st === 'NO_DATA' && (nearDist === null || nearDist === undefined) ? (
                            <span style={{ color: 'var(--text-3)' }}>None mapped in search radius</span>
                          ) : (
                            nearName || <span style={{ color: 'var(--text-3)' }}>Unnamed mapped feature</span>
                          )}
                        </td>
                        <td style={{ fontFamily: 'monospace', color: nearDist !== null && nearDist !== undefined ? (outsideRadius ? 'var(--warn)' : 'var(--text-primary)') : 'var(--text-3)' }}>
                          {nearDist !== null && nearDist !== undefined ? `${Number(nearDist).toFixed(2)} km${outsideRadius ? ' *' : ''}` : '—'}
                        </td>
                        <td style={{ fontFamily: 'monospace' }}>{(st === 'SOURCE_UNAVAILABLE' || st === 'NOT_IN_SNAPSHOT') ? 'N/A' : formatCount(c1, st === 'NO_DATA')}</td>
                        <td style={{ fontFamily: 'monospace' }}>{(st === 'SOURCE_UNAVAILABLE' || st === 'NOT_IN_SNAPSHOT') ? 'N/A' : formatCount(c3, st === 'NO_DATA')}</td>
                        <td style={{ fontFamily: 'monospace' }}>{(st === 'SOURCE_UNAVAILABLE' || st === 'NOT_IN_SNAPSHOT') ? 'N/A' : formatCount(c5, st === 'NO_DATA')}</td>
                        <td style={{ fontSize: 12 }}>{src}</td>
                        <td><span style={{ color: stBadge.color, fontWeight: 600, fontSize: 12 }}>{stBadge.text}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '10px 16px', lineHeight: 1.5 }}>
                {anyOutside3km && '* Nearest feature is outside the 3 km count radius. '}
                All distances are straight-line Haversine distances, not road travel distances. Rural/civic facilities unmapped in OSM automatically check ArcGIS World Geocoder.
                {ev.last_gis_retrieved_at && ` | Last retrieved: ${String(ev.last_gis_retrieved_at).slice(0, 19).replace('T', ' ')} UTC`}
              </div>
            </div>
          </div>
        );
      })()}

      {/* 6.5. ENVIRONMENTAL & RISK CHECKS */}
      {(() => {
        const envB = ev.environment_breakdown || {};
        const wb = facilities?.waterbody || {};
        const cn = facilities?.canal || {};
        const pk = facilities?.park || {};
        const wbDist = wb.nearest_distance_km ?? wb.distance_km;
        const cnDist = cn.nearest_distance_km ?? cn.distance_km;
        const pkDist = pk.nearest_distance_km ?? pk.distance_km;
        const floodNote = wbDist !== null && wbDist !== undefined
          ? (Number(wbDist) < 0.25
            ? 'Elevated GIS proximity alert (<250 m to mapped waterbody) — official Karnataka Minor Irrigation / MDA flood clearance mandatory.'
            : Number(wbDist) < 1.0
              ? 'Moderate proximity to mapped waterbody (<1 km). Indicative GIS proxy only — NOT an official flood-zone determination.'
              : 'Mapped waterbody >1.0 km away (indicative GIS proximity check only — NOT an official flood-zone determination).')
          : 'Hydrological GIS proximity unavailable / unconfirmed — official Karnataka Minor Irrigation / drainage verification mandatory.';
        return (
          <div className="card fade-in" style={{ marginBottom: 32 }}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div className="card-title">Environmental &amp; Risk Checks</div>
              <span className="badge badge-neutral">
                Score: {ev.environment_score !== null && ev.environment_score !== undefined ? `${Number(ev.environment_score).toFixed(1)} / 100` : 'N/A (Excluded)'}
                {ev.environmental_coverage_pct !== null && ev.environmental_coverage_pct !== undefined ? ` · ${ev.environmental_coverage_pct}% coverage` : ''}
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginBottom: 12 }}>
              <div style={{ padding: '10px 12px', borderRadius: 8, background: '#F6F8F6', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase' }}>Lakes &amp; Waterbodies</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>
                  {wbDist !== null && wbDist !== undefined ? `${wb.nearest?.name || 'Waterbody'} · ${Number(wbDist).toFixed(2)} km` : (wb.status === 'NO_DATA' ? 'None mapped in 5 km' : 'Query incomplete / unavailable')}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>Within 3 km: {wb.count_within_3km ?? 'N/A'}</div>
              </div>
              <div style={{ padding: '10px 12px', borderRadius: 8, background: '#F6F8F6', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase' }}>Irrigation Canals</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>
                  {cnDist !== null && cnDist !== undefined ? `${cn.nearest?.name || 'Irrigation Canal'} · ${Number(cnDist).toFixed(2)} km` : (cn.status === 'NO_DATA' ? 'None mapped in 5 km' : 'Query incomplete / unavailable')}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>Within 3 km: {cn.count_within_3km ?? 'N/A'}</div>
              </div>
              <div style={{ padding: '10px 12px', borderRadius: 8, background: '#F6F8F6', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase' }}>Parks &amp; Greenery</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>
                  {pkDist !== null && pkDist !== undefined ? `${pk.nearest?.name || 'Public Park'} · ${Number(pkDist).toFixed(2)} km` : (pk.status === 'NO_DATA' ? 'None mapped in radius' : 'Query incomplete / unavailable')}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>Within 3 km: {pk.count_within_3km ?? 'N/A'}</div>
              </div>
              <div style={{ padding: '10px 12px', borderRadius: 8, background: '#F6F8F6', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase' }}>Flood &amp; Official Clearance</div>
                <div style={{ fontSize: 12, fontWeight: 600, marginTop: 2, color: 'var(--warn)' }}>{floodNote}</div>
              </div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.5 }}>
              {envB.disclaimer || 'OSM-derived proximity indicators do NOT substitute for official Karnataka Minor Irrigation / MDA flood-zone maps or Rajakaluve buffer demarcations.'}
            </div>
          </div>
        );
      })()}

      {/* ACTION BUTTONS */}
      <div style={{ display: 'flex', gap: '16px', justifyContent: 'center', flexWrap: 'wrap' }}>
        <button className="btn btn-secondary btn-lg" onClick={() => document.getElementById('map-view')?.scrollIntoView({ behavior: 'smooth' })}>
          <MapPin size={18} /> View Map
        </button>
        <Link to={`/student/compare?add=${property.id}`} className="btn btn-secondary btn-lg">
          <GitCompare size={18} /> Compare
        </Link>
        <Link to={`/student/documents?property_id=${property.id}`} className="btn btn-secondary btn-lg">
          <FileText size={18} /> View Documents
        </Link>
        <button
          type="button"
          className="btn btn-secondary btn-lg"
          onClick={async () => {
            try {
              const res = await toggleSavedProperty(property.id);
              setShortlistMsg(res.data.saved ? 'Added to Saved Shortlist' : 'Removed from Saved Shortlist');
            } catch {
              setShortlistMsg('Could not update shortlist');
            }
          }}
        >
          <Bookmark size={18} /> {shortlistMsg || 'Shortlist Parcel'}
        </button>
        <button
          className="btn btn-primary btn-lg"
          onClick={handleGeneratePDF}
          disabled={pdfGenerating}
        >
          {pdfGenerating
            ? <><Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> Generating...</>
            : <><FileDown size={18} /> Generate PDF Report</>
          }
        </button>
      </div>

      {/* MAP VIEW */}
      <div id="map-view" className="card" style={{ marginTop: '48px', padding: 0, overflow: 'hidden' }}>
        <PropertyMap 
          lat={property.latitude} 
          lon={property.longitude} 
          label={property.name}
          status={property.coordinate_status}
          facilities={Object.entries(facilities)
            .map(([type, d]) => ({
              type,
              name: d?.nearest?.name,
              lat: d?.nearest?.latitude ?? d?.nearest?.lat,
              lon: d?.nearest?.longitude ?? d?.nearest?.lon,
              distance_km: d?.nearest_distance_km
            }))
            .filter(f => f.lat && f.lon)}
          height={500} 
        />
        {!isExactCoords && (
          <div style={{ padding: '12px 24px', background: 'var(--warn-bg)', borderTop: '1px solid var(--warn)', fontSize: '13px', color: 'var(--warn)', display: 'flex', gap: '8px' }}>
            <AlertTriangle size={16} />
            <div>
              <strong>
                {isMapPin ? `[MAP_SELECTED] User-Pinned Coordinates:`
                  : isBrowserGps ? `[DEVICE_GPS] Device / Browser Geolocation:`
                  : isUserEntered ? `[USER_ENTERED] Manual User Coordinates:`
                  : isGeocoded ? `[GEOCODED] Address Search Coordinates:`
                  : `[LOCALITY_CENTROID] Locality Approximation:`}
              </strong>{' '}
              {isMapPin || isUserEntered || isGeocoded
                ? 'Coordinates are NOT surveyed parcel boundaries; verify against official revenue survey sketch.'
                : isBrowserGps
                  ? 'Browser/device geolocation may reflect Wi-Fi/ISP tower approximation; confirm exact parcel coordinates.'
                  : 'Using locality-level centroid approximation. Exact facility distances may vary; provide surveyed GPS coordinates for parcel-level precision.'}
            </div>
          </div>
        )}
      </div>

    </div>
  );
}
