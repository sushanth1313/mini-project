import { Info, ShieldAlert, Cpu, Map, Scale, Code } from 'lucide-react';

export default function About() {
  return (
    <div className="page-body fade-in" style={{ maxWidth: 900 }}>
      <div className="page-header">
        <div className="page-header-text">
          <h2>About the Platform</h2>
          <p>Architecture, methodology, and limitations of Smart Land Evaluation.</p>
        </div>
      </div>

      <div className="card" style={{ padding: '40px' }}>
        <h3 style={{ color: 'var(--accent)', marginBottom: 16, fontSize: '24px', fontWeight: '700' }}>Smart Land Evaluation — Mysuru</h3>
        <p style={{ marginBottom: 32, fontSize: '15px', color: 'var(--text-2)', lineHeight: 1.6 }}>
          This platform is a data-driven decision support tool designed to assist in evaluating land and plots in the Mysuru district.
          It combines machine learning for price prediction with geospatial (GIS) analysis to evaluate infrastructure, connectivity, and environmental risk.
        </p>

        <h4 style={{ color: '#141C17', marginBottom: 16, fontSize: '16px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>System Capabilities</h4>
        <div className="grid grid-2" style={{ gap: '20px', marginBottom: '32px' }}>
          
          <div style={{ background: 'var(--surface-2)', padding: '20px', borderRadius: '8px', border: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent)', marginBottom: '8px', fontWeight: '600' }}>
              <Cpu size={18} /> Price Prediction ML
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-3)', margin: 0, lineHeight: 1.5 }}>
              Uses an ExtraTreesRegressor pipeline selected from 5 candidate algorithms on 1,050 Mysuru records (892 training, 158 independent holdout) to provide indicative price-per-sq.ft estimates with SHAP explanations.
            </p>
          </div>

          <div style={{ background: 'var(--surface-2)', padding: '20px', borderRadius: '8px', border: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent)', marginBottom: '8px', fontWeight: '600' }}>
              <Map size={18} /> Geospatial Analysis
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-3)', margin: 0, lineHeight: 1.5 }}>
              Integrates with OpenStreetMap (Overpass API) to dynamically calculate network proximity to critical facilities (hospitals, schools, transit).
            </p>
          </div>

          <div style={{ background: 'var(--surface-2)', padding: '20px', borderRadius: '8px', border: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent)', marginBottom: '8px', fontWeight: '600' }}>
              <Code size={18} /> Document Intelligence
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-3)', margin: 0, lineHeight: 1.5 }}>
              Extracts text from uploaded property documents (PDF, Images) using OCR (Tesseract) and PDF parsing to automatically verify survey numbers against metadata.
            </p>
          </div>

          <div style={{ background: 'var(--surface-2)', padding: '20px', borderRadius: '8px', border: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent)', marginBottom: '8px', fontWeight: '600' }}>
              <Scale size={18} /> Algorithmic Scoring
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-3)', margin: 0, lineHeight: 1.5 }}>
              Uses a transparent, weighted scoring matrix (Location, Infrastructure, Environment, Facilities) rather than a "black-box" AI approach. Admin configurable.
            </p>
          </div>

        </div>

        <div className="alert alert-danger" style={{ display: 'flex', gap: '16px', alignItems: 'flex-start', padding: '24px' }}>
          <ShieldAlert size={24} style={{ flexShrink: 0, marginTop: '2px' }} />
          <div>
            <h4 style={{ margin: 0, marginBottom: '8px', color: 'var(--danger)', fontSize: '15px' }}>Important Disclaimer</h4>
            <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-2)', lineHeight: 1.6 }}>
              This platform is an academic/technical project. <strong>It is NOT a replacement for a certified property valuation, legal title verification, or physical land survey.</strong><br/><br/>
              The data models are trained on small datasets and may not reflect current market realities. GIS data is community-sourced and may contain inaccuracies. Always consult official government portals (Kaveri, Bhoomi) and licensed legal advisors before making real estate decisions.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
