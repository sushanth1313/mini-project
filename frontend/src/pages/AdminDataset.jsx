import React, { useEffect, useState } from 'react';
import { CheckCircle2, Database, Download, ShieldCheck, Sparkles } from 'lucide-react';
import { getDatasetRecords } from '../api/client';
import {
  ADMIN_TOKEN_KEY,
  cleanAdminDataset,
  downloadAdminDatasetCsvUrl,
  fetchAdminDatasets,
  validateAdminDataset,
} from '../api/adminClient';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';

export default function AdminDataset() {
  const { hasPermission } = useAdminAuth();
  const [datasets, setDatasets] = useState([]);
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const loadAll = async () => {
    setLoading(true);
    setErr('');
    try {
      const [dsRes, recRes] = await Promise.all([
        fetchAdminDatasets(),
        getDatasetRecords({ per_page: 50 }),
      ]);
      setDatasets(dsRes.data.datasets || []);
      setRecords(recRes.data.records || []);
      setTotal(recRes.data.total || 0);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Failed to load dataset governance records.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleValidate = async (dsId) => {
    setMsg('');
    setErr('');
    try {
      const res = await validateAdminDataset(dsId);
      setMsg(`Validated ${dsId}: ${res.data.validation_summary?.validation_status || 'DONE'}`);
      loadAll();
    } catch (e) {
      setErr(e?.response?.data?.error || 'Dataset validation failed.');
    }
  };

  const handleClean = async (dsId) => {
    if (!window.confirm(`Create a cleaned version from dataset ${dsId}? Raw source rows remain untouched.`)) return;
    setMsg('');
    setErr('');
    try {
      const res = await cleanAdminDataset(dsId, {});
      setMsg(`Created clean version ${res.data.cleaned_dataset?.dataset_id || 'successfully'}.`);
      loadAll();
    } catch (e) {
      setErr(e?.response?.data?.error || 'Dataset cleaning failed.');
    }
  };

  const handleDownloadCsv = async (dsId) => {
    const token = localStorage.getItem(ADMIN_TOKEN_KEY);
    const resp = await fetch(downloadAdminDatasetCsvUrl(dsId), {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await resp.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${dsId}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#E3E8E4] pb-4">
        <div>
          <h1 className="font-serif text-2xl text-[#141C17] flex items-center gap-2">
            <Database className="w-5 h-5 text-[#144D29]" /> Curated Dataset Engine (Mysuru District)
          </h1>
          <p className="text-xs text-[#4A5750] mt-1">
            Total live SQLite dataset rows: {total.toLocaleString()} · Schema, bounds &amp; outlier governance
          </p>
        </div>
      </div>

      <AdminModuleHeader
        whatItShows={`Master Mysuru ${total.toLocaleString()}-record dataset versions, validation checks, and curated training rows.`}
        adminAction="Validate bounding box & taluk consistency, generate cleaned versions, or export audited CSV."
        consequence="Cleaning creates a new versioned snapshot; original dataset rows are never destructively deleted."
      />

      {err && <div className="p-3 rounded-lg bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23]">{err}</div>}
      {msg && <div className="p-3 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D]">{msg}</div>}

      {/* Versioned Datasets Table */}
      <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
            <tr>
              <th className="p-3">Dataset ID</th>
              <th className="p-3">Name / Source</th>
              <th className="p-3">Rows</th>
              <th className="p-3">Validation Status</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E3E8E4]">
            {datasets.map((ds) => (
              <tr key={ds.dataset_id}>
                <td className="p-3 font-mono text-[#144D29]">{ds.dataset_id}</td>
                <td className="p-3">
                  <div className="text-[#141C17] font-medium">{ds.dataset_name || ds.filename}</div>
                  <div className="text-[11px] text-[#4A5750]">{ds.description || 'Mysuru District curated property dataset'}</div>
                </td>
                <td className="p-3 font-mono">{ds.row_count ?? total}</td>
                <td className="p-3">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded font-mono text-[10px] ${
                    ds.ready_for_training ? 'bg-[#E7F5EC] text-[#14532D]' : 'bg-[#FEF6E6] text-[#85520E]'
                  }`}>
                    <CheckCircle2 className="w-3 h-3" /> {ds.validation_status || 'PENDING'}
                  </span>
                </td>
                <td className="p-3 flex flex-wrap gap-1.5">
                  {hasPermission('datasets:validate') && (
                    <button type="button" onClick={() => handleValidate(ds.dataset_id)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px] hover:border-[#144D29]">
                      <ShieldCheck className="w-3 h-3 text-[#14532D]" /> Validate
                    </button>
                  )}
                  {hasPermission('datasets:clean') && (
                    <button type="button" onClick={() => handleClean(ds.dataset_id)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px] hover:border-[#144D29]">
                      <Sparkles className="w-3 h-3 text-[#144D29]" /> Clean Copy
                    </button>
                  )}
                  {hasPermission('datasets:download') && (
                    <button type="button" onClick={() => handleDownloadCsv(ds.dataset_id)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px] hover:border-[#144D29]">
                      <Download className="w-3 h-3" /> CSV
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Curated Rows Sample */}
      <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
        <div className="p-4 border-b border-[#E3E8E4] text-sm font-semibold text-[#141C17]">
          SQLite Training Dataset Sample (Latest 50 of {total.toLocaleString()} records)
        </div>
        {loading ? (
          <div className="p-6 text-xs text-[#4A5750]">Loading dataset rows...</div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
              <tr>
                <th className="p-3">ID</th>
                <th className="p-3">Locality &amp; Taluk</th>
                <th className="p-3">Area (sq.ft)</th>
                <th className="p-3">Total Price (₹)</th>
                <th className="p-3">Rate / sq.ft</th>
                <th className="p-3">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E3E8E4]">
              {records.map((r) => (
                <tr key={r.id}>
                  <td className="p-3 font-mono text-[#144D29]">{r.id}</td>
                  <td className="p-3">{r.village_or_locality} · <span className="text-[#4A5750]">{r.taluk}</span></td>
                  <td className="p-3 font-mono">{r.land_area_sqft}</td>
                  <td className="p-3 font-mono">₹{Number(r.price_inr || 0).toLocaleString('en-IN')}</td>
                  <td className="p-3 font-mono">₹{Number(r.price_per_sqft_inr || 0).toLocaleString('en-IN')}</td>
                  <td className="p-3 text-[#4A5750]">{r.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
