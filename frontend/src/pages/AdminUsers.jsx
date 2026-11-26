import React, { useEffect, useState } from 'react';
import { AlertTriangle, Shield, UserCheck, Users, UserX } from 'lucide-react';
import {
  fetchAdminAccounts,
  fetchUsers,
  processUserDeletion,
  updateUserRole,
  updateUserStatus,
} from '../api/adminClient';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';

const USER_ROLES = [
  { value: 'STANDARD_USER', label: 'Standard User' },
  { value: 'AUTHORIZED_SURVEYOR', label: 'Authorized Surveyor' },
  { value: 'VALUATION_ANALYST', label: 'Valuation Analyst' },
];

const USER_STATUSES = ['ACTIVE', 'DEACTIVATED', 'SUSPENDED'];

export default function AdminUsers() {
  const { admin: currentAdmin, hasPermission } = useAdminAuth();
  const [users, setUsers] = useState([]);
  const [admins, setAdmins] = useState([]);
  const [governance, setGovernance] = useState(null);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [confirmDlg, setConfirmDlg] = useState(null);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const load = async () => {
    setErr('');
    try {
      const params = {};
      if (search.trim()) params.search = search.trim();
      if (roleFilter) params.role = roleFilter;
      if (statusFilter) params.status = statusFilter;
      const uRes = await fetchUsers(params);
      setUsers(uRes.data.users || []);
      if (hasPermission('admins:manage')) {
        const aRes = await fetchAdminAccounts();
        setAdmins(aRes.data.admins || []);
        setGovernance(aRes.data.governance_summary || null);
      }
    } catch (e) {
      setErr(e?.response?.data?.error || 'Failed to load user records.');
    }
  };

  useEffect(() => {
    load();
  }, [roleFilter, statusFilter]);

  const executeConfirmedAction = async () => {
    if (!confirmDlg) return;
    setErr('');
    setMsg('');
    try {
      if (confirmDlg.kind === 'user_status') {
        const res = await updateUserStatus(confirmDlg.user.user_id, {
          account_status: confirmDlg.nextStatus,
          reason: `Administrator action -> ${confirmDlg.nextStatus}`,
        });
        const updated = res.data?.user;
        if (!updated || updated.account_status !== confirmDlg.nextStatus) {
          throw new Error('Backend did not confirm updated status.');
        }
        setMsg(`Updated ${updated.email} status to ${updated.account_status}.`);
      } else if (confirmDlg.kind === 'user_role') {
        const res = await updateUserRole(confirmDlg.user.user_id, { role: confirmDlg.nextRole });
        const updated = res.data?.user;
        if (!updated || updated.role !== confirmDlg.nextRole) {
          throw new Error('Backend did not confirm updated role.');
        }
        setMsg(`Updated ${updated.email} platform role to ${updated.role}.`);
      } else if (confirmDlg.kind === 'user_delete') {
        await processUserDeletion(confirmDlg.user.user_id, { decision: 'APPROVED' });
        setMsg(`Processed deletion request for ${confirmDlg.user.email}.`);
      }
      setConfirmDlg(null);
      await load();
    } catch (e) {
      setErr(e?.response?.data?.error || e?.message || 'Administrative update failed.');
      setConfirmDlg(null);
    }
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#E3E8E4] pb-4">
        <div>
          <h1 className="font-serif text-2xl text-[#141C17] flex items-center gap-2">
            <Users className="w-5 h-5 text-[#144D29]" /> Users &amp; RBAC Governance
          </h1>
          <p className="text-xs text-[#4A5750] mt-1">
            Platform accounts ({users.length}) separated cleanly from 5-role RBAC Administrators.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, email, taluk..."
            className="px-3 py-1.5 rounded-lg bg-white shadow-sm border border-[#D2DBD4] text-xs text-[#141C17]"
          />
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-lg bg-white border border-[#D2DBD4] text-xs text-[#141C17]"
          >
            <option value="">All Roles</option>
            {USER_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-lg bg-white border border-[#D2DBD4] text-xs text-[#141C17]"
          >
            <option value="">All Statuses</option>
            {USER_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button
            type="button"
            onClick={load}
            className="px-3.5 py-1.5 rounded-lg bg-[#144D29] text-white text-xs font-semibold"
          >
            Search
          </button>
        </div>
      </div>

      <AdminModuleHeader
        whatItShows="Registered platform user accounts (STANDARD_USER, AUTHORIZED_SURVEYOR, VALUATION_ANALYST) plus the 5-role Admin RBAC roster."
        adminAction="Search, filter, update permitted roles, activate/deactivate/suspend users with confirmation, or govern administrator accounts."
        consequence="Platform users can never receive administrator privileges via user endpoints; every change is persisted and audit-logged."
      />

      {err && <div className="p-3 rounded-lg bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23]">{err}</div>}
      {msg && <div className="p-3 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D]">{msg}</div>}

      {/* Platform Users Table */}
      <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
            <tr>
              <th className="p-3">User ID</th>
              <th className="p-3">Name &amp; Email</th>
              <th className="p-3">Taluk</th>
              <th className="p-3">Platform Role</th>
              <th className="p-3">Status</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E3E8E4]">
            {users.map((u) => (
              <tr key={u.user_id} className="hover:bg-[#F6F8F6]">
                <td className="p-3 font-mono text-[#144D29]">{u.user_id}</td>
                <td className="p-3">
                  <div className="font-medium text-[#141C17]">{u.full_name}</div>
                  <div className="text-[11px] text-[#4A5750]">{u.email}</div>
                </td>
                <td className="p-3 text-[#4A5750]">{u.registered_taluk}</td>
                <td className="p-3">
                  {hasPermission('users:roles') ? (
                    <select
                      value={u.role}
                      onChange={(e) => {
                        const nextRole = e.target.value;
                        if (nextRole !== u.role) {
                          setConfirmDlg({
                            kind: 'user_role',
                            user: u,
                            nextRole,
                            title: `Change role for ${u.email}?`,
                            detail: `Change platform role from ${u.role} to ${nextRole}.`,
                          });
                        }
                      }}
                      className="px-2 py-1 rounded bg-[#F6F8F6] border border-[#D2DBD4] text-xs text-[#141C17]"
                    >
                      {USER_ROLES.map((r) => (
                        <option key={r.value} value={r.value}>{r.label} ({r.value})</option>
                      ))}
                    </select>
                  ) : (
                    <span className="font-mono">{u.role}</span>
                  )}
                </td>
                <td className="p-3">
                  <span
                    className={`px-2 py-0.5 rounded font-mono text-[10px] ${
                      u.account_status === 'ACTIVE'
                        ? 'bg-emerald-500/15 text-[#14532D]'
                        : u.account_status === 'SUSPENDED'
                          ? 'bg-amber-500/20 text-[#85520E]'
                          : 'bg-red-500/15 text-[#8C2D23]'
                    }`}
                  >
                    {u.account_status}
                  </span>
                </td>
                <td className="p-3 flex flex-wrap gap-1.5">
                  {hasPermission('users:manage') && (
                    <>
                      {u.account_status !== 'ACTIVE' && (
                        <button
                          type="button"
                          onClick={() => setConfirmDlg({
                            kind: 'user_status',
                            user: u,
                            nextStatus: 'ACTIVE',
                            title: `Restore / Activate ${u.email}?`,
                            detail: `Set account status from ${u.account_status} to ACTIVE.`,
                          })}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded border border-[#BCE0C8] bg-[#E7F5EC] text-[#14532D] text-[11px]"
                        >
                          <UserCheck className="w-3 h-3" /> Activate
                        </button>
                      )}
                      {u.account_status !== 'SUSPENDED' && (
                        <button
                          type="button"
                          onClick={() => setConfirmDlg({
                            kind: 'user_status',
                            user: u,
                            nextStatus: 'SUSPENDED',
                            title: `Suspend ${u.email}?`,
                            detail: 'Suspends login access until restored by an administrator.',
                          })}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded border border-amber-400/50 text-[#85520E] text-[11px]"
                        >
                          <UserX className="w-3 h-3" /> Suspend
                        </button>
                      )}
                      {u.account_status !== 'DEACTIVATED' && (
                        <button
                          type="button"
                          onClick={() => setConfirmDlg({
                            kind: 'user_status',
                            user: u,
                            nextStatus: 'DEACTIVATED',
                            title: `Deactivate ${u.email}?`,
                            detail: 'Deactivates user account cleanly (audit logged).',
                          })}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded border border-red-400/50 text-[#8C2D23] text-[11px]"
                        >
                          <UserX className="w-3 h-3" /> Deactivate
                        </button>
                      )}
                    </>
                  )}
                  {hasPermission('users:delete_requests') && u.deletion_request && (
                    <button
                      type="button"
                      onClick={() => setConfirmDlg({
                        kind: 'user_delete',
                        user: u,
                        title: `Approve deletion request for ${u.email}?`,
                        detail: 'Archives deleted account per user deletion request.',
                      })}
                      className="px-2.5 py-1 rounded bg-red-500/20 text-[#8C2D23] text-[11px]"
                    >
                      Approve Deletion
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={6} className="p-6 text-center text-[#4A5750]">No users matched your filters.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Consolidated Single Active Super Admin Governance Section */}
      {hasPermission('admins:manage') && (
        <div className="space-y-4 pt-4">
          <h2 className="font-serif text-lg text-[#141C17] flex items-center gap-2">
            <Shield className="w-4 h-4 text-[#144D29]" /> Administrator Governance (Single Active Super Admin)
          </h2>

          {governance && (
            <div className={`p-3.5 rounded-xl border text-xs flex items-start gap-2.5 ${
              governance.single_admin_mode
                ? 'bg-[#E7F5EC] border-[#A7D7B8] text-[#14532D]'
                : 'bg-[#FEF6E6] border-[#EDD49F] text-[#85520E]'
            }`}>
              {governance.single_admin_mode ? (
                <UserCheck className="w-4 h-4 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              )}
              <div>
                <strong>
                  {governance.single_admin_mode
                    ? `Consolidated Mode Active (${governance.active_admin_count} Active Super Admin: ${governance.recommended_primary_super_admin})`
                    : `Super Admin Consolidation Advisory (${governance.active_admin_count ?? governance.super_admin_count} active admins found):`}
                </strong>{' '}
                {governance.migration_plan}
              </div>
            </div>
          )}

          <div className="grid lg:grid-cols-12 gap-5">
            <div className="lg:col-span-8 rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
                  <tr>
                    <th className="p-3">Admin</th>
                    <th className="p-3">Role</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Governance State</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E3E8E4]">
                  {admins.map((a) => {
                    const isSelf = currentAdmin?.admin_id === a.admin_id;
                    const isPrimary = a.admin_id === 'ADM-0002' || (a.status === 'ACTIVE' && a.role === 'SUPER_ADMIN');
                    return (
                      <tr key={a.admin_id}>
                        <td className="p-3">
                          <div className="text-[#141C17] font-medium">
                            {a.username} {isSelf && <span className="text-[10px] font-mono text-[#144D29]">(You)</span>}
                          </div>
                          <div className="text-[11px] text-[#4A5750]">{a.full_name} · {a.admin_id}</div>
                        </td>
                        <td className="p-3">
                          <span className="px-2 py-0.5 rounded bg-[#F6F8F6] border border-[#D2DBD4] text-[11px] font-mono text-[#1B6336]">
                            {a.role}
                          </span>
                        </td>
                        <td className="p-3 font-mono">
                          <span className={`px-2 py-0.5 rounded text-[10px] ${a.status === 'ACTIVE' ? 'bg-[#E7F5EC] text-[#14532D]' : 'bg-[#FDEEEC] text-[#8C2D23]'}`}>
                            {a.status}
                          </span>
                        </td>
                        <td className="p-3 text-[11px] text-[#4A5750]">
                          {isPrimary && a.status === 'ACTIVE'
                            ? 'Sole Active Super Admin (Protected)'
                            : 'Consolidated — Historical Record Preserved'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="lg:col-span-4 p-4 rounded-xl bg-white shadow-sm border border-[#E3E8E4] space-y-2.5 text-xs">
              <div className="font-semibold text-[#141C17] flex items-center gap-1.5">
                <Shield className="w-4 h-4 text-[#144D29]" /> Single Active Admin Policy
              </div>
              <p className="text-[#4A5750] leading-relaxed">
                Administrative access is consolidated exclusively to <strong>ADM-0002 (superadmin)</strong> with full permissions across all modules.
              </p>
              <p className="text-[#4A5750] leading-relaxed">
                Historical accounts remain preserved in <strong>DEACTIVATED</strong> state so audit logs, login history, and governance traceability stay intact without granting active access.
              </p>
            </div>
          </div>
        </div>
      )}

      {confirmDlg && (
        <div className="fixed inset-0 z-50 bg-black/45 flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-xl border border-[#1B6336] p-6 space-y-4 text-xs">
            <h3 className="font-serif text-lg text-[#141C17]">{confirmDlg.title}</h3>
            <p className="text-[#4A5750]">{confirmDlg.detail}</p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setConfirmDlg(null)} className="px-3.5 py-2 rounded border border-[#D2DBD4] text-[#4A5750]">
                Cancel
              </button>
              <button type="button" onClick={executeConfirmedAction} className="px-4 py-2 rounded bg-[#144D29] text-white font-semibold">
                Confirm &amp; Audit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
