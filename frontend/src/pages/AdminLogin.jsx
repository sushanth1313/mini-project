import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowLeft, Eye, EyeOff, KeyRound, Lock, ShieldCheck } from 'lucide-react';
import { useAdminAuth } from '../context/AdminAuthContext';
import { BrandLogo } from '../components/BrandLogo';

export default function AdminLogin() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { login } = useAdminAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const destination = location.state?.from || '/admin/dashboard';

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    if (!username.trim() || !password) {
      setError('Enter both Admin ID / Username and Password.');
      return;
    }
    setLoading(true);
    try {
      await login(username.trim(), password);
      navigate(destination, { replace: true });
    } catch (err) {
      setError(
        err?.response?.data?.error ||
          err.message ||
          'Administrator authentication failed. Verify Admin ID and password.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={pageStyle}>
      <div style={bgLayerStyle} aria-hidden="true" />
      <div style={bgTintStyle} aria-hidden="true" />

      <header style={headerStyle}>
        <Link to="/" style={{ textDecoration: 'none' }}>
          <BrandLogo />
        </Link>
        <nav style={{ display: 'flex', alignItems: 'center', gap: '1.15rem', fontSize: '0.84rem', flexWrap: 'wrap' }}>
          <Link to="/" style={{ color: '#4A5750', fontWeight: 500, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <ArrowLeft size={14} /> Public Site
          </Link>
          <Link
            to="/login"
            style={{
              color: '#144D29',
              fontWeight: 600,
              background: '#E7F5EC',
              border: '1px solid #BCE0C8',
              padding: '0.38rem 0.85rem',
              borderRadius: 999,
            }}
          >
            Citizen Login
          </Link>
        </nav>
      </header>

      {/* Horizontally & Vertically Centered Admin Login Card */}
      <main style={centerStageStyle}>
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '0.9rem' }}>
            <BrandLogo />
          </div>

          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '0.75rem' }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: '#E7F5EC',
                border: '1px solid #BCE0C8',
                color: '#144D29',
                borderRadius: 999,
                padding: '3px 11px',
                fontSize: '0.72rem',
                fontWeight: 700,
              }}
            >
              <ShieldCheck size={13} /> Restricted Governance Console
            </span>
          </div>

          <div style={{ textAlign: 'center', marginBottom: '1.25rem' }}>
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.45rem', fontWeight: 700, color: '#141C17', margin: 0 }}>
              Administrator Sign In
            </h1>
            <p style={{ fontSize: '0.82rem', color: '#4A5750', marginTop: 4 }}>
              Authorized governance access for SLV-GIS Mysuru platform controls
            </p>
          </div>

          {error && (
            <div className="alert alert-danger" style={{ fontSize: '0.8rem', marginBottom: '1rem' }}>
              <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Admin ID / Username</label>
              <div style={inputWrapStyle}>
                <KeyRound size={15} style={inputIconStyle} />
                <input
                  type="text"
                  required
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter Admin ID or username"
                  className="form-control"
                  style={{ paddingLeft: '2.35rem' }}
                />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Password</label>
              <div style={inputWrapStyle}>
                <Lock size={15} style={inputIconStyle} />
                <input
                  type={showPass ? 'text' : 'password'}
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter administrator password"
                  className="form-control"
                  style={{ paddingLeft: '2.35rem', paddingRight: '2.5rem' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPass((v) => !v)}
                  style={eyeBtnStyle}
                  aria-label={showPass ? 'Hide password' : 'Show password'}
                >
                  {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <div
              style={{
                padding: '0.6rem 0.75rem',
                borderRadius: 8,
                background: '#F6F8F6',
                border: '1px solid #E3E8E4',
                fontSize: '0.73rem',
                color: '#4A5750',
                lineHeight: 1.45,
              }}
            >
              Security notice: Single active Super Admin governance applies. Unauthorized access attempts and configuration changes are recorded in the immutable audit log.
            </div>

            <button type="submit" disabled={loading} className="btn btn-primary btn-full" style={{ paddingBlock: '0.72rem', fontSize: '0.9rem' }}>
              <ShieldCheck size={16} />
              <span>{loading ? 'Verifying Credentials...' : 'Sign In to Admin Console'}</span>
            </button>
          </form>

          <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid #E3E8E4', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, fontSize: '0.76rem', color: '#6E7B73' }}>
            <Link to="/login" style={{ color: '#144D29', fontWeight: 600 }}>← Citizen Login Portal</Link>
            <Link to="/" style={{ color: '#4A5750' }}>Return Home</Link>
          </div>
        </div>
      </main>
    </div>
  );
}

const pageStyle = {
  position: 'relative',
  minHeight: '100vh',
  display: 'flex',
  flexDirection: 'column',
  backgroundColor: '#F6F8F6',
  fontFamily: 'var(--font-sans)',
  overflow: 'hidden',
};

const bgLayerStyle = {
  position: 'absolute',
  inset: 0,
  backgroundImage: "url('/images/mysuru-palace-hero.jpg')",
  backgroundSize: 'cover',
  backgroundPosition: 'center',
  opacity: 0.12,
  pointerEvents: 'none',
};

const bgTintStyle = {
  position: 'absolute',
  inset: 0,
  background: 'radial-gradient(circle at 50% 45%, rgba(255,255,255,0.68) 0%, rgba(246,248,246,0.94) 72%)',
  pointerEvents: 'none',
};

const headerStyle = {
  position: 'relative',
  zIndex: 2,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '0.85rem 1.75rem',
  background: 'rgba(255,255,255,0.9)',
  backdropFilter: 'blur(8px)',
  borderBottom: '1px solid #E3E8E4',
  flexWrap: 'wrap',
  gap: '0.75rem',
};

const centerStageStyle = {
  position: 'relative',
  zIndex: 2,
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '2rem 1rem',
};

const cardStyle = {
  width: '100%',
  maxWidth: 440,
  background: '#FFFFFF',
  border: '1px solid #D2DBD4',
  borderRadius: 16,
  boxShadow: '0 16px 40px rgba(16, 36, 24, 0.09)',
  padding: '2rem',
};

const inputWrapStyle = { position: 'relative', display: 'flex', alignItems: 'center' };
const inputIconStyle = { position: 'absolute', left: '0.75rem', color: '#6E7B73', pointerEvents: 'none' };
const eyeBtnStyle = { position: 'absolute', right: '0.65rem', background: 'none', border: 'none', color: '#6E7B73', cursor: 'pointer', padding: 4, display: 'flex', alignItems: 'center' };
