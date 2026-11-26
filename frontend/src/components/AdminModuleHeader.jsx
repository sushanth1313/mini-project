import React from 'react';
import { Info } from 'lucide-react';

/**
 * Shared plain-language guidance header for every RBAC Admin module.
 */
export default function AdminModuleHeader({ whatItShows, adminAction, consequence }) {
  return (
    <div
      className="surface-card"
      style={{
        padding: '0.9rem 1.15rem',
        backgroundColor: 'var(--bg-sage-tint)',
        borderColor: '#CBE3D1',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem',
        fontSize: '0.8rem',
      }}
    >
      <Info size={17} color="var(--brand-800)" style={{ flexShrink: 0, marginTop: 2 }} />
      <div className="grid-3" style={{ flex: 1, gap: '0.75rem' }}>
        <div>
          <span style={{ display: 'block', fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--brand-800)' }}>
            What This Monitors
          </span>
          <span style={{ color: 'var(--text-primary)' }}>{whatItShows}</span>
        </div>
        <div>
          <span style={{ display: 'block', fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--brand-800)' }}>
            Operator Action
          </span>
          <span style={{ color: 'var(--text-secondary)' }}>{adminAction}</span>
        </div>
        <div>
          <span style={{ display: 'block', fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--brand-800)' }}>
            Impact &amp; Safety
          </span>
          <span style={{ color: 'var(--text-secondary)' }}>{consequence}</span>
        </div>
      </div>
    </div>
  );
}
