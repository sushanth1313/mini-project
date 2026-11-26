import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
  Lock,
  Mail,
  MapPin,
  ShieldCheck,
  UserCheck,
  UserPlus,
} from 'lucide-react';
import { BrandLogo } from '../components/BrandLogo';
import { API_BASE_URL } from '../config/api';

const BASE_URL = API_BASE_URL;
const TALUKS = ['Mysuru', 'Nanjangud', 'Hunsur', 'K.R. Nagar', 'Periyapatna', 'T. Narasipura', 'H.D. Kote'];

export default function Login() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [mode, setMode] = useState(searchParams.get('mode') === 'register' ? 'register' : 'login');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState(() => localStorage.getItem('slv_remember_email') || '');
  const [password, setPassword] = useState('');
  const [preferredTaluk, setPreferredTaluk] = useState('Mysuru');
  const [showPass, setShowPass] = useState(false);
  const [rememberMe, setRememberMe] = useState(Boolean(localStorage.getItem('slv_remember_email')));
  const [showForgotHelp, setShowForgotHelp] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (searchParams.get('mode') === 'register') {
      setMode('register');
    }
  }, [searchParams]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!email.trim() || !password) {
      setError('Please enter your email address and password.');
      return;
    }
    if (mode === 'register' && !fullName.trim()) {
      setError('Please enter your full name.');
      return;
    }
    setLoading(true);
    try {
      if (mode === 'register') {
        const res = await axios.post(`${BASE_URL}/auth/register`, {
          full_name: fullName.trim(),
          email: email.trim(),
          password,
          preferred_taluk: preferredTaluk,
        });
        if (res.data?.token) localStorage.setItem('user_access_token', res.data.token);
        localStorage.setItem('user_profile', JSON.stringify(res.data.user));
        localStorage.setItem('user_role', res.data.role || 'user');
        navigate('/student');
      } else {
        const res = await axios.post(`${BASE_URL}/auth/login`, {
          email: email.trim(),
          password,
        });
        if (rememberMe) localStorage.setItem('slv_remember_email', email.trim());
        else localStorage.removeItem('slv_remember_email');
        if (res.data?.token) localStorage.setItem('user_access_token', res.data.token);
        localStorage.setItem('user_profile', JSON.stringify(res.data.user));
        localStorage.setItem('user_role', res.data.role || 'user');
        navigate('/student');
      }
    } catch (err) {
      setError(
        err?.response?.data?.error ||
          'Authentication failed. Administrators must sign in at the protected Admin Portal.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={pageStyle}>
      {/* Subtle Mysuru architectural wash + geometric grid */}
      <div style={bgLayerStyle} aria-hidden="true" />
      <div style={bgTintStyle} aria-hidden="true" />

      {/* Top clean navigation bar */}
      <header style={headerStyle}>
        <Link to="/" style={{ textDecoration: 'none' }}>
          <BrandLogo />
        </Link>
        <nav style={{ display: 'flex', alignItems: 'center', gap: '1.15rem', fontSize: '0.84rem', flexWrap: 'wrap' }}>
          <Link to="/" style={{ color: '#4A5750', fontWeight: 500, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <ArrowLeft size={14} /> Home
          </Link>
          <Link to="/about" style={{ color: '#4A5750', fontWeight: 500 }}>About</Link>
          <Link to="/help" style={{ color: '#4A5750', fontWeight: 500 }}>Help</Link>
          <Link
            to="/admin/login"
            style={{
              color: '#144D29',
              fontWeight: 600,
              background: '#E7F5EC',
              border: '1px solid #BCE0C8',
              padding: '0.38rem 0.85rem',
              borderRadius: 999,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
            }}
          >
            <ShieldCheck size={14} /> Admin Login
          </Link>
        </nav>
      </header>

      {/* Horizontally & Vertically Centered Login Card */}
      <main style={centerStageStyle}>
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '0.9rem' }}>
            <BrandLogo />
          </div>

          {/* Login / Register Mode Switcher */}
          <div style={tabContainerStyle}>
            <button
              type="button"
              onClick={() => { setMode('login'); setError(''); setShowForgotHelp(false); }}
              style={mode === 'login' ? tabActiveStyle : tabInactiveStyle}
            >
              <UserCheck size={15} /> Sign In
            </button>
            <button
              type="button"
              onClick={() => { setMode('register'); setError(''); setShowForgotHelp(false); }}
              style={mode === 'register' ? tabActiveStyle : tabInactiveStyle}
            >
              <UserPlus size={15} /> Register
            </button>
          </div>

          <div style={{ textAlign: 'center', marginBottom: '1.25rem' }}>
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.45rem', fontWeight: 700, color: '#141C17', margin: 0 }}>
              {mode === 'login' ? 'Welcome Back' : 'Create Your Account'}
            </h1>
            <p style={{ fontSize: '0.82rem', color: '#4A5750', marginTop: 4 }}>
              {mode === 'login'
                ? 'Sign in to access Mysuru property valuations, GIS boundaries & document scrutiny'
                : 'Register for citizen & analyst access across Mysuru District'}
            </p>
          </div>

          {error && (
            <div className="alert alert-danger" style={{ fontSize: '0.8rem', marginBottom: '1rem' }}>
              <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>{error}</span>
            </div>
          )}

          {showForgotHelp && (
            <div className="alert alert-info" style={{ fontSize: '0.78rem', marginBottom: '1rem' }}>
              <span>
                Need a password reset? Sign in later or submit a request via the <Link to="/contact" style={{ fontWeight: 700, textDecoration: 'underline' }}>Contact &amp; Help</Link> page so an administrator can assist.
              </span>
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
            {mode === 'register' && (
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">Full Name</label>
                <div style={inputWrapStyle}>
                  <UserCheck size={15} style={inputIconStyle} />
                  <input
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Enter your full name"
                    className="form-control"
                    style={{ paddingLeft: '2.35rem' }}
                  />
                </div>
              </div>
            )}

            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">User ID / Email Address</label>
              <div style={inputWrapStyle}>
                <Mail size={15} style={inputIconStyle} />
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
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
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === 'register' ? 'Create a password (min 6 chars)' : 'Enter your password'}
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

            {mode === 'register' && (
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">Preferred Taluk</label>
                <div style={inputWrapStyle}>
                  <MapPin size={15} style={inputIconStyle} />
                  <select
                    value={preferredTaluk}
                    onChange={(e) => setPreferredTaluk(e.target.value)}
                    className="form-control"
                    style={{ paddingLeft: '2.35rem' }}
                  >
                    {TALUKS.map((t) => (
                      <option key={t} value={t}>{t} Taluk</option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {mode === 'login' && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#4A5750', cursor: 'pointer', fontWeight: 500 }}>
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    style={{ accentColor: '#144D29' }}
                  />
                  Remember me
                </label>
                <button
                  type="button"
                  onClick={() => setShowForgotHelp((v) => !v)}
                  style={{ background: 'none', border: 'none', color: '#144D29', fontWeight: 600, fontSize: '0.8rem', cursor: 'pointer', padding: 0 }}
                >
                  Forgot password?
                </button>
              </div>
            )}

            <button type="submit" disabled={loading} className="btn btn-primary btn-full" style={{ paddingBlock: '0.72rem', fontSize: '0.9rem' }}>
              {loading ? 'Authenticating...' : (
                <>
                  <span>{mode === 'login' ? 'Sign In' : 'Create Account'}</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>

          <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid #E3E8E4', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, fontSize: '0.76rem', color: '#6E7B73' }}>
            <span>Mysuru District Geospatial Portal</span>
            <Link to="/admin/login" style={{ color: '#144D29', fontWeight: 600 }}>Administrator Sign In →</Link>
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
  opacity: 0.14,
  pointerEvents: 'none',
};

const bgTintStyle = {
  position: 'absolute',
  inset: 0,
  background: 'radial-gradient(circle at 50% 45%, rgba(255,255,255,0.65) 0%, rgba(246,248,246,0.92) 72%)',
  pointerEvents: 'none',
};

const headerStyle = {
  position: 'relative',
  zIndex: 2,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '0.85rem 1.75rem',
  background: 'rgba(255,255,255,0.88)',
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

const tabContainerStyle = {
  display: 'flex',
  gap: 6,
  padding: 4,
  background: '#F0F4F1',
  border: '1px solid #E3E8E4',
  borderRadius: 10,
  marginBottom: '1.15rem',
};

const tabActiveStyle = {
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 6,
  padding: '0.5rem 0.75rem',
  borderRadius: 8,
  border: 'none',
  background: '#144D29',
  color: '#FFFFFF',
  fontWeight: 600,
  fontSize: '0.83rem',
  cursor: 'pointer',
};

const tabInactiveStyle = {
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 6,
  padding: '0.5rem 0.75rem',
  borderRadius: 8,
  border: 'none',
  background: 'transparent',
  color: '#4A5750',
  fontWeight: 500,
  fontSize: '0.83rem',
  cursor: 'pointer',
};

const inputWrapStyle = { position: 'relative', display: 'flex', alignItems: 'center' };
const inputIconStyle = { position: 'absolute', left: '0.75rem', color: '#6E7B73', pointerEvents: 'none' };
const eyeBtnStyle = { position: 'absolute', right: '0.65rem', background: 'none', border: 'none', color: '#6E7B73', cursor: 'pointer', padding: 4, display: 'flex', alignItems: 'center' };
