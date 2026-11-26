import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Brain,
  Compass,
  Database,
  FileCheck2,
  FileText,
  LifeBuoy,
  MapPin,
  RefreshCw,
  ShieldAlert,
  Sliders,
  Users,
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
import {
  fetchOverviewMetrics,
  fetchWeightages,
  updateWeightages,
} from '../api/adminClient';
import { getGisConfig } from '../api/client';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';
import { PageHeader, StatCard, StatusBadge } from '../components/ui';

export default function AdminDashboard() {
  const { hasPermission } = useAdminAuth();
  const [overview, setOverview] = useState(null);
  const [gisCfg, setGisCfg] = useState(null);
  const [weightage, setWeightage] = useState(null);
  const [weightsForm, setWeightsForm] = useState({
    price_weight: 30,
    location_weight: 25,
    facility_weight: 0,
    environment_weight: 10,
    infrastructure_weight: 20,
    utility_weight: 15,
  });
  const [editWeights, setEditWeights] = useState(false);
  const [loading, setLoading] = useState(true);
  const [statusMsg, setStatusMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [accessDenied, setAccessDenied] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setErrorMsg('');
    setAccessDenied(false);
    try {
      const [ovRes, gRes] = await Promise.all([
        fetchOverviewMetrics(),
        getGisConfig().catch(() => ({ data: null })),
      ]);
      setOverview(ovRes.data);
      setGisCfg(gRes.data || null);
      if (hasPermission('settings:view')) {
        const wRes = await fetchWeightages();
        if (wRes.data?.active) {
          setWeightage(wRes.data.active);
          setWeightsForm({
            price_weight: wRes.data.active.price_weight,
            location_weight: wRes.data.active.location_weight,
            facility_weight: wRes.data.active.facility_weight,
            environment_weight: wRes.data.active.environment_weight,
            infrastructure_weight: wRes.data.active.infrastructure_weight,
            utility_weight: wRes.data.active.utility_weight,
          });
        }
      }
    } catch (err) {
      if (err?.response?.status === 403) {
        setAccessDenied(true);
      }
      setErrorMsg(err?.response?.data?.error || 'Failed to load overview metrics.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSaveWeights = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setStatusMsg('');
    try {
      const res = await updateWeightages(weightsForm);
      setWeightage(res.data);
      setEditWeights(false);
      setStatusMsg(`Weightage v${res.data.version} saved & audited. Prior evaluation snapshots remain immutable.`);
    } catch (err) {
      setErrorMsg(err?.response?.data?.error || 'Weightage update failed.');
    }
  };

  const kpis = overview?.kpis || {};
  const kgisCov = gisCfg?.kgis_coverage || null;
  const talukData = Array.isArray(overview?.charts?.taluk_wise_distribution)
    ? overview.charts.taluk_wise_distribution.map((item) => ({
        taluk: item.taluk,
        count: item.evaluations ?? item.count ?? 0,
      }))
    : Object.entries(overview?.charts?.taluk_wise_distribution || {}).map(([taluk, val]) => ({
        taluk,
        count: typeof val === 'object' ? (val.evaluations ?? 0) : val,
      }));
  const weightSum = Object.values(weightsForm).reduce((acc, v) => acc + Number(v || 0), 0);

  return (
    <div className="space-y-6 fade-in">
      <PageHeader
        eyebrow={`Live SQLite & Runtime Governance (${overview?.adapter_mode || 'sqlite_live_runtime'})`}
        title="Platform Operations Overview"
        subtitle="Real-time operational metrics, Mysuru GIS boundary coverage, and scoring engine governance."
        icon={Activity}
        actions={
          <button
            type="button"
            onClick={loadData}
            disabled={loading}
            className="btn btn-secondary btn-sm"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh Live Stats
          </button>
        }
      />

      <AdminModuleHeader
        whatItShows="Live SQLite KPIs, actual KGIS boundary layer coverage, deduplicated alerts, and active scoring weights."
        adminAction="Monitor alerts, GIS availability, and adjust site scoring weights when approved."
        consequence="Weight edits create immutable new versions; historical evaluations keep their original weights."
      />

      {overview?.database_architecture && (
        <div className="p-3.5 rounded-xl bg-white shadow-sm border border-[#E3E8E4] text-xs flex flex-wrap items-center justify-between gap-2 text-[#4A5750]">
          <span>
            <strong className="text-[#144D29]">Storage Architecture:</strong> {overview.database_architecture.primary_store} · {overview.database_architecture.secondary_document_store}
          </span>
          <StatusBadge status="OPERATIONAL">Live Hybrid SQLite Sync Active</StatusBadge>
        </div>
      )}

      {loading && (
        <div className="p-4 rounded-xl bg-white border border-[#E3E8E4] text-xs text-[#4A5750]">
          Loading live SQLite metrics and governance alerts...
        </div>
      )}
      {accessDenied && (
        <div className="p-3.5 rounded-xl bg-[#FEF6E6] border border-[#EDD49F] text-xs text-[#85520E] flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 shrink-0" /> Unauthorized (403): {errorMsg || 'Your role lacks overview access.'}
        </div>
      )}
      {errorMsg && !accessDenied && (
        <div className="p-3.5 rounded-xl bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23] flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" /> {errorMsg}
        </div>
      )}
      {statusMsg && (
        <div className="p-3.5 rounded-xl bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D]">
          {statusMsg}
        </div>
      )}

      {/* Primary Balanced 4-Column KPI Grid (no truncated model names or dangling slots) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Property Evaluations"
          value={kpis.total_property_evaluations ?? '—'}
          sub={`${kpis.evaluations_today ?? 0} logged today (UTC)`}
          icon={Activity}
          tone="green"
        />
        <StatCard
          label="Platform Users"
          value={kpis.total_users ?? '—'}
          sub={`${kpis.active_users ?? 0} active registered user(s)`}
          icon={Users}
          tone="green"
        />
        <StatCard
          label="Production ML Model"
          value={kpis.current_production_model || 'ExtraTreesRegressor'}
          sub="Holdout verified · active predictor"
          icon={Brain}
          tone="blue"
        />
        <StatCard
          label="Curated Dataset Rows"
          value={kpis.dataset_records != null ? Number(kpis.dataset_records).toLocaleString('en-IN') : '—'}
          sub="Live DB training records"
          icon={Database}
          tone="green"
        />
        <StatCard
          label="GIS Service Availability"
          value={`${kpis.gis_service_availability_pct ?? 100}%`}
          sub={`${kpis.failed_api_requests_24h ?? 0} failed request(s) in 24h`}
          icon={MapPin}
          tone={(kpis.failed_api_requests_24h ?? 0) > 0 ? 'amber' : 'green'}
        />
        <StatCard
          label="Document Analyses"
          value={kpis.total_document_analyses ?? 0}
          sub="AI due-diligence scrutiny packets"
          icon={FileCheck2}
          tone="blue"
        />
        <StatCard
          label="Generated Reports"
          value={kpis.reports_generated ?? 0}
          sub="Downloadable A4 PDF snapshots"
          icon={FileText}
          tone="green"
        />
        <StatCard
          label="Support Tickets"
          value={kpis.pending_support_tickets ?? 0}
          sub={`${kpis.open_high_priority_tickets ?? 0} high/urgent pending`}
          icon={LifeBuoy}
          tone={(kpis.pending_support_tickets ?? 0) > 0 ? 'amber' : 'green'}
        />
      </div>

      {/* Live KGIS District Coverage Card (computed from actual loaded GeoJSON files) */}
      {kgisCov && (
        <div className="p-5 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-[#141C17] flex items-center gap-2">
              <Compass className="w-4 h-4 text-[#144D29]" /> Loaded KGIS Boundary Coverage (Live GeoJSON Audit)
            </h2>
            <StatusBadge status={kgisCov.assembly_constituency_available ? 'VERIFIED' : 'PARTIAL'}>
              {kgisCov.assembly_constituency_available ? 'Full Layer Stack' : 'Partial — AC Boundaries Not Loaded'}
            </StatusBadge>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
            <div className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
              <div className="text-[11px] text-[#6E7B73]">KGIS Taluks</div>
              <div className="text-base font-bold text-[#141C17] mt-0.5">{kgisCov.unique_kgis_taluks?.length ?? 0} ({kgisCov.taluk_polygons} polys)</div>
            </div>
            <div className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
              <div className="text-[11px] text-[#6E7B73]">Hoblis</div>
              <div className="text-base font-bold text-[#141C17] mt-0.5">{kgisCov.hobli_polygons}</div>
            </div>
            <div className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
              <div className="text-[11px] text-[#6E7B73]">Revenue Villages</div>
              <div className="text-base font-bold text-[#141C17] mt-0.5">{kgisCov.revenue_village_polygons?.toLocaleString()}</div>
            </div>
            <div className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
              <div className="text-[11px] text-[#6E7B73]">Villages w/ GP Code</div>
              <div className="text-base font-bold text-[#141C17] mt-0.5">{kgisCov.villages_with_lgd_gp_code?.toLocaleString()}</div>
            </div>
            <div className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
              <div className="text-[11px] text-[#6E7B73]">ULBs &amp; Wards</div>
              <div className="text-base font-bold text-[#141C17] mt-0.5">{kgisCov.urban_local_body_polygons} ULBs / {kgisCov.municipal_ward_polygons} Wards</div>
            </div>
            <div className="p-3 rounded-lg bg-[#FEF6E6] border border-[#EDD49F]">
              <div className="text-[11px] text-[#85520E]">Assembly Constituencies</div>
              <div className="text-sm font-bold text-[#85520E] mt-0.5">0 Loaded (Gap)</div>
            </div>
          </div>
        </div>
      )}

      {/* Taluk Distribution + System Alerts */}
      <div className="grid lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 p-5 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#141C17]">Evaluations by Taluk (Live DB)</h2>
            <span className="text-[11px] text-[#6E7B73]">{talukData.length} taluk bucket(s)</span>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={talukData} margin={{ top: 8, right: 12, left: -12, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E3E8E4" vertical={false} />
                <XAxis dataKey="taluk" stroke="#4A5750" fontSize={11} tickLine={false} />
                <YAxis stroke="#4A5750" fontSize={11} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#BCE0C8', borderRadius: 8, fontSize: '12px' }}
                />
                <Bar dataKey="count" name="Evaluations" fill="#144D29" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="lg:col-span-5 p-5 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-3">
          <h2 className="text-sm font-semibold text-[#141C17]">Governance Alerts &amp; Audit Snapshot</h2>
          <div className="space-y-2.5 max-h-64 overflow-y-auto pr-1">
            {(overview?.system_alerts || []).map((alert, idx) => (
              <div
                key={`${alert.module}-${alert.alert_type || 'ALERT'}-${alert.reference}-${idx}`}
                className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4] text-xs space-y-1"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-[#FEF6E6] text-[#85520E] border border-[#EDD49F]">
                    {alert.severity || 'INFO'} · {alert.alert_type || 'NOTICE'}
                  </span>
                  <span className="font-mono text-[10px] text-[#4A5750]">{alert.module} ({alert.reference})</span>
                </div>
                <div className="text-[#141C17]">{alert.message}</div>
              </div>
            ))}
            {(!overview?.system_alerts || overview.system_alerts.length === 0) && (
              <div className="text-xs text-[#4A5750] py-6 text-center">No critical anomalies reported.</div>
            )}
          </div>
        </div>
      </div>

      {/* Site Scoring Weightage Versioning Control */}
      {hasPermission('settings:view') && (
        <div className="p-5 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-[#141C17] flex items-center gap-2">
                <Sliders className="w-4 h-4 text-[#144D29]" /> Scoring Engine Weightages
                {weightage && (
                  <span className="px-2 py-0.5 rounded bg-[#ECF5EE] text-[#144D29] font-mono text-[10px] border border-[#BCE0C8]">
                    v{weightage.version} Active
                  </span>
                )}
              </h2>
              <p className="text-xs text-[#4A5750] mt-0.5">
                Adjusting weights creates an immutable new version; historical evaluations remain locked to their original version.
              </p>
            </div>
            {hasPermission('settings:manage') && !editWeights && (
              <button
                type="button"
                onClick={() => setEditWeights(true)}
                className="btn btn-primary btn-sm"
              >
                Adjust Weights
              </button>
            )}
          </div>

          <form onSubmit={handleSaveWeights} className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {[
                ['price_weight', 'Price Fair Value'],
                ['location_weight', 'Location'],
                ['facility_weight', 'Facilities'],
                ['environment_weight', 'Environment'],
                ['infrastructure_weight', 'Infrastructure'],
                ['utility_weight', 'Utilities'],
              ].map(([key, label]) => (
                <div key={key} className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
                  <div className="text-[11px] text-[#4A5750] mb-1">{label}</div>
                  {editWeights ? (
                    <input
                      type="number"
                      step="0.5"
                      min="0"
                      max="100"
                      value={weightsForm[key]}
                      onChange={(e) =>
                        setWeightsForm((p) => ({ ...p, [key]: Number(e.target.value) }))
                      }
                      className="w-full px-2 py-1 rounded bg-white shadow-sm border border-[#D2DBD4] text-sm font-mono text-[#141C17]"
                    />
                  ) : (
                    <div className="text-lg font-mono font-bold text-[#144D29]">
                      {weightage?.[key] ?? weightsForm[key]}%
                    </div>
                  )}
                </div>
              ))}
            </div>
            {editWeights && (
              <div className="flex items-center justify-between pt-2">
                <span className={`text-xs font-mono ${Math.abs(weightSum - 100) <= 0.01 ? 'text-[#14532D]' : 'text-[#8C2D23]'}`}>
                  Total Sum: {weightSum}% (must equal 100%)
                </span>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setEditWeights(false)} className="btn btn-secondary btn-sm">
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={Math.abs(weightSum - 100) > 0.01}
                    className="btn btn-primary btn-sm"
                  >
                    Save Version &amp; Audit
                  </button>
                </div>
              </div>
            )}
          </form>
        </div>
      )}
    </div>
  );
}
