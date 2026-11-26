import React, { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  Bell,
  FileText,
  FolderOpen,
  GitCompare,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  MapPin,
  Menu,
  Search,
  UserCircle,
  X,
} from 'lucide-react';
import { getUserNotifications } from '../api/client';

const NAV = [
  { to: '/student',                  label: 'Dashboard',              icon: LayoutDashboard, end: true },
  { to: '/student/evaluate',         label: 'Evaluate Property',      icon: MapPin },
  { to: '/student/documents',        label: 'Document Analyzer',      icon: FileText },
  { to: '/student/properties',       label: 'My Properties & Reports',icon: FolderOpen },
  { to: '/student/compare',          label: 'Compare Properties',     icon: GitCompare },
  { to: '/student/account?tab=help', label: 'Support / Report Issue', icon: LifeBuoy },
  { to: '/student/account',          label: 'Profile & Settings',     icon: UserCircle, end: true },
];

export default function StudentLayout() {
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [globalSearch, setGlobalSearch] = useState('');
  const [unreadCount, setUnreadCount] = useState(0);

  let user = null;
  try {
    user = JSON.parse(localStorage.getItem('user_profile') || 'null');
  } catch {
    user = null;
  }

  useEffect(() => {
    const token = localStorage.getItem('user_access_token');
    if (!token) return;
    const poll = () =>
      getUserNotifications()
        .then((res) => setUnreadCount(res.data?.unread_count || 0))
        .catch(() => {});
    poll();
    const timer = setInterval(poll, 15000);
    return () => clearInterval(timer);
  }, [user?.email]);

  const handleSearch = (e) => {
    e.preventDefault();
    const q = globalSearch.trim();
    navigate(q ? `/student/evaluate?q=${encodeURIComponent(q)}` : '/student/evaluate');
  };

  const handleSignOut = () => {
    localStorage.removeItem('user_access_token');
    localStorage.removeItem('user_profile');
    localStorage.removeItem('user_role');
    navigate('/login');
  };

  const initials = user?.full_name
    ? user.full_name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase()
    : 'U';

  return (
    <div style={sh.shell}>
      {sidebarOpen && <div style={sh.backdrop} onClick={() => setSidebarOpen(false)} />}

      <aside className={`slv-sidebar ${sidebarOpen ? 'open' : ''}`} style={sh.sidebar} aria-label="User portal navigation">
        <div style={sh.brand}>
          <Link to="/" style={sh.brandLink} onClick={() => setSidebarOpen(false)}>
            <svg width="34" height="34" viewBox="0 0 40 40" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
              <rect width="40" height="40" rx="9" fill="rgba(255,255,255,0.14)" stroke="rgba(255,255,255,0.28)" />
              <path d="M12 29H28M14 29V20H26V29M17 20V16.5C17 14.8 18.3 13.5 20 13.5C21.7 13.5 23 14.8 23 16.5V20M17.5 29V24.5H22.5V29" stroke="white" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <div>
              <div style={sh.brandName}>SLV-GIS</div>
              <div style={sh.brandSub}>Mysuru Property Portal</div>
            </div>
          </Link>
          <button type="button" className="slv-close-mobile" style={sh.closeMobile} onClick={() => setSidebarOpen(false)} aria-label="Close menu">
            <X size={18} stroke="rgba(255,255,255,0.8)" />
          </button>
        </div>

        <div style={sh.sidebarDivider} />

        <nav style={sh.nav}>
          <div style={sh.navSection}>
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                onClick={() => setSidebarOpen(false)}
                style={({ isActive }) => ({
                  ...sh.navItem,
                  ...(isActive ? sh.navItemActive : {}),
                })}
              >
                <Icon size={17} style={{ flexShrink: 0 }} />
                <span style={sh.navLabel}>{label}</span>
              </NavLink>
            ))}
          </div>
        </nav>

        {/* Subtle Mysuru Context Card */}
        <div style={{ padding: '0 0.75rem 0.6rem' }}>
          <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(255,255,255,0.06)' }}>
            <img
              src="/images/mysuru-palace-hero.jpg"
              alt="Mysuru District heritage"
              style={{ width: '100%', height: 74, objectFit: 'cover', opacity: 0.9 }}
            />
            <div style={{ padding: '6px 10px' }}>
              <div style={{ fontSize: '0.73rem', fontWeight: 700, color: '#FFFFFF' }}>Mysuru District</div>
              <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.68)' }}>Land Intelligence &amp; GIS</div>
            </div>
          </div>
        </div>

        <div style={sh.sidebarFooter}>
          <div style={sh.sidebarDivider} />
          {user ? (
            <div style={sh.userBlock}>
              <div style={sh.avatar}>{initials}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={sh.userName}>{user.full_name}</div>
                <div style={sh.userEmail} title={user.email}>{user.email}</div>
              </div>
            </div>
          ) : null}
          {user ? (
            <button type="button" style={sh.logoutBtn} onClick={handleSignOut}>
              <LogOut size={15} /> Sign Out
            </button>
          ) : (
            <Link to="/login" style={{ ...sh.logoutBtn, textDecoration: 'none', justifyContent: 'center' }}>
              Sign In
            </Link>
          )}
        </div>
      </aside>

      <div style={sh.main}>
        <header style={sh.topbar}>
          <div style={sh.topbarLeft}>
            <button type="button" className="slv-hamburger" style={sh.hamburger} onClick={() => setSidebarOpen(true)} aria-label="Open menu">
              <Menu size={20} />
            </button>
            <div className="desktop-only-nav" style={{ alignItems: 'center', gap: 6, padding: '0.32rem 0.75rem', borderRadius: 999, background: '#F0F4F1', border: '1px solid #E3E8E4', fontSize: '0.76rem', fontWeight: 600, color: '#144D29', flexShrink: 0 }}>
              <MapPin size={13} /> Mysuru District
            </div>
            <form onSubmit={handleSearch} style={sh.searchForm}>
              <Search size={15} style={{ color: '#6E7B73', flexShrink: 0 }} />
              <input
                type="search"
                value={globalSearch}
                onChange={(e) => setGlobalSearch(e.target.value)}
                placeholder="Search locality, village, or ward in Mysuru..."
                style={sh.searchInput}
                aria-label="Global locality search"
              />
            </form>
          </div>
          <div style={sh.topbarRight}>
            <Link to="/student/evaluate" className="btn btn-primary btn-sm">
              New Evaluation
            </Link>
            <Link to="/student/account?tab=help" style={sh.notifBtn} aria-label={`${unreadCount} notifications`}>
              <Bell size={17} />
              {unreadCount > 0 && <span style={sh.badge}>{unreadCount}</span>}
            </Link>
            <Link to="/student/account" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, textDecoration: 'none' }} title="Profile & Settings">
              <div style={sh.topAvatar}>{initials}</div>
              {user?.full_name && (
                <span className="desktop-only-nav" style={{ fontSize: '0.8rem', fontWeight: 600, color: '#141C17' }}>
                  {user.full_name}
                </span>
              )}
            </Link>
          </div>
        </header>

        <main style={sh.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

const SIDEBAR_W = 240;

const sh = {
  shell: { display: 'flex', minHeight: '100vh', background: '#F6F8F6', fontFamily: 'var(--font-sans)' },
  backdrop: { position: 'fixed', inset: 0, background: 'rgba(16, 36, 24, 0.45)', zIndex: 199 },
  sidebar: {
    width: SIDEBAR_W,
    flexShrink: 0,
    background: 'linear-gradient(180deg, #0E3B20 0%, #144D29 100%)',
    display: 'flex',
    flexDirection: 'column',
    position: 'sticky',
    top: 0,
    height: '100vh',
    overflowY: 'auto',
    transition: 'transform 220ms cubic-bezier(0.22,1,0.36,1)',
    zIndex: 200,
  },
  brand: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem 1rem 0.85rem' },
  brandLink: { display: 'flex', alignItems: 'center', gap: '0.6rem', textDecoration: 'none' },
  brandName: { fontSize: '1rem', fontWeight: 800, color: '#FFFFFF', letterSpacing: '-0.02em', lineHeight: 1.1, fontFamily: 'var(--font-display)' },
  brandSub: { fontSize: '0.64rem', color: 'rgba(255,255,255,0.62)', letterSpacing: '0.02em' },
  closeMobile: { background: 'none', border: 'none', cursor: 'pointer', padding: 4 },
  sidebarDivider: { height: 1, background: 'rgba(255,255,255,0.12)', margin: '0 0.9rem' },
  nav: { flex: 1, padding: '0.55rem 0.65rem', display: 'flex', flexDirection: 'column', gap: 2 },
  navSection: { display: 'flex', flexDirection: 'column', gap: '0.18rem' },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.65rem',
    padding: '0.58rem 0.75rem',
    borderRadius: 9,
    color: 'rgba(255,255,255,0.76)',
    textDecoration: 'none',
    fontSize: '0.84rem',
    fontWeight: 500,
    transition: 'background 150ms, color 150ms',
  },
  navItemActive: {
    background: 'rgba(255,255,255,0.16)',
    color: '#FFFFFF',
    fontWeight: 700,
    boxShadow: 'inset 3px 0 0 #8BE0AC',
  },
  navLabel: { flex: 1 },
  sidebarFooter: { padding: '0.5rem 0.75rem 0.85rem', display: 'flex', flexDirection: 'column', gap: '0.55rem' },
  userBlock: { display: 'flex', alignItems: 'center', gap: '0.55rem', padding: '0.35rem 0.25rem' },
  avatar: { width: 32, height: 32, borderRadius: '50%', background: 'rgba(255,255,255,0.18)', color: '#FFFFFF', fontWeight: 700, fontSize: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  userName: { fontSize: '0.8rem', fontWeight: 600, color: '#FFFFFF', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  userEmail: { fontSize: '0.66rem', color: 'rgba(255,255,255,0.6)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  logoutBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    background: 'rgba(255,255,255,0.09)',
    border: '1px solid rgba(255,255,255,0.16)',
    borderRadius: 8,
    padding: '0.48rem 0.75rem',
    color: 'rgba(255,255,255,0.86)',
    fontSize: '0.8rem',
    fontWeight: 600,
    cursor: 'pointer',
    width: '100%',
    fontFamily: 'var(--font-sans)',
  },
  main: { flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' },
  topbar: {
    height: 60,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 1.5rem',
    background: '#FFFFFF',
    borderBottom: '1px solid #E3E8E4',
    position: 'sticky',
    top: 0,
    zIndex: 100,
    gap: '0.75rem',
  },
  topbarLeft: { display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: 0 },
  hamburger: { background: 'none', border: 'none', cursor: 'pointer', color: '#4A5750', display: 'flex', alignItems: 'center', padding: 4, borderRadius: 6 },
  searchForm: { display: 'flex', alignItems: 'center', gap: '0.5rem', background: '#F6F8F6', border: '1px solid #E3E8E4', borderRadius: 9, padding: '0.38rem 0.75rem', maxWidth: 360, flex: 1, minWidth: 0 },
  searchInput: { background: 'none', border: 'none', outline: 'none', fontSize: '0.84rem', color: '#141C17', width: '100%', fontFamily: 'var(--font-sans)' },
  topbarRight: { display: 'flex', alignItems: 'center', gap: '0.65rem', flexShrink: 0 },
  notifBtn: { position: 'relative', background: '#FFFFFF', border: '1px solid #E3E8E4', borderRadius: 8, padding: '0.4rem 0.5rem', display: 'flex', alignItems: 'center', color: '#4A5750', textDecoration: 'none', cursor: 'pointer' },
  badge: { position: 'absolute', top: -4, right: -4, width: 16, height: 16, borderRadius: '50%', background: '#8C2D23', color: '#FFFFFF', fontSize: '0.6rem', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  topAvatar: { width: 32, height: 32, borderRadius: '50%', background: '#144D29', color: '#FFFFFF', fontWeight: 700, fontSize: '0.74rem', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  content: { flex: 1, padding: '1.5rem 1.75rem 3rem', maxWidth: 1340, width: '100%', margin: '0 auto' },
};
