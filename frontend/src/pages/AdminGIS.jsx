import React, { useEffect, useState } from 'react';
import { Compass, MapPin, RefreshCw, Save, Trash2 } from 'lucide-react';
import {
  clearGisCache,
  fetchGisLogs,
  fetchGisOverview,
  updateGisConfig,
} from '../api/adminClient';
import { getGisConfig } from '../api/client';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';
import { PageHeader, StatCard, StatusBadge } from '../components/ui';

export default function AdminGIS() {
  const { hasPermission } = useAdminAuth();
  const [overview, setOverview] = useState(null);
  const [gisCfg, setGisCfg] = useState(null);
  const [logs, setLogs] = useState([]);
  const [radius, setRadius] = useState(3000);
  const [timeoutSec, setTimeoutSec] = useState(45);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const load = async () => {
    setLoading(true);
    setErr('');
    try {
      const [oRes, lRes, cfgRes] = await Promise.all([
        fetchGisOverview(),
        fetchGisLogs(),
        getGisConfig().catch(() => ({ data: null })),
      ]);
      setOverview(oRes.data);
      setLogs(lRes.data.logs || []);
      setGisCfg(cfgRes.data || null);
      if (oRes.data?.configuration) {
        setRadius(oRes.data.configuration.search_radius_meters || 3000);
        setTimeoutSec(oRes.data.configuration.api_timeout_seconds || 45);
      }
    } catch (e) {
      setErr(e?.response?.data?.error || 'Failed to load GIS monitor.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleSaveConfig = async (e) => {
    e.preventDefault();
    setMsg('');
    setErr('');
    try {
      await updateGisConfig({ search_radius_meters: Number(radius), api_timeout_seconds: Number(timeoutSec) });
      setMsg('GIS configuration updated & audited.');
      load();
    } catch (e2) {
      setErr(e2?.response?.data?.error || 'GIS config update failed.');
    }
  };

  const handleClearCache = async () => {
    if (!window.confirm('Flush all in-memory OSM Overpass, ArcGIS, and Nominatim caches?')) return;
    const res = await clearGisCache();
    setMsg(res?.data?.message || 'GIS cache cleared and recorded in audit log.');
    load();
  };

  const kgisCov = gisCfg?.kgis_coverage;

  return (
    <div className="space-y-6 fade-in">
      <PageHeader
        eyebrow="Geospatial Services & KGIS Boundaries"
        title="GIS Management & Source Health"
        subtitle="Inspect KGIS polygon coverage, Overpass/Nominatim adapters, search radius parameters, and lookup logs."
        icon={MapPin}
        actions={
          <>
            {hasPermission('gis:manage_cache') && (
              <button
                type="button"
                onClick={handleClearCache}
                className="btn btn-secondary btn-sm"
                style={{ color: '#8C2D23', borderColor: '#ECC2BC' }}
              >
                <Trash2 size={14} /> Clear GIS Cache
              </button>
            )}
            <button type="button" onClick={load} disabled={loading} className="btn btn-primary btn-sm">
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
            </button>
          </>
        }
      />

      <AdminModuleHeader
        whatItShows="Loaded KGIS Mysuru boundary layers plus Overpass, Nominatim, and Google geocoder health."
        adminAction="Tune search radius/timeout or flush stale in-memory GIS caches."
        consequence="Preserves strict 4-state telemetry (SUCCESS, NO_DATA, PARTIAL, SOURCE_UNAVAILABLE)."
      />

      {err && <div className="p-3 rounded-lg bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23]">{err}</div>}
      {msg && <div className="p-3 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D]">{msg}</div>}

      {kgisCov && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="KGIS Taluks & Hoblis"
            value={`${kgisCov.unique_kgis_taluks?.length ?? 0} Taluks / ${kgisCov.hobli_polygons ?? 0} Hoblis`}
            sub={`${kgisCov.taluk_polygons ?? 0} KGIS taluk polygons loaded`}
            icon={Compass}
            tone="green"
          />
          <StatCard
            label="Revenue Villages"
            value={kgisCov.revenue_village_polygons?.toLocaleString() ?? '0'}
            sub={`${kgisCov.villages_with_lgd_gp_code?.toLocaleString() ?? 0} mapped with LGD GP Code`}
            icon={MapPin}
            tone="green"
          />
          <StatCard
            label="ULBs & Municipal Wards"
            value={`${kgisCov.urban_local_body_polygons ?? 0} ULBs / ${kgisCov.municipal_ward_polygons ?? 0} Wards`}
            sub={`Includes ${kgisCov.mcc_mysuru_wards ?? 0} MCC Mysuru wards`}
            icon={MapPin}
            tone="blue"
          />
          <StatCard
            label="Assembly Constituencies"
            value="0 Loaded"
            sub="Authoritative AC GeoJSON dataset not yet loaded"
            icon={Compass}
            tone="amber"
          />
        </div>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {(overview?.endpoints || []).map((ep) => (
          <div key={ep.service_id} className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[10px] font-bold text-[#144D29]">{ep.service_id}</span>
              <StatusBadge status={ep.availability_status}>{ep.availability_status}</StatusBadge>
            </div>
            <div className="text-xs font-bold text-[#141C17]">{ep.service_name}</div>
            <div className="text-[11px] font-mono text-[#6E7B73] break-all">{ep.endpoint_url}</div>
            <div className="text-xs font-mono font-semibold text-[#144D29]">Success Rate: {ep.retrieval_success_rate_pct}%</div>
          </div>
        ))}
      </div>

      {hasPermission('gis:configure') && (
        <form onSubmit={handleSaveConfig} className="p-5 rounded-xl bg-white shadow-sm border border-[#E3E8E4] flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-[11px] font-semibold text-[#4A5750] mb-1">Search Radius (meters)</label>
            <input
              type="number"
              min={500}
              max={10000}
              value={radius}
              onChange={(e) => setRadius(e.target.value)}
              className="px-3 py-2 rounded-lg bg-[#F6F8F6] border border-[#D2DBD4] text-xs font-mono text-[#141C17]"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-[#4A5750] mb-1">API Timeout (seconds)</label>
            <input
              type="number"
              min={5}
              max={90}
              value={timeoutSec}
              onChange={(e) => setTimeoutSec(e.target.value)}
              className="px-3 py-2 rounded-lg bg-[#F6F8F6] border border-[#D2DBD4] text-xs font-mono text-[#141C17]"
            />
          </div>
          <button type="submit" className="btn btn-primary btn-sm">
            <Save size={14} /> Save GIS Parameters
          </button>
        </form>
      )}

      <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
        <div className="px-4 py-3 border-b border-[#E3E8E4] text-xs font-bold text-[#141C17]">
          Recent GIS Facility &amp; Geocoding Queries
        </div>
        <table className="w-full text-left text-xs">
          <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
            <tr>
              <th className="p-3">Log ID</th>
              <th className="p-3">Locality &amp; Taluk</th>
              <th className="p-3">Coordinates</th>
              <th className="p-3">Features Returned</th>
              <th className="p-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E3E8E4]">
            {logs.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-6 text-center text-[#6E7B73]">No GIS logs recorded yet.</td>
              </tr>
            ) : (
              logs.slice(0, 40).map((l) => (
                <tr key={l.log_id}>
                  <td className="p-3 font-mono text-[#144D29]">{l.log_id}</td>
                  <td className="p-3">
                    <div className="font-semibold text-[#141C17]">{l.locality}</div>
                    <div className="text-[11px] text-[#4A5750]">{l.taluk}</div>
                  </td>
                  <td className="p-3 font-mono text-[#4A5750]">{l.coordinates}</td>
                  <td className="p-3 font-mono text-[#141C17]">{l.features_returned}</td>
                  <td className="p-3">
                    <StatusBadge status={l.status}>{l.status}</StatusBadge>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
