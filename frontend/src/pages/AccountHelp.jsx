import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Bell,
  HelpCircle,
  KeyRound,
  LogOut,
  MessageSquare,
  Paperclip,
  Send,
  ShieldCheck,
  User,
} from 'lucide-react';
import {
  changeCustomerPassword,
  createUserSupportTicket,
  getCustomerProfile,
  getProperties,
  getUserNotifications,
  getUserSupportTicket,
  getUserSupportTickets,
  markAllUserNotificationsRead,
  markUserNotificationRead,
  replyUserSupportTicket,
  updateCustomerProfile,
} from '../api/client';
import { PageHeader, TabBar } from '../components/ui';

const MYSURU_TALUKS = [
  'Mysuru', 'Nanjangud', 'HD Kote', 'Periyapatna', 'Hunsur', 'K. R. Nagar', 'T. Narasipura',
];

const SUPPORT_CATEGORIES = [
  'Property Valuation',
  'GIS / Map',
  'Document Analyzer',
  'PDF Report',
  'Login / Account',
  'Technical Bug',
  'Feature Request',
  'Other',
];

const TICKET_PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'URGENT'];

export default function AccountHelp() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') === 'help' ? 'help' : 'profile';
  const [tab, setTab] = useState(initialTab);
  const [form, setForm] = useState({ full_name: '', phone: '', preferred_taluk: 'Mysuru', email: '' });
  const [pwForm, setPwForm] = useState({ current_password: '', new_password: '', confirm_password: '' });
  const [properties, setProperties] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [activeTicket, setActiveTicket] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [notifications, setNotifications] = useState([]);
  const [unreadNotifs, setUnreadNotifs] = useState(0);
  const [ticketForm, setTicketForm] = useState({
    title: '',
    description: '',
    category: 'Property Valuation',
    priority: 'MEDIUM',
    property_id: '',
  });
  const [attachment, setAttachment] = useState(null);
  const [authMissing, setAuthMissing] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  useEffect(() => {
    const qpTab = searchParams.get('tab');
    if (qpTab === 'help' || qpTab === 'profile' || qpTab === 'password') {
      setTab(qpTab);
    }
    const qTicket = searchParams.get('ticket');
    if (qTicket) {
      setTab('help');
      getUserSupportTicket(qTicket)
        .then((res) => setActiveTicket(res.data.ticket))
        .catch(() => {});
    }
  }, [searchParams]);

  const loadSupportAndNotifs = async () => {
    try {
      const [tRes, nRes] = await Promise.all([
        getUserSupportTickets().catch(() => ({ data: { tickets: [] } })),
        getUserNotifications().catch(() => ({ data: { notifications: [], unread_count: 0 } })),
      ]);
      setTickets(tRes.data?.tickets || []);
      setNotifications(nRes.data?.notifications || []);
      setUnreadNotifs(nRes.data?.unread_count || 0);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    getCustomerProfile()
      .then((res) => {
        const u = res.data.user || {};
        setForm({
          full_name: u.full_name || '',
          phone: u.phone || '',
          preferred_taluk: u.preferred_taluk || 'Mysuru',
          email: u.email || '',
        });
      })
      .catch((error) => {
        if (error?.response?.status === 401) setAuthMissing(true);
      });

    getProperties().then((pRes) => setProperties(pRes.data?.properties || [])).catch(() => {});
    loadSupportAndNotifs();
  }, []);

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    setMsg('');
    setErr('');
    try {
      const res = await updateCustomerProfile(form);
      localStorage.setItem('user_profile', JSON.stringify(res.data.user));
      setMsg('Account profile saved cleanly.');
    } catch (error) {
      setErr(error?.response?.data?.error || 'Could not update profile.');
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setMsg('');
    setErr('');
    if (pwForm.new_password !== pwForm.confirm_password) {
      setErr('New password and confirmation do not match.');
      return;
    }
    try {
      await changeCustomerPassword({
        current_password: pwForm.current_password,
        new_password: pwForm.new_password,
      });
      setMsg('Password changed cleanly.');
      setPwForm({ current_password: '', new_password: '', confirm_password: '' });
    } catch (error) {
      setErr(error?.response?.data?.error || 'Password update failed.');
    }
  };

  const handleSubmitTicket = async (e) => {
    e.preventDefault();
    setMsg('');
    setErr('');
    try {
      const fd = new FormData();
      fd.append('title', ticketForm.title);
      fd.append('description', ticketForm.description);
      fd.append('category', ticketForm.category);
      fd.append('priority', ticketForm.priority);
      if (ticketForm.property_id) fd.append('property_id', ticketForm.property_id);
      if (attachment) fd.append('attachment', attachment);

      const res = await createUserSupportTicket(fd);
      const created = res.data?.ticket;
      setMsg(`Support ticket ${created?.ticket_id || ''} submitted cleanly. Administrators have been notified.`);
      setTicketForm((f) => ({ ...f, title: '', description: '' }));
      setAttachment(null);
      if (created) setActiveTicket(created);
      await loadSupportAndNotifs();
    } catch (error) {
      setErr(error?.response?.data?.error || 'Could not submit support ticket.');
    }
  };

  const handleOpenTicket = async (ticketId) => {
    setErr('');
    try {
      const res = await getUserSupportTicket(ticketId);
      setActiveTicket(res.data.ticket);
    } catch (error) {
      setErr(error?.response?.data?.error || 'Could not open ticket.');
    }
  };

  const handleUserReply = async (e) => {
    e.preventDefault();
    if (!activeTicket || !replyText.trim()) return;
    setMsg('');
    setErr('');
    try {
      const res = await replyUserSupportTicket(activeTicket.ticket_id, { message: replyText.trim() });
      setActiveTicket(res.data.ticket);
      setReplyText('');
      setMsg(`Reply sent on ${activeTicket.ticket_id}. Support team notified.`);
      loadSupportAndNotifs();
    } catch (error) {
      setErr(error?.response?.data?.error || 'Failed to send reply.');
    }
  };

  const handleMarkNotifsRead = async () => {
    try {
      await markAllUserNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadNotifs(0);
    } catch {
      // ignore
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('user_access_token');
    localStorage.removeItem('user_profile');
    localStorage.removeItem('user_role');
    navigate('/login');
  };

  return (
    <div className="page-body fade-in">
      <PageHeader
        eyebrow="Citizen Workspace"
        title="Account & Support Center"
        subtitle="Manage profile details, password security, and report issues directly to administrators."
        icon={User}
        breadcrumbs={['Dashboard', 'Account & Support']}
        actions={
          !authMissing ? (
            <button type="button" onClick={handleLogout} className="btn btn-danger btn-sm">
              <LogOut size={14} /> Sign Out
            </button>
          ) : (
            <Link to="/login" className="btn btn-primary btn-sm">Sign In / Register</Link>
          )
        }
      />

      <div style={{ marginBottom: '22px' }}>
        <TabBar
          tabs={[
            { key: 'profile', label: 'Profile & Settings', icon: User },
            { key: 'password', label: 'Password Security', icon: KeyRound },
            { key: 'help', label: `Support / Report an Issue${unreadNotifs > 0 ? ` (${unreadNotifs})` : ''}`, icon: HelpCircle },
          ]}
          activeKey={tab}
          onChange={(k) => {
            setTab(k);
            if (k === 'profile') setSearchParams({});
            else setSearchParams({ tab: k });
          }}
        />
      </div>

      {err && <div className="alert alert-danger" style={{ marginBottom: 16 }}>{err}</div>}
      {msg && <div className="alert alert-ok" style={{ marginBottom: 16 }}>{msg}</div>}

      {tab === 'profile' && (
        authMissing ? (
          <div className="card" style={{ maxWidth: 520, padding: 28 }}>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>Guest Session Active</h3>
            <p style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 8 }}>
              Sign in or create a free customer account to bind property evaluations, saved parcels, and support tickets privately to your profile.
            </p>
            <Link to="/login" className="btn btn-primary" style={{ marginTop: 16 }}>Sign In / Register</Link>
          </div>
        ) : (
          <form onSubmit={handleSaveProfile} className="card" style={{ maxWidth: 560, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Account Email: <strong style={{ color: 'var(--text-primary)' }}>{form.email}</strong></div>
            <div className="form-group">
              <label className="form-label">Full Name</label>
              <input className="form-control" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">Phone</label>
              <input className="form-control" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">Preferred Taluk (Mysuru District)</label>
              <select className="form-control" value={form.preferred_taluk} onChange={(e) => setForm({ ...form, preferred_taluk: e.target.value })}>
                {MYSURU_TALUKS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>Save Changes</button>
          </form>
        )
      )}

      {tab === 'password' && (
        authMissing ? (
          <div className="card" style={{ maxWidth: 520, padding: 24, fontSize: 13, color: 'var(--text-2)' }}>
            Sign in first to change your account password.
          </div>
        ) : (
          <form onSubmit={handleChangePassword} className="card" style={{ maxWidth: 520, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
              <ShieldCheck size={16} color="var(--accent)" /> Update Password
            </h3>
            <div className="form-group">
              <label className="form-label">Current Password</label>
              <input type="password" className="form-control" required value={pwForm.current_password} onChange={(e) => setPwForm({ ...pwForm, current_password: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">New Password (min 6 characters)</label>
              <input type="password" className="form-control" required minLength={6} value={pwForm.new_password} onChange={(e) => setPwForm({ ...pwForm, new_password: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">Confirm New Password</label>
              <input type="password" className="form-control" required minLength={6} value={pwForm.confirm_password} onChange={(e) => setPwForm({ ...pwForm, confirm_password: e.target.value })} />
            </div>
            <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>Update Password</button>
          </form>
        )
      )}

      {tab === 'help' && (
        authMissing ? (
          <div className="card" style={{ maxWidth: 560, padding: 28 }}>
            <h3 style={{ fontSize: 18, fontWeight: 700 }}>Sign In Required for Support Tickets</h3>
            <p style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 8 }}>
              Please sign in to submit support tickets, track administrator responses, and receive persistent notifications.
            </p>
            <Link to="/login" className="btn btn-primary" style={{ marginTop: 16 }}>Sign In / Register</Link>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            {notifications.length > 0 && (
              <div className="card" style={{ padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <strong style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 14 }}>
                    <Bell size={15} color="var(--accent)" /> Support Notifications ({unreadNotifs} unread)
                  </strong>
                  {unreadNotifs > 0 && (
                    <button type="button" onClick={handleMarkNotifsRead} className="btn btn-secondary btn-sm">
                      Mark all read
                    </button>
                  )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 170, overflowY: 'auto' }}>
                  {notifications.map((n) => (
                    <button
                      key={n.notification_id}
                      type="button"
                      onClick={() => {
                        markUserNotificationRead(n.notification_id).catch(() => {});
                        setNotifications((prev) => prev.map((x) => x.notification_id === n.notification_id ? { ...x, is_read: true } : x));
                        setUnreadNotifs((c) => (n.is_read ? c : Math.max(0, c - 1)));
                        if (n.ticket_id) handleOpenTicket(n.ticket_id);
                      }}
                      style={{
                        textAlign: 'left',
                        padding: '8px 12px',
                        borderRadius: 8,
                        border: '1px solid var(--border)',
                        background: n.is_read ? 'var(--surface-2)' : 'rgba(20,77,41,0.08)',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-3)' }}>
                        <span>{n.category}</span>
                        <span>{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</span>
                      </div>
                      <div style={{ fontSize: 13, fontWeight: n.is_read ? 500 : 700, color: 'var(--text-primary)' }}>{n.title}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{n.message}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="grid grid-2" style={{ gap: '24px' }}>
              <form onSubmit={handleSubmitTicket} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <MessageSquare size={16} color="var(--accent)" /> Report an Issue / Submit Support Ticket
                </h3>
                <div className="form-group">
                  <label className="form-label">Issue Title *</label>
                  <input className="form-control" required value={ticketForm.title} onChange={(e) => setTicketForm({ ...ticketForm, title: e.target.value })} placeholder="Brief summary of the issue" />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Category *</label>
                    <select className="form-control" value={ticketForm.category} onChange={(e) => setTicketForm({ ...ticketForm, category: e.target.value })}>
                      {SUPPORT_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Priority *</label>
                    <select className="form-control" value={ticketForm.priority} onChange={(e) => setTicketForm({ ...ticketForm, priority: e.target.value })}>
                      {TICKET_PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Related Property (Optional)</label>
                  <select className="form-control" value={ticketForm.property_id} onChange={(e) => setTicketForm({ ...ticketForm, property_id: e.target.value })}>
                    <option value="">General Platform Issue</option>
                    {properties.map((p) => <option key={p.id} value={p.id}>#{p.id} — {p.name || p.village_or_locality} ({p.taluk})</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Description *</label>
                  <textarea className="form-control" required rows={4} value={ticketForm.description} onChange={(e) => setTicketForm({ ...ticketForm, description: e.target.value })} placeholder="Describe what happened, expected behaviour, or steps to reproduce..." />
                </div>
                <div className="form-group">
                  <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Paperclip size={13} /> Optional Screenshot / Attachment (PNG, JPG, PDF)
                  </label>
                  <input
                    type="file"
                    accept=".png,.jpg,.jpeg,.pdf"
                    onChange={(e) => setAttachment(e.target.files?.[0] || null)}
                    className="form-control"
                  />
                </div>
                <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>
                  <Send size={14} /> Submit Support Ticket
                </button>
              </form>

              <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 700 }}>My Support Tickets ({tickets.length})</h3>
                {tickets.length === 0 ? (
                  <div style={{ fontSize: 13, color: 'var(--text-3)', padding: '16px 0' }}>
                    You have not submitted any support tickets yet.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 240, overflowY: 'auto' }}>
                    {tickets.map((t) => (
                      <button
                        key={t.ticket_id}
                        type="button"
                        onClick={() => handleOpenTicket(t.ticket_id)}
                        style={{
                          textAlign: 'left',
                          padding: '10px 12px',
                          borderRadius: 8,
                          background: activeTicket?.ticket_id === t.ticket_id ? 'rgba(20,77,41,0.08)' : 'var(--surface-2)',
                          border: `1px solid ${activeTicket?.ticket_id === t.ticket_id ? 'var(--accent)' : 'var(--border)'}`,
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                          <span style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 700, color: 'var(--accent)' }}>{t.ticket_id}</span>
                          <span className="badge badge-info">{t.status} · {t.priority}</span>
                        </div>
                        <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)', marginTop: 3 }}>{t.title}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{t.category} · {(t.messages || []).length} message(s)</div>
                      </button>
                    ))}
                  </div>
                )}

                {activeTicket && (
                  <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: 14 }}>{activeTicket.ticket_id}: {activeTicket.title}</strong>
                      <span className="badge badge-info">{activeTicket.status}</span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 220, overflowY: 'auto', padding: 8, background: 'var(--surface-2)', borderRadius: 8 }}>
                      {(activeTicket.messages || []).map((m) => (
                        <div key={m.message_id} style={{ padding: '8px 10px', borderRadius: 6, background: m.sender_type === 'ADMIN' ? 'rgba(20,77,41,0.1)' : '#fff', border: '1px solid var(--border)', fontSize: 12 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-3)', marginBottom: 2 }}>
                            <span><strong>{m.sender_name}</strong> ({m.sender_type})</span>
                            <span>{m.timestamp ? new Date(m.timestamp).toLocaleString() : ''}</span>
                          </div>
                          <div style={{ whiteSpace: 'pre-wrap' }}>{m.body}</div>
                        </div>
                      ))}
                    </div>
                    {activeTicket.status !== 'CLOSED' && (
                      <form onSubmit={handleUserReply} style={{ display: 'flex', gap: 8 }}>
                        <input
                          className="form-control"
                          required
                          value={replyText}
                          onChange={(e) => setReplyText(e.target.value)}
                          placeholder="Write a reply to support..."
                        />
                        <button type="submit" className="btn btn-primary btn-sm">Reply</button>
                      </form>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      )}
    </div>
  );
}
