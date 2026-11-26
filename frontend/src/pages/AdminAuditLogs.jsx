import React, { useEffect, useState } from 'react';
import { RefreshCw, Search, Shield } from 'lucide-react';
import { fetchAuditLogs } from '../api/adminClient';
import AdminModuleHeader from '../components/AdminModuleHeader';
import { PageHeader, StatusBadge } from '../components/ui';

export default function AdminAuditLogs() {
  const [logs, setLogs] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetchAuditLogs(search ? { search } : {});
      setLogs(res.data.audit_logs || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-6 fade-in">
      <PageHeader
        eyebrow="Append-Only SQLite Security Ledger"
        title="Immutable Security Audit Trail"
        subtitle="Chronological governance audit log. Deletion and updates are blocked at both route and DB layers."
        icon={Shield}
        actions={
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-[#6E7B73] absolute left-2.5 top-2.5" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && load()}
                placeholder="Filter actor or action..."
                className="pl-8 pr-3 py-1.5 rounded-lg bg-white border border-[#D2DBD4] text-xs text-[#141C17]"
              />
            </div>
            <button type="button" onClick={load} disabled={loading} className="btn btn-primary btn-sm">
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Filter
            </button>
          </div>
        }
      />

      <AdminModuleHeader
        whatItShows="Tamper-resistant chronological trail of admin logins, RBAC denials, flags, cache purges, and policy edits."
        adminAction="Filter by username or security action keyword to audit compliance and denied attempts."
        consequence="Strictly append-only; no endpoint or user role can edit or delete audit records."
      />

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
            {logs.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-6 text-center text-[#6E7B73]">No audit log entries match the current filter.</td>
              </tr>
            ) : (
              logs.map((l) => (
                <tr key={l.audit_id}>
                  <td className="p-3 font-mono text-[11px] text-[#4A5750]">
                    {l.timestamp ? new Date(l.timestamp).toLocaleString() : '—'}
                  </td>
                  <td className="p-3">
                    <div className="font-semibold text-[#141C17]">{l.actor}</div>
                    <div className="text-[10px] font-mono text-[#144D29]">{l.role}</div>
                  </td>
                  <td className="p-3 font-mono font-semibold text-[#141C17]">{l.action}</td>
                  <td className="p-3 font-mono text-[11px] text-[#4A5750]">{l.resource}</td>
                  <td className="p-3">
                    <StatusBadge status={l.result}>{l.result}</StatusBadge>
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
