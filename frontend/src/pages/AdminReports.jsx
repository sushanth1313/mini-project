import React, { useEffect, useState } from 'react';
import { CheckCircle2, FileDown, ShieldCheck } from 'lucide-react';
import {
  ADMIN_TOKEN_KEY,
  checkReportConsistency,
  downloadAdminReportUrl,
  fetchAdminReports,
} from '../api/adminClient';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';

export default function AdminReports() {
  const { hasPermission } = useAdminAuth();
  const [reports, setReports] = useState([]);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const load = async () => {
    try {
      const res = await fetchAdminReports();
      setReports(res.data.reports || []);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Failed to load reports.');
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleVerify = async (reportId) => {
    try {
      const res = await checkReportConsistency(reportId);
      setMsg(`Report ${reportId} integrity: ${res.data.consistency_check_passed ? 'SHA-256 VERIFIED' : 'MISMATCH / MISSING'}.`);
      load();
    } catch (e) {
      setErr(e?.response?.data?.error || 'Integrity check failed.');
    }
  };

  const handleDownload = async (reportId) => {
    const token = localStorage.getItem(ADMIN_TOKEN_KEY);
    const resp = await fetch(downloadAdminReportUrl(reportId), {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await resp.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${reportId}.json`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="border-b border-[#E3E8E4] pb-4">
        <h1 className="font-serif text-2xl text-[#141C17] flex items-center gap-2">
          <FileDown className="w-5 h-5 text-[#144D29]" /> Immutable PDF Reports Registry
        </h1>
        <p className="text-xs text-[#4A5750] mt-1">
          Live SHA-256 verification against generated PDF files on disk ({reports.length} records).
        </p>
      </div>

      <AdminModuleHeader
        whatItShows="Generated valuation & document due-diligence A4 PDF artifacts with SHA-256 integrity hashes."
        adminAction="Click Verify SHA to verify the PDF exists unmodified on disk or download report metadata."
        consequence="Snapshot PDFs are read-only; missing or tampered disk files immediately flag as inconsistent."
      />

      {err && <div className="p-3 rounded-lg bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23]">{err}</div>}
      {msg && <div className="p-3 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D]">{msg}</div>}

      <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
            <tr>
              <th className="p-3">Report ID</th>
              <th className="p-3">Property &amp; Type</th>
              <th className="p-3">Size</th>
              <th className="p-3">SHA-256 Snapshot</th>
              <th className="p-3">Status</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E3E8E4]">
            {reports.slice(0, 60).map((r) => (
              <tr key={r.report_id}>
                <td className="p-3 font-mono text-[#144D29]">{r.report_id}</td>
                <td className="p-3">
                  <div className="text-[#141C17] font-medium">{r.property_reference}</div>
                  <div className="text-[11px] text-[#4A5750]">{r.report_type} • {r.taluk}</div>
                </td>
                <td className="p-3 font-mono">{r.file_size_kb} KB</td>
                <td className="p-3 font-mono text-[10px] text-[#6E7B73] max-w-[180px] truncate" title={r.snapshot_hash_sha256 || ''}>
                  {r.snapshot_hash_sha256 || 'missing-on-disk'}
                </td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded font-mono text-[10px] ${
                    r.consistency_check_passed ? 'bg-[#E7F5EC] text-[#14532D]' : 'bg-[#FDEEEC] text-[#8C2D23]'
                  }`}>
                    {r.report_status}
                  </span>
                </td>
                <td className="p-3 flex gap-2">
                  {hasPermission('reports:consistency') && (
                    <button
                      type="button"
                      onClick={() => handleVerify(r.report_id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px]"
                    >
                      <ShieldCheck className="w-3 h-3 text-[#14532D]" /> Verify SHA
                    </button>
                  )}
                  {hasPermission('reports:download') && (
                    <button
                      type="button"
                      onClick={() => handleDownload(r.report_id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px]"
                    >
                      <CheckCircle2 className="w-3 h-3 text-[#144D29]" /> Metadata
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
