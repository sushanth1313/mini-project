import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  getProperties,
  getCustomerDashboardSummary,
  getSavedProperties,
  getGisConfig,
  toggleSavedProperty,
} from '../api/client';
import {
  Activity,
  ArrowRight,
  BarChart3,
  Bookmark,
  Compass,
  FileText,
  FolderOpen,
  LifeBuoy,
  MapPin,
  Plus,
  ShieldCheck,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import PropertyMap from '../components/PropertyMap';
import { EmptyState, LoadingState, SectionCard, StatCard } from '../components/ui';

export default function Dashboard() {
  const [properties, setProperties] = useState([]);
  const [summary, setSummary] = useState(null);
  const [gisCfg, setGisCfg] = useState(null);
  const [savedIds, setSavedIds] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [propRes, sumRes, savRes, gisRes] = await Promise.all([
        getProperties(),
        getCustomerDashboardSummary(),
        getSavedProperties().catch(() => ({ data: { saved_properties: [] } })),
        getGisConfig().catch(() => ({ data: null })),
      ]);
      setProperties(propRes.data.properties || []);
      setSummary(sumRes.data);
      setGisCfg(gisRes.data || null);
      setSavedIds(new Set((savRes.data?.saved_properties || []).map((item) => item.id)));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleSave = async (propId) => {
    try {
      const res = await toggleSavedProperty(propId);
      setSavedIds((prev) => {
        const next = new Set(prev);
        if (res.data.saved) next.add(propId);
        else next.delete(propId);
        return next;
      });
    } catch {
      // silent
    }
  };

  if (loading) return <LoadingState message="Loading SLV-GIS Mysuru workspace..." />;

  const counts = summary?.counts || {};
  const userObj = summary?.user;
  const recentProps = properties.slice(0, 6);
  const evaluatedWithVal = properties.filter((p) => p.latest_evaluation?.predicted_total_price);
  const avgValLakhs =
    evaluatedWithVal.length > 0
      ? evaluatedWithVal.reduce((acc, p) => acc + Number(p.latest_evaluation.predicted_total_price || 0), 0) /
        evaluatedWithVal.length /
        100000
      : null;

  const chartData = evaluatedWithVal
    .slice(0, 6)
    .reverse()
    .map((p) => ({
      name: (p.village_or_locality || p.name || `#${p.id}`).slice(0, 14),
      valueLakhs: Number((Number(p.latest_evaluation.predicted_total_price) / 100000).toFixed(2)),
      score: Number(p.latest_evaluation.overall_score || 0),
    }));

  const mapProp = properties.find((p) => p.latitude && p.longitude) || null;
  const cov = gisCfg?.kgis_coverage;

  return (
    <div className="stack-lg fade-in">
      {/* Row 1: Executive Mysuru Intelligence Banner */}
      <div
        style={{
          borderRadius: 14,
          border: '1px solid #D2DBD4',
          overflow: 'hidden',
          padding: '1.5rem 1.75rem',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1.25rem',
          backgroundImage:
            'linear-gradient(92deg, rgba(255,255,255,0.97) 0%, rgba(255,255,255,0.92) 48%, rgba(255,255,255,0.28) 85%, rgba(255,255,255,0.12) 100%), url(/images/mysuru-palace-hero.jpg)',
          backgroundSize: 'cover',
          backgroundPosition: 'right center',
          boxShadow: '0 2px 10px rgba(16,36,24,0.05)',
        }}
      >
        <div style={{ maxWidth: 620 }}>
          <span className="badge badge-success" style={{ marginBottom: 8 }}>
            Mysuru District · Property Intelligence Workspace
          </span>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.55rem', fontWeight: 700, color: '#141C17', margin: '0 0 6px' }}>
            {userObj ? `Welcome back, ${userObj.full_name}` : 'Smart Land Valuation & Geospatial Analysis System'}
          </h1>
          <p style={{ fontSize: '0.86rem', color: '#4A5750', marginBottom: '1rem', lineHeight: 1.55 }}>
            Accurate KGIS boundary verification, ML market valuation, 4-factor infrastructure checks, nearby facilities, and AI document scrutiny.
          </p>
          <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap' }}>
            <Link to="/student/evaluate" className="btn btn-primary btn-sm">
              <Plus size={14} /> Evaluate Property
            </Link>
            <Link to="/student/documents" className="btn btn-secondary btn-sm" style={{ background: '#FFFFFF' }}>
              <FileText size={14} /> Open Document Analyzer
            </Link>
            <Link to="/student/compare" className="btn btn-secondary btn-sm" style={{ background: '#FFFFFF' }}>
              Compare Parcels
            </Link>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">Unable to load workspace metrics: {error}</div>}

      {/* Row 2: 4 Real-Data KPI Cards */}
      <div className="stats-grid">
        <StatCard
          label="Properties Evaluated"
          value={counts.evaluations ?? 0}
          sub={`${counts.properties ?? 0} saved parcel profile(s)`}
          icon={Compass}
          tone="green"
        />
        <StatCard
          label="Avg Estimated Value"
          value={avgValLakhs !== null ? `₹${avgValLakhs.toFixed(2)} L` : '—'}
          sub={evaluatedWithVal.length > 0 ? `Across ${evaluatedWithVal.length} evaluated parcel(s)` : 'Run an evaluation to compute'}
          icon={BarChart3}
          tone="blue"
        />
        <StatCard
          label="District GIS Villages"
          value={cov?.revenue_village_polygons ? cov.revenue_village_polygons.toLocaleString() : '—'}
          sub={cov ? `${cov.unique_kgis_taluks?.length || 8} KGIS taluks · ${cov.municipal_ward_polygons} wards` : 'Loading KGIS boundary summary'}
          icon={MapPin}
          tone="green"
        />
        <StatCard
          label="Reports & Document Runs"
          value={counts.reports ?? 0}
          sub={`${counts.documents_analyzed_total ?? 0} doc(s) · ${counts.document_analyses ?? 0} analysis packet(s)`}
          icon={ShieldCheck}
          tone="amber"
        />
      </div>

      {/* Row 3: Interactive GIS Map Preview + Valuation Summary Chart + Recent Activities */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1.15fr) minmax(0, 1.1fr) minmax(260px, 0.85fr)',
          gap: '1.15rem',
        }}
        className="dash-mid-grid"
      >
        <SectionCard
          title="Interactive GIS Map"
          subtitle={mapProp ? `Centered on ${mapProp.village_or_locality} (${mapProp.taluk})` : 'Mysuru District Spatial View'}
          icon={MapPin}
          actions={
            <Link to={mapProp ? `/student/map?property_id=${mapProp.id}` : '/student/evaluate'} style={{ fontSize: '0.78rem', fontWeight: 600, color: '#144D29' }}>
              {mapProp ? 'View Full Map →' : 'Pick Parcel →'}
            </Link>
          }
          style={{ display: 'flex', flexDirection: 'column' }}
        >
          <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid #E3E8E4' }}>
            <PropertyMap
              interactive={false}
              lat={mapProp?.latitude ?? 12.3052}
              lon={mapProp?.longitude ?? 76.6552}
              label={mapProp ? mapProp.village_or_locality : 'Mysuru District Centre'}
              status={mapProp?.coordinate_status || 'LOCALITY_CENTROID'}
              zoom={mapProp ? 14 : 11}
              height={250}
            />
          </div>
        </SectionCard>

        <SectionCard
          title="Property Valuation Summary"
          subtitle="Estimated value (₹ Lakhs) across recent evaluations"
          icon={BarChart3}
          actions={
            <Link to="/student/properties" style={{ fontSize: '0.78rem', fontWeight: 600, color: '#144D29' }}>
              History →
            </Link>
          }
        >
          {chartData.length === 0 ? (
            <EmptyState
              icon={BarChart3}
              title="No Valuation History Yet"
              message="Evaluate your first Mysuru parcel to visualize indicative value comparisons here."
              action={<Link to="/student/evaluate" className="btn btn-primary btn-sm">Evaluate Property</Link>}
            />
          ) : (
            <div style={{ width: '100%', height: 250 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 12, left: -10, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E3E8E4" vertical={false} />
                  <XAxis dataKey="name" stroke="#4A5750" fontSize={11} tickLine={false} />
                  <YAxis stroke="#4A5750" fontSize={11} tickLine={false} />
                  <Tooltip
                    formatter={(val) => [`₹${val} L`, 'Estimated Value']}
                    contentStyle={{ background: '#FFFFFF', borderColor: '#BCE0C8', borderRadius: 8, fontSize: 12 }}
                  />
                  <Bar dataKey="valueLakhs" fill="#144D29" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="Recent Activities"
          subtitle="Latest account evaluations"
          icon={Activity}
          actions={
            <Link to="/student/properties" style={{ fontSize: '0.78rem', fontWeight: 600, color: '#144D29' }}>
              View All →
            </Link>
          }
        >
          {recentProps.length === 0 ? (
            <div style={{ fontSize: '0.82rem', color: '#6E7B73', padding: '1rem 0', textAlign: 'center' }}>
              No evaluations recorded yet.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem', maxHeight: 250, overflowY: 'auto' }}>
              {recentProps.slice(0, 5).map((p) => {
                const ev = p.latest_evaluation;
                return (
                  <Link
                    key={p.id}
                    to={`/student/map?property_id=${p.id}`}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '0.6rem',
                      padding: '0.6rem 0.7rem',
                      borderRadius: 9,
                      background: '#F6F8F6',
                      border: '1px solid #E3E8E4',
                      textDecoration: 'none',
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#141C17', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {p.name || p.village_or_locality}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: '#6E7B73' }}>
                        {p.village_or_locality} · {p.taluk}
                      </div>
                    </div>
                    <span className="badge badge-success" style={{ fontSize: '0.68rem', flexShrink: 0 }}>
                      {ev?.predicted_total_price ? `₹${(ev.predicted_total_price / 100000).toFixed(1)}L` : 'Pending'}
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
        </SectionCard>
      </div>

      {/* Row 4: Quick Feature Shortcuts */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        {[
          { to: '/student/evaluate', title: 'Evaluate Property & GIS', desc: 'Map selection, KGIS boundaries & ML price estimate', cta: 'Start Evaluation', icon: MapPin, bg: '#E7F5EC', fg: '#144D29' },
          { to: '/student/documents', title: 'AI Document Analyzer', desc: 'OCR & consistency audit for Deeds, RTC, EC & Khata', cta: 'Analyze Documents', icon: FileText, bg: '#ECF4FC', fg: '#1B4D7A' },
          { to: '/student/properties', title: 'Reports & History', desc: 'Download A4 PDFs and compare evaluated properties', cta: 'View Archive', icon: FolderOpen, bg: '#FEF6E6', fg: '#85520E' },
          { to: '/student/account?tab=help', title: 'Support & Notifications', desc: 'Raise support tickets or check administrator updates', cta: 'Open Support', icon: LifeBuoy, bg: '#F0F4F1', fg: '#144D29' },
        ].map(({ to, title, desc, cta, icon: Icon, bg, fg }) => (
          <Link
            key={title}
            to={to}
            style={{
              background: '#FFFFFF',
              border: '1px solid #E3E8E4',
              borderRadius: 12,
              padding: '1rem 1.15rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              gap: '0.65rem',
              textDecoration: 'none',
              boxShadow: '0 1px 4px rgba(16,36,24,0.04)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
              <div>
                <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#141C17' }}>{title}</div>
                <div style={{ fontSize: '0.76rem', color: '#4A5750', marginTop: 3, lineHeight: 1.45 }}>{desc}</div>
              </div>
              <div style={{ width: 34, height: 34, borderRadius: 9, background: bg, color: fg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Icon size={17} />
              </div>
            </div>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#144D29', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              {cta} <ArrowRight size={13} />
            </div>
          </Link>
        ))}
      </div>

      {/* Row 5: Evaluated Property Cards Grid */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.85rem' }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.12rem', fontWeight: 700, color: '#141C17', margin: 0 }}>
            Saved &amp; Recent Property Profiles
          </h2>
          <Link to="/student/properties" style={{ fontSize: '0.82rem', color: '#144D29', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            All Properties &amp; Reports <ArrowRight size={14} />
          </Link>
        </div>

        {recentProps.length === 0 ? (
          <EmptyState
            icon={Activity}
            title="No evaluations yet in your account"
            message="Start a new Mysuru District evaluation to estimate indicative market value, check nearby facilities, and analyze land documents."
            action={<Link to="/student/evaluate" className="btn btn-primary btn-sm">Evaluate Your First Property</Link>}
          />
        ) : (
          <div className="grid grid-3">
            {recentProps.map((p) => {
              const ev = p.latest_evaluation;
              const isSaved = savedIds.has(p.id);
              return (
                <div key={p.id} className="surface-card surface-card-body" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12, gap: 8 }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '0.96rem', color: '#141C17' }}>{p.name || p.village_or_locality}</div>
                        <div style={{ fontSize: '0.78rem', color: '#6E7B73', display: 'flex', alignItems: 'center', gap: 4, marginTop: 3 }}>
                          <MapPin size={12} color="#144D29" /> {p.village_or_locality} · {p.taluk || 'Mysuru'} Taluk
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleToggleSave(p.id)}
                        title={isSaved ? 'Remove Bookmark' : 'Save Property'}
                        className="btn btn-secondary btn-sm"
                        style={{ padding: '5px 7px' }}
                      >
                        <Bookmark size={14} fill={isSaved ? 'currentColor' : 'none'} color={isSaved ? '#144D29' : '#6E7B73'} />
                      </button>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#4A5750', padding: '9px 0', borderTop: '1px solid #E3E8E4', borderBottom: '1px solid #E3E8E4', marginBottom: 12 }}>
                      <span>Area: <strong style={{ color: '#141C17' }}>{p.land_area_sqft?.toLocaleString()} sq.ft</strong></span>
                      <span>Asking: <strong style={{ color: '#141C17' }}>{p.asking_price_inr ? `₹${(p.asking_price_inr / 100000).toFixed(1)}L` : '—'}</strong></span>
                    </div>

                    {ev && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                        <div>
                          <div style={{ fontSize: '0.7rem', color: '#6E7B73', fontWeight: 600 }}>INDICATIVE VALUE</div>
                          <div style={{ fontSize: '1.15rem', fontWeight: 700, color: '#144D29' }}>
                            ₹{ev.predicted_total_price ? (ev.predicted_total_price / 100000).toFixed(2) : '--'} L
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: '0.7rem', color: '#6E7B73', fontWeight: 600 }}>SITE SCORE</div>
                          <div style={{ fontSize: '1.15rem', fontWeight: 700, color: ev.overall_score >= 70 ? '#14532D' : ev.overall_score >= 50 ? '#85520E' : '#8C2D23' }}>
                            {ev.overall_score ?? '--'}<span style={{ fontSize: '0.72rem', color: '#6E7B73' }}>/100</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'flex', gap: 8, marginTop: 'auto' }}>
                    <Link to={`/student/map?property_id=${p.id}`} className="btn btn-secondary btn-sm" style={{ flex: 1 }}>
                      Open Evaluation
                    </Link>
                    <Link to={`/student/documents?property_id=${p.id}`} className="btn btn-secondary btn-sm" style={{ flex: 1 }}>
                      Documents
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
