import React, { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  Activity, BarChart2, Bell, Brain, CheckCheck, ClipboardList,
  FileText, LayoutDashboard, LifeBuoy,
  LogOut, MapPin, Menu, Settings, ShieldAlert, Users, X,
} from 'lucide-react';
import { useAdminAuth } from '../context/AdminAuthContext';
import {
  fetchAdminNotifications,
  markAdminNotificationRead,
  markAllAdminNotificationsRead,
} from '../api/adminClient';

const ADMIN_NAV = [
  { to: '/admin/dashboard',   label: 'Dashboard',            icon: LayoutDashboard, perm: 'overview:view' },
  { to: '/admin/users',       label: 'User Management',      icon: Users,           perm: 'users:view' },
  { to: '/admin/evaluations', label: 'Property Evaluations', icon: BarChart2,       perm: 'evaluations:view' },
  { to: '/admin/documents',   label: 'Documents & Reports',  icon: FileText,        perm: 'documents:view' },
  { to: '/admin/data-model',  label: 'Data & Model',         icon: Brain,           perm: ['models:view', 'datasets:view'] },
  { to: '/admin/gis',         label: 'GIS Management',       icon: MapPin,          perm: 'gis:view' },
  { to: '/admin/support',     label: 'Support Center',       icon: LifeBuoy,        perm: 'support:view' },
  { to: '/admin/audit',       label: 'Audit Logs',           icon: ClipboardList,   perm: 'audit:view' },
  { to: '/admin/health',      label: 'System Health',        icon: Activity,        perm: 'health:view' },
  { to: '/admin/settings',    label: 'System & Settings',    icon: Settings,        perm: 'settings:view' },
];

export default function AdminLayout() {
  const { admin, logout, hasPermission } = useAdminAuth();
  const navigate   = useNavigate();
  const [sidebarOpen, setSidebarOpen]     = useState(false);
  const [notifOpen, setNotifOpen]         = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount]     = useState(0);
  const notifRef = useRef(null);

  const loadNotifications = async () => {
    try {
      const res = await fetchAdminNotifications();
      setNotifications(res.data?.notifications || []);
      setUnreadCount(res.data?.unread_count || 0);
    } catch { /* silent */ }
  };

  useEffect(() => {
    if (admin) {
      loadNotifications();
      const t = setInterval(loadNotifications, 15000);
      return () => clearInterval(t);
    }
  }, [admin?.admin_id]);

  /* Close notif dropdown on outside click */
  useEffect(() => {
    const handler = (e) => { if (notifRef.current && !notifRef.current.contains(e.target)) setNotifOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleNotifClick = async (n) => {
    try {
      await markAdminNotificationRead(n.notification_id);
      setNotifications(prev => prev.map(x => x.notification_id === n.notification_id ? { ...x, is_read: true } : x));
      setUnreadCount(c => n.is_read ? c : Math.max(0, c - 1));
    } catch { /* ignore */ }
    setNotifOpen(false);
    if (n.link) navigate(n.link);
    else if (n.ticket_id) navigate(`/admin/support?ticket=${n.ticket_id}`);
  };

  const handleMarkAll = async () => {
    try {
      await markAllAdminNotificationsRead();
      setNotifications(prev => prev.map(x => ({ ...x, is_read: true })));
      setUnreadCount(0);
    } catch { /* ignore */ }
  };

  const handleLogout = async () => { await logout(); navigate('/admin/login', { replace: true }); };

  const visible = ADMIN_NAV.filter(item =>
    Array.isArray(item.perm) ? item.perm.some(p => hasPermission(p)) : hasPermission(item.perm)
  );

  const initials = admin?.full_name
    ? admin.full_name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : admin?.username?.slice(0, 2).toUpperCase() || 'A';

  return (
    <div style={sh.shell}>
      {sidebarOpen && <div style={sh.backdrop} onClick={() => setSidebarOpen(false)} />}

      {/* ── SIDEBAR ── */}
      <aside className={`slv-sidebar ${sidebarOpen ? 'open' : ''}`} style={sh.sidebar}>
        {/* Brand */}
        <div style={sh.brand}>
          <Link to="/admin/dashboard" style={sh.brandLink}>
            <svg width="32" height="32" viewBox="0 0 40 40" fill="none" aria-hidden="true">
              <rect width="40" height="40" rx="9" fill="rgba(255,255,255,0.12)" stroke="rgba(255,255,255,0.25)" />
              <path d="M12 29H28M14 29V20H26V29M17 20V16.5C17 14.8 18.3 13.5 20 13.5C21.7 13.5 23 14.8 23 16.5V20M17.5 29V24.5H22.5V29" stroke="white" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <div>
              <div style={sh.brandName}>Admin Console</div>
              <div style={sh.brandSub}>SLV-GIS Mysuru</div>
            </div>
          </Link>
          <button type="button" className="slv-close-mobile" style={sh.closeMobile} onClick={() => setSidebarOpen(false)} aria-label="Close">
            <X size={18} stroke="rgba(255,255,255,0.65)" />
          </button>
        </div>

        <div style={sh.divider} />

        {/* Nav */}
        <nav style={sh.nav} aria-label="Admin navigation">
          {visible.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to} to={to}
              onClick={() => setSidebarOpen(false)}
              style={({ isActive }) => ({ ...sh.navItem, ...(isActive ? sh.navItemActive : {}) })}
            >
              <Icon size={17} style={{ flexShrink: 0 }} />
              <span style={{ flex: 1 }}>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div style={sh.sidebarFooter}>
          <div style={sh.divider} />
          <div style={sh.adminBlock}>
            <div style={sh.adminAvatar}>{initials}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={sh.adminName}>{admin?.full_name || admin?.username || 'Administrator'}</div>
              <div style={sh.adminRole}>Super Admin</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.4rem' }}>
            <Link to="/student" style={{ ...sh.outlineBtn, flex: 1, textAlign: 'center', textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              Citizen Portal
            </Link>
            <button type="button" style={{ ...sh.outlineBtn, flex: 1, cursor: 'pointer' }} onClick={handleLogout}>
              <LogOut size={13} /> Logout
            </button>
          </div>
        </div>
      </aside>

      {/* ── MAIN ── */}
      <div style={sh.main}>
        {/* Top bar */}
        <header style={sh.topbar}>
          <div style={sh.topLeft}>
            <button type="button" className="slv-hamburger" style={sh.hamburger} onClick={() => setSidebarOpen(true)} aria-label="Open menu">
              <Menu size={20} />
            </button>
            <div>
              <span style={sh.consoleLabel}>SLV-GIS</span>
              <span style={{ color: '#D2DBD4', margin: '0 0.4rem' }}>·</span>
              <span style={sh.consoleLabel}>Administrator Console</span>
            </div>
          </div>
          <div style={sh.topRight}>
            {/* Notifications */}
            <div ref={notifRef} style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => { setNotifOpen(v => !v); loadNotifications(); }}
                style={sh.iconBtn} aria-label="Notifications"
              >
                <Bell size={18} />
                {unreadCount > 0 && <span style={sh.badge}>{unreadCount > 9 ? '9+' : unreadCount}</span>}
              </button>
              {notifOpen && (
                <div style={sh.notifDropdown}>
                  <div style={sh.notifHeader}>
                    <strong style={{ fontSize: '0.8rem', color: '#141C17' }}>Notifications ({unreadCount} unread)</strong>
                    {unreadCount > 0 && (
                      <button type="button" onClick={handleMarkAll} style={sh.markAllBtn}>
                        <CheckCheck size={12} /> Mark all read
                      </button>
                    )}
                  </div>
                  {notifications.length === 0 ? (
                    <div style={{ padding: '1.5rem', textAlign: 'center', fontSize: '0.78rem', color: '#6E7B73' }}>No notifications yet.</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', padding: '0.4rem' }}>
                      {notifications.slice(0, 15).map(n => (
                        <button key={n.notification_id} type="button" onClick={() => handleNotifClick(n)} style={{ ...sh.notifItem, background: n.is_read ? '#fff' : '#ECF5EE' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: '#6E7B73', marginBottom: 2 }}>
                            <span style={{ fontWeight: 700, color: '#144D29' }}>{n.category}</span>
                            <span>{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</span>
                          </div>
                          <div style={{ fontSize: '0.78rem', fontWeight: n.is_read ? 500 : 700, color: '#141C17' }}>{n.title}</div>
                          <div style={{ fontSize: '0.72rem', color: '#4A5750', marginTop: 2 }}>{n.message}</div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            {/* Admin badge */}
            <div style={sh.adminBadge}>
              <ShieldAlert size={14} />
              <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>Super Admin</span>
            </div>
            <div style={sh.topAvatar}>{initials}</div>
          </div>
        </header>

        <main style={sh.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

const sh = {
  shell: { display: 'flex', minHeight: '100vh', background: '#F6F8F6', fontFamily: 'var(--font-sans)' },
  backdrop: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 199 },
  sidebar: {
    width: 240, flexShrink: 0,
    background: 'linear-gradient(180deg, #0E3B20 0%, #144D29 100%)',
    display: 'flex', flexDirection: 'column',
    position: 'sticky', top: 0, height: '100vh', overflowY: 'auto',
    transition: 'transform 220ms cubic-bezier(0.22,1,0.36,1)', zIndex: 200,
  },
  brand: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem 1rem 0.85rem' },
  brandLink: { display: 'flex', alignItems: 'center', gap: '0.6rem', textDecoration: 'none' },
  brandName: { fontSize: '0.98rem', fontWeight: 800, color: '#FFFFFF', letterSpacing: '-0.02em', lineHeight: 1.1, fontFamily: 'var(--font-display)' },
  brandSub: { fontSize: '0.64rem', color: 'rgba(255,255,255,0.62)', letterSpacing: '0.02em' },
  closeMobile: { background: 'none', border: 'none', cursor: 'pointer', padding: 4 },
  divider: { height: 1, background: 'rgba(255,255,255,0.12)', margin: '0 0.9rem' },
  nav: { flex: 1, padding: '0.55rem 0.65rem', display: 'flex', flexDirection: 'column', gap: '0.15rem' },
  navItem: { display: 'flex', alignItems: 'center', gap: '0.65rem', padding: '0.56rem 0.75rem', borderRadius: 9, color: 'rgba(255,255,255,0.76)', textDecoration: 'none', fontSize: '0.835rem', fontWeight: 500, transition: 'all 150ms' },
  navItemActive: { background: 'rgba(255,255,255,0.16)', color: '#FFFFFF', fontWeight: 700, boxShadow: 'inset 3px 0 0 #8BE0AC' },
  sidebarFooter: { padding: '0.5rem 0.75rem 0.85rem', display: 'flex', flexDirection: 'column', gap: '0.55rem' },
  adminBlock: { display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.4rem 0.5rem' },
  adminAvatar: { width: 34, height: 34, borderRadius: '50%', background: 'rgba(255,255,255,0.18)', color: '#fff', fontWeight: 700, fontSize: '0.78rem', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  adminName: { fontSize: '0.82rem', fontWeight: 600, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  adminRole: { fontSize: '0.65rem', color: 'rgba(255,255,255,0.5)' },
  outlineBtn: { display: 'flex', alignItems: 'center', gap: '0.3rem', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 7, padding: '0.42rem 0.6rem', color: 'rgba(255,255,255,0.65)', fontSize: '0.75rem', fontWeight: 600, fontFamily: 'var(--font-sans)' },
  /* Main */
  main: { flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' },
  topbar: { height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 1.5rem', background: '#fff', borderBottom: '1px solid #E3E8E4', position: 'sticky', top: 0, zIndex: 100, boxShadow: '0 1px 3px rgba(16,36,24,0.04)' },
  topLeft: { display: 'flex', alignItems: 'center', gap: '0.75rem' },
  hamburger: { background: 'none', border: 'none', cursor: 'pointer', color: '#4A5750', display: 'flex', alignItems: 'center', padding: 4, borderRadius: 6 },
  consoleLabel: { fontSize: '0.875rem', fontWeight: 600, color: '#141C17' },
  topRight: { display: 'flex', alignItems: 'center', gap: '0.65rem' },
  iconBtn: { position: 'relative', background: 'none', border: '1px solid #E3E8E4', borderRadius: 8, padding: '0.4rem 0.5rem', display: 'flex', alignItems: 'center', color: '#4A5750', cursor: 'pointer' },
  badge: { position: 'absolute', top: -5, right: -5, background: '#E53935', color: '#fff', fontSize: '0.6rem', fontWeight: 700, borderRadius: 999, padding: '1px 5px', minWidth: 16, textAlign: 'center' },
  notifDropdown: { position: 'absolute', right: 0, top: '110%', width: 340, maxHeight: 400, overflowY: 'auto', background: '#fff', border: '1px solid #D2DBD4', borderRadius: 12, boxShadow: '0 12px 32px rgba(0,0,0,0.14)', zIndex: 1200 },
  notifHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.65rem 0.75rem', borderBottom: '1px solid #E3E8E4' },
  markAllBtn: { background: 'none', border: 'none', color: '#144D29', fontSize: '0.72rem', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 },
  notifItem: { textAlign: 'left', padding: '0.5rem 0.65rem', borderRadius: 8, border: '1px solid #E3E8E4', cursor: 'pointer', width: '100%', fontFamily: 'var(--font-sans)' },
  adminBadge: { display: 'flex', alignItems: 'center', gap: '0.35rem', background: '#ECF5EE', border: '1px solid #BCE0C8', borderRadius: 999, padding: '0.3rem 0.75rem', color: '#144D29' },
  topAvatar: { width: 34, height: 34, borderRadius: '50%', background: 'linear-gradient(135deg, #144D29, #1B6336)', color: '#fff', fontWeight: 700, fontSize: '0.78rem', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  content: { flex: 1, padding: '1.75rem 2rem 3rem', maxWidth: 1320, width: '100%', margin: '0 auto' },
};
