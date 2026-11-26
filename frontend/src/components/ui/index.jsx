import React from 'react';
import { AlertCircle, CheckCircle2, Info, Loader2, X } from 'lucide-react';

export function StatCard({ label, value, sub, icon: Icon, tone = 'green', onClick }) {
  const tones = {
    green: { bg: '#E7F5EC', fg: '#144D29', border: '#BCE0C8' },
    amber: { bg: '#FEF6E6', fg: '#85520E', border: '#EDD49F' },
    blue:  { bg: '#ECF4FC', fg: '#1B4D7A', border: '#C3DDF5' },
    red:   { bg: '#FDEEEC', fg: '#8C2D23', border: '#ECC2BC' },
  };
  const t = tones[tone] || tones.green;
  const isLong = String(value ?? '').length > 14;

  return (
    <div
      onClick={onClick}
      style={{
        background: '#FFFFFF',
        border: '1px solid #E3E8E4',
        borderRadius: 12,
        padding: '1rem 1.15rem',
        boxShadow: '0 1px 4px rgba(16, 36, 24, 0.04)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        gap: '0.5rem',
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
        <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#4A5750' }}>{label}</span>
        {Icon && (
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: t.bg,
              border: `1px solid ${t.border}`,
              color: t.fg,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Icon size={16} />
          </div>
        )}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: isLong ? '1.05rem' : '1.55rem',
          fontWeight: 700,
          lineHeight: 1.25,
          color: '#141C17',
          wordBreak: 'break-word',
        }}
      >
        {value ?? '—'}
      </div>
      {sub && (
        <div style={{ fontSize: '0.74rem', color: '#6E7B73', lineHeight: 1.35 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

export function StatusBadge({ status, children }) {
  const s = String(status || children || '').toUpperCase();
  let style = { bg: '#F1F4F2', fg: '#4A5750', border: '#D7DFE0' };
  if (['VERIFIED', 'SUCCESS', 'OPERATIONAL', 'ACTIVE', 'APPROVED', 'HEALTHY', 'MATCHED', 'COMPLETE', 'READY'].some((k) => s.includes(k))) {
    style = { bg: '#E7F5EC', fg: '#14532D', border: '#BCE0C8' };
  } else if (['DISAGREEMENT', 'PARTIAL', 'WARNING', 'REVIEW', 'PENDING', 'DEGRADED', 'SUSPENDED', 'OPEN'].some((k) => s.includes(k))) {
    style = { bg: '#FEF6E6', fg: '#85520E', border: '#EDD49F' };
  } else if (['ERROR', 'FAIL', 'UNAVAILABLE', 'REJECTED', 'CRITICAL', 'REQUIRES_VERIFICATION', 'DEACTIVATED'].some((k) => s.includes(k))) {
    style = { bg: '#FDEEEC', fg: '#8C2D23', border: '#ECC2BC' };
  } else if (['INFO', 'GEOCODED', 'KGIS'].some((k) => s.includes(k))) {
    style = { bg: '#ECF4FC', fg: '#1B4D7A', border: '#C3DDF5' };
  }
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '2px 9px',
        borderRadius: 999,
        fontSize: '0.7rem',
        fontWeight: 700,
        letterSpacing: '0.02em',
        background: style.bg,
        color: style.fg,
        border: `1px solid ${style.border}`,
        whiteSpace: 'nowrap',
      }}
    >
      {children || status}
    </span>
  );
}

export function PageHeader({ eyebrow, title, subtitle, icon: Icon, breadcrumbs, actions }) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        gap: '1rem',
        paddingBottom: '1rem',
        borderBottom: '1px solid #E3E8E4',
        marginBottom: '1.25rem',
      }}
    >
      <div>
        {Array.isArray(breadcrumbs) && breadcrumbs.length > 0 && (
          <div style={{ fontSize: '0.72rem', color: '#6E7B73', marginBottom: 4, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {breadcrumbs.map((b, i) => (
              <span key={i}>
                {i > 0 && <span style={{ marginRight: 6 }}>/</span>}
                <span style={{ fontWeight: i === breadcrumbs.length - 1 ? 600 : 400 }}>{b}</span>
              </span>
            ))}
          </div>
        )}
        {eyebrow && (
          <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#1B6336', marginBottom: 4 }}>
            {eyebrow}
          </div>
        )}
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.45rem', fontWeight: 700, color: '#141C17', display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
          {Icon && <Icon size={21} style={{ color: '#144D29', flexShrink: 0 }} />}
          <span>{title}</span>
        </h1>
        {subtitle && (
          <p style={{ fontSize: '0.84rem', color: '#4A5750', marginTop: 4 }}>{subtitle}</p>
        )}
      </div>
      {actions && <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>{actions}</div>}
    </div>
  );
}

export function SectionCard({ title, subtitle, icon: Icon, badge, actions, children, style = {} }) {
  return (
    <div
      style={{
        background: '#FFFFFF',
        border: '1px solid #E3E8E4',
        borderRadius: 12,
        padding: '1.25rem',
        boxShadow: '0 1px 4px rgba(16, 36, 24, 0.04)',
        ...style,
      }}
    >
      {(title || actions || badge) && (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: '0.75rem',
            flexWrap: 'wrap',
            paddingBottom: '0.85rem',
            marginBottom: '1rem',
            borderBottom: '1px solid #E3E8E4',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
              {Icon && <Icon size={17} style={{ color: '#144D29', flexShrink: 0 }} />}
              <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '0.98rem', fontWeight: 700, color: '#141C17', margin: 0 }}>
                {title}
              </h2>
              {badge}
            </div>
            {subtitle && (
              <p style={{ fontSize: '0.78rem', color: '#6E7B73', marginTop: 3 }}>{subtitle}</p>
            )}
          </div>
          {actions && <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

export function TabBar({ tabs, activeKey, onChange }) {
  return (
    <div
      style={{
        display: 'inline-flex',
        flexWrap: 'wrap',
        gap: '0.35rem',
        padding: '0.3rem',
        background: '#F0F4F1',
        border: '1px solid #E3E8E4',
        borderRadius: 10,
      }}
    >
      {tabs.map((t) => {
        const active = t.key === activeKey;
        const Icon = t.icon;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.45rem 0.85rem',
              borderRadius: 8,
              border: 'none',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              background: active ? '#144D29' : 'transparent',
              color: active ? '#FFFFFF' : '#4A5750',
              transition: 'all 150ms ease',
            }}
          >
            {Icon && <Icon size={14} />}
            <span>{t.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function ConfirmModal({ open, title, detail, confirmLabel = 'Confirm', tone = 'primary', onCancel, onConfirm, loading = false, children }) {
  if (!open) return null;
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1500,
        background: 'rgba(16, 36, 24, 0.45)',
        backdropFilter: 'blur(2px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 460,
          background: '#FFFFFF',
          borderRadius: 14,
          border: '1px solid #D2DBD4',
          boxShadow: '0 20px 50px rgba(16, 36, 24, 0.18)',
          padding: '1.5rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '0.75rem' }}>
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1.08rem', fontWeight: 700, color: '#141C17', margin: 0 }}>{title}</h3>
          <button type="button" onClick={onCancel} style={{ background: 'none', border: 'none', color: '#6E7B73', cursor: 'pointer', padding: 2 }} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        {detail && <p style={{ fontSize: '0.84rem', color: '#4A5750', lineHeight: 1.55, marginBottom: '1rem' }}>{detail}</p>}
        {children}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1.15rem' }}>
          <button type="button" onClick={onCancel} className="btn btn-secondary btn-sm">Cancel</button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`btn btn-sm ${tone === 'danger' ? 'btn-danger' : 'btn-primary'}`}
          >
            {loading ? 'Processing...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function LoadingState({ message = 'Loading data...' }) {
  return (
    <div style={{ padding: '2.5rem 1rem', textAlign: 'center', color: '#4A5750', fontSize: '0.88rem', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.65rem' }}>
      <Loader2 size={24} color="#144D29" style={{ animation: 'spin 1s linear infinite' }} />
      <span>{message}</span>
    </div>
  );
}

export function EmptyState({ icon: Icon = Info, title, message, action }) {
  return (
    <div
      style={{
        padding: '2.25rem 1.25rem',
        textAlign: 'center',
        background: '#F6F8F6',
        border: '1px dashed #D2DBD4',
        borderRadius: 12,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '0.5rem',
      }}
    >
      <Icon size={28} color="#1B6336" />
      {title && <h4 style={{ fontSize: '0.98rem', fontWeight: 700, color: '#141C17', margin: '0.25rem 0 0' }}>{title}</h4>}
      {message && <p style={{ fontSize: '0.82rem', color: '#4A5750', maxWidth: 440 }}>{message}</p>}
      {action && <div style={{ marginTop: '0.5rem' }}>{action}</div>}
    </div>
  );
}

export function FeedbackBanner({ type = 'info', children }) {
  if (!children) return null;
  const styles = {
    error:   { bg: '#FDEEEC', fg: '#8C2D23', border: '#ECC2BC', icon: AlertCircle },
    warning: { bg: '#FEF6E6', fg: '#85520E', border: '#EDD49F', icon: AlertCircle },
    success: { bg: '#E7F5EC', fg: '#14532D', border: '#BCE0C8', icon: CheckCircle2 },
    info:    { bg: '#ECF4FC', fg: '#1B4D7A', border: '#C3DDF5', icon: Info },
  }[type] || { bg: '#ECF4FC', fg: '#1B4D7A', border: '#C3DDF5', icon: Info };
  const Icon = styles.icon;
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.6rem',
        padding: '0.75rem 1rem',
        borderRadius: 10,
        background: styles.bg,
        color: styles.fg,
        border: `1px solid ${styles.border}`,
        fontSize: '0.82rem',
      }}
    >
      <Icon size={16} style={{ flexShrink: 0, marginTop: 2 }} />
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  );
}
