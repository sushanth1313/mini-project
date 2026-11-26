import React from 'react';
import {
  CheckSquare,
  FileSearch,
  FileText,
  Scale,
  ShieldAlert,
  UploadCloud,
} from 'lucide-react';

const NAV_ITEMS = [
  { id: 'summary', label: '7-Step Buyer Summary', icon: ShieldAlert },
  { id: 'uploads', label: 'Upload & Vault', icon: UploadCloud },
  { id: 'technical', label: 'OCR & Field Edits', icon: FileSearch },
  { id: 'ownership', label: 'Cross-Check & Govt Links', icon: Scale },
  { id: 'checklist', label: 'Missing Docs Checklist', icon: CheckSquare },
  { id: 'report', label: 'A4 Due-Diligence PDF', icon: FileText },
];

export default function Sidebar({ activeSection, onSelect, overallAssessment }) {
  return (
    <aside
      style={{
        width: '240px',
        flexShrink: 0,
        background: 'var(--bg-surface)',
        color: 'var(--text-primary)',
        borderRight: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border-subtle)' }}>
        <p style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.12em', color: 'var(--brand-800)', textTransform: 'uppercase' }}>
          Karnataka Due-Diligence
        </p>
        <h2 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '4px', lineHeight: 1.3 }}>
          Document Intelligence
        </h2>
        <p style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
          Mysuru 7-Taluk Scrutiny
        </p>
      </div>

      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-sage-tint)' }}>
        <p style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-tertiary)', fontWeight: 600 }}>
          Preliminary Status
        </p>
        <p style={{ fontSize: '12px', fontWeight: 700, color: 'var(--brand-900)', marginTop: '3px', lineHeight: 1.35 }}>
          {overallAssessment || 'No Documents Analyzed Yet'}
        </p>
      </div>

      <nav style={{ flex: 1, padding: '10px 8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const active = activeSection === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onSelect(id)}
              className={`nav-item ${active ? 'active' : ''}`}
              style={{
                width: '100%',
                border: 'none',
                textAlign: 'left',
                cursor: 'pointer',
              }}
            >
              <Icon size={15} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
            </button>
          );
        })}
      </nav>

      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border-subtle)', fontSize: '11px', color: 'var(--text-tertiary)', lineHeight: 1.45 }}>
        Preliminary decision-support only. Not legal title certification.
      </div>
    </aside>
  );
}
