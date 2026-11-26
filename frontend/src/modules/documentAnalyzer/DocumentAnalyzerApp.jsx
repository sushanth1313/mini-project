import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  ExternalLink,
  Eye,
  FileSearch,
  FileText,
  Gavel,
  Landmark,
  Lock,
  Pencil,
  Save,
  Scale,
  ShieldAlert,
  Trash2,
  UploadCloud,
} from 'lucide-react';
import {
  FICTIONAL_SAMPLE_ANALYSIS,
  MANDATORY_DISCLAIMER,
  SUPPORTED_DOCUMENT_TYPES,
} from './data/sampleCaseData';
import {
  analyzePropertyDocuments,
  deleteUploadedDocument,
  downloadDocumentAnalysisPdf,
  fetchAnalysisByProperty,
  hasDocumentAnalyzerAuthToken,
  reclassifyDocumentType,
  saveManualCorrections,
} from './api/documentAnalysisApi';

const SEVERITY_STYLE = {
  Critical: { bg: 'rgba(239,68,68,0.14)', border: 'rgba(239,68,68,0.4)', color: '#8C2D23' },
  High: { bg: 'rgba(249,115,22,0.14)', border: 'rgba(249,115,22,0.4)', color: '#85520E' },
  Medium: { bg: 'rgba(245,158,11,0.14)', border: 'rgba(245,158,11,0.4)', color: '#85520E' },
  Low: { bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.35)', color: '#14532D' },
  Unverified: { bg: 'rgba(148,163,184,0.12)', border: 'rgba(148,163,184,0.3)', color: '#4A5750' },
};

function SeverityPill({ severity }) {
  const st = SEVERITY_STYLE[severity] || SEVERITY_STYLE.Unverified;
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 9px',
        borderRadius: '999px',
        fontSize: '11px',
        fontWeight: 700,
        background: st.bg,
        border: `1px solid ${st.border}`,
        color: st.color,
      }}
    >
      {severity || 'Unverified'}
    </span>
  );
}

function AccordionCard({ title, subtitle, defaultOpen = false, badge = null, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden', border: '1px solid var(--border)' }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          width: '100%',
          background: 'var(--surface-2)',
          border: 'none',
          padding: '14px 18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          cursor: 'pointer',
          textAlign: 'left',
          color: 'var(--text)',
        }}
      >
        <div>
          <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            {title}
            {badge}
          </div>
          {subtitle && <div style={{ fontSize: '12px', color: 'var(--text-3)', marginTop: '2px' }}>{subtitle}</div>}
        </div>
        {open ? <ChevronUp size={18} color="var(--accent)" /> : <ChevronDown size={18} color="var(--text-3)" />}
      </button>
      {open && <div style={{ padding: '18px', borderTop: '1px solid var(--border)' }}>{children}</div>}
    </div>
  );
}

export default function App({ initialPropertyInfo = null, onAnalysisComplete = null }) {
  const [viewMode, setViewMode] = useState('buyer'); // 'buyer' (7-step) | 'technical' (OCR/metadata/edits)
  const [analysis, setAnalysis] = useState(null);
  const [isDemoPreview, setIsDemoPreview] = useState(false);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [authRequired, setAuthRequired] = useState(!hasDocumentAnalyzerAuthToken());
  const [propertyForm, setPropertyForm] = useState(
    initialPropertyInfo || {
      property_id: '',
      property_label: 'Selected Mysuru Property',
      district: 'Mysuru',
      taluk: 'Mysuru',
      locality: '',
      village: '',
      latitude: '',
      longitude: '',
      survey_number: '',
      hissa_number: '',
      plot_number: '',
      property_type: 'residential_plot',
      land_area: '',
    }
  );

  const [queuedFiles, setQueuedFiles] = useState([]);
  const [externalAiConsent, setExternalAiConsent] = useState(false);
  const [manualCases, setManualCases] = useState([]);
  const [newCase, setNewCase] = useState({
    court_name: '',
    case_number: '',
    parties: '',
    survey_number: '',
    nature_of_dispute: '',
  });
  const [isProcessing, setIsProcessing] = useState(false);
  const [pdfDownloading, setPdfDownloading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [editingField, setEditingField] = useState(null);
  const [editValue, setEditValue] = useState('');

  useEffect(() => {
    setAuthRequired(!hasDocumentAnalyzerAuthToken());
  }, []);

  useEffect(() => {
    if (!initialPropertyInfo) return;
    setPropertyForm((prev) => ({
      ...prev,
      ...initialPropertyInfo,
    }));

    const propId = initialPropertyInfo.property_id;
    if (!propId || Number.isNaN(Number(propId))) return;

    let cancelled = false;
    setLoadingAnalysis(true);
    setErrorMsg('');
    fetchAnalysisByProperty(propId)
      .then((res) => {
        if (cancelled) return;
        setAuthRequired(false);
        if (res?.property_info) {
          setPropertyForm((prev) => ({ ...prev, ...res.property_info }));
        }
        // Strictly keep null when property has 0 analyzed documents — never auto-show Hootagalli sample!
        if (res?.latest_analysis) {
          setAnalysis(res.latest_analysis);
          setIsDemoPreview(false);
        } else {
          setAnalysis(null);
          setIsDemoPreview(false);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        const status = err?.response?.status;
        if (status === 401) {
          localStorage.removeItem('user_access_token');
          localStorage.removeItem('user_profile');
          localStorage.removeItem('user_role');
          setAuthRequired(true);
        } else if (status === 403 && !hasDocumentAnalyzerAuthToken()) {
          setAuthRequired(true);
        } else if (status === 403) {
          setErrorMsg(err?.response?.data?.error || 'Your account role does not have permission to view this document analysis.');
        }
        setAnalysis(null);
        setIsDemoPreview(false);
      })
      .finally(() => {
        if (!cancelled) setLoadingAnalysis(false);
      });

    return () => {
      cancelled = true;
    };
  }, [initialPropertyInfo?.property_id, initialPropertyInfo?.locality, initialPropertyInfo?.taluk, initialPropertyInfo?.land_area]);

  const handleFileDrop = (event) => {
    event.preventDefault();
    const dropped = Array.from(event.dataTransfer?.files || event.target.files || []);
    const valid = dropped.filter((f) => /\.(pdf|jpg|jpeg|png)$/i.test(f.name) && f.size <= 25 * 1024 * 1024);
    if (valid.length !== dropped.length) {
      setErrorMsg('Some files were rejected. Only PDF, JPG, JPEG, PNG under 25 MB are accepted (executables blocked).');
    } else {
      setErrorMsg('');
    }
    setQueuedFiles((prev) => [...prev, ...valid]);
  };

  const handleRunAnalysis = async () => {
    if (!queuedFiles.length) {
      setErrorMsg('Upload at least one land document (PDF/JPG/PNG) before running analysis.');
      return;
    }
    setIsProcessing(true);
    setErrorMsg('');
    try {
      const result = await analyzePropertyDocuments({
        propertyInfo: propertyForm,
        files: queuedFiles,
        manualCases,
        externalAiConsent,
      });
      setAnalysis(result);
      setIsDemoPreview(false);
      setAuthRequired(false);
      setQueuedFiles([]);
      setViewMode('buyer');
      if (typeof onAnalysisComplete === 'function') {
        onAnalysisComplete(result);
      }
    } catch (err) {
      if (err?.response?.status === 401) {
        localStorage.removeItem('user_access_token');
        localStorage.removeItem('user_profile');
        localStorage.removeItem('user_role');
        setAuthRequired(true);
      }
      setErrorMsg(
        err?.response?.data?.error ||
          'Document analysis failed. Ensure you are signed in and uploaded valid PDF/image files.'
      );
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSaveCorrection = async (documentId, fieldName) => {
    if (!analysis || isDemoPreview) return;
    try {
      const updated = await saveManualCorrections(analysis.analysis_id, documentId, {
        [fieldName]: editValue,
      });
      setAnalysis(updated);
      setEditingField(null);
      if (typeof onAnalysisComplete === 'function') {
        onAnalysisComplete(updated);
      }
    } catch (err) {
      setErrorMsg(err?.response?.data?.error || 'Could not save manual field correction.');
    }
  };

  const handleDeleteDoc = async (documentId) => {
    if (!analysis || isDemoPreview) return;
    try {
      const updated = await deleteUploadedDocument(analysis.analysis_id, documentId);
      setAnalysis(updated);
      if (typeof onAnalysisComplete === 'function') {
        onAnalysisComplete(updated);
      }
    } catch (err) {
      setErrorMsg(err?.response?.data?.error || 'Could not remove uploaded document.');
    }
  };

  const handleReclassifyDocument = async (documentId, newType) => {
    if (!analysis || isDemoPreview || !newType) return;
    setErrorMsg('');
    try {
      const updated = await reclassifyDocumentType(analysis.analysis_id, documentId, newType);
      setAnalysis(updated);
      if (typeof onAnalysisComplete === 'function') {
        onAnalysisComplete(updated);
      }
    } catch (err) {
      setErrorMsg(err?.response?.data?.error || 'Could not update document classification.');
    }
  };

  const handleExportPdf = async () => {
    if (!analysis?.analysis_id || isDemoPreview) return;
    setPdfDownloading(true);
    setErrorMsg('');
    try {
      await downloadDocumentAnalysisPdf(analysis.analysis_id);
    } catch (err) {
      setErrorMsg(err?.response?.data?.error || 'Failed to download PDF report. Verify session sign-in.');
    } finally {
      setPdfDownloading(false);
    }
  };

  const docs = analysis?.documents || [];
  const procSummary = analysis?.processing_summary || {};
  const compObj = analysis?.cross_document_comparisons || {};
  const compSum = compObj.summary || {};
  const discrepancyRows = compObj.discrepancy_table || [];
  const mismatchCount = compSum.confirmed_mismatches ?? discrepancyRows.filter((r) => r.result === 'MISMATCH' || r.result === 'Mismatch').length;
  const incompleteCount = compSum.incomplete_comparisons ?? discrepancyRows.filter((r) => r.result === 'UNABLE TO COMPARE' || r.result === 'MISSING INFORMATION').length;
  const riskFindings = analysis?.risk_assessment?.findings || [];
  const checklistItems = analysis?.missing_documents?.items || [];
  const missingDocsOnly = checklistItems.filter((item) => item.status === 'Not provided' || item.status === 'Provided — processing failed' || item.status === 'Verification required');
  const activeCounts = analysis?.risk_assessment?.severity_counts || { Critical: 0, High: 0, Medium: 0, Low: 0 };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', color: 'var(--text)' }}>
      {/* Top Property Binding & Mode Switcher Header */}
      <div
        className="card"
        style={{
          padding: '20px 24px',
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '16px',
          background: 'linear-gradient(135deg, var(--bg-surface), var(--bg-sage-tint))',
          border: '1px solid var(--accent-border)',
        }}
      >
        <div>
          <div style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.12em', color: 'var(--accent)', textTransform: 'uppercase' }}>
            AI Land Document Scrutiny · {propertyForm.taluk || 'Mysuru'} Taluk
          </div>
          <h3 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '4px' }}>
            {propertyForm.property_label || propertyForm.locality || 'Selected Property'}
          </h3>
          <div style={{ fontSize: '12px', color: 'var(--text-3)', marginTop: '3px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <span>Locality: <strong style={{ color: 'var(--text-2)' }}>{propertyForm.locality || 'Not specified'}</strong></span>
            <span>·</span>
            <span>Area: <strong style={{ color: 'var(--text-2)' }}>{propertyForm.land_area || '—'}</strong></span>
            {analysis && !isDemoPreview && (
              <>
                <span>·</span>
                <span>Analyzed Docs: <strong style={{ color: 'var(--accent)' }}>{docs.length}</strong></span>
              </>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
          {analysis && (
            <>
              <button
                type="button"
                className={viewMode === 'buyer' ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm'}
                onClick={() => setViewMode('buyer')}
              >
                7-Step Buyer Summary
              </button>
              <button
                type="button"
                className={viewMode === 'technical' ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm'}
                onClick={() => setViewMode('technical')}
              >
                <FileSearch size={14} /> Technical OCR &amp; Field Edits
              </button>
            </>
          )}
          {!isDemoPreview && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setAnalysis(FICTIONAL_SAMPLE_ANALYSIS);
                setIsDemoPreview(true);
                setViewMode('buyer');
              }}
            >
              <Eye size={14} /> Preview Fictional Sample
            </button>
          )}
        </div>
      </div>

      {/* Fictional Demo Warning Banner — ONLY when explicitly opted in */}
      {isDemoPreview && (
        <div
          className="alert alert-warn"
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertTriangle size={18} />
            <div style={{ fontSize: '13px' }}>
              <strong>FICTIONAL SAMPLE PREVIEW ACTIVE (Hootagalli Demo):</strong> These 6 documents are synthetic training examples — NOT uploaded records for <strong>{propertyForm.property_label}</strong>.
            </div>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setIsDemoPreview(false);
              setAnalysis(null);
            }}
          >
            Exit Demo Preview
          </button>
        </div>
      )}

      {/* Backend Authentication Guard Banner */}
      {authRequired && (
        <div
          className="alert alert-warn"
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13px' }}>
            <Lock size={17} />
            <span>
              <strong>Sign In Required for Private Document OCR:</strong> Document analysis APIs enforce backend Bearer authentication so private deeds are isolated per authorized session.
            </span>
          </div>
          <Link to="/login" className="btn btn-primary btn-sm">
            Sign In / Register
          </Link>
        </div>
      )}

      {errorMsg && (
        <div className="alert alert-danger" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}>
          <AlertTriangle size={16} />
          <span>{errorMsg}</span>
        </div>
      )}

      {loadingAnalysis && (
        <div className="loading-state" style={{ padding: '32px' }}>
          <div className="spinner" />
          Loading property document history...
        </div>
      )}

      {/* REAL PROPERTY EMPTY STATE OR UPLOAD PANEL */}
      {!loadingAnalysis && (
        <div className="card" style={{ border: '1px solid var(--border)', padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
            <div>
              <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
                1. Upload Property Documents ({isDemoPreview ? 'Demo Active — Exit demo before real upload' : `${docs.length} uploaded in analysis`})
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-3)', marginTop: '3px' }}>
                Upload digital PDFs or scans (Sale Deed, RTC/Pahani, EC, Khata, Conversion Order, Layout Approval — up to 25 MB, executables blocked).
              </div>
            </div>
          </div>

          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleFileDrop}
            style={{
              border: '2px dashed var(--accent-border)',
              borderRadius: '10px',
              padding: '24px 16px',
              textAlign: 'center',
              background: 'var(--bg-sage-tint)',
            }}
          >
            <UploadCloud size={28} color="var(--accent)" style={{ margin: '0 auto 8px' }} />
            <p style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Drag &amp; drop Karnataka land documents here
            </p>
            <p style={{ fontSize: '11px', color: 'var(--text-3)', marginTop: '4px' }}>
              Supports {SUPPORTED_DOCUMENT_TYPES.length} Karnataka document classes · Zero fake results generated for empty vaults
            </p>
            <label className="btn btn-primary btn-sm" style={{ marginTop: '12px', cursor: 'pointer', display: 'inline-flex' }}>
              Browse PDF / Images
              <input type="file" multiple accept=".pdf,.jpg,.jpeg,.png" onChange={handleFileDrop} style={{ display: 'none' }} />
            </label>
          </div>

          <label style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', marginTop: '12px', fontSize: '12px', color: 'var(--text-2)' }}>
            <input
              type="checkbox"
              checked={externalAiConsent}
              onChange={(e) => setExternalAiConsent(e.target.checked)}
              style={{ marginTop: '3px' }}
            />
            <span>
              <strong>Optional Third-Party AI Consent:</strong> Keep unchecked for 100% local PyMuPDF OCR &amp; regex/heuristic extraction (recommended for privacy).
            </span>
          </label>

          {queuedFiles.length > 0 && (
            <div style={{ marginTop: '14px', padding: '12px', borderRadius: '8px', background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--accent)', marginBottom: '8px' }}>
                Queued for Analysis ({queuedFiles.length} file{queuedFiles.length > 1 ? 's' : ''}):
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '12px' }}>
                {queuedFiles.map((f, idx) => (
                  <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-2)' }}>
                    <span>{f.name} ({(f.size / 1024).toFixed(1)} KB)</span>
                    <button
                      type="button"
                      onClick={() => setQueuedFiles((prev) => prev.filter((_, i) => i !== idx))}
                      style={{ background: 'none', border: 'none', color: 'var(--status-danger-text)', cursor: 'pointer', fontSize: '12px' }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="btn btn-primary"
                disabled={isProcessing}
                onClick={handleRunAnalysis}
              >
                {isProcessing ? 'Running OCR & Cross-Document Scrutiny...' : 'Run Document Analysis'}
              </button>
            </div>
          )}

          {!analysis && (
            <div style={{ marginTop: '16px', padding: '16px', borderRadius: '8px', background: 'var(--bg-subtle)', border: '1px solid var(--border)', fontSize: '13px', color: 'var(--text-2)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>No documents have been analyzed for this property yet.</strong>
              <p style={{ marginTop: '4px', fontSize: '12px', color: 'var(--text-3)' }}>
                Upload at least one document above (for example, your Sale Deed or RTC/EC) to generate the 7-step buyer summary, cross-document comparison, missing checklist, and A4 PDF report.
              </p>
            </div>
          )}
        </div>
      )}

      {/* VIEW A: 7-STEP PLAIN-LANGUAGE BUYER SUMMARY */}
      {analysis && viewMode === 'buyer' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* KPI Strip */}
          <div className="grid grid-4" style={{ gap: '12px' }}>
            <div className="card" style={{ padding: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-3)', textTransform: 'uppercase' }}>Overall Preliminary Status</div>
              <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--accent)', marginTop: '6px' }}>
                {analysis.overall_assessment}
              </div>
            </div>
            <div className="card" style={{ padding: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-3)', textTransform: 'uppercase' }}>Documents Processed</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '4px' }}>{docs.length}</div>
            </div>
            <div className="card" style={{ padding: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-3)', textTransform: 'uppercase' }}>Critical / High Flags</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: (activeCounts.Critical + activeCounts.High) > 0 ? 'var(--status-danger-text)' : 'var(--ok)', marginTop: '4px' }}>
                {(activeCounts.Critical || 0) + (activeCounts.High || 0)}
              </div>
            </div>
            <div className="card" style={{ padding: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-3)', textTransform: 'uppercase' }}>Docs Needed Before Purchase</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: missingDocsOnly.length > 0 ? 'var(--warn)' : 'var(--ok)', marginTop: '4px' }}>
                {missingDocsOnly.length}
              </div>
            </div>
          </div>

          {/* Processing Summary Strip (Separates OCR vs Classification vs Field Extraction) */}
          <div className="card" style={{ padding: '16px 20px', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--accent)', marginBottom: '10px' }}>
              Processing &amp; Extraction Summary
            </div>
            <div className="grid grid-4" style={{ gap: '10px', fontSize: '12px' }}>
              <div style={{ padding: '10px', borderRadius: '8px', background: 'var(--surface-2)' }}>
                <div style={{ color: 'var(--text-3)' }}>Files / Confirmation</div>
                <strong style={{ color: 'var(--text-primary)' }}>
                  {procSummary.files_received ?? docs.length} received · {procSummary.duplicate_files ?? 0} dup
                </strong>
                <div style={{ fontSize: '11px', color: (procSummary.files_requiring_confirmation || 0) > 0 ? 'var(--warn)' : 'var(--ok)' }}>
                  {procSummary.files_requiring_confirmation || 0} require confirmation
                </div>
              </div>
              <div style={{ padding: '10px', borderRadius: '8px', background: 'var(--surface-2)' }}>
                <div style={{ color: 'var(--text-3)' }}>Text Layer / OCR Status</div>
                <strong style={{ color: 'var(--text-primary)' }}>
                  {procSummary.ocr_performed_on_any_document && procSummary.avg_ocr_confidence != null
                    ? `OCR ${Math.round(procSummary.avg_ocr_confidence * 100)}%`
                    : `Digital PDF ${Math.round((procSummary.text_extraction_quality ?? 0) * 100)}%`}
                </strong>
                <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>
                  {procSummary.ocr_performed_on_any_document ? 'OCR performed' : 'OCR not performed'} · {procSummary.pages_processed ?? docs.reduce((acc, d) => acc + (d.ocr?.page_count || 0), 0)} pg
                </div>
              </div>
              <div style={{ padding: '10px', borderRadius: '8px', background: 'var(--surface-2)' }}>
                <div style={{ color: 'var(--text-3)' }}>Structured Fields Extracted</div>
                <strong style={{ color: (procSummary.fields_extracted || 0) > 0 ? 'var(--ok)' : 'var(--warn)' }}>
                  {procSummary.fields_extracted ?? 0} / {procSummary.total_schema_fields ?? 0} ({Math.round((procSummary.field_extraction_rate ?? 0) * 100)}%)
                </strong>
                <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>
                  Field conf: {Math.round((procSummary.avg_field_extraction_confidence ?? 0) * 100)}% (not legal conf.)
                </div>
              </div>
              <div style={{ padding: '10px', borderRadius: '8px', background: 'var(--surface-2)' }}>
                <div style={{ color: 'var(--text-3)' }}>Comparison Outcomes</div>
                <strong style={{ color: mismatchCount > 0 ? 'var(--status-danger-text)' : 'var(--text-primary)' }}>
                  {procSummary.comparisons_matched ?? 0} match · {mismatchCount} mismatch
                </strong>
                <div style={{ fontSize: '11px', color: 'var(--warn)' }}>
                  {incompleteCount} incomplete (Unable/Missing)
                </div>
              </div>
            </div>
          </div>

          {/* Step 2: Identified Documents & Extracted Key Details */}
          <div className="card" style={{ padding: '20px' }}>
            <h4 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FileText size={16} color="var(--accent)" /> 2. Identified Documents &amp; Extracted Highlights
            </h4>
            <div className="grid grid-2" style={{ gap: '12px' }}>
              {docs.map((doc) => {
                const fields = doc.extraction?.fields || {};
                const owner =
                  fields.owner_names?.effective_value ||
                  fields.buyer_names?.effective_value ||
                  fields.new_owner?.effective_value ||
                  fields.applicant_name?.effective_value ||
                  fields.seller_names?.effective_value ||
                  'Unable to extract';
                const survey = fields.survey_number?.effective_value || 'Unable to extract';
                const area =
                  fields.property_extent?.effective_value ||
                  fields.total_land_extent?.effective_value ||
                  'Unable to extract';
                const extRate = Math.round((doc.extraction?.field_extraction_rate || 0) * 100);
                const needsConf = Boolean(doc.classification?.requires_confirmation);
                return (
                  <div key={doc.document_id} style={{ padding: '14px', borderRadius: '8px', background: 'var(--surface-2)', border: needsConf ? '1px solid rgba(245,158,11,0.5)' : '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                          <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--accent)' }}>{doc.document_type}</span>
                          {needsConf && (
                            <span style={{ fontSize: '10px', fontWeight: 700, padding: '2px 7px', borderRadius: '999px', background: 'rgba(245,158,11,0.16)', color: 'var(--warn)' }}>
                              Document type requires confirmation
                            </span>
                          )}
                          {doc.is_duplicate && (
                            <span style={{ fontSize: '10px', fontWeight: 700, padding: '2px 7px', borderRadius: '999px', background: 'rgba(148,163,184,0.2)', color: '#4A5750' }}>
                              Duplicate File
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-3)', marginTop: '3px' }}>
                          {doc.original_filename} · {doc.ocr?.page_count || 0} pg · {doc.ocr?.ocr_applied ? `OCR ${Math.round((doc.ocr?.ocr_confidence || 0) * 100)}%` : `Digital PDF ${Math.round((doc.ocr?.text_extraction_quality ?? doc.ocr?.average_confidence ?? 0) * 100)}% (No OCR)`} · Classif {Math.round((doc.classification?.confidence || 0) * 100)}% · Fields {doc.extraction?.extracted_count || 0}/{doc.extraction?.total_fields || Object.keys(fields).length} ({extRate}%)
                        </div>
                        {!isDemoPreview && (
                          <div style={{ marginTop: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ fontSize: '11px', color: 'var(--text-3)' }}>Reclassify:</span>
                            <select
                              className="form-control"
                              value={doc.document_type}
                              onChange={(e) => handleReclassifyDocument(doc.document_id, e.target.value)}
                              style={{ padding: '2px 6px', fontSize: '11px', maxWidth: '210px' }}
                            >
                              {SUPPORTED_DOCUMENT_TYPES.map((dt) => (
                                <option key={dt} value={dt}>{dt}</option>
                              ))}
                            </select>
                          </div>
                        )}
                      </div>
                      {!isDemoPreview && (
                        <button
                          type="button"
                          onClick={() => handleDeleteDoc(doc.document_id)}
                          style={{ background: 'none', border: 'none', color: 'var(--status-danger-text)', cursor: 'pointer', fontSize: '11px' }}
                          title="Delete document"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-2)', marginTop: '8px', display: 'grid', gap: '3px' }}>
                      <div>Owner / Party: <strong>{owner}</strong></div>
                      <div>Survey / Ref: <strong>{survey}</strong></div>
                      <div>Extent Mentioned: <strong>{area}</strong></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Step 3: Cross-Document Consistency */}
          <div className="card" style={{ padding: '20px' }}>
            <h4 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Scale size={16} color="var(--accent)" /> 3. Cross-Document Consistency Check
            </h4>
            <p style={{ fontSize: '13px', color: mismatchCount > 0 ? '#85520E' : (compObj.summary?.comparable_checks > 0 ? 'var(--ok)' : 'var(--warn)'), marginBottom: '12px', fontWeight: 600 }}>
              {compObj.comparison_status || (mismatchCount > 0
                ? `${mismatchCount} discrepancy/mismatch item(s) detected across uploaded documents — verify carefully before making any payment.`
                : 'Comparison incomplete — insufficient extracted information.')}
            </p>
            <AccordionCard
              title="View Detailed Field-by-Field Comparison"
              subtitle="Compares Survey No., Owner Name, Village/Taluk, Document Refs, Dates, and Land Extent across papers"
              defaultOpen={mismatchCount > 0 || discrepancyRows.length > 0}
            >
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Document A</th>
                      <th>Document B</th>
                      <th>Result</th>
                      <th>Evidence &amp; Page</th>
                    </tr>
                  </thead>
                  <tbody>
                    {discrepancyRows.map((row, idx) => {
                      const isMatch = row.result === 'MATCH' || row.result === 'Match' || row.result === 'Consistent';
                      const isMismatch = row.result === 'MISMATCH' || row.result === 'Mismatch';
                      return (
                        <tr key={idx}>
                          <td style={{ fontWeight: 600 }}>{row.field}</td>
                          <td style={{ fontSize: '12px' }}>{row.document_a}: <strong>{row.document_a_value}</strong></td>
                          <td style={{ fontSize: '12px' }}>{row.document_b}: <strong>{row.document_b_value}</strong></td>
                          <td>
                            <span style={{ color: isMatch ? 'var(--ok)' : isMismatch ? '#8C2D23' : 'var(--warn)', fontWeight: 700, fontSize: '12px' }}>
                              {row.result}
                            </span>
                          </td>
                          <td style={{ fontSize: '12px', color: 'var(--text-3)' }}>
                            {row.note} (p.{row.document_a_page || '-'} / p.{row.document_b_page || '-'})
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </AccordionCard>
          </div>

          {/* Step 4: Plain-Language Risk Warnings */}
          <div className="card" style={{ padding: '20px' }}>
            <h4 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ShieldAlert size={16} color="var(--accent)" /> 4. Key Risk Warnings &amp; Next Actions
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {riskFindings.map((f, idx) => (
                <div key={idx} style={{ padding: '14px', borderRadius: '8px', background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <SeverityPill severity={f.severity} />
                      <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{f.risk_category}</strong>
                    </div>
                    <span style={{ fontSize: '11px', color: 'var(--text-3)' }}>
                      {f.confirmation_status} · Pages: {(f.page_numbers || []).join(', ') || 'N/A'}
                    </span>
                  </div>
                  <p style={{ fontSize: '13px', color: 'var(--text-2)', marginTop: '6px' }}>{f.description}</p>
                  <div style={{ fontSize: '12px', color: 'var(--text-3)', marginTop: '6px' }}>
                    <strong style={{ color: 'var(--accent)' }}>Recommended Next Step:</strong> {f.recommended_verification_step}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Step 5: Missing Documents Needed */}
          <div className="card" style={{ padding: '20px' }}>
            <h4 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '10px' }}>
              5. Documents Still Needed Before Purchase ({missingDocsOnly.length} pending)
            </h4>
            <div style={{ display: 'grid', gap: '8px' }}>
              {checklistItems.map((item, idx) => (
                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', padding: '10px 12px', borderRadius: '8px', background: 'var(--surface-2)', border: '1px solid var(--border)', flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>{item.document_type}</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>{item.requirement_level} · {item.rationale}</div>
                  </div>
                  <span style={{
                    fontSize: '11px', fontWeight: 700, padding: '3px 9px', borderRadius: '999px',
                    background: item.status === 'Provided' ? 'rgba(16,185,129,0.14)' : 'rgba(245,158,11,0.14)',
                    color: item.status === 'Provided' ? 'var(--ok)' : 'var(--warn)',
                  }}>
                    {item.status === 'Provided' && <CheckCircle2 size={11} style={{ display: 'inline', marginRight: 4 }} />}
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Step 6: Official Government Verification Portals */}
          <div className="card" style={{ padding: '20px' }}>
            <h4 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Landmark size={16} color="var(--accent)" /> 6. Official Government Verification Portals (Manual Check Required)
            </h4>
            <p style={{ fontSize: '12px', color: 'var(--warn)', marginBottom: '12px' }}>
              This system does NOT automatically connect to government registries or clear legal title. Always verify manually on official Karnataka portals:
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
              <a href={analysis.official_verification_status?.bhoomi?.portal_url || 'https://landrecords.karnataka.gov.in/'} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
                Bhoomi (RTC / Pahani) <ExternalLink size={13} />
              </a>
              <a href={analysis.official_verification_status?.kaveri_ec?.portal_url || 'https://kaveri.karnataka.gov.in/'} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
                Kaveri (Encumbrance EC) <ExternalLink size={13} />
              </a>
              <a href={analysis.litigation_findings?.ecourts_portal_url || 'https://services.ecourts.gov.in/ecourtindia_v6/casestatus/'} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
                eCourts Litigation <ExternalLink size={13} />
              </a>
              {(analysis.approval_analysis?.jurisdiction?.official_portals || []).map((p) => (
                <a key={p.url} href={p.url} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
                  {p.name} <ExternalLink size={13} />
                </a>
              ))}
            </div>
          </div>

          {/* Step 7: Export PDF & Legal Limitations */}
          <div className="card" style={{ padding: '20px', border: '1px solid var(--accent-border)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
              <div>
                <h4 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>
                  7. Download Due-Diligence Packet &amp; Legal Disclaimer
                </h4>
                <p style={{ fontSize: '12px', color: 'var(--text-3)', marginTop: '2px' }}>
                  Generates an 18-section A4 PDF preserving original OCR values, manual edits, and page citations.
                </p>
              </div>
              {isDemoPreview ? (
                <span style={{ fontSize: '12px', color: 'var(--warn)', fontWeight: 600 }}>
                  Upload real documents to export an authenticated PDF report
                </span>
              ) : (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={pdfDownloading}
                  onClick={handleExportPdf}
                >
                  <Download size={16} /> {pdfDownloading ? 'Downloading PDF...' : 'Download Due-Diligence PDF'}
                </button>
              )}
            </div>
            <div style={{ marginTop: '12px', padding: '12px', borderRadius: '8px', background: 'var(--bg-subtle)', fontSize: '11.5px', color: 'var(--text-3)', lineHeight: 1.5 }}>
              <strong style={{ color: 'var(--accent)' }}>Important Legal Notice:</strong> {MANDATORY_DISCLAIMER}
            </div>
          </div>
        </div>
      )}

      {/* VIEW B: TECHNICAL OCR, METADATA, APPROVALS & MANUAL CORRECTIONS */}
      {analysis && viewMode === 'technical' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <AccordionCard
            title="A. Property Reference Metadata (Sent with Next Re-Analysis)"
            subtitle="Separates user-typed identifiers cleanly from AI extracted fields"
            defaultOpen={false}
          >
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Property Label</label>
                <input className="form-control" value={propertyForm.property_label || ''} onChange={(e) => setPropertyForm({ ...propertyForm, property_label: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Property Workflow Type</label>
                <select className="form-control" value={propertyForm.property_type || 'residential_plot'} onChange={(e) => setPropertyForm({ ...propertyForm, property_type: e.target.value })}>
                  <option value="residential_plot">Residential Plot</option>
                  <option value="apartment">Apartment / Flat</option>
                  <option value="agricultural">Agricultural Land</option>
                  <option value="commercial">Commercial Land</option>
                  <option value="industrial">Industrial Plot</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Survey No. / Hissa</label>
                <input className="form-control" value={propertyForm.survey_number || ''} onChange={(e) => setPropertyForm({ ...propertyForm, survey_number: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Plot / Khata Extent</label>
                <input className="form-control" value={propertyForm.land_area || ''} onChange={(e) => setPropertyForm({ ...propertyForm, land_area: e.target.value })} />
              </div>
            </div>
          </AccordionCard>

          <AccordionCard
            title="B. OCR Extracted Fields & Manual Correction Audit"
            subtitle="Original OCR extraction is always preserved alongside any user correction"
            defaultOpen={true}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {docs.map((doc) => (
                <div key={doc.document_id} style={{ padding: '14px', borderRadius: '8px', background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', flexWrap: 'wrap', gap: '8px' }}>
                    <div>
                      <strong style={{ color: 'var(--accent)', fontSize: '13px' }}>{doc.document_type}</strong>
                      <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>
                        {doc.original_filename}
                        {doc.classification?.original_classified_type && doc.classification.original_classified_type !== doc.document_type
                          ? ` · Reclassified from ${doc.classification.original_classified_type}`
                          : ''}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                        Text/OCR: <strong>{Math.round((doc.ocr?.average_confidence || 0) * 100)}%</strong> · Classif: <strong>{Math.round((doc.classification?.confidence || 0) * 100)}%</strong> · Fields: <strong>{Math.round((doc.extraction?.field_extraction_confidence || 0) * 100)}%</strong>
                      </span>
                      {!isDemoPreview && (
                        <select
                          className="form-control"
                          value={doc.document_type}
                          onChange={(e) => handleReclassifyDocument(doc.document_id, e.target.value)}
                          style={{ padding: '2px 6px', fontSize: '11px', maxWidth: '220px' }}
                        >
                          {SUPPORTED_DOCUMENT_TYPES.map((dt) => (
                            <option key={dt} value={dt}>{dt}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Field</th>
                          <th>Original OCR</th>
                          <th>Effective Value</th>
                          <th>Pg</th>
                          <th>Conf</th>
                          <th>Edit</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(doc.extraction?.fields || {}).map(([fname, finfo]) => {
                          const editKey = `${doc.document_id}:${fname}`;
                          const isEditing = editingField === editKey;
                          return (
                            <tr key={fname}>
                              <td style={{ textTransform: 'capitalize', fontWeight: 600 }}>{fname.replace(/_/g, ' ')}</td>
                              <td style={{ color: 'var(--text-3)', fontSize: '12px' }}>{finfo.original_value}</td>
                              <td style={{ fontWeight: 600 }}>
                                {isEditing ? (
                                  <input className="form-control" value={editValue} onChange={(e) => setEditValue(e.target.value)} style={{ padding: '4px 8px', fontSize: '12px' }} />
                                ) : (
                                  <>
                                    {finfo.effective_value}
                                    {finfo.is_corrected && (
                                      <span style={{ marginLeft: '6px', fontSize: '10px', padding: '1px 6px', borderRadius: '4px', background: 'var(--brand-100)', color: 'var(--accent)' }}>
                                        User Edited
                                      </span>
                                    )}
                                  </>
                                )}
                              </td>
                              <td>{finfo.page_number || '—'}</td>
                              <td>{Math.round((finfo.confidence || 0) * 100)}%</td>
                              <td>
                                {isDemoPreview ? (
                                  <span style={{ fontSize: '11px', color: 'var(--text-3)' }}>Demo</span>
                                ) : isEditing ? (
                                  <button type="button" className="btn btn-primary btn-sm" onClick={() => handleSaveCorrection(doc.document_id, fname)}>
                                    <Save size={12} /> Save
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => {
                                      setEditingField(editKey);
                                      setEditValue(finfo.effective_value || '');
                                    }}
                                  >
                                    <Pencil size={12} /> Edit
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          </AccordionCard>

          <AccordionCard
            title="C. Jurisdiction, Conversion (Sec. 95) & Layout Approval"
            subtitle="Competent authority estimate for Mysuru district parcels"
            defaultOpen={false}
          >
            <div style={{ display: 'grid', gap: '12px', fontSize: '13px' }}>
              <div style={{ padding: '12px', borderRadius: '8px', background: 'var(--bg-sage-tint)', border: '1px solid var(--accent-border)' }}>
                <strong style={{ color: 'var(--accent)' }}>Estimated Competent Authority:</strong>{' '}
                {analysis.approval_analysis?.jurisdiction?.estimated_competent_authority}
              </div>
              <div className="grid grid-2" style={{ gap: '12px' }}>
                <div style={{ padding: '12px', borderRadius: '8px', background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}><Building2 size={14} style={{ display: 'inline', marginRight: 6 }} />Sec. 95 Land Conversion</div>
                  <div style={{ marginTop: '4px', color: 'var(--warn)' }}>{analysis.approval_analysis?.land_conversion?.status}</div>
                </div>
                <div style={{ padding: '12px', borderRadius: '8px', background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>Layout Approval Status</div>
                  <div style={{ marginTop: '4px', color: 'var(--warn)' }}>{analysis.approval_analysis?.layout_approval?.status}</div>
                </div>
              </div>
            </div>
          </AccordionCard>

          <AccordionCard
            title="D. Manual eCourts Litigation Reference Queue"
            subtitle="Attach case numbers for the next document analysis pass"
            defaultOpen={false}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {(analysis.litigation_findings?.findings || []).map((f, idx) => (
                <div key={idx} style={{ padding: '10px', borderRadius: '8px', background: 'var(--status-danger-bg)', border: '1px solid var(--status-danger-border)', fontSize: '12px' }}>
                  <strong><Gavel size={13} style={{ display: 'inline', marginRight: 4 }} />{f.case_number}</strong> — {f.court_name} ({f.status})
                </div>
              ))}
              <div className="form-row">
                <input className="form-control" placeholder="Court Name" value={newCase.court_name} onChange={(e) => setNewCase({ ...newCase, court_name: e.target.value })} />
                <input className="form-control" placeholder="Case No. (e.g. O.S. 12/2025)" value={newCase.case_number} onChange={(e) => setNewCase({ ...newCase, case_number: e.target.value })} />
                <input className="form-control" placeholder="Parties" value={newCase.parties} onChange={(e) => setNewCase({ ...newCase, parties: e.target.value })} />
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                style={{ alignSelf: 'flex-start' }}
                onClick={() => {
                  if (!newCase.case_number) return;
                  setManualCases((prev) => [...prev, newCase]);
                  setNewCase({ court_name: '', case_number: '', parties: '', survey_number: '', nature_of_dispute: '' });
                }}
              >
                Queue Case Entry ({manualCases.length} queued)
              </button>
            </div>
          </AccordionCard>
        </div>
      )}
    </div>
  );
}
