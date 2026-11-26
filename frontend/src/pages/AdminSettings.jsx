import React, { useEffect, useState } from 'react';
import {
  Activity,
  HardDrive,
  MapPin,
  RefreshCw,
  Save,
  Settings,
  Shield,
  Sliders,
  Trash2,
  User,
} from 'lucide-react';
import {
  clearGisCache,
  fetchAuditLogs,
  fetchGisLogs,
  fetchGisOverview,
  fetchSystemHealth,
  fetchSystemSettings,
  fetchWeightages,
  probeSystemHealth,
  updateGisConfig,
  updateSystemSettings,
  updateWeightages,
} from '../api/adminClient';
import { useAdminAuth } from '../context/AdminAuthContext';
import { PageHeader, SectionCard, StatusBadge, TabBar } from '../components/ui';
import AdminModuleHeader from '../components/AdminModuleHeader';

export default function AdminSettings() {
  const { admin, hasPermission } = useAdminAuth();
  const [tab, setTab] = useState('health'); // health | gis | audit | policies | profile
  const [health, setHealth] = useState(null);
  const [gisOverview, setGisOverview] = useState(null);
  const [gisLogs, setGisLogs] = useState([]);
  const [audits, setAudits] = useState([]);
  const [auditSearch, setAuditSearch] = useState('');

  const [maintenanceMode, setMaintenanceMode] = useState(false);
  const [bannerMsg, setBannerMsg] = useState('');
  const [radius, setRadius] = useState(3000);
  const [timeoutSec, setTimeoutSec] = useState(45);
  const [retentionDays, setRetentionDays] = useState(30);
  const [maxUploadMb, setMaxUploadMb] = useState(25);

  const [weightage, setWeightage] = useState(null);
  const [weightsForm, setWeightsForm] = useState({
    price_weight: 30,
    location_weight: 25,
    facility_weight: 0,
    environment_weight: 10,
    infrastructure_weight: 20,
    utility_weight: 15,
  });

  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const canManage = hasPermission('settings:manage');

  const loadAll = async () => {
    setLoading(true);
    setErr('');
    try {
      const [hRes, gOvRes, gLogsRes, sRes, aRes, wRes] = await Promise.all([
        fetchSystemHealth().catch(() => ({ data: null })),
        fetchGisOverview().catch(() => ({ data: null })),
        fetchGisLogs().catch(() => ({ data: { logs: [] } })),
        fetchSystemSettings().catch(() => ({ data: null })),
        fetchAuditLogs(auditSearch ? { search: auditSearch } : {}).catch(() => ({ data: { audit_logs: [] } })),
        fetchWeightages().catch(() => ({ data: null })),
      ]);
      setHealth(hRes.data);
      setGisOverview(gOvRes.data);
      setGisLogs(gLogsRes.data?.logs || []);
      setAudits(aRes.data?.audit_logs || []);
      const s = sRes.data?.settings;
      if (s) {
        setMaintenanceMode(Boolean(s.application_config?.maintenance_mode));
        setBannerMsg(s.application_config?.maintenance_banner_message || '');
        setRadius(s.gis_configuration?.default_search_radius_meters || 3000);
        setTimeoutSec(s.gis_configuration?.api_timeout_seconds || 45);
        setRetentionDays(s.document_and_report_policies?.file_retention_days || 30);
        setMaxUploadMb(s.document_and_report_policies?.max_upload_size_mb || 25);
      }
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
    } catch (e) {
      setErr(e?.response?.data?.error || 'Failed to load system & settings data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleProbe = async () => {
    setMsg('');
    setLoading(true);
    try {
      await probeSystemHealth();
      setMsg('Active health probe executed across Flask/SQLite, ML pipeline, GIS, OCR, and Storage.');
      await loadAll();
    } finally {
      setLoading(false);
    }
  };

  const handleClearCache = async () => {
    if (!window.confirm('Flush in-memory OSM Overpass, ArcGIS, and Nominatim caches?')) return;
    const res = await clearGisCache();
    setMsg(res?.data?.message || 'GIS caches cleared.');
    loadAll();
  };

  const handleSavePolicies = async (e) => {
    e.preventDefault();
    setMsg('');
    setErr('');
    try {
      await updateSystemSettings({
        maintenance_mode: maintenanceMode,
        maintenance_banner_message: bannerMsg,
        default_search_radius_meters: Number(radius),
        api_timeout_seconds: Number(timeoutSec),
        file_retention_days: Number(retentionDays),
        max_upload_size_mb: Number(maxUploadMb),
      });
      await updateGisConfig({ search_radius_meters: Number(radius), api_timeout_seconds: Number(timeoutSec) }).catch(() => {});
      setMsg('System & GIS parameters updated and audited.');
    } catch (e2) {
      setErr(e2?.response?.data?.error || 'Settings save failed.');
    }
  };

  const handleSaveWeights = async (e) => {
    e.preventDefault();
    setMsg('');
    setErr('');
    try {
      const res = await updateWeightages(weightsForm);
      setWeightage(res.data);
      setMsg(`Weightage v${res.data.version} saved & audited. Prior evaluations remain locked.`);
    } catch (e2) {
      setErr(e2?.response?.data?.error || 'Weightage update failed.');
    }
  };

  const weightSum = Object.values(weightsForm).reduce((acc, v) => acc + Number(v || 0), 0);

  return (
    <div className="space-y-6 fade-in">
      <PageHeader
        eyebrow="Administration & Governance"
        title="System Health, GIS, Audit & Settings"
        subtitle="Unified diagnostics across Backend/Database, GIS sources, Security Audit Log, Application Policies, and Super Admin session profile."
        icon={Settings}
        breadcrumbs={['Admin Console', 'Settings & Profile']}
      />

      <TabBar
        tabs={[
          { key: 'health', label: 'Backend & DB Health', icon: HardDrive },
          { key: 'gis', label: 'GIS Source Health', icon: MapPin },
          { key: 'audit', label: 'Audit & Security Logs', icon: Shield },
          { key: 'policies', label: 'App Settings & Weights', icon: Sliders },
          { key: 'profile', label: 'Admin Profile & Security', icon: User },
        ]}
        activeKey={tab}
        onChange={setTab}
      />

      <AdminModuleHeader
        whatItShows="Live SQLite, ML artifact, GIS adapter uptime, error/audit logs, and global configuration."
        adminAction="Run health probes, clear stale GIS caches, review audit history, or update settings (Super Admin)."
        consequence="Audit history is strictly append-only; policy & weightage edits record full actor attribution."
      />

      {err && <div className="p-3 rounded-lg bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23]">{err}</div>}
      {msg && <div className="p-3 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D]">{msg}</div>}

      {tab === 'health' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleProbe}
              disabled={loading}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#144D29] text-white text-xs font-semibold"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Run Active Health Probe
            </button>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {(health?.services || []).map((svc) => (
              <div key={svc.service_key} className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-[#141C17]">{svc.service_name}</span>
                  <span className={`px-2 py-0.5 rounded font-mono text-[10px] ${
                    svc.status === 'OPERATIONAL' ? 'bg-emerald-500/15 text-[#14532D]' : 'bg-amber-500/20 text-[#85520E]'
                  }`}>
                    {svc.status}
                  </span>
                </div>
                <div className="text-[11px] font-mono text-[#4A5750]">
                  Checked: {svc.last_checked_at ? new Date(svc.last_checked_at).toLocaleString() : '—'}
                </div>
                {(svc.recent_errors || []).map((e, i) => (
                  <div key={i} className="text-[11px] text-[#85520E] bg-amber-500/10 p-2 rounded">{e}</div>
                ))}
              </div>
            ))}
          </div>
          {health?.storage_capacity && (
            <div className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <HardDrive className="w-5 h-5 text-[#144D29]" />
                <div className="text-xs text-[#4A5750]">
                  <strong className="text-[#141C17] block">Local Disk Storage</strong>
                  {health.storage_capacity.free_gb} GB free / {health.storage_capacity.total_gb} GB total
                </div>
              </div>
              <span className="font-mono font-bold text-[#144D29]">{health.storage_capacity.utilization_pct}% used</span>
            </div>
          )}
        </div>
      )}

      {tab === 'gis' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center flex-wrap gap-3">
            <span className="text-xs text-[#4A5750]">
              Strict 4-state telemetry across OSM Overpass, Nominatim &amp; ArcGIS World Geocoder.
            </span>
            <button
              type="button"
              onClick={handleClearCache}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-red-500/30 text-xs text-[#8C2D23] hover:bg-red-500/10"
            >
              <Trash2 className="w-3.5 h-3.5" /> Clear GIS Cache
            </button>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
            {(gisOverview?.endpoints || []).map((ep) => (
              <div key={ep.service_id} className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-2">
                <div className="flex justify-between">
                  <span className="font-mono text-[10px] text-[#144D29]">{ep.service_id}</span>
                  <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-[#14532D] font-mono text-[10px]">{ep.availability_status}</span>
                </div>
                <div className="text-xs font-semibold text-[#141C17]">{ep.service_name}</div>
                <div className="text-[11px] font-mono text-[#4A5750]">Success Rate: {ep.retrieval_success_rate_pct}%</div>
              </div>
            ))}
          </div>
          <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
                <tr>
                  <th className="p-3">Log ID</th>
                  <th className="p-3">Locality &amp; Taluk</th>
                  <th className="p-3">Coordinates</th>
                  <th className="p-3">Features</th>
                  <th className="p-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E3E8E4]">
                {gisLogs.slice(0, 30).map((l) => (
                  <tr key={l.log_id}>
                    <td className="p-3 font-mono text-[#144D29]">{l.log_id}</td>
                    <td className="p-3">{l.locality} · <span className="text-[#4A5750]">{l.taluk}</span></td>
                    <td className="p-3 font-mono text-[#4A5750]">{l.coordinates}</td>
                    <td className="p-3 font-mono">{l.features_returned}</td>
                    <td className="p-3 font-mono">{l.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'audit' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <input
              value={auditSearch}
              onChange={(e) => setAuditSearch(e.target.value)}
              placeholder="Filter actor or security action..."
              className="px-3 py-1.5 rounded-lg bg-white shadow-sm border border-[#D2DBD4] text-xs text-[#141C17]"
            />
            <button type="button" onClick={loadAll} className="px-3.5 py-1.5 rounded-lg bg-[#144D29] text-white text-xs font-semibold">
              Filter
            </button>
          </div>
          <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
                <tr>
                  <th className="p-3">Timestamp</th>
                  <th className="p-3">Actor &amp; Role</th>
                  <th className="p-3">Action</th>
                  <th className="p-3">Resource</th>
                  <th className="p-3">Result</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E3E8E4]">
                {audits.map((l) => (
                  <tr key={l.audit_id}>
                    <td className="p-3 font-mono text-[11px] text-[#4A5750]">{l.timestamp ? new Date(l.timestamp).toLocaleString() : '—'}</td>
                    <td className="p-3"><div className="text-[#141C17]">{l.actor}</div><div className="text-[10px] font-mono text-[#144D29]">{l.role}</div></td>
                    <td className="p-3 font-mono text-[#141C17]">{l.action}</td>
                    <td className="p-3 font-mono text-[11px] text-[#4A5750]">{l.resource}</td>
                    <td className="p-3 font-mono">{l.result}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'policies' && (
        <div className="grid lg:grid-cols-2 gap-6">
          <form onSubmit={handleSavePolicies} className="p-6 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-4 text-xs">
            <h3 className="text-sm font-semibold text-[#141C17] flex items-center gap-2"><MapPin className="w-4 h-4 text-[#144D29]" /> Application &amp; GIS Parameters</h3>
            <label className="flex items-center justify-between p-3 rounded bg-[#F6F8F6] border border-[#E3E8E4]">
              <span>Maintenance Banner Enabled</span>
              <input type="checkbox" disabled={!canManage} checked={maintenanceMode} onChange={(e) => setMaintenanceMode(e.target.checked)} />
            </label>
            <input value={bannerMsg} disabled={!canManage} onChange={(e) => setBannerMsg(e.target.value)} placeholder="Optional notice message" className="w-full px-3 py-2 rounded bg-[#F6F8F6] border border-[#D2DBD4] text-[#141C17]" />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[#4A5750] mb-1">GIS Radius (m)</label>
                <input type="number" disabled={!canManage} min={500} max={10000} value={radius} onChange={(e) => setRadius(e.target.value)} className="w-full px-3 py-2 rounded bg-[#F6F8F6] border border-[#D2DBD4] text-[#141C17] font-mono" />
              </div>
              <div>
                <label className="block text-[#4A5750] mb-1">Timeout (s)</label>
                <input type="number" disabled={!canManage} min={5} max={90} value={timeoutSec} onChange={(e) => setTimeoutSec(e.target.value)} className="w-full px-3 py-2 rounded bg-[#F6F8F6] border border-[#D2DBD4] text-[#141C17] font-mono" />
              </div>
              <div>
                <label className="block text-[#4A5750] mb-1">Retention Days</label>
                <input type="number" disabled={!canManage} min={1} max={365} value={retentionDays} onChange={(e) => setRetentionDays(e.target.value)} className="w-full px-3 py-2 rounded bg-[#F6F8F6] border border-[#D2DBD4] text-[#141C17] font-mono" />
              </div>
              <div>
                <label className="block text-[#4A5750] mb-1">Max Upload (MB)</label>
                <input type="number" disabled={!canManage} min={1} max={50} value={maxUploadMb} onChange={(e) => setMaxUploadMb(e.target.value)} className="w-full px-3 py-2 rounded bg-[#F6F8F6] border border-[#D2DBD4] text-[#141C17] font-mono" />
              </div>
            </div>
            {canManage ? (
              <button type="submit" className="inline-flex items-center gap-2 px-4 py-2 rounded bg-[#144D29] text-white font-semibold">
                <Save className="w-3.5 h-3.5" /> Save Settings
              </button>
            ) : (
              <div className="text-[#4A5750]">Read-only for Operations Admin. Super Admin access required to modify global parameters.</div>
            )}
          </form>

          <form onSubmit={handleSaveWeights} className="p-6 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-4 text-xs">
            <h3 className="text-sm font-semibold text-[#141C17] flex items-center gap-2">
              <Sliders className="w-4 h-4 text-[#144D29]" /> Scoring Framework Weightages {weightage ? `(v${weightage.version})` : ''}
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {[
                ['price_weight', 'Price Fair Value'],
                ['location_weight', 'Location'],
                ['facility_weight', 'Facilities'],
                ['environment_weight', 'Environment'],
                ['infrastructure_weight', 'Infrastructure'],
                ['utility_weight', 'Utilities'],
              ].map(([k, lbl]) => (
                <div key={k} className="p-3 rounded bg-[#F6F8F6] border border-[#E3E8E4]">
                  <div className="text-[11px] text-[#4A5750] mb-1">{lbl}</div>
                  <input
                    type="number"
                    step="0.5"
                    disabled={!canManage}
                    value={weightsForm[k]}
                    onChange={(e) => setWeightsForm((p) => ({ ...p, [k]: Number(e.target.value) }))}
                    className="w-full px-2 py-1 rounded bg-white shadow-sm border border-[#D2DBD4] text-[#141C17] font-mono"
                  />
                </div>
              ))}
            </div>
            <div className={`font-mono ${Math.abs(weightSum - 100) <= 0.01 ? 'text-[#14532D]' : 'text-[#8C2D23]'}`}>
              Sum: {weightSum}% (must equal 100%)
            </div>
            {canManage && (
              <button
                type="submit"
                disabled={Math.abs(weightSum - 100) > 0.01}
                className="inline-flex items-center gap-2 px-4 py-2 rounded bg-[#144D29] text-white font-semibold disabled:opacity-40"
              >
                <Shield className="w-3.5 h-3.5" /> Save Weightage Version
              </button>
            )}
          </form>
        </div>
      )}

      {tab === 'profile' && (
        <div className="space-y-4">
          <SectionCard
            title="Active Administrator Identity & Session Security"
            subtitle="Authenticated console account metadata and single-admin governance boundary"
            icon={User}
            badge={<StatusBadge status={admin?.status || 'ACTIVE'} />}
          >
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
                <div className="text-[#4A5750] uppercase text-[10px] font-semibold">Admin ID</div>
                <div className="font-mono font-bold text-[#144D29] mt-1">{admin?.admin_id || 'ADM-0002'}</div>
              </div>
              <div className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
                <div className="text-[#4A5750] uppercase text-[10px] font-semibold">Username</div>
                <div className="font-mono font-bold text-[#141C17] mt-1">{admin?.username || 'superadmin'}</div>
              </div>
              <div className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
                <div className="text-[#4A5750] uppercase text-[10px] font-semibold">Full Name &amp; Role</div>
                <div className="font-semibold text-[#141C17] mt-1">{admin?.full_name || 'System Super Admin'}</div>
                <div className="text-[11px] text-[#4A5750] mt-0.5">{admin?.role || 'SUPER_ADMIN'}</div>
              </div>
              <div className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
                <div className="text-[#4A5750] uppercase text-[10px] font-semibold">Governance Scope</div>
                <div className="font-semibold text-[#14532D] mt-1">Single Active Super Admin</div>
                <div className="text-[11px] text-[#4A5750] mt-0.5">Legacy admin accounts consolidated</div>
              </div>
            </div>

            {Array.isArray(admin?.permissions) && admin.permissions.length > 0 && (
              <div className="mt-4 pt-4 border-t border-[#E3E8E4]">
                <div className="text-xs font-semibold text-[#141C17] mb-2">
                  Granted RBAC Permissions ({admin.permissions.length})
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {admin.permissions.map((perm) => (
                    <span
                      key={perm}
                      className="px-2.5 py-1 rounded-md bg-[#E7F5EC] border border-[#BCE0C8] text-[#14532D] font-mono text-[11px]"
                    >
                      {perm}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </SectionCard>
        </div>
      )}
    </div>
  );
}
