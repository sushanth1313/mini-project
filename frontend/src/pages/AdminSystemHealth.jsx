import React, { useEffect, useState } from 'react';
import { Activity, HardDrive, RefreshCw } from 'lucide-react';
import { fetchSystemHealth, probeSystemHealth } from '../api/adminClient';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';
import { PageHeader, StatusBadge } from '../components/ui';

export default function AdminSystemHealth() {
  const { hasPermission } = useAdminAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetchSystemHealth();
      setData(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleProbe = async () => {
    setLoading(true);
    try {
      await probeSystemHealth();
      await load();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 fade-in">
      <PageHeader
        eyebrow="Runtime Infrastructure Probe"
        title="System Health & Diagnostics"
        subtitle="Live SQLite ping, ML artifact verification, Overpass/Nominatim status, and OCR binary availability."
        icon={Activity}
        actions={
          hasPermission('health:check') && (
            <button type="button" onClick={handleProbe} disabled={loading} className="btn btn-primary btn-sm">
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Run Active Probe
            </button>
          )
        }
      />

      <AdminModuleHeader
        whatItShows="Real host checks across SQLite DB, ML pipeline artifact, GIS endpoints, OCR binaries, and disk space."
        adminAction="Run Active Probe to verify live connectivity and inspect degraded services."
        consequence="Services never report OPERATIONAL without an actual active diagnostic check."
      />

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {(data?.services || []).map((svc) => (
          <div key={svc.service_key} className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-bold text-[#141C17]">{svc.service_name}</span>
              <StatusBadge status={svc.status}>{svc.status}</StatusBadge>
            </div>
            <div className="text-[11px] font-mono text-[#6E7B73]">
              Checked: {svc.last_checked_at ? new Date(svc.last_checked_at).toLocaleString() : '—'}
            </div>
            {(svc.recent_errors || []).map((err, i) => (
              <div key={i} className="text-[11px] text-[#85520E] bg-[#FEF6E6] border border-[#EDD49F] p-2 rounded">
                {err}
              </div>
            ))}
          </div>
        ))}
      </div>

      {data?.storage_capacity && (
        <div className="p-5 rounded-xl bg-white shadow-sm border border-[#E3E8E4] flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] flex items-center justify-center text-[#144D29]">
              <HardDrive className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-[#141C17]">Local Disk Storage</div>
              <div className="text-xs font-mono text-[#4A5750]">
                {data.storage_capacity.free_gb} GB free / {data.storage_capacity.total_gb} GB total
              </div>
            </div>
          </div>
          <div className="text-lg font-mono font-bold text-[#144D29]">
            {data.storage_capacity.utilization_pct}% used
          </div>
        </div>
      )}
    </div>
  );
}
