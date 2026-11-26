import React, { useEffect, useState } from 'react';
import { Activity, Brain, CheckCircle2, Play, RotateCcw, Target } from 'lucide-react';
import { getModelMetrics } from '../api/client';
import {
  approveModelDeployment,
  compareAdminModels,
  fetchAdminDatasets,
  fetchAdminModels,
  rollbackAdminModel,
  trainCandidateModel,
} from '../api/adminClient';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';

export default function AdminMLModel() {
  const { hasPermission } = useAdminAuth();
  const [metrics, setMetrics] = useState(null);
  const [models, setModels] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [selectedDs, setSelectedDs] = useState('');
  const [confirmAction, setConfirmAction] = useState(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const loadAll = async () => {
    setLoading(true);
    setErr('');
    try {
      const [mRes, aRes, cRes, dRes] = await Promise.all([
        getModelMetrics(),
        fetchAdminModels(),
        compareAdminModels(),
        fetchAdminDatasets(),
      ]);
      setMetrics(mRes.data);
      setModels(aRes.data.models || []);
      setComparison(cRes.data);
      const validDs = (dRes.data.datasets || []).filter((d) => d.ready_for_training);
      setDatasets(dRes.data.datasets || []);
      if (!selectedDs && validDs.length > 0) setSelectedDs(validDs[0].dataset_id);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Failed to load ML governance metrics.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const executeConfirmed = async () => {
    if (!confirmAction) return;
    setMsg('');
    setErr('');
    try {
      if (confirmAction.type === 'train') {
        const res = await trainCandidateModel({ dataset_id: selectedDs });
        setMsg(`Trained candidate ${res.data.candidate_model?.model_version}. Production remains active until explicit promotion.`);
      } else if (confirmAction.type === 'approve') {
        await approveModelDeployment(confirmAction.modelId);
        setMsg(`Promoted model ${confirmAction.modelId} to production & logged audit entry.`);
      } else if (confirmAction.type === 'rollback') {
        await rollbackAdminModel(confirmAction.modelId);
        setMsg(`Rolled back production to archived model ${confirmAction.modelId}.`);
      }
      setConfirmAction(null);
      loadAll();
    } catch (e) {
      setErr(e?.response?.data?.error || 'Action failed.');
      setConfirmAction(null);
    }
  };

  const holdoutR2 = metrics?.holdout_metrics?.r2 ?? metrics?.validation_r2;
  const holdoutMae = metrics?.holdout_metrics?.mae ?? metrics?.validation_mae;
  const gkfR2 = metrics?.validation_r2;
  const gkfMae = metrics?.validation_mae;
  const prod = comparison?.current_production_model;
  const cand = comparison?.candidate_model;

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#E3E8E4] pb-4">
        <div>
          <h1 className="font-serif text-2xl text-[#141C17] flex items-center gap-2">
            <Brain className="w-5 h-5 text-[#144D29]" /> ML Model Lifecycle &amp; Governance
          </h1>
          <p className="text-xs text-[#4A5750] mt-1">
            ExtraTreesRegressor · R² quantifies variance explained (NOT per-property percentage accuracy).
          </p>
        </div>
      </div>

      <AdminModuleHeader
        whatItShows="Active production pipeline metrics (Holdout vs Locality GroupKFold) and candidate/rollback versions."
        adminAction="Train candidate models only on validated datasets, inspect metrics deltas, then explicitly approve."
        consequence="Training NEVER overwrites production automatically; promotion & rollback require confirmation and are audited."
      />

      {err && <div className="p-3 rounded-lg bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23]">{err}</div>}
      {msg && <div className="p-3 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D]">{msg}</div>}

      {/* Metrics Strip */}
      {!loading && metrics && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4]">
            <div className="text-xs text-[#4A5750] flex items-center gap-1.5"><Brain className="w-3.5 h-3.5 text-[#144D29]" /> Production Algorithm</div>
            <div className="text-base font-mono font-bold text-[#141C17] mt-1 break-words">{metrics.best_model || 'ExtraTreesRegressor'}</div>
            <div className="text-[11px] text-[#6E7B73] mt-1">{metrics.feature_count || 47} engineered features</div>
          </div>
          <div className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4]">
            <div className="text-xs text-[#4A5750] flex items-center gap-1.5"><Activity className="w-3.5 h-3.5 text-[#14532D]" /> Holdout Test (158)</div>
            <div className="text-lg font-mono font-bold text-[#14532D] mt-1">R²={holdoutR2 != null ? Number(holdoutR2).toFixed(4) : '—'}</div>
            <div className="text-[11px] text-[#6E7B73] mt-1">MAE ₹{holdoutMae != null ? Math.round(holdoutMae) : '—'}/sq.ft</div>
          </div>
          <div className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4]">
            <div className="text-xs text-[#4A5750] flex items-center gap-1.5"><Target className="w-3.5 h-3.5 text-[#85520E]" /> Unseen Locality (GroupKFold)</div>
            <div className="text-lg font-mono font-bold text-[#85520E] mt-1">R²={gkfR2 != null ? Number(gkfR2).toFixed(4) : '—'}</div>
            <div className="text-[11px] text-[#6E7B73] mt-1">MAE ₹{gkfMae != null ? Math.round(gkfMae) : '—'}/sq.ft</div>
          </div>
          <div className="p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4]">
            <div className="text-xs text-[#4A5750]">Dataset Split</div>
            <div className="text-lg font-mono font-bold text-[#141C17] mt-1">{metrics.total_records_in_file || '—'} Records</div>
            <div className="text-[11px] text-[#6E7B73] mt-1">{metrics.training_records || '—'} Train / {metrics.train_test_split?.test_size || '—'} Holdout</div>
          </div>
        </div>
      )}

      {/* Candidate Training & Compare Controls */}
      {hasPermission('models:train') && (
        <div className="p-5 rounded-xl bg-white shadow-sm border border-[#E3E8E4] flex flex-wrap items-end gap-4 text-xs">
          <div className="flex-1 min-w-[240px]">
            <label className="block text-[#4A5750] font-semibold mb-1">Validated Dataset for Candidate Training</label>
            <select
              value={selectedDs}
              onChange={(e) => setSelectedDs(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-[#F6F8F6] border border-[#D2DBD4] text-[#141C17]"
            >
              {datasets.map((d) => (
                <option key={d.dataset_id} value={d.dataset_id}>
                  {d.dataset_id} — {d.validation_status} ({d.row_count || 'live'} rows)
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            disabled={!selectedDs}
            onClick={() => setConfirmAction({
              type: 'train',
              title: 'Start Candidate Training Job?',
              detail: `Trains a new ExtraTreesRegressor candidate on dataset ${selectedDs}. Current production (${prod?.model_version || 'live'}) will NOT change until approved.`,
            })}
            className="btn btn-primary btn-sm"
          >
            <Play className="w-3.5 h-3.5" /> Train Candidate Model
          </button>
        </div>
      )}

      {cand && (
        <div className="p-4 rounded-xl bg-[#FEF6E6] border border-[#EDD49F] text-xs flex flex-wrap justify-between items-center gap-3">
          <div>
            <strong className="text-[#85520E]">Candidate Awaiting Approval: {cand.model_version}</strong>
            <div className="text-[#4A5750] mt-0.5">
              R²={cand.holdout_metrics?.r2_score} · MAE=₹{cand.holdout_metrics?.mae_inr_per_sqft}/sq.ft
            </div>
          </div>
          {hasPermission('models:approve_deploy') && (
            <button
              type="button"
              onClick={() => setConfirmAction({
                type: 'approve',
                modelId: cand.model_id,
                title: `Promote ${cand.model_version} to Production?`,
                detail: 'Replaces current active production version while keeping previous model archived for instant rollback.',
              })}
              className="btn btn-primary btn-sm"
            >
              <CheckCircle2 className="w-3.5 h-3.5" /> Approve &amp; Promote
            </button>
          )}
        </div>
      )}

      {/* Registry Table */}
      <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
            <tr>
              <th className="p-3">Model ID &amp; Version</th>
              <th className="p-3">Status</th>
              <th className="p-3">Holdout R²</th>
              <th className="p-3">Holdout MAE</th>
              <th className="p-3">GroupKFold MAE</th>
              <th className="p-3">Action</th>
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
                  <span className={`px-2 py-0.5 rounded text-[10px] ${m.is_production ? 'bg-[#E7F5EC] text-[#14532D]' : 'bg-[#F0F4F1] text-[#4A5750]'}`}>
                    {m.status}
                  </span>
                </td>
                <td className="p-3 font-mono">{m.holdout_metrics?.r2_score ?? '—'}</td>
                <td className="p-3 font-mono">₹{m.holdout_metrics?.mae_inr_per_sqft ?? '—'}</td>
                <td className="p-3 font-mono">₹{m.locality_group_kfold_metrics?.mae_inr_per_sqft ?? '—'}</td>
                <td className="p-3">
                  {hasPermission('models:rollback') && m.status === 'ARCHIVED_ROLLBACK_READY' && (
                    <button
                      type="button"
                      onClick={() => setConfirmAction({
                        type: 'rollback',
                        modelId: m.model_id,
                        title: `Roll Back Production to ${m.model_version}?`,
                        detail: 'Restores the archived model version cleanly and records an audit entry.',
                      })}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#EDD49F] bg-[#FEF6E6] text-[#85520E] text-[11px]"
                    >
                      <RotateCcw className="w-3 h-3" /> Rollback
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Confirmation Modal */}
      {confirmAction && (
        <div className="fixed inset-0 z-50 bg-black/45 flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-xl border border-[#144D29] p-6 space-y-4 text-xs">
            <h3 className="font-serif text-lg text-[#141C17]">{confirmAction.title}</h3>
            <p className="text-[#4A5750]">{confirmAction.detail}</p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setConfirmAction(null)} className="btn btn-secondary btn-sm">
                Cancel
              </button>
              <button type="button" onClick={executeConfirmed} className="btn btn-primary btn-sm">
                Confirm Action
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
