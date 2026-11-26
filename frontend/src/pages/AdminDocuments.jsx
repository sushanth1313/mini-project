import React, { useEffect, useState } from 'react';
import { CheckCircle2, Eye, FileDown, FileText, Lock, ShieldAlert, ShieldCheck, Trash2, X } from 'lucide-react';
import {
  ADMIN_TOKEN_KEY,
  checkReportConsistency,
  downloadAdminDocumentFileUrl,
  downloadAdminReportUrl,
  fetchAdminDocumentDetail,
  fetchAdminDocuments,
  fetchAdminReports,
  processDocumentDeletion,
  updateDocumentVerification,
} from '../api/adminClient';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';

export default function AdminDocuments() {
  const { hasPermission } = useAdminAuth();
  const [tab, setTab] = useState('documents'); // documents | reports
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState({});
  const [reports, setReports] = useState([]);
  const [sensitiveGranted, setSensitiveGranted] = useState(true);
  const [inspectJob, setInspectJob] = useState(null);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const load = async () => {
    setErr('');
    try {
      const [docRes, repRes] = await Promise.all([
        fetchAdminDocuments(),
        fetchAdminReports().catch(() => ({ data: { reports: [] } })),
      ]);
      setJobs(docRes.data.jobs || []);
      setStats(docRes.data.statistics || {});
      setSensitiveGranted(docRes.data.sensitive_access_granted !== false);
      setReports(repRes.data?.reports || []);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Failed to load documents & reports oversight.');
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleInspect = async (jobId) => {
    setErr('');
    try {
      const res = await fetchAdminDocumentDetail(jobId);
      setInspectJob(res.data.job);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Could not inspect document job.');
    }
  };

  const handleVerifyOfficial = async (job) => {
    const ref = window.prompt(
      'Enter official Bhoomi/Kaveri reference ID (server blocks automated legal title claims):',
      job.official_verification_reference || ''
    );
    if (!ref) return;
    try {
      await updateDocumentVerification(job.job_id, {
        official_verification_status: 'INDEPENDENTLY_VERIFIED_OFFICIAL',
        official_verification_reference: ref,
      });
      setMsg(`Recorded official portal reference for ${job.job_id}.`);
      load();
    } catch (e) {
      setErr(e?.response?.data?.error || 'Verification update failed.');
    }
  };

  const handleVerifyReport = async (reportId) => {
    try {
      const res = await checkReportConsistency(reportId);
      setMsg(`Report ${reportId} integrity: ${res.data.consistency_check_passed ? 'SHA-256 VERIFIED' : 'MISSING ON DISK'}.`);
      load();
    } catch (e) {
      setErr(e?.response?.data?.error || 'Integrity check failed.');
    }
  };

  const handleDownloadPdf = async (reportId) => {
    setErr('');
    const token = localStorage.getItem(ADMIN_TOKEN_KEY);
    const resp = await fetch(downloadAdminReportUrl(reportId), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) {
      setErr(`Could not download PDF for ${reportId} (${resp.status}).`);
      return;
    }
    const blob = await resp.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${reportId}.pdf`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  const handleOpenUploadedFile = async (jobId, docId, filename) => {
    setErr('');
    const token = localStorage.getItem(ADMIN_TOKEN_KEY);
    const resp = await fetch(downloadAdminDocumentFileUrl(jobId, docId), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) {
      setErr('Unauthorized or file unavailable.');
      return;
    }
    const blob = await resp.blob();
    const url = window.URL.createObjectURL(blob);
    window.open(url, '_blank', 'noopener,noreferrer');
    setTimeout(() => window.URL.revokeObjectURL(url), 10000);
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#E3E8E4] pb-4">
        <div>
          <h1 className="font-serif text-2xl text-[#141C17] flex items-center gap-2">
            <FileText className="w-5 h-5 text-[#144D29]" /> Documents &amp; PDF Reports Oversight
          </h1>
          <p className="text-xs text-[#4A5750] mt-1">
            Review OCR processing status, document access logs, and SHA-256 verified A4 PDF reports.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setTab('documents')}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold ${tab === 'documents' ? 'bg-[#144D29] text-white' : 'border border-[#D2DBD4] text-[#4A5750]'}`}
          >
            Document OCR Jobs ({jobs.length})
          </button>
          <button
            type="button"
            onClick={() => setTab('reports')}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold ${tab === 'reports' ? 'bg-[#144D29] text-white' : 'border border-[#D2DBD4] text-[#4A5750]'}`}
          >
            Generated PDF Reports ({reports.length})
          </button>
        </div>
      </div>

      <AdminModuleHeader
        whatItShows="Customer land document scrutiny jobs, failed/low-confidence OCR states, and immutable PDF snapshots."
        adminAction="Inspect processing status, verify SHA-256 report files, or purge approved deletion requests."
        consequence="Sensitive customer OCR text stays masked for standard Admins; automated title clearance is strictly blocked."
      />

      {!sensitiveGranted && (
        <div className="p-3.5 rounded-xl bg-[#ECF5EE] border border-[#BCE0C8] text-xs text-[#141C17] flex items-center gap-2.5">
          <Lock className="w-4 h-4 text-[#144D29] shrink-0" />
          <span>
            <strong>Privacy Protection Active:</strong> Standard Admin role views status metadata only. Raw OCR text is masked on the backend.
          </span>
        </div>
      )}

      {err && <div className="p-3 rounded-lg bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23]">{err}</div>}
      {msg && <div className="p-3 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D]">{msg}</div>}

      {tab === 'documents' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              ['Total Document Jobs', stats.total_jobs ?? 0],
              ['Avg OCR Confidence', `${stats.avg_ocr_confidence_pct ?? 0}%`],
              ['Mismatches Flagged', stats.cross_document_mismatch_count ?? 0],
              ['Failed OCR Jobs', stats.ocr_failure_count ?? 0],
            ].map(([lbl, val]) => (
              <div key={lbl} className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4]">
                <div className="text-xs text-[#4A5750]">{lbl}</div>
                <div className="text-xl font-mono font-bold text-[#141C17] mt-1">{val}</div>
              </div>
            ))}
          </div>

          <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
                <tr>
                  <th className="p-3">Analysis ID &amp; Date</th>
                  <th className="p-3">User &amp; Docs Detected</th>
                  <th className="p-3">OCR Conf.</th>
                  <th className="p-3">Mismatches / Risks</th>
                  <th className="p-3">Report &amp; Verif.</th>
                  <th className="p-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E3E8E4]">
                {jobs.map((j) => (
                  <tr key={j.job_id}>
                    <td className="p-3">
                      <div className="font-mono text-[#144D29] font-semibold">{j.job_id}</div>
                      <div className="text-[10px] font-mono text-[#4A5750]">{j.submitted_at ? new Date(j.submitted_at).toLocaleDateString() : '—'}</div>
                    </td>
                    <td className="p-3">
                      <div className="text-[#141C17] font-medium">{j.property_reference}</div>
                      <div className="text-[11px] text-[#4A5750]">User: {j.user_name || j.user_id} · {j.document_category}</div>
                    </td>
                    <td className="p-3 font-mono">{j.ocr_confidence_pct}% ({j.ocr_status})</td>
                    <td className="p-3 font-mono">
                      <div>Mismatch: {j.cross_document_mismatch_detected ? 'YES' : 'NO'} ({j.confirmed_mismatches_count || 0})</div>
                      <div className="text-[10px] text-[#4A5750]">Legal flags: {j.legal_concerns_count ?? 0}</div>
                    </td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded bg-[#E3E8E4] text-[#141C17] font-mono text-[10px]">
                        {j.official_verification_status}
                      </span>
                      {j.report_pdf_exists && (
                        <div className="text-[10px] font-mono text-[#14532D] mt-1">PDF Ready ({j.report_id})</div>
                      )}
                    </td>
                    <td className="p-3 flex flex-wrap gap-1.5">
                      <button type="button" onClick={() => handleInspect(j.job_id)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px] text-[#141C17]">
                        <Eye className="w-3 h-3 text-[#144D29]" /> Inspect
                      </button>
                      {j.report_pdf_exists && hasPermission('reports:download') && (
                        <button type="button" onClick={() => handleDownloadPdf(j.report_id)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px]">
                          <FileDown className="w-3 h-3 text-[#144D29]" /> PDF
                        </button>
                      )}
                      {hasPermission('documents:inspect_sensitive') && (
                        <button type="button" onClick={() => handleVerifyOfficial(j)} className="px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px]">
                          Attach Ref
                        </button>
                      )}
                      {hasPermission('documents:delete_requests') && (
                        <button
                          type="button"
                          onClick={() => {
                            if (window.confirm(`Permanently purge document analysis ${j.job_id}?`)) {
                              processDocumentDeletion(j.job_id, { decision: 'APPROVED' }).then(load);
                            }
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-red-500/30 text-[#8C2D23] text-[11px]"
                        >
                          <Trash2 className="w-3 h-3" /> Purge
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {jobs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-[#4A5750]">
                      No document analysis jobs recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'reports' && (
        <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
              <tr>
                <th className="p-3">Report ID</th>
                <th className="p-3">Property &amp; Type</th>
                <th className="p-3">Size</th>
                <th className="p-3">SHA-256 Hash</th>
                <th className="p-3">Disk Check</th>
                <th className="p-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E3E8E4]">
              {reports.slice(0, 60).map((r) => (
                <tr key={r.report_id}>
                  <td className="p-3 font-mono text-[#144D29]">{r.report_id}</td>
                  <td className="p-3">
                    <div className="text-[#141C17] font-medium">{r.property_reference}</div>
                    <div className="text-[11px] text-[#4A5750]">{r.report_type} · {r.taluk}</div>
                  </td>
                  <td className="p-3 font-mono">{r.file_size_kb} KB</td>
                  <td className="p-3 font-mono text-[10px] text-[#4A5750] max-w-[180px] truncate">{r.snapshot_hash_sha256 || 'missing'}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded font-mono text-[10px] ${r.consistency_check_passed ? 'bg-emerald-500/15 text-[#14532D]' : 'bg-red-500/20 text-[#8C2D23]'}`}>
                      {r.report_status}
                    </span>
                  </td>
                  <td className="p-3 flex gap-2">
                    <button type="button" onClick={() => handleVerifyReport(r.report_id)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px]">
                      <ShieldCheck className="w-3 h-3 text-emerald-400" /> Verify SHA
                    </button>
                    <button type="button" onClick={() => handleDownloadPdf(r.report_id)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px]">
                      <FileDown className="w-3 h-3 text-[#144D29]" /> Download PDF
                    </button>
                  </td>
                </tr>
              ))}
              {reports.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-6 text-center text-[#4A5750]">No generated PDF reports found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {inspectJob && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="w-full max-w-xl rounded-2xl bg-white shadow-sm border border-[#1B6336] p-6 space-y-4 text-xs">
            <div className="flex items-center justify-between border-b border-[#E3E8E4] pb-3">
              <div>
                <div className="font-mono text-[#144D29]">{inspectJob.job_id}</div>
                <h3 className="font-serif text-lg text-[#141C17]">{inspectJob.property_reference}</h3>
              </div>
              <button type="button" onClick={() => setInspectJob(null)} className="text-[#4A5750] hover:text-[#141C17]">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-2">
              <div><strong>Category:</strong> {inspectJob.document_category}</div>
              <div><strong>OCR Confidence:</strong> {inspectJob.ocr_confidence_pct}% ({inspectJob.ocr_status})</div>
              <div><strong>Mismatch Detected:</strong> {inspectJob.cross_document_mismatch_detected ? 'YES' : 'NO'} ({inspectJob.confirmed_mismatches_count || 0})</div>
              <div><strong>Legal Concerns:</strong> {inspectJob.legal_concerns_count ?? 0}</div>
              <div><strong>Assessment:</strong> {inspectJob.overall_assessment || '—'}</div>
              {Array.isArray(inspectJob.files) && inspectJob.files.length > 0 && (
                <div className="space-y-1.5 pt-2">
                  <strong>Uploaded Documents:</strong>
                  {inspectJob.files.map((f) => (
                    <div key={f.document_id} className="flex items-center justify-between p-2 rounded bg-[#F6F8F6] border border-[#E3E8E4]">
                      <span>{f.original_filename} ({f.document_type})</span>
                      {hasPermission('documents:inspect_sensitive') && (
                        <button
                          type="button"
                          onClick={() => handleOpenUploadedFile(inspectJob.job_id, f.document_id, f.original_filename)}
                          className="px-2 py-1 rounded border border-[#D2DBD4] text-[11px]"
                        >
                          View File
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {inspectJob.raw_text_preview && (
                <div className="p-3 rounded bg-[#F6F8F6] border border-[#E3E8E4] font-mono text-[11px] text-[#4A5750]">
                  {inspectJob.raw_text_preview}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
