import React, { useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { BrandLogo } from '../components/BrandLogo';

export function PublicLightLayout() {
  const { pathname } = useLocation();
  const navLinks = [
    { to: '/', label: 'Home' },
    { to: '/about', label: 'About' },
    { to: '/help', label: 'Help' },
    { to: '/contact', label: 'Contact' },
  ];

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-canvas)' }}>
      <header className="public-light-header">
        <div className="container public-light-header-inner">
          <Link to="/">
            <BrandLogo />
          </Link>
          <nav style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.88rem', flexWrap: 'wrap' }}>
            {navLinks.map((item) => {
              const active = pathname === item.to;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  style={{
                    color: active ? '#144D29' : 'var(--text-secondary)',
                    fontWeight: active ? 700 : 500,
                    background: active ? '#E7F5EC' : 'transparent',
                    padding: '6px 11px',
                    borderRadius: 8,
                    textDecoration: 'none',
                  }}
                >
                  {item.label}
                </Link>
              );
            })}
            <Link to="/login" className="btn btn-secondary btn-sm">Sign In</Link>
            <Link to="/student/evaluate" className="btn btn-primary btn-sm">Evaluate Property</Link>
          </nav>
        </div>
      </header>

      <main style={{ flex: 1 }}>
        <Outlet />
      </main>

      <footer style={{ borderTop: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg-surface)', paddingBlock: '1.75rem' }}>
        <div className="container" style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '1rem', fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
          <span>Smart Land Valuation &amp; Geospatial Analysis · Mysuru District, Karnataka</span>
          <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap' }}>
            <Link to="/privacy">Privacy Policy</Link>
            <Link to="/terms">Terms of Use</Link>
            <Link to="/disclaimers">Valuation &amp; Document Disclaimers</Link>
            <Link to="/admin/login">Administrator Portal</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

export function PublicAboutPage() {
  return (
    <div className="container public-page-shell" style={{ maxWidth: 880 }}>
      <div style={{ background: '#FFFFFF', border: '1px solid #E3E8E4', borderRadius: 16, padding: '32px', boxShadow: '0 2px 10px rgba(14,59,32,0.04)' }} className="prose-article">
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#144D29', marginBottom: 6 }}>
          Mysuru District Geospatial Platform
        </div>
        <h1>About SLV-GIS Mysuru</h1>
        <p>
          The Smart Land Valuation &amp; Geospatial Analysis System (SLV-GIS) supports buyers, landowners,
          researchers, and civic analysts evaluating residential, commercial, industrial, and agricultural
          parcels across all seven taluks of Mysuru District, Karnataka.
        </p>
        <h2>District-Wide Coverage &amp; Architecture</h2>
        <p>
          Built around curated Mysuru District records evaluated across urban corridors and rural settlements
          (Mysuru, Nanjangud, Hunsur, K.R. Nagar, Periyapatna, T. Narasipura, and H.D. Kote), SLV-GIS combines
          coordinate-aware ML estimation, OpenStreetMap Overpass facility discovery, and Karnataka property
          document parsing into one transparent workflow.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 22 }}>
          <Link to="/student/evaluate" className="btn btn-primary btn-sm">Launch Property Evaluation</Link>
          <Link to="/student/documents" className="btn btn-secondary btn-sm">Open Document Analyzer</Link>
        </div>
      </div>
    </div>
  );
}

export function PublicHelpPage() {
  return (
    <div className="container public-page-shell" style={{ maxWidth: 880 }}>
      <div style={{ background: '#FFFFFF', border: '1px solid #E3E8E4', borderRadius: 16, padding: '32px', boxShadow: '0 2px 10px rgba(14,59,32,0.04)' }} className="prose-article">
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#144D29', marginBottom: 6 }}>
          Citizen &amp; Analyst Guide
        </div>
        <h1>Platform Help &amp; Workflow Guide</h1>
        <h2>1. Property Evaluation &amp; GIS Search</h2>
        <p>
          Use the autocomplete search or click anywhere inside Mysuru District boundaries to resolve canonical locality,
          taluk, and district metadata while preserving any custom parcel label or entered extent.
        </p>
        <h2>2. AI Land Document Analyzer</h2>
        <p>
          Upload Sale Deeds, RTC / Pahani extracts, Mutation Register Extracts, Encumbrance Certificates, or Khata
          records. Text extraction, OCR status (when applicable), classification confidence, and individual field confidence
          are reported separately alongside cross-document comparisons and download-ready A4 PDF reports.
        </p>
      </div>
    </div>
  );
}

export function PublicContactPage() {
  const [sent, setSent] = useState(false);
  return (
    <div className="container public-page-shell" style={{ maxWidth: 680 }}>
      <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#144D29', marginBottom: 6 }}>
        Citizen Inquiries
      </div>
      <h1 style={{ fontSize: 'var(--text-2xl)', color: '#141C17', marginBottom: 8 }}>Contact &amp; Feedback</h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 20 }}>
        Submit questions about Mysuru District valuation methodology or document analyzer feedback.
      </p>
      <div className="surface-card surface-card-body">
        {sent ? (
          <div className="alert alert-ok">Thank you — your message has been recorded locally for review.</div>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); setSent(true); }} className="stack-sm">
            <div>
              <label className="form-label">Name</label>
              <input className="form-control" required placeholder="Your full name" />
            </div>
            <div>
              <label className="form-label">Email</label>
              <input className="form-control" type="email" required placeholder="name@example.com" />
            </div>
            <div>
              <label className="form-label">Message</label>
              <textarea className="form-control" rows={4} required placeholder="Describe your query..." />
            </div>
            <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>Send Feedback</button>
          </form>
        )}
      </div>
    </div>
  );
}

export function PublicLegalPage({ type = 'disclaimers' }) {
  const titles = {
    privacy: 'Privacy Policy',
    terms: 'Terms of Use',
    disclaimers: 'Valuation & Document Analysis Disclaimers',
  };
  return (
    <div className="container public-page-shell" style={{ maxWidth: 880 }}>
      <div style={{ background: '#FFFFFF', border: '1px solid #E3E8E4', borderRadius: 16, padding: '32px', boxShadow: '0 2px 10px rgba(14,59,32,0.04)' }} className="prose-article">
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#144D29', marginBottom: 6 }}>
          Governance &amp; Legal Notice
        </div>
        <h1>{titles[type] || titles.disclaimers}</h1>
        <p>
          This system provides AI-assisted preliminary land valuation estimates and document parsing checks
          for academic and informational decision-support purposes only.
        </p>
        <h2>Non-Legal &amp; Non-Statutory Boundary</h2>
        <p>
          Outputs do not constitute certified title clearance, Sub-Registrar valuation, government land-record
          authentication, or a guarantee of absence of litigation or encumbrance. Always confirm current RTC/MR records
          on Karnataka Bhoomi, Encumbrance Certificates on Kaveri Online Services, and case records via eCourts with a
          qualified property advocate.
        </p>
      </div>
    </div>
  );
}
