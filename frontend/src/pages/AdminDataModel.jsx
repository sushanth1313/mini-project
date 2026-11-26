import React, { useEffect, useState } from 'react';
import {
  Activity,
  Brain,
  CheckCircle2,
  Database,
  Download,
  Play,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Target,
} from 'lucide-react';
import { getDatasetRecords, getModelMetrics } from '../api/client';
import {
  ADMIN_TOKEN_KEY,
  approveModelDeployment,
  cleanAdminDataset,
  compareAdminModels,
  downloadAdminDatasetCsvUrl,
  fetchAdminDatasets,
  fetchAdminModels,
  rollbackAdminModel,
  trainCandidateModel,
  validateAdminDataset,
} from '../api/adminClient';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';

export default function AdminDataModel() {
  const { hasPermission } = useAdminAuth();
  const canViewModels = hasPermission('models:view');
  const canTrain = hasPermission('models:train');
  const canClean = hasPermission('datasets:clean');
  const [tab, setTab] = useState(canTrain ? 'model' : (hasPermission('datasets:view') && !canViewModels ? 'dataset' : 'model')); // model | dataset
  const [metrics, setMetrics] = useState(null);
  const [models, setModels] = useState([]);
  const [trainingJobs, setTrainingJobs] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [records, setRecords] = useState([]);
  const [totalRecords, setTotalRecords] = useState(0);
  const [selectedDs, setSelectedDs] = useState('');
  const [confirmAction, setConfirmAction] = useState(null);
  const [loading, setLoading] = useState(true);
  const [accessDenied, setAccessDenied] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const loadAll = async (silent = false) => {
    if (!silent) setLoading(true);
    setErr('');
    setAccessDenied(false);
    try {
      const [mRes, aRes, cRes, dRes, recRes] = await Promise.all([
        getModelMetrics().catch(() => ({ data: null })),
        canViewModels ? fetchAdminModels().catch(() => ({ data: { models: [], training_jobs: [] } })) : Promise.resolve({ data: { models: [], training_jobs: [] } }),
        canViewModels ? compareAdminModels().catch(() => ({ data: null })) : Promise.resolve({ data: null }),
        hasPermission('datasets:view') ? fetchAdminDatasets().catch(() => ({ data: { datasets: [] } })) : Promise.resolve({ data: { datasets: [] } }),
        getDatasetRecords({ per_page: 40 }).catch(() => ({ data: { records: [], total: 0 } })),
      ]);
      setMetrics(mRes.data);
      setModels(aRes.data?.models || []);
      setTrainingJobs(aRes.data?.training_jobs || []);
      setComparison(cRes.data);
      setDatasets(dRes.data?.datasets || []);
      setRecords(recRes.data?.records || []);
      setTotalRecords(recRes.data?.total || 0);
      const validDs = (dRes.data?.datasets || []).filter((d) => d.ready_for_training);
      if (!selectedDs && validDs.length > 0) setSelectedDs(validDs[0].dataset_id);
    } catch (e) {
      if (e?.response?.status === 403) setAccessDenied(true);
      setErr(e?.response?.data?.error || 'Failed to load dataset & ML model status.');
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    const hasRunning = trainingJobs.some((j) => j.status === 'RUNNING');
    if (!hasRunning) return undefined;
    const timer = setInterval(() => {
      loadAll(true);
    }, 4000);
    return () => clearInterval(timer);
  }, [trainingJobs]);

  const executeConfirmed = async () => {
    if (!confirmAction) return;
    setMsg('');
    setErr('');
    try {
      if (confirmAction.type === 'train') {
        const res = await trainCandidateModel({ dataset_id: selectedDs });
        setMsg(
          res.data?.message ||
          `Started candidate training ${res.data?.model_version || res.data?.training_job?.model_version || ''}. Production remains active until approved.`
        );
      } else if (confirmAction.type === 'approve') {
        await approveModelDeployment(confirmAction.modelId);
        setMsg(`Promoted model ${confirmAction.modelId} to production and reloaded live predictor.`);
      } else if (confirmAction.type === 'rollback') {
        await rollbackAdminModel(confirmAction.modelId);
        setMsg(`Rolled back production model cleanly and reloaded live predictor.`);
      }
      setConfirmAction(null);
      loadAll(true);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Action failed.');
      setConfirmAction(null);
    }
  };

  const handleValidateDs = async (dsId) => {
    try {
      const res = await validateAdminDataset(dsId);
      setMsg(`Validated ${dsId}: ${res.data.validation_summary?.validation_status || 'VALIDATED'}`);
      loadAll();
    } catch (e) {
      setErr(e?.response?.data?.error || 'Validation failed.');
    }
  };

  const handleCleanDs = async (dsId) => {
    if (!window.confirm(`Generate a cleaned snapshot from ${dsId}? Source records stay preserved.`)) return;
    try {
      const res = await cleanAdminDataset(dsId, {});
      setMsg(`Created clean snapshot ${res.data.cleaned_dataset?.dataset_id || ''}.`);
      loadAll();
    } catch (e) {
      setErr(e?.response?.data?.error || 'Cleaning failed.');
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

  const holdoutR2 = metrics?.holdout_metrics?.r2 ?? metrics?.validation_r2;
  const holdoutMae = metrics?.holdout_metrics?.mae ?? metrics?.validation_mae;
  const gkfR2 = metrics?.validation_r2;
  const gkfMae = metrics?.validation_mae;
  const cand = comparison?.candidate_model;

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#E3E8E4] pb-4">
        <div>
          <h1 className="font-serif text-2xl text-[#141C17] flex items-center gap-2">
            <Brain className="w-5 h-5 text-[#144D29]" /> Data &amp; ML Valuation Engine
          </h1>
          <p className="text-xs text-[#4A5750] mt-1">
            Mysuru dataset ({totalRecords.toLocaleString()} live DB records) and production regression validation metrics (R² = variance explained, NOT % accuracy).
          </p>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setTab('model')}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold ${
              tab === 'model' ? 'bg-[#144D29] text-white' : 'bg-white border border-[#D2DBD4] text-[#4A5750]'
            }`}
          >
            ML Model &amp; Validation
          </button>
          <button
            type="button"
            onClick={() => setTab('dataset')}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold ${
              tab === 'dataset' ? 'bg-[#144D29] text-white' : 'bg-white border border-[#D2DBD4] text-[#4A5750]'
            }`}
          >
            Dataset Version &amp; Quality
          </button>
        </div>
      </div>

      <AdminModuleHeader
        whatItShows={`Curated ${totalRecords.toLocaleString()}-record Mysuru dataset quality, production ML version, Holdout vs Locality GroupKFold validation.`}
        adminAction={canTrain ? 'Super Admins inspect validation, manage dataset versions, or train/promote models with confirmation.' : 'Operations Admins monitor active dataset quality and production validation benchmarks.'}
        consequence="Production model & training rows stay protected; advanced ML engineering controls are restricted to Super Admins."
      />

      {loading && (
        <div className="p-4 rounded-xl bg-white border border-[#E3E8E4] text-xs text-[#4A5750]">
          Loading ML pipeline metrics, candidate registry, and dataset audit...
        </div>
      )}
      {accessDenied && (
        <div className="p-3 rounded-lg bg-[#FEF6E6] border border-[#EDD49F] text-xs text-[#85520E]">
          Unauthorized (403): {err || 'Your role lacks Data/ML administration permission.'}
        </div>
      )}
      {err && !accessDenied && <div className="p-3 rounded-lg bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23]">{err}</div>}
      {msg && <div className="p-3 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D]">{msg}</div>}

      {tab === 'model' && !loading && (
        <div className="space-y-5">
          {metrics && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4]">
                <div className="text-xs text-[#4A5750] flex items-center gap-1.5"><Brain className="w-3.5 h-3.5 text-[#144D29]" /> Production Model</div>
                <div className="text-lg font-mono font-bold text-[#141C17] mt-1">{metrics.best_model || 'ExtraTreesRegressor'}</div>
                <div className="text-[11px] text-[#4A5750] mt-1">
                  {metrics.feature_count || 47} features · Trained {metrics.trained_at ? String(metrics.trained_at).slice(0, 10) : 'active'}
                </div>
              </div>
              <div className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4]">
                <div className="text-xs text-[#4A5750] flex items-center gap-1.5"><Activity className="w-3.5 h-3.5 text-emerald-400" /> Holdout (158 unseen)</div>
                <div className="text-lg font-mono font-bold text-[#14532D] mt-1">R²={holdoutR2 != null ? Number(holdoutR2).toFixed(4) : '—'}</div>
                <div className="text-[11px] text-[#4A5750] mt-1">MAE ₹{holdoutMae != null ? Math.round(holdoutMae) : '—'}/sq.ft</div>
              </div>
              <div className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4]">
                <div className="text-xs text-[#4A5750] flex items-center gap-1.5"><Target className="w-3.5 h-3.5 text-[#85520E]" /> Locality GroupKFold</div>
                <div className="text-lg font-mono font-bold text-[#85520E] mt-1">R²={gkfR2 != null ? Number(gkfR2).toFixed(4) : '—'}</div>
                <div className="text-[11px] text-[#4A5750] mt-1">MAE ₹{gkfMae != null ? Math.round(gkfMae) : '—'}/sq.ft</div>
              </div>
              <div className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4]">
                <div className="text-xs text-[#4A5750] flex items-center gap-1.5"><Database className="w-3.5 h-3.5 text-[#144D29]" /> Partition</div>
                <div className="text-lg font-mono font-bold text-[#141C17] mt-1">{metrics.total_records_in_file || 1050} Rows</div>
                <div className="text-[11px] text-[#4A5750] mt-1">{metrics.training_records || 892} Train / {metrics.train_test_split?.test_size || 158} Test</div>
              </div>
            </div>
          )}

          {canTrain && (
            <div className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4] flex flex-wrap items-end gap-4 text-xs">
              <div className="flex-1 min-w-[240px]">
                <label className="block text-[#4A5750] mb-1">Super Admin Control — Validated Dataset for Candidate Training</label>
                <select
                  value={selectedDs}
                  onChange={(e) => setSelectedDs(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-[#F6F8F6] border border-[#D2DBD4] text-[#141C17]"
                >
                  {datasets.map((d) => (
                    <option key={d.dataset_id} value={d.dataset_id}>
                      {d.dataset_id} — {d.validation_status} ({d.row_count || 1050} rows)
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                disabled={!selectedDs}
                onClick={() => setConfirmAction({
                  type: 'train',
                  title: 'Train Candidate ML Model?',
                  detail: `Runs candidate training on dataset ${selectedDs}. Production model stays active until explicitly promoted.`,
                })}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#144D29] text-white font-semibold disabled:opacity-40"
              >
                <Play className="w-3.5 h-3.5" /> Train Candidate
              </button>
            </div>
          )}

          {canTrain && cand && (
            <div className="p-4 rounded-xl bg-[#FEF6E6] border border-[#EDD49F] text-xs flex justify-between items-center gap-3 flex-wrap">
              <div>
                <strong className="text-[#85520E]">Candidate Awaiting Approval: {cand.model_version}</strong>
                <div className="text-[#4A5750]">R²={cand.holdout_metrics?.r2_score} · MAE=₹{cand.holdout_metrics?.mae_inr_per_sqft}/sq.ft</div>
              </div>
              <button
                type="button"
                onClick={() => setConfirmAction({
                  type: 'approve',
                  modelId: cand.model_id,
                  title: `Promote ${cand.model_version} to Production?`,
                  detail: 'Replaces current active production model while keeping prior version archived for rollback.',
                })}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-[#144D29] text-white font-semibold"
              >
                <CheckCircle2 className="w-3.5 h-3.5" /> Approve Deployment
              </button>
            </div>
          )}

          <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
                <tr>
                  <th className="p-3">Model Version</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Holdout R²</th>
                  <th className="p-3">Holdout MAE</th>
                  <th className="p-3">GroupKFold MAE</th>
                  {canTrain && <th className="p-3">Action</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E3E8E4]">
                {models.map((m) => (
                  <tr key={m.model_id}>
                    <td className="p-3">
                      <div className="font-mono text-[#144D29]">{m.model_id}</div>
                      <div className="text-[#141C17]">{m.model_version}</div>
                    </td>
                    <td className="p-3 font-mono">
                      <span className={`px-2 py-0.5 rounded text-[10px] ${m.is_production ? 'bg-emerald-500/15 text-[#14532D]' : 'bg-white/10 text-[#4A5750]'}`}>
                        {m.status}
                      </span>
                    </td>
                    <td className="p-3 font-mono">{m.holdout_metrics?.r2_score ?? '—'}</td>
                    <td className="p-3 font-mono">₹{m.holdout_metrics?.mae_inr_per_sqft ?? '—'}</td>
                    <td className="p-3 font-mono">₹{m.locality_group_kfold_metrics?.mae_inr_per_sqft ?? '—'}</td>
                    {canTrain && (
                      <td className="p-3">
                        {m.status === 'ARCHIVED_ROLLBACK_READY' && (
                          <button
                            type="button"
                            onClick={() => setConfirmAction({
                              type: 'rollback',
                              modelId: m.model_id,
                              title: `Rollback to ${m.model_version}?`,
                              detail: 'Restores archived production pipeline cleanly.',
                            })}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-amber-500/40 text-[#85520E] text-[11px]"
                          >
                            <RotateCcw className="w-3 h-3" /> Rollback
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {trainingJobs.length > 0 && (
            <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
              <div className="px-4 py-3 border-b border-[#E3E8E4] text-xs font-semibold text-[#141C17]">
                Background Candidate Training Jobs
              </div>
              <table className="w-full text-left text-xs">
                <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
                  <tr>
                    <th className="p-3">Job ID</th>
                    <th className="p-3">Candidate Model</th>
                    <th className="p-3">Dataset</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Started</th>
                    <th className="p-3">Result / Error</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E3E8E4]">
                  {trainingJobs.map((job) => (
                    <tr key={job.job_id}>
                      <td className="p-3 font-mono text-[11px] text-[#4A5750]">{job.job_id}</td>
                      <td className="p-3 font-mono text-[#144D29]">{job.model_version || job.model_id}</td>
                      <td className="p-3 font-mono text-[11px]">{job.dataset_id}</td>
                      <td className="p-3 font-mono">
                        <span className={`px-2 py-0.5 rounded text-[10px] ${
                          job.status === 'COMPLETED'
                            ? 'bg-[#E7F5EC] text-[#14532D]'
                            : job.status === 'FAILED'
                            ? 'bg-[#FDEEEC] text-[#8C2D23]'
                            : 'bg-[#FEF6E6] text-[#85520E]'
                        }`}>
                          {job.status}
                        </span>
                      </td>
                      <td className="p-3 font-mono text-[11px] text-[#4A5750]">
                        {job.started_at ? String(job.started_at).slice(0, 19).replace('T', ' ') : '—'}
                      </td>
                      <td className="p-3 text-[11px] text-[#4A5750]">
                        {job.error || (job.status === 'COMPLETED' ? 'Candidate ready for comparison & promotion' : 'Training in background...')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'dataset' && !loading && (
        <div className="space-y-5">
          <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
                <tr>
                  <th className="p-3">Dataset Version</th>
                  <th className="p-3">Description</th>
                  <th className="p-3">Rows</th>
                  <th className="p-3">Quality Status</th>
                  {canClean && <th className="p-3">Super Admin Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E3E8E4]">
                {datasets.map((ds) => (
                  <tr key={ds.dataset_id}>
                    <td className="p-3 font-mono text-[#144D29]">{ds.dataset_id}</td>
                    <td className="p-3 text-[#141C17]">{ds.dataset_name || ds.filename}</td>
                    <td className="p-3 font-mono">{ds.row_count ?? totalRecords}</td>
                    <td className="p-3 font-mono text-[#14532D]">{ds.validation_status || 'VALIDATED'}</td>
                    {canClean && (
                      <td className="p-3 flex flex-wrap gap-1.5">
                        <button type="button" onClick={() => handleValidateDs(ds.dataset_id)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px]">
                          <ShieldCheck className="w-3 h-3 text-emerald-400" /> Validate
                        </button>
                        <button type="button" onClick={() => handleCleanDs(ds.dataset_id)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px]">
                          <Sparkles className="w-3 h-3 text-[#144D29]" /> Clean Snapshot
                        </button>
                        <button type="button" onClick={() => handleDownloadCsv(ds.dataset_id)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px]">
                          <Download className="w-3 h-3" /> CSV
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
            <div className="p-4 border-b border-[#E3E8E4] text-sm font-semibold text-[#141C17]">
              Master Dataset Sample (Latest 40 of {totalRecords.toLocaleString()} records)
            </div>
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
                <tr>
                  <th className="p-3">ID</th>
                  <th className="p-3">Locality &amp; Taluk</th>
                  <th className="p-3">Area (sq.ft)</th>
                  <th className="p-3">Price / sq.ft</th>
                  <th className="p-3">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E3E8E4]">
                {records.map((r) => (
                  <tr key={r.id}>
                    <td className="p-3 font-mono text-[#144D29]">{r.id}</td>
                    <td className="p-3">{r.village_or_locality} · <span className="text-[#4A5750]">{r.taluk}</span></td>
                    <td className="p-3 font-mono">{r.land_area_sqft}</td>
                    <td className="p-3 font-mono">₹{Number(r.price_per_sqft_inr || 0).toLocaleString('en-IN')}</td>
                    <td className="p-3 text-[#4A5750]">{r.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {confirmAction && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-lg border border-[#144D29] p-6 space-y-4 text-xs">
            <h3 className="font-serif text-lg text-[#141C17]">{confirmAction.title}</h3>
            <p className="text-[#4A5750]">{confirmAction.detail}</p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setConfirmAction(null)} className="px-3.5 py-2 rounded border border-[#D2DBD4] text-[#4A5750]">
                Cancel
              </button>
              <button type="button" onClick={executeConfirmed} className="px-4 py-2 rounded bg-[#144D29] text-white font-semibold">
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
