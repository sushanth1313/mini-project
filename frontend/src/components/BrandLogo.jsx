import React from 'react';

export function BrandLogo({ compact = false }) {
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.6rem' }}>
      <svg width="34" height="34" viewBox="0 0 40 40" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
        <rect width="40" height="40" rx="9" fill="#ECF5EE" stroke="#CBE3D1" />
        <path
          d="M12 29H28M14 29V20H26V29M17 20V16.5C17 14.8 18.3 13.5 20 13.5C21.7 13.5 23 14.8 23 16.5V20M20 10.5V13.5M14 20L12.5 17.5M26 20L27.5 17.5"
          stroke="#144D29"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M17.5 29V24.5H22.5V29"
          stroke="#144D29"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.12 }}>
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 800,
            fontSize: compact ? '0.95rem' : '1.02rem',
            letterSpacing: '-0.02em',
            color: '#144D29',
          }}
        >
          SLV-GIS
        </span>
        <span style={{ fontSize: '0.68rem', fontWeight: 500, color: '#5A6960' }}>
          {compact ? 'Mysuru' : 'Mysuru District'}
        </span>
      </div>
    </div>
  );
}
