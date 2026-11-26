import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  CheckCircle2,
  LifeBuoy,
  MessageSquare,
  Paperclip,
  RefreshCw,
  Send,
  X,
} from 'lucide-react';
import {
  ADMIN_TOKEN_KEY,
  adminSupportAttachmentUrl,
  fetchAdminSupportTicket,
  fetchAdminSupportTickets,
  replyAdminSupportTicket,
  updateAdminSupportTicketStatus,
} from '../api/adminClient';
import { useAdminAuth } from '../context/AdminAuthContext';
import AdminModuleHeader from '../components/AdminModuleHeader';

const STATUS_BADGE = {
  OPEN: 'bg-amber-500/20 text-[#85520E]',
  IN_PROGRESS: 'bg-sky-500/15 text-[#1A5276]',
  AWAITING_USER: 'bg-purple-500/15 text-purple-800',
  RESOLVED: 'bg-emerald-500/15 text-[#14532D]',
  CLOSED: 'bg-gray-200 text-gray-700',
};

const PRIORITY_BADGE = {
  LOW: 'bg-gray-100 text-gray-700',
  MEDIUM: 'bg-sky-500/15 text-[#1A5276]',
  HIGH: 'bg-amber-500/20 text-[#85520E]',
  URGENT: 'bg-red-500/20 text-[#8C2D23]',
};

export default function AdminSupport() {
  const { hasPermission } = useAdminAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tickets, setTickets] = useState([]);
  const [legacyEnquiries, setLegacyEnquiries] = useState([]);
  const [supportAdmins, setSupportAdmins] = useState([]);
  const [statuses, setStatuses] = useState(['OPEN', 'IN_PROGRESS', 'AWAITING_USER', 'RESOLVED', 'CLOSED']);
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [search, setSearch] = useState('');
  const [activeTicket, setActiveTicket] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const canReply = hasPermission('support:reply');
  const canManage = hasPermission('support:manage');

  const load = async () => {
    setLoading(true);
    setErr('');
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (priorityFilter) params.priority = priorityFilter;
      if (search.trim()) params.search = search.trim();
      const res = await fetchAdminSupportTickets(params);
      setTickets(res.data.tickets || []);
      setLegacyEnquiries(res.data.legacy_enquiries || []);
      setSupportAdmins(res.data.support_admins || []);
      if (Array.isArray(res.data.statuses)) setStatuses(res.data.statuses);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Failed to load support tickets.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [statusFilter, priorityFilter]);

  useEffect(() => {
    const tid = searchParams.get('ticket');
    if (tid) {
      openTicket(tid);
    }
  }, [searchParams]);

  const openTicket = async (ticketId) => {
    setErr('');
    try {
      const res = await fetchAdminSupportTicket(ticketId);
      setActiveTicket(res.data.ticket);
    } catch (e) {
      setErr(e?.response?.data?.error || 'Could not load ticket details.');
    }
  };

  const handleSendReply = async (e) => {
    e.preventDefault();
    if (!activeTicket || !replyText.trim()) return;
    setErr('');
    setMsg('');
    try {
      const res = await replyAdminSupportTicket(activeTicket.ticket_id, { message: replyText.trim() });
      setActiveTicket(res.data.ticket);
      setReplyText('');
      setMsg(`Reply sent on ${activeTicket.ticket_id} and user notified.`);
      load();
    } catch (e2) {
      setErr(e2?.response?.data?.error || 'Failed to send reply.');
    }
  };

  const handleStatusOrAssign = async (patch) => {
    if (!activeTicket) return;
    setErr('');
    setMsg('');
    try {
      const res = await updateAdminSupportTicketStatus(activeTicket.ticket_id, patch);
      setActiveTicket(res.data.ticket);
      setMsg(`Updated ${activeTicket.ticket_id} successfully.`);
      load();
    } catch (e2) {
      setErr(e2?.response?.data?.error || 'Ticket update failed.');
    }
  };

  const handleViewAttachment = async (ticketId, filename) => {
    const token = localStorage.getItem(ADMIN_TOKEN_KEY);
    const resp = await fetch(adminSupportAttachmentUrl(ticketId), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) {
      setErr('Could not download attachment.');
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
            <LifeBuoy className="w-5 h-5 text-[#144D29]" /> Support Center &amp; User Tickets
          </h1>
          <p className="text-xs text-[#4A5750] mt-1">
            Persistent SQLite ticket queue ({tickets.length} shown) with real-time user-admin notifications.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search ticket ID, user, title..."
            className="px-3 py-1.5 rounded-lg bg-white border border-[#D2DBD4] text-xs text-[#141C17]"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-white border border-[#D2DBD4] text-xs text-[#141C17]"
          >
            <option value="">All Statuses</option>
            {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-white border border-[#D2DBD4] text-xs text-[#141C17]"
          >
            <option value="">All Priorities</option>
            {['LOW', 'MEDIUM', 'HIGH', 'URGENT'].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <button
            type="button"
            onClick={load}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#144D29] text-white text-xs font-semibold"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>
      </div>

      <AdminModuleHeader
        whatItShows="User-submitted support tickets across Property Valuation, GIS/Map, Document Analyzer, PDF Report, and Account issues."
        adminAction="Open any ticket to review conversation history, assign a Support Admin, reply, or update status."
        consequence="Every reply and status change persists to the database and dispatches an instant notification to the user."
      />

      {err && <div className="p-3 rounded-lg bg-[#FDEEEC] border border-[#ECC2BC] text-xs text-[#8C2D23] flex items-center gap-2"><AlertCircle className="w-4 h-4" />{err}</div>}
      {msg && <div className="p-3 rounded-lg bg-[#E7F5EC] border border-[#BCE0C8] text-xs text-[#14532D] flex items-center gap-2"><CheckCircle2 className="w-4 h-4" />{msg}</div>}

      <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
            <tr>
              <th className="p-3">Ticket ID</th>
              <th className="p-3">User</th>
              <th className="p-3">Issue &amp; Category</th>
              <th className="p-3">Priority</th>
              <th className="p-3">Status</th>
              <th className="p-3">Submitted</th>
              <th className="p-3">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E3E8E4]">
            {tickets.map((t) => (
              <tr key={t.ticket_id} className="hover:bg-[#F6F8F6]">
                <td className="p-3 font-mono font-semibold text-[#144D29]">{t.ticket_id}</td>
                <td className="p-3">
                  <div className="font-medium text-[#141C17]">{t.user_name}</div>
                  <div className="text-[11px] text-[#4A5750]">{t.user_email}</div>
                </td>
                <td className="p-3">
                  <div className="font-medium text-[#141C17]">{t.title}</div>
                  <div className="text-[11px] text-[#4A5750]">{t.category} · {(t.messages || []).length} msg(s)</div>
                </td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded font-mono text-[10px] ${PRIORITY_BADGE[t.priority] || ''}`}>
                    {t.priority}
                  </span>
                </td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded font-mono text-[10px] ${STATUS_BADGE[t.status] || ''}`}>
                    {t.status}
                  </span>
                </td>
                <td className="p-3 font-mono text-[11px] text-[#4A5750]">
                  {t.created_at ? new Date(t.created_at).toLocaleString() : '—'}
                </td>
                <td className="p-3">
                  <button
                    type="button"
                    onClick={() => {
                      setSearchParams({ ticket: t.ticket_id });
                      openTicket(t.ticket_id);
                    }}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#D2DBD4] text-[11px] hover:border-[#144D29]"
                  >
                    <MessageSquare className="w-3 h-3 text-[#144D29]" /> Open
                  </button>
                </td>
              </tr>
            ))}
            {!loading && tickets.length === 0 && (
              <tr>
                <td colSpan={7} className="p-6 text-center text-[#4A5750]">
                  No support tickets found matching current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {legacyEnquiries.length > 0 && (
        <div className="space-y-2">
          <h2 className="font-serif text-base text-[#141C17]">General Help Enquiries ({legacyEnquiries.length})</h2>
          <div className="rounded-xl bg-white shadow-sm border border-[#E3E8E4] overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F6F8F6] text-[#4A5750] font-mono uppercase text-[10px]">
                <tr>
                  <th className="p-3">Name &amp; Email</th>
                  <th className="p-3">Taluk</th>
                  <th className="p-3">Subject &amp; Message</th>
                  <th className="p-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E3E8E4]">
                {legacyEnquiries.map((eq) => (
                  <tr key={eq.id}>
                    <td className="p-3"><div className="font-medium">{eq.name}</div><div className="text-[11px] text-[#4A5750]">{eq.email}</div></td>
                    <td className="p-3">{eq.taluk}</td>
                    <td className="p-3"><div className="font-medium">{eq.subject}</div><div className="text-[11px] text-[#4A5750]">{eq.message}</div></td>
                    <td className="p-3 font-mono text-[#144D29]">{eq.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Ticket Detail & Conversation Modal */}
      {activeTicket && (
        <div className="fixed inset-0 z-50 bg-black/45 flex items-center justify-center p-4">
          <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white shadow-xl border border-[#1B6336] p-6 space-y-4 text-xs">
            <div className="flex items-start justify-between border-b border-[#E3E8E4] pb-3 gap-4">
              <div>
                <div className="flex items-center gap-2 font-mono text-[11px]">
                  <span className="text-[#144D29] font-bold">{activeTicket.ticket_id}</span>
                  <span className={`px-2 py-0.5 rounded ${PRIORITY_BADGE[activeTicket.priority] || ''}`}>{activeTicket.priority}</span>
                  <span className={`px-2 py-0.5 rounded ${STATUS_BADGE[activeTicket.status] || ''}`}>{activeTicket.status}</span>
                </div>
                <h2 className="font-serif text-lg text-[#141C17] mt-1">{activeTicket.title}</h2>
                <div className="text-[#4A5750] mt-0.5">
                  From <strong>{activeTicket.user_name}</strong> ({activeTicket.user_email}) · Category: {activeTicket.category}
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setActiveTicket(null);
                  setSearchParams({});
                }}
                className="text-[#4A5750] hover:text-[#141C17]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {activeTicket.has_attachment && (
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
                <span className="flex items-center gap-1.5 text-[#141C17]">
                  <Paperclip className="w-3.5 h-3.5 text-[#144D29]" />
                  Attachment: <strong>{activeTicket.attachment_name}</strong>
                </span>
                <button
                  type="button"
                  onClick={() => handleViewAttachment(activeTicket.ticket_id, activeTicket.attachment_name)}
                  className="px-2.5 py-1 rounded border border-[#D2DBD4] hover:border-[#144D29]"
                >
                  Open File
                </button>
              </div>
            )}

            {canManage && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
                <div>
                  <label className="block text-[11px] text-[#4A5750] mb-1">Ticket Status</label>
                  <select
                    value={activeTicket.status}
                    onChange={(e) => handleStatusOrAssign({ status: e.target.value })}
                    className="w-full px-2.5 py-1.5 rounded bg-white border border-[#D2DBD4] text-[#141C17]"
                  >
                    {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-[#4A5750] mb-1">Assigned Support Administrator</label>
                  <select
                    value={activeTicket.assigned_admin_id || ''}
                    onChange={(e) => handleStatusOrAssign({ assigned_admin_id: e.target.value })}
                    className="w-full px-2.5 py-1.5 rounded bg-white border border-[#D2DBD4] text-[#141C17]"
                  >
                    <option value="">Unassigned</option>
                    {supportAdmins.map((a) => (
                      <option key={a.admin_id} value={a.admin_id}>{a.full_name} ({a.role})</option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            <div className="space-y-2.5 max-h-72 overflow-y-auto p-3 rounded-lg bg-[#F6F8F6] border border-[#E3E8E4]">
              {(activeTicket.messages || []).map((m) => (
                <div
                  key={m.message_id}
                  className={`p-3 rounded-lg border ${
                    m.sender_type === 'ADMIN'
                      ? 'bg-[#ECF5EE] border-[#BCE0C8] ml-6'
                      : 'bg-white border-[#E3E8E4] mr-6'
                  }`}
                >
                  <div className="flex justify-between text-[10px] font-mono text-[#4A5750] mb-1">
                    <span><strong>{m.sender_name}</strong> ({m.sender_role})</span>
                    <span>{m.timestamp ? new Date(m.timestamp).toLocaleString() : ''}</span>
                  </div>
                  <div className="text-[#141C17] whitespace-pre-wrap">{m.body}</div>
                </div>
              ))}
            </div>

            {canReply && (
              <form onSubmit={handleSendReply} className="space-y-2">
                <textarea
                  rows={3}
                  required
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder="Write an administrator response to the user..."
                  className="w-full px-3 py-2 rounded-lg bg-white border border-[#D2DBD4] text-[#141C17]"
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="submit"
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#144D29] text-white font-semibold"
                  >
                    <Send className="w-3.5 h-3.5" /> Send Reply &amp; Notify User
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
