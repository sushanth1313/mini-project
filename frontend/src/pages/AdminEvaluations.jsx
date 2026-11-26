import React, { useEffect, useState } from 'react';
import { BarChart2, Eye, Flag, MessageSquare, Search, X } from 'lucide-react';
import {
  fetchAdminEvaluationDetail,
  fetchAdminEvaluations,
  flagAdminEvaluation,
} from '../api/adminClient';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';

export default function AdminEvaluations() {
  const { hasPermission } = useAdminAuth();
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [talukFilter, setTalukFilter] = useState('');
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [inspectDetail, setInspectDetail] = useState(null);
  const [inspectLoading, setInspectLoading] = useState(false);
  const [flagModal, setFlagModal] = useState(null);
  const [flagReasonInput, setFlagReasonInput] = useState('');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const load = async (targetPage = page) => {
    setLoading(true);
    setErr('');
    try {
      const params = { page: targetPage, per_page: 20 };
      if (talukFilter) params.taluk = talukFilter;
      if (flaggedOnly) params.flagged = 'true';
      if (search.trim()) params.search = search.trim();
      const res = await fetchAdminEvaluations(params);
      setRows(res.data.evaluations || []);
      setTotal(res.data.total || 0);
      setPage(res.data.page || targetPage);
      setTotalPages(res.data.total_pages || 1);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Failed to load property evaluations.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setPage(1);
    load(1);
  }, [talukFilter, flaggedOnly]);

  const handleInspect = async (evaluationId) => {
    setInspectLoading(true);
    setErr('');
    try {
      const res = await fetchAdminEvaluationDetail(evaluationId);
      setInspectDetail(res.data);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Could not load evaluation inspection details.');
    } finally {
      setInspectLoading(false);
    }
  };

  const openFlagDialog = (ev) => {
    setFlagModal(ev);
    setFlagReasonInput(ev.flagged_suspicious ? 'Cleared by administrator' : ev.flag_reason || 'Anomaly requires verification');
  };

  const submitFlagDialog = async (e) => {
    e.preventDefault();
    if (!flagModal) return;
    const nextFlag = !flagModal.flagged_suspicious;
    try {
      await flagAdminEvaluation(flagModal.evaluation_id, {
        flagged_suspicious: nextFlag,
        flag_reason: flagReasonInput.trim(),
        admin_comment: flagReasonInput.trim(),
      });
      setMsg(`Updated flag state on ${flagModal.evaluation_id}.`);
      setFlagModal(null);
      load();
    } catch (e2) {
      setErr(e2?.response?.data?.error || 'Flag update failed.');
    }
  };

  const filtered = rows;

  const evDet = inspectDetail?.evaluation;

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#E3E8E4] pb-4">
        <div>
          <h1 className="font-serif text-2xl text-[#141C17] flex items-center gap-2">
            <BarChart2 className="w-5 h-5 text-[#144D29]" /> Property Evaluations Oversight
          </h1>
          <p className="text-xs text-[#4A5750] mt-1">
            Live SQLite evaluations ({total} total · page {page} of {totalPages}) with statistical anomaly detection &amp; audit flagging.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-[#4A5750] absolute left-2.5 top-2.5" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && load(1)}
              placeholder="Search ID, user, locality..."
              className="pl-8 pr-3 py-1.5 rounded-lg bg-white shadow-sm border border-[#D2DBD4] text-xs text-[#141C17]"
            />
          </div>
          <button type="button" onClick={() => load(1)} className="px-3 py-1.5 rounded-lg bg-[#144D29] text-white text-xs font-semibold">
            Search
          </button>
          <select
            value={talukFilter}
            onChange={(e) => setTalukFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-white shadow-sm border border-[#D2DBD4] text-xs text-[#141C17]"
          >
            <option value="">All 7 Taluks</option>
            {['Mysuru', 'Nanjangud', 'HD Kote', 'Periyapatna', 'Hunsur', 'K. R. Nagar', 'T. Narasipura'].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setFlaggedOnly((v) => !v)}
            className={`px-3 py-1.5 rounded-lg border text-xs ${
              flaggedOnly ? 'bg-amber-500/20 border-amber-500/50 text-[#85520E]' : 'border-[#D2DBD4] text-[#4A5750]'
            }`}
          >
            Flagged Only
          </button>
        </div>
      </div>

      <AdminModuleHeader
        whatItShows="Every property valuation across all 7 Mysuru taluks plus statistical divergence flags (>2x or <0.4x asking)."
        adminAction="Click Inspect to verify sub-scores, market comps, and 13 GIS facilities, or Flag anomalies."
        consequence="Historical ML price outputs stay 100% immutable; only review flags & notes append to the audit log."
      />

      {err && <div className="p-3 rounded-lg bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23]">{err}</div>}
      {msg && <div className="p-3 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D]">{msg}</div>}

      <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
            <tr>
              <th className="p-3">Eval ID &amp; Date</th>
              <th className="p-3">User &amp; Property</th>
              <th className="p-3">Type &amp; Area</th>
              <th className="p-3">Rate / sq.ft</th>
              <th className="p-3">Total Valuation</th>
              <th className="p-3">Status</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E3E8E4]">
            {filtered.map((ev) => (
              <tr key={ev.evaluation_id} className="hover:bg-[#F6F8F6]">
                <td className="p-3">
                  <div className="font-mono text-[#144D29] font-semibold">{ev.evaluation_id}</div>
                  <div className="text-[10px] font-mono text-[#4A5750]">{ev.evaluation_date ? new Date(ev.evaluation_date).toLocaleDateString() : '—'}</div>
                </td>
                <td className="p-3">
                  <div className="text-[#141C17] font-medium">{ev.property_label}</div>
                  <div className="text-[11px] text-[#4A5750]">{ev.locality} • {ev.taluk}</div>
                  <div className="text-[10px] text-[#4A5750]">User: {ev.user_name || ev.user_id}</div>
                  {ev.flag_reason && (
                    <div className="text-[10px] text-[#85520E] mt-0.5 flex items-center gap-1">
                      <MessageSquare className="w-3 h-3" /> {ev.flag_reason}
                    </div>
                  )}
                </td>
                <td className="p-3">
                  <div>{ev.property_type || '—'}</div>
                  <div className="text-[11px] font-mono text-[#4A5750]">{ev.land_area_sqft ? `${Math.round(ev.land_area_sqft).toLocaleString()} sqft` : '—'}</div>
                </td>
                <td className="p-3 font-mono">{ev.predicted_price_per_sqft ? `₹${Math.round(ev.predicted_price_per_sqft).toLocaleString('en-IN')}` : '—'}</td>
                <td className="p-3 font-mono text-[#14532D] font-semibold">
                  {ev.predicted_price_inr ? `₹${Math.round(ev.predicted_price_inr).toLocaleString('en-IN')}` : '—'}
                </td>
                <td className="p-3">
                  <span
                    className={`px-2 py-0.5 rounded font-mono text-[10px] ${
                      ev.flagged_suspicious
                        ? 'bg-amber-500/20 text-[#85520E]'
                        : 'bg-emerald-500/15 text-[#14532D]'
                    }`}
                  >
                    {ev.evaluation_status}
                  </span>
                </td>
                <td className="p-3 flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => handleInspect(ev.evaluation_id)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px] text-[#141C17] hover:border-[#144D29]"
                  >
                    <Eye className="w-3 h-3 text-[#144D29]" /> Inspect
                  </button>
                  {hasPermission('evaluations:flag') && (
                    <button
                      type="button"
                      onClick={() => openFlagDialog(ev)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px] hover:border-amber-400"
                    >
                      <Flag className="w-3 h-3 text-[#85520E]" />
                      {ev.flagged_suspicious ? 'Unflag' : 'Flag'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="p-6 text-center text-[#4A5750]">
                  No property evaluations matched your filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-[#4A5750]">
          <span>Showing page {page} of {totalPages} ({total} total evaluations)</span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => load(page - 1)}
              className="px-3 py-1.5 rounded border border-[#D2DBD4] bg-white disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => load(page + 1)}
              className="px-3 py-1.5 rounded border border-[#D2DBD4] bg-white disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Inspection Modal */}
      {(inspectLoading || evDet) && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="w-full max-w-3xl max-h-[88vh] overflow-y-auto rounded-2xl bg-white shadow-sm border border-[#1B6336] p-6 space-y-5">
            <div className="flex items-center justify-between border-b border-[#E3E8E4] pb-3">
              <div>
                <div className="text-[11px] font-mono text-[#144D29]">{evDet?.evaluation_id || 'Loading...'}</div>
                <h2 className="font-serif text-lg text-[#141C17]">{evDet?.property_label || 'Evaluation Inspection'}</h2>
              </div>
              <button type="button" onClick={() => setInspectDetail(null)} className="text-[#4A5750] hover:text-[#141C17]">
                <X className="w-5 h-5" />
              </button>
            </div>
            {inspectLoading ? (
              <div className="text-xs text-[#4A5750]">Loading detailed breakdown &amp; 13 GIS records...</div>
            ) : evDet && (
              <div className="space-y-4 text-xs">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    ['ML Estimate', `₹${Math.round(evDet.predicted_price_inr || 0).toLocaleString('en-IN')}`],
                    ['Rate / sq.ft', `₹${Math.round(evDet.predicted_price_per_sqft || 0).toLocaleString('en-IN')}`],
                    ['Overall Score', evDet.overall_score != null ? `${Number(evDet.overall_score).toFixed(1)}/100` : '—'],
                    ['Confidence', evDet.confidence_level || '—'],
                  ].map(([k, v]) => (
                    <div key={k} className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
                      <div className="text-[#4A5750]">{k}</div>
                      <div className="font-mono font-bold text-[#141C17] mt-0.5">{v}</div>
                    </div>
                  ))}
                </div>

                {evDet.location_audit && (
                  <div className="p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4] space-y-1">
                    <div className="font-semibold text-[#144D29]">Location Audit Provenance</div>
                    <div>Entered: {evDet.location_audit.entered_locality || '—'} ({evDet.location_audit.entered_taluk || '—'}) → Canonical: {evDet.locality} ({evDet.taluk})</div>
                  </div>
                )}

                {Array.isArray(evDet.facilities) && evDet.facilities.length > 0 && (
                  <div>
                    <div className="font-semibold text-[#141C17] mb-2">GIS Facility Records ({evDet.facilities.length})</div>
                    <div className="max-h-56 overflow-y-auto rounded-lg border border-[#E3E8E4]">
                      <table className="w-full text-left text-[11px]">
                        <thead className="bg-[#F6F8F6] text-[#4A5750]">
                          <tr>
                            <th className="p-2">Category</th>
                            <th className="p-2">Nearest Place</th>
                            <th className="p-2">Dist</th>
                            <th className="p-2">Source</th>
                            <th className="p-2">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#E3E8E4]">
                          {evDet.facilities.map((f, i) => (
                            <tr key={i}>
                              <td className="p-2 capitalize">{String(f.facility_type || '').replace(/_/g, ' ')}</td>
                              <td className="p-2">{f.name || '—'}</td>
                              <td className="p-2 font-mono">{f.distance_km != null ? `${Number(f.distance_km).toFixed(2)} km` : '—'}</td>
                              <td className="p-2 text-[#4A5750]">{f.source || '—'}</td>
                              <td className="p-2 font-mono">{f.status}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Confirmation Modal for Flag / Unflag */}
      {flagModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <form onSubmit={submitFlagDialog} className="w-full max-w-md rounded-2xl bg-white shadow-sm border border-amber-500/40 p-6 space-y-4 text-xs">
            <h3 className="font-serif text-lg text-[#141C17]">
              {flagModal.flagged_suspicious ? `Unflag ${flagModal.evaluation_id}` : `Flag ${flagModal.evaluation_id} for Review`}
            </h3>
            <p className="text-[#4A5750]">
              Consequence: Updates governance status &amp; creates an immutable audit trail entry without altering predicted ML numbers.
            </p>
            <div>
              <label className="block text-[#4A5750] mb-1">Audit Reason / Review Note</label>
              <input
                required
                value={flagReasonInput}
                onChange={(e) => setFlagReasonInput(e.target.value)}
                className="w-full px-3 py-2 rounded bg-[#F6F8F6] border border-[#D2DBD4] text-[#141C17]"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setFlagModal(null)} className="px-3.5 py-2 rounded border border-[#D2DBD4] text-[#4A5750]">
                Cancel
              </button>
              <button type="submit" className="px-4 py-2 rounded bg-[#144D29] text-white font-semibold">
                Confirm &amp; Audit
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
