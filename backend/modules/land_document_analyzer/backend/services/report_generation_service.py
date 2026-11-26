"""Concise, buyer-focused A4 PDF due-diligence report generator (4-5 pages) with optional technical appendix."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from modules.land_document_analyzer.backend.config.settings import Settings
from modules.land_document_analyzer.backend.models.schemas import MANDATORY_LEGAL_DISCLAIMER

# Clean Editorial Palette
CHARCOAL = colors.HexColor("#141C17")
CHARCOAL_LIGHT = colors.HexColor("#223128")
ACCENT_GREEN = colors.HexColor("#1B6336")
TINT_GREEN = colors.HexColor("#EDF7F0")
RED_DARK = colors.HexColor("#991B1B")
RED_BG = colors.HexColor("#FEF2F2")
AMBER_DARK = colors.HexColor("#9A3412")
AMBER_BG = colors.HexColor("#FFF7ED")
SLATE_BG = colors.HexColor("#F4F6F8")
SURFACE = colors.HexColor("#F7F9F8")
BORDER = colors.HexColor("#CFD9D2")
TEXT_DARK = colors.HexColor("#141C17")
TEXT_MUTED = colors.HexColor("#4A5750")

# Canonical buyer recommendations
REC_PROCEED = "PROCEED TO NEXT VERIFICATION STAGE"
REC_CAUTION = "PROCEED WITH CAUTION"
REC_HOLD = "HOLD — RESOLVE ISSUES BEFORE PURCHASE"
REC_INSUFFICIENT = "INSUFFICIENT INFORMATION TO ASSESS"


class CompactCanvas(canvas.Canvas):
    """Lightweight numbered footer with clean top rule on pages 2+."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_chrome(total_pages)
            super().showPage()
        super().save()

    def _draw_chrome(self, total_pages: int):
        page_num = self._pageNumber
        width, height = A4
        self.saveState()
        if page_num > 1:
            self.setStrokeColor(ACCENT_GREEN)
            self.setLineWidth(0.7)
            self.line(14 * mm, height - 11.5 * mm, width - 14 * mm, height - 11.5 * mm)
            self.setFont("Helvetica-Bold", 7.8)
            self.setFillColor(CHARCOAL)
            self.drawString(14 * mm, height - 9.8 * mm, "PROPERTY DOCUMENT DUE-DILIGENCE SUMMARY (MYSURU DISTRICT)")
            self.setFont("Helvetica-Oblique", 7.5)
            self.setFillColor(TEXT_MUTED)
            self.drawRightString(width - 14 * mm, height - 9.8 * mm, "Preliminary Review — Not Legal Advice")

        self.setStrokeColor(BORDER)
        self.setLineWidth(0.5)
        self.line(14 * mm, 11.5 * mm, width - 14 * mm, 11.5 * mm)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(TEXT_MUTED)
        self.drawString(14 * mm, 8.2 * mm, "Automated extraction & cross-check only. Official government portal & advocate verification required.")
        self.drawRightString(width - 14 * mm, 8.2 * mm, f"Page {page_num} of {total_pages}")
        self.restoreState()


def _p(text: Any, style: ParagraphStyle) -> Paragraph:
    safe = escape(str(text if text is not None else "Not available")).replace("\n", "<br/>")
    return Paragraph(safe, style)


def _clean_val(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("", "none", "unable to extract", "unable to extract from uploaded document", "not available", "n/a"):
        return ""
    return s


def _field_val(doc: Dict[str, Any], *keys: str) -> str:
    fields = (doc.get("extraction") or {}).get("fields") or {}
    for k in keys:
        item = fields.get(k)
        if isinstance(item, dict):
            v = _clean_val(item.get("effective_value")) or _clean_val(item.get("value"))
            if v:
                return v
        else:
            v = _clean_val(item)
            if v:
                return v
    return ""


def _detect_fictional_notice(analysis: Dict[str, Any]) -> Optional[str]:
    markers = ("fictional", "illustrative", "sample test", "dummy", "test record")
    hits = set()
    for doc in analysis.get("documents", []) or []:
        fname = str(doc.get("original_filename") or "")
        for fval in (doc.get("extraction") or {}).get("fields", {}).values():
            txt = str(fval.get("effective_value") if isinstance(fval, dict) else fval or "")
            if any(m in txt.lower() for m in markers):
                hits.add(fname)
                break
        raw_txt = str((doc.get("ocr") or {}).get("raw_text") or "")
        if any(m in raw_txt.lower() for m in markers):
            hits.add(fname)
    if hits:
        return (
            "Illustrative / Fictional Test Records Detected ("
            + ", ".join(sorted(hits))
            + "): These documents contain non-official test/illustrative data and MUST NOT be treated as genuine government records."
        )
    return None


def _compute_buyer_recommendation(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dynamically compute preliminary buyer recommendation strictly from observed findings,
    mismatches, document sufficiency, and unresolved conversion/legal indicators.
    Never hardcodes a positive or negative decision.
    """
    prop = analysis.get("property_info", {}) or {}
    proc = analysis.get("processing_summary", {}) or {}
    risk = analysis.get("risk_assessment", {}) or {}
    comp = analysis.get("cross_document_comparisons", {}) or {}
    comp_sum = comp.get("summary", {}) or {}
    ref_mm = comp.get("reference_mismatches", []) or []
    findings = risk.get("findings", []) or []
    counts = risk.get("severity_counts", {}) or {}
    chk = analysis.get("missing_documents", {}) or {}
    docs = [d for d in (analysis.get("documents") or []) if not d.get("is_duplicate")]

    processed_ok = int(proc.get("documents_processed_successfully") or len(docs) or 0)
    identified_doc_types = {
        d.get("document_type")
        for d in docs
        if d.get("document_type") and d.get("document_type") != "Other Supporting Document"
    }
    fields_extracted = int(proc.get("fields_extracted") or 0)
    confirmed_mm = int(comp_sum.get("confirmed_mismatches", comp_sum.get("mismatches", 0)) or 0)
    incomplete_cnt = int(comp_sum.get("incomplete_comparisons", 0) or 0)
    missing_info_cnt = int(comp_sum.get("missing_information", 0) or 0)
    crit_cnt = int(counts.get("Critical", 0) or 0)
    high_cnt = int(counts.get("High", 0) or 0)
    med_cnt = int(counts.get("Medium", 0) or 0)
    missing_workflow = [
        item.get("document_type")
        for item in (chk.get("items") or [])
        if str(item.get("status", "")).lower() in ("missing", "not provided", "pending")
        and "required" in str(item.get("requirement_level", "")).lower()
    ]

    entered_loc = _clean_val(prop.get("locality") or prop.get("village")) or "Entered location not specified"
    entered_area = _clean_val(prop.get("land_area")) or "Not specified"
    prop_type = _clean_val(prop.get("property_type")).replace("_", " ") or "property"

    loc_mm_docs = [m for m in ref_mm if m.get("field") in ("Village / Locality", "Taluk", "District")]
    ext_mm_docs = [m for m in ref_mm if m.get("field") == "Property Extent"]
    conv_findings = [f for f in findings if "conversion" in str(f.get("risk_category", "")).lower() or "land-use" in str(f.get("risk_category", "")).lower()]

    # Build human-readable reason from real evidence
    reason_parts: List[str] = []
    if loc_mm_docs:
        doc_locs = sorted({f"{m.get('document_type')} ('{m.get('document_value')}')" for m in loc_mm_docs})
        reason_parts.append(
            f"The entered property location is {entered_loc}, whereas uploaded {', '.join(doc_locs)} identify a different location."
        )
    if ext_mm_docs:
        doc_exts = sorted({f"{m.get('document_type')} ({m.get('document_value')})" for m in ext_mm_docs})
        reason_parts.append(
            f"Entered extent is {entered_area}, whereas uploaded {', '.join(doc_exts)} state a materially different extent."
        )
    if conv_findings:
        reason_parts.append(conv_findings[0].get("description", "Land-use / NA conversion alignment requires official verification."))
    if not reason_parts and confirmed_mm > 0:
        crit_descs = [str(f.get("description")) for f in findings if f.get("severity") in ("Critical", "High") and f.get("description")]
        reason_parts.extend(crit_descs[:2])

    # Dynamic rule selection (never use PROCEED WITH CAUTION when only 1 document type was identified)
    if processed_ok < 1 or len(identified_doc_types) < 2 or (processed_ok < 2 and fields_extracted < 3):
        rec = REC_INSUFFICIENT
        tone = "slate"
        if not reason_parts:
            reason_parts.append(
                f"Only {len(identified_doc_types)} distinct document type(s) across {processed_ok} readable item(s) "
                f"({fields_extracted} fields extracted) could be identified, which is insufficient for cross-document verification."
            )
        payment_advice = "Do not pay any booking amount or advance until all core RTC, Mutation, EC, and Sale Deed documents are separately verified."
        should_proceed = "No — identified documents or essential property details are insufficient for a meaningful preliminary assessment."
    elif crit_cnt > 0 or confirmed_mm > 0:
        rec = REC_HOLD
        tone = "red"
        if loc_mm_docs or ext_mm_docs:
            reason_parts.append("These discrepancies indicate the uploaded records may relate to a different parcel or an unsubdivided parent survey.")
        payment_advice = "Do not pay an advance or proceed with registration until the property identity, location, and extent discrepancies are resolved."
        should_proceed = "No (HOLD) — major property-reference or cross-document mismatches must be resolved before any financial commitment."
    elif high_cnt > 0 or med_cnt > 0 or incomplete_cnt > 0 or missing_workflow:
        rec = REC_CAUTION
        tone = "amber"
        if not reason_parts:
            gap_bits = []
            if missing_workflow:
                gap_bits.append(f"missing workflow document(s): {', '.join(missing_workflow[:4])}")
            if incomplete_cnt > 0:
                gap_bits.append(f"{incomplete_cnt} incomplete comparison check(s) due to unextracted/missing fields")
            reason_parts.append("Moderate concerns or unresolved gaps exist: " + "; ".join(gap_bits or ["official checks pending"]) + ".")
        payment_advice = "Hold financial advance or tie any token strictly to written advocate clearance and verified missing records."
        should_proceed = "Only cautiously — resolve missing documents and moderate warnings before paying an advance."
    else:
        rec = REC_PROCEED
        tone = "green"
        reason_parts.append(
            f"No material document-to-document or reference mismatches were detected across {processed_ok} uploaded file(s) "
            f"({comp_sum.get('matches', 0)} consistent check(s)). Automated extraction does NOT verify legal title — proceed only to official government portal and lawyer review."
        )
        payment_advice = "Proceed to official Bhoomi/Kaveri verification and independent legal opinion before paying any final consideration."
        should_proceed = "Yes, to the next official verification & legal review stage ONLY (NOT clearance to purchase without lawyer sign-off)."

    # Tailored action checklist
    before_proceeding: List[str] = []
    if loc_mm_docs or ext_mm_docs:
        before_proceeding.append(
            f"Obtain genuine documents that explicitly match the target {entered_loc} property ({entered_area}, {prop_type})."
        )
    before_proceeding.append("Verify survey number, hissa number, extent, and physical boundaries against official Survey / Bhoomi records.")
    if missing_workflow:
        before_proceeding.append(f"Collect missing documents from the seller: {', '.join(missing_workflow)}.")
    else:
        before_proceeding.append("Cross-verify original RTC/Pahani, Mutation Extract, up-to-date EC, and registered Sale Deed chain.")
    if conv_findings or "residential" in prop_type.lower() or "plot" in prop_type.lower():
        before_proceeding.append("Confirm DC NA land conversion (Section 95 KLR Act) and planning authority (MUDA/DTCP/Town Planning) layout approval.")
    before_proceeding.append("Engage an independent Karnataka property advocate for a written Title Search Report before executing an Agreement to Sell.")

    return {
        "recommendation": rec,
        "tone": tone,
        "reason": " ".join(str(x) for x in reason_parts if x).strip() or "Confirmed discrepancies detected across submitted documents.",
        "before_proceeding": before_proceeding[:5],
        "payment_advice": payment_advice,
        "should_proceed": should_proceed,
        "missing_workflow": missing_workflow,
    }


def _group_findings_for_buyer(analysis: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Produce compact grouped findings eliminating per-document repetition while preserving
    all document names, page numbers, severity, and concrete action.
    """
    findings = (analysis.get("risk_assessment") or {}).get("findings") or []
    grouped: List[Dict[str, str]] = []
    for f in findings:
        pages = ", ".join(f"p.{p}" for p in f.get("page_numbers", [])) or "p.1"
        docs = ", ".join(f.get("documents_involved", [])) or "Uploaded files"
        ftype = f.get("finding_type") or f.get("confirmation_status") or "Observation"
        ev_raw = str(f.get("extracted_evidence") or f.get("description") or "").strip()
        ev = (ev_raw[:107] + "...") if len(ev_raw) > 110 else ev_raw
        desc_raw = str(f.get("description") or "").strip()
        desc = (desc_raw[:117] + "...") if len(desc_raw) > 120 else desc_raw
        act_raw = str(f.get("recommended_verification_step") or "Verify with issuing authority.").strip()
        act = (act_raw[:97] + "...") if len(act_raw) > 100 else act_raw
        grouped.append({
            "severity": str(f.get("severity") or "Medium"),
            "category": str(f.get("risk_category") or "Document Check"),
            "finding_type": str(ftype),
            "description": desc,
            "evidence": f"{ev} | {docs} ({pages})",
            "action": act,
        })
    return grouped


class ReportGenerationService:
    """Generates a concise 4-5 page buyer-focused A4 PDF due-diligence report + optional technical appendix."""

    def __init__(self, report_dir: Optional[Path] = None):
        Settings.ensure_directories()
        self.report_dir = Path(report_dir) if report_dir else Settings.REPORT_DIR
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate_pdf(self, analysis_result: Dict[str, Any], output_path: Optional[Path] = None) -> Path:
        analysis_id = analysis_result.get("analysis_id", "analysis")
        target = Path(output_path) if output_path else (self.report_dir / f"Due_Diligence_Report_{analysis_id}.pdf")
        target.parent.mkdir(parents=True, exist_ok=True)

        # Also emit the optional technical appendix PDF beside the main buyer report
        appendix_path = target.parent / f"Due_Diligence_Appendix_{analysis_id}.pdf"
        try:
            self.generate_appendix_pdf(analysis_result, output_path=appendix_path)
        except Exception:
            pass

        doc = SimpleDocTemplate(
            str(target),
            pagesize=A4,
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
            title="AI LAND DOCUMENT ANALYSIS & PROPERTY DUE-DILIGENCE REPORT",
            author="Smart Land Valuation & Geospatial Analysis System — Mysuru District",
        )

        s = self._build_styles()
        rec_info = _compute_buyer_recommendation(analysis_result)
        fictional_notice = _detect_fictional_notice(analysis_result)

        story: List[Any] = []

        # PAGE 1 — Property & Executive Decision
        story.extend(self._page1_executive_decision(analysis_result, rec_info, fictional_notice, s))
        story.append(PageBreak())

        # PAGES 2–3 — Key Findings & Verification Checklist (natural flow across 2 pages)
        story.extend(self._page2_key_findings(analysis_result, s))
        story.append(Spacer(1, 5 * mm))

        # PAGE 3 — Documents Required & Verification Checklist
        story.extend(self._page3_verification_checklist(analysis_result, s))
        story.append(PageBreak())

        # PAGE 4 — Final Buyer Action Plan & Legal Limitations
        story.extend(self._page4_action_plan(analysis_result, rec_info, fictional_notice, s))
        story.append(PageBreak())

        # PAGE 5 (Compact Summary) — Classification, Confidences & Key Fields Snapshot
        story.extend(self._page5_extraction_summary(analysis_result, appendix_path.name, s))

        doc.build(story, canvasmaker=CompactCanvas)
        return target

    def generate_appendix_pdf(self, analysis_result: Dict[str, Any], output_path: Optional[Path] = None) -> Path:
        """Optional technical appendix containing full field-by-field extractions and pairwise matrix."""
        analysis_id = analysis_result.get("analysis_id", "analysis")
        target = Path(output_path) if output_path else (self.report_dir / f"Due_Diligence_Appendix_{analysis_id}.pdf")
        target.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(target),
            pagesize=A4,
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
            title=f"Technical Appendix — {analysis_id}",
        )
        s = self._build_styles()
        story: List[Any] = [
            Paragraph("OPTIONAL TECHNICAL APPENDIX — FIELD EXTRACTION & CROSS-COMPARISON", s["h1"]),
            Paragraph(f"Analysis ID: {escape(str(analysis_id))} | Automated parsing output (non-official).", s["muted"]),
            Spacer(1, 2 * mm),
        ]
        story.extend(self._appendix_extracted_fields(analysis_result, s))
        story.append(PageBreak())
        story.extend(self._appendix_cross_comparisons(analysis_result, s))
        doc.build(story, canvasmaker=CompactCanvas)
        return target

    @staticmethod
    def _build_styles() -> Dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        return {
            "h1": ParagraphStyle(
                "h1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=11.5,
                leading=14, textColor=CHARCOAL, spaceBefore=2, spaceAfter=4,
            ),
            "h2": ParagraphStyle(
                "h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=9.5,
                leading=12, textColor=ACCENT_GREEN, spaceBefore=5, spaceAfter=3,
            ),
            "title": ParagraphStyle(
                "title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=15,
                leading=18.5, textColor=CHARCOAL, spaceAfter=3, alignment=TA_LEFT,
            ),
            "sub": ParagraphStyle(
                "sub", parent=base["Normal"], fontName="Helvetica", fontSize=8.8,
                leading=12, textColor=TEXT_MUTED, spaceAfter=6, alignment=TA_LEFT,
            ),
            "body": ParagraphStyle(
                "body", parent=base["Normal"], fontName="Helvetica", fontSize=8.6,
                leading=12, textColor=TEXT_DARK, spaceAfter=3, alignment=TA_JUSTIFY,
            ),
            "body_bold": ParagraphStyle(
                "body_bold", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8.8,
                leading=12, textColor=CHARCOAL, spaceAfter=3, alignment=TA_LEFT,
            ),
            "muted": ParagraphStyle(
                "muted", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=7.9,
                leading=10.5, textColor=TEXT_MUTED, spaceAfter=3,
            ),
            "cell": ParagraphStyle(
                "cell", parent=base["Normal"], fontName="Helvetica", fontSize=7.9,
                leading=10.3, textColor=TEXT_DARK, alignment=TA_LEFT,
            ),
            "cell_bold": ParagraphStyle(
                "cell_bold", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.9,
                leading=10.3, textColor=CHARCOAL, alignment=TA_LEFT,
            ),
            "cell_header": ParagraphStyle(
                "cell_header", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.9,
                leading=10.3, textColor=colors.white, alignment=TA_LEFT,
            ),
            "rec_title": ParagraphStyle(
                "rec_title", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=10.5,
                leading=13.5, textColor=CHARCOAL, spaceAfter=3,
            ),
            "disclaimer": ParagraphStyle(
                "disclaimer", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=7.8,
                leading=10.5, textColor=CHARCOAL, alignment=TA_JUSTIFY,
            ),
        }

    def _styled_table(self, data: List[List[Any]], col_widths: List[float], pad_v: float = 3.5) -> Table:
        tbl = Table(data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), CHARCOAL),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE]),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
                    ("TOPPADDING", (0, 0), (-1, -1), pad_v),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), pad_v),
                ]
            )
        )
        return tbl

    def _recommendation_box(self, rec_info: Dict[str, Any], s: Dict[str, ParagraphStyle], compact: bool = True) -> Table:
        tone = rec_info.get("tone", "amber")
        accent, bg = {
            "red": (RED_DARK, RED_BG),
            "amber": (AMBER_DARK, AMBER_BG),
            "green": (ACCENT_GREEN, TINT_GREEN),
            "slate": (CHARCOAL_LIGHT, SLATE_BG),
        }.get(tone, (AMBER_DARK, AMBER_BG))

        steps_html = "".join(
            f"<br/>{idx}. {escape(step)}" for idx, step in enumerate(rec_info.get("before_proceeding", []), start=1)
        )
        txt = (
            f"<b>Preliminary Buyer Recommendation: <font color='{accent.hexval()}'>{escape(rec_info['recommendation'])}</font></b><br/>"
            f"<b>Reason:</b> {escape(rec_info['reason'])}<br/>"
        )
        if not compact and steps_html:
            txt += f"<b>Before proceeding:</b>{steps_html}<br/>"
        txt += f"<b>Payment Advice:</b> {escape(rec_info['payment_advice'])}"

        box = Table([[Paragraph(txt, s["body"])]], colWidths=[182 * mm])
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), bg),
                    ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
                    ("LINEBEFORE", (0, 0), (0, -1), 3.5, accent),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return box

    # ── PAGE 1: PROPERTY & EXECUTIVE DECISION ───────────────────────────────────
    def _page1_executive_decision(
        self,
        analysis: Dict[str, Any],
        rec_info: Dict[str, Any],
        fictional_notice: Optional[str],
        s: Dict[str, ParagraphStyle],
    ) -> List[Any]:
        prop = analysis.get("property_info", {}) or {}
        proc = analysis.get("processing_summary", {}) or {}
        risk = analysis.get("risk_assessment", {}) or {}
        comp_sum = (analysis.get("cross_document_comparisons") or {}).get("summary") or {}
        counts = risk.get("severity_counts") or {}
        docs = [d for d in (analysis.get("documents") or []) if not d.get("is_duplicate")]

        generated_at = str(analysis.get("generated_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))[:19].replace("T", " ")
        uploaded_n = int(proc.get("uploaded_file_count") or len({d.get("original_filename") for d in docs}) or len(docs))
        identified_n = int(proc.get("identified_document_count") or len(docs))
        doc_list_str = ", ".join(
            f"{d.get('document_type')} ({d.get('page_range') or d.get('original_filename')})"
            for d in docs
        ) or "None uploaded"

        banner = Table(
            [[Paragraph("<b>SLV-GIS MYSURU — BUYER PROPERTY DOCUMENT DUE-DILIGENCE SUMMARY</b>", s["cell_header"])]],
            colWidths=[182 * mm],
        )
        banner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), CHARCOAL),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, 0), (-1, -1), 2.0, ACCENT_GREEN),
                ]
            )
        )

        prop_rows = [
            [_p("Report / Analysis ID", s["cell_bold"]), _p(f"{analysis.get('report_id', 'N/A')}  |  {analysis.get('analysis_id', 'N/A')}  |  {generated_at} UTC", s["cell"])],
            [_p("Property Label", s["cell_bold"]), _p(f"{prop.get('property_label', 'Not specified')} (Ref ID: {prop.get('property_id', 'N/A')})", s["cell"])],
            [_p("Entered Location", s["cell_bold"]), _p(f"{prop.get('locality') or prop.get('village') or 'Not specified'}, {prop.get('taluk') or 'Mysuru'} Taluk, {prop.get('district') or 'Mysuru'} District", s["cell"])],
            [_p("Property Type & Entered Extent", s["cell_bold"]), _p(f"{str(prop.get('property_type', 'N/A')).replace('_', ' ').title()}  |  Entered Extent: {prop.get('land_area') or 'Not entered'}  |  Sy.No.: {prop.get('survey_number') or 'Not entered'}", s["cell"])],
            [_p("Files Uploaded vs Documents Identified", s["cell_bold"]), _p(f"{uploaded_n} uploaded file(s) -> {identified_n} individual document(s): {doc_list_str}", s["cell"])],
            [_p("Comparison Coverage", s["cell_bold"]), _p(f"{comp_sum.get('comparable_checks', 0)} comparable of {comp_sum.get('total_checks', 0)} total checks ({round((comp_sum.get('comparable_checks', 0) / max(comp_sum.get('total_checks', 1), 1)) * 100)}%)", s["cell"])],
            [_p("Overall Preliminary Assessment", s["cell_bold"]), _p(risk.get("overall_assessment", "Further Verification Required"), s["cell_bold"])],
        ]
        prop_tbl = Table(prop_rows, colWidths=[46 * mm, 136 * mm])
        prop_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), SURFACE),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )

        # Clean 4-outcome comparison counts bar (never conflating missing info with mismatches)
        matches_n = int(comp_sum.get("matches", 0) or 0)
        mismatch_n = int(comp_sum.get("confirmed_mismatches", comp_sum.get("mismatches", 0)) or 0)
        missing_n = int(comp_sum.get("missing_information", 0) or 0)
        unable_n = int(comp_sum.get("unable_to_compare", 0) or 0)
        outcome_tbl = self._styled_table(
            [
                [_p("MATCH", s["cell_header"]), _p("MISMATCH (Confirmed)", s["cell_header"]), _p("MISSING INFORMATION", s["cell_header"]), _p("UNABLE TO COMPARE", s["cell_header"])],
                [_p(f"{matches_n} consistent check(s)", s["cell_bold"]), _p(f"{mismatch_n} confirmed mismatch(es)", s["cell_bold"]), _p(f"{missing_n} missing field(s) (not mismatch)", s["cell"]), _p(f"{unable_n} uncomparable check(s)", s["cell"])],
            ],
            [45.5 * mm, 45.5 * mm, 45.5 * mm, 45.5 * mm],
        )

        sev_line = (
            f"<b>Findings Summary:</b> Critical: {counts.get('Critical', 0)}  |  High: {counts.get('High', 0)}  |  "
            f"Medium: {counts.get('Medium', 0)}  |  Official Checks Pending: {counts.get('Unverified', 0)}  |  "
            f"Text Readability: {proc.get('text_extraction_quality', 0):.0%}"
        )

        elements: List[Any] = [
            banner,
            Spacer(1, 3 * mm),
            Paragraph("AI Land Document Analysis &amp; Property Due-Diligence Report", s["title"]),
            Paragraph("1. Property Profile &amp; Executive Buyer Decision (Preliminary Review — Not Certified Title Advice)", s["sub"]),
            prop_tbl,
            Spacer(1, 3 * mm),
            self._recommendation_box(rec_info, s, compact=False),
            Spacer(1, 3 * mm),
            Paragraph(sev_line, s["body"]),
            outcome_tbl,
            Spacer(1, 2.5 * mm),
        ]

        if fictional_notice:
            fbox = Table([[Paragraph(f"<b>TEST RECORD LABEL:</b> {escape(fictional_notice)}", s["cell"])]], colWidths=[182 * mm])
            fbox.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), AMBER_BG), ("BOX", (0, 0), (-1, -1), 0.6, AMBER_DARK), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            elements.extend([fbox, Spacer(1, 2 * mm)])

        elements.append(
            Paragraph(
                "<b>Scope Guard:</b> User-entered details and extracted values are stored separately. High parsing/extraction confidence does NOT guarantee clear title or government record authenticity. \"Proceed to next verification stage\" never implies a property is legally safe to buy.",
                s["muted"],
            )
        )
        return elements

    # ── PAGE 2: KEY FINDINGS & DOCUMENT COMPARISON ──────────────────────────────
    def _page2_key_findings(self, analysis: Dict[str, Any], s: Dict[str, ParagraphStyle]) -> List[Any]:
        grouped = _group_findings_for_buyer(analysis)
        rows = [[
            _p("Severity & Area", s["cell_header"]),
            _p("Finding & Classification", s["cell_header"]),
            _p("Supporting Evidence (Docs & Pages)", s["cell_header"]),
            _p("Recommended Action", s["cell_header"]),
        ]]
        for g in grouped:
            rows.append([
                _p(f"[{g['severity']}]\n{g['category']}", s["cell_bold"]),
                Paragraph(f"<b>{escape(g['finding_type'])}</b><br/>{escape(g['description'])}", s["cell"]),
                _p(g["evidence"], s["cell"]),
                _p(g["action"], s["cell"]),
            ])

        if len(rows) == 1:
            rows.append([
                _p("[Low]\nCross-Document Review", s["cell_bold"]),
                _p("No confirmed discrepancies detected in supplied documents.", s["cell"]),
                _p("Uploaded documents inspected.", s["cell"]),
                _p("Proceed to official Bhoomi, Kaveri EC, and advocate verification.", s["cell"]),
            ])

        return [
            Paragraph("2. Key Findings &amp; Grouped Document Comparison", s["h1"]),
            Paragraph(
                "Related findings across multiple documents are grouped once per property attribute (locality, survey/hissa, extent, ownership, land-use conversion, missing documents, and pending official checks). Missing information is never counted as a confirmed mismatch.",
                s["muted"],
            ),
            self._styled_table(rows, [33 * mm, 50 * mm, 59 * mm, 40 * mm], pad_v=2.2),
        ]

    # ── PAGE 3: DOCUMENTS REQUIRED & VERIFICATION CHECKLIST ─────────────────────
    def _page3_verification_checklist(self, analysis: Dict[str, Any], s: Dict[str, ParagraphStyle]) -> List[Any]:
        docs = [d for d in (analysis.get("documents") or []) if not d.get("is_duplicate")]
        chk = analysis.get("missing_documents", {}) or {}
        items = chk.get("items") or []

        received = [f"{d.get('document_type')} ({d.get('original_filename')})" for d in docs]
        request_seller = [
            f"{i['document_type']} — {i.get('rationale', 'Required')}"
            for i in items
            if str(i.get("status", "")).lower() in ("missing", "not provided", "pending")
            and "conditional" not in str(i.get("requirement_level", "")).lower()
        ]
        conditional = [
            f"{i['document_type']} ({i.get('status')}) — {i.get('rationale', 'Context-dependent')}"
            for i in items
            if "conditional" in str(i.get("requirement_level", "")).lower()
            or "recommended" in str(i.get("requirement_level", "")).lower()
        ]

        doc_summary_rows = [
            [_p("Category", s["cell_header"]), _p("Document Status & Seller Requests", s["cell_header"])],
            [_p("Documents Received", s["cell_bold"]), _p(", ".join(received) if received else "None uploaded", s["cell"])],
            [_p("Request From Seller (Before Advance)", s["cell_bold"]), _p("\n".join(f"• {x}" for x in request_seller) if request_seller else "Core uploaded documents present (still verify originals).", s["cell"])],
            [_p("Conditional / Context Documents", s["cell_bold"]), _p("\n".join(f"• {x}" for x in conditional) if conditional else "Check NA conversion & layout approval if plot/residential.", s["cell"])],
        ]

        appr = analysis.get("approval_analysis", {}) or {}
        auth_name = ((appr.get("jurisdiction") or {}).get("estimated_competent_authority") or "MUDA / DTCP / Town Planning")

        portal_rows = [
            [_p("Verification Item & Authority", s["cell_header"]), _p("Check Mode", s["cell_header"]), _p("Practical Buyer Verification Steps", s["cell_header"])],
            [_p("Karnataka Bhoomi\n(RTC / Pahani & Mutation)", s["cell_bold"]), _p("Online Portal +\nPhysical RTC", s["cell"]), _p("Verify current year RTC (Pahani), survey/hissa number, cultivator/owner khata, extent in Acres-Guntas, and Mutation Register (MR) entry matching the seller.", s["cell"])],
            [_p("Kaveri Online Services\n(EC & Deed Index)", s["cell_bold"]), _p("Online Portal +\nOfficial EC", s["cell"]), _p("Apply for digitally signed Encumbrance Certificate (EC Form 15/16) covering at least 15-30 years for the exact survey & site number.", s["cell"])],
            [_p("Sub-Registrar Office (SRO)\n(Registered Title Chain)", s["cell_bold"]), _p("Physical / SRO\nCertified Copy", s["cell"]), _p("Obtain certified copies of the Sale Deed and link/mother deeds; inspect original registered Sale Deed & schedule boundaries held by seller.", s["cell"])],
            [_p(f"Planning Authority\n({auth_name})", s["cell_bold"]), _p("Official Portal /\nPhysical File", s["cell"]), _p("Verify DC NA Conversion Order (Sec. 95 KLR Act) and sanctioned layout plan release certificate for non-agricultural residential plots.", s["cell"])],
            [_p("Survey / ADLR Authority\n(Boundaries & Extent)", s["cell_bold"]), _p("Physical Survey /\nRevenue Sketch", s["cell"]), _p("Compare FMB / Akarband / Hissa sketch against site measurements to confirm exact extent, road frontage, and absence of encroachments.", s["cell"])],
            [_p("eCourts Portal\n(Litigation Screening)", s["cell_bold"]), _p("Online Search +\nAdvocate Check", s["cell"]), _p("Search seller names and survey numbers on eCourts Mysuru civil/revenue courts and ask an advocate to screen pending suits.", s["cell"])],
        ]

        return [
            Paragraph("3. Documents Required &amp; Practical Verification Checklist", s["h1"]),
            Paragraph(f"Checklist context: {escape(str(chk.get('land_classification_detected', 'Parcel')))} | {escape(str(chk.get('location_context', 'Mysuru District')))} (missing files are informational gaps, not proof of defect).", s["muted"]),
            self._styled_table(doc_summary_rows, [52 * mm, 130 * mm], pad_v=2.5),
            Spacer(1, 3 * mm),
            Paragraph("Where &amp; How to Verify (Distinguishing Online Checks vs Physical / Professional Checks)", s["h2"]),
            self._styled_table(portal_rows, [48 * mm, 30 * mm, 104 * mm], pad_v=2.5),
        ]

    # ── PAGE 4: FINAL BUYER ACTION PLAN & LEGAL LIMITATIONS ─────────────────────
    def _page4_action_plan(
        self,
        analysis: Dict[str, Any],
        rec_info: Dict[str, Any],
        fictional_notice: Optional[str],
        s: Dict[str, ParagraphStyle],
    ) -> List[Any]:
        prop = analysis.get("property_info", {}) or {}
        docs = [d for d in (analysis.get("documents") or []) if not d.get("is_duplicate")]
        doc_names = ", ".join(str(d.get("document_type")) for d in docs) or "title records"
        loc_lbl = _clean_val(prop.get("locality") or prop.get("village")) or "target parcel"

        qa_rows = [
            [_p("Buyer Decision Question", s["cell_header"]), _p("Evidence-Based Guidance", s["cell_header"])],
            [_p("1. Should the buyer proceed now?", s["cell_bold"]), _p(rec_info["should_proceed"], s["cell"])],
            [_p("2. What must be resolved before paying an advance?", s["cell_bold"]), _p("\n".join(f"• {x}" for x in rec_info["before_proceeding"]), s["cell"])],
            [_p("3. Which original documents should be requested?", s["cell_bold"]), _p(f"Original registered Sale Deed & Mother Deeds, latest Karnataka Bhoomi RTC, Mutation Register Extract, up-to-date Kaveri EC, Khata Extract/Tax Paid Receipt, and DC NA Conversion / Layout Approval for {loc_lbl}.", s["cell"])],
            [_p("4. What must be checked before registration?", s["cell_bold"]), _p("Confirm SRO certified copies match originals, check latest EC up to registration week, verify vendor KYC/legal heirs, confirm zero pending tax/maintenance dues, and validate sale deed schedule against measured site dimensions.", s["cell"])],
            [_p("5. What requires a property lawyer or surveyor?", s["cell_bold"]), _p("Licensed Advocate: 30-year title chain opinion, encumbrance/litigation check, SC/ST PTCL / grant-land screening, and conversion legality. Licensed Surveyor: physical boundary & extent measurement against FMB/Hissa map.", s["cell"])],
        ]

        disc_txt = MANDATORY_LEGAL_DISCLAIMER
        if fictional_notice:
            disc_txt = f"{fictional_notice} {disc_txt}"
        disc_box = Table([[_p(disc_txt, s["disclaimer"])]], colWidths=[182 * mm])
        disc_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                    ("BOX", (0, 0), (-1, -1), 0.7, CHARCOAL),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        return [
            Paragraph("4. Final Buyer Action Plan &amp; Legal Limitations", s["h1"]),
            self._styled_table(qa_rows, [56 * mm, 126 * mm]),
            Spacer(1, 3.5 * mm),
            Paragraph("Direct Buyer Conclusion", s["h2"]),
            self._recommendation_box(rec_info, s, compact=False),
            Spacer(1, 3.5 * mm),
            Paragraph("Legal &amp; Automated Parsing Limitations", s["h2"]),
            disc_box,
            Spacer(1, 2 * mm),
            Paragraph(f"Reviewed set ({doc_names}) reflects automated file parsing only and does not replace statutory registration checks.", s["muted"]),
        ]

    # ── PAGE 5: COMPACT EXTRACTION SUMMARY (OPTIONAL TECHNICAL SUMMARY) ─────────
    def _page5_extraction_summary(
        self,
        analysis: Dict[str, Any],
        appendix_filename: str,
        s: Dict[str, ParagraphStyle],
    ) -> List[Any]:
        proc = analysis.get("processing_summary", {}) or {}
        docs = analysis.get("documents", []) or []

        conf_rows = [
            [_p("Metric", s["cell_header"]), _p("Measured Value", s["cell_header"]), _p("Meaning", s["cell_header"])],
            [_p("Text Extraction Quality", s["cell_bold"]), _p(f"{proc.get('text_extraction_quality', 0):.0%}", s["cell"]), _p("PDF digital text readability", s["cell"])],
            [_p("OCR Status / Confidence", s["cell_bold"]), _p(proc.get("ocr_status_note", "Not performed (Digital PDF)"), s["cell"]), _p("OCR reported only if scanned OCR ran", s["cell"])],
            [_p("Classification Confidence", s["cell_bold"]), _p(f"{proc.get('avg_classification_confidence', 0):.0%}", s["cell"]), _p("Document type match confidence", s["cell"])],
            [_p("Field Extraction Coverage", s["cell_bold"]), _p(f"{proc.get('avg_field_extraction_confidence', 0):.0%} ({proc.get('fields_extracted', 0)}/{proc.get('total_schema_fields', 0)})", s["cell"]), _p("Automated parsing metric != legal validity", s["cell"])],
        ]

        doc_rows = [[
            _p("Document Type & File", s["cell_header"]),
            _p("Classif. / Fields", s["cell_header"]),
            _p("Survey / Hissa", s["cell_header"]),
            _p("Village / Locality", s["cell_header"]),
            _p("Extracted Extent", s["cell_header"]),
            _p("Owner / Key Parties", s["cell_header"]),
        ]]
        for d in docs:
            cls = d.get("classification") or {}
            ext = d.get("extraction") or {}
            sy = _field_val(d, "survey_number", "site_number") or "Not extracted"
            hi = _field_val(d, "hissa_number")
            sy_str = f"{sy} / {hi}" if hi else sy
            vill = _field_val(d, "village", "locality") or "Not extracted"
            extent = _field_val(d, "property_extent", "total_land_extent", "converted_extent", "total_layout_extent") or "Not extracted"
            owner = _field_val(d, "owner_names", "new_owner", "buyer_names", "seller_names", "claimant", "applicant") or "Not extracted"
            pr_str = d.get("page_range") or f"{(d.get('ocr') or {}).get('page_count', 1)} pg"
            f_conf = float(ext.get("field_extraction_confidence") or 0.0)
            doc_rows.append([
                _p(f"{d.get('document_type')}\n({d.get('original_filename')} · {pr_str})", s["cell_bold"]),
                _p(f"Cls: {cls.get('confidence', 0):.0%}\nExt: {f_conf:.0%} ({ext.get('extracted_count', 0)}/{ext.get('total_fields', 0)})", s["cell"]),
                _p(sy_str, s["cell"]),
                _p(vill, s["cell"]),
                _p(extent, s["cell"]),
                _p(owner[:70], s["cell"]),
            ])

        return [
            Paragraph("5. Compact Extraction Summary (Reference Overview)", s["h1"]),
            Paragraph("Automated parsing metrics and primary extracted property identifiers per file.", s["muted"]),
            self._styled_table(conf_rows, [46 * mm, 64 * mm, 72 * mm]),
            Spacer(1, 3.5 * mm),
            self._styled_table(doc_rows, [42 * mm, 24 * mm, 24 * mm, 32 * mm, 30 * mm, 30 * mm]),
            Spacer(1, 3 * mm),
            Paragraph(
                f"<b>Optional Technical Appendix:</b> Detailed schema field-by-field values and exhaustive pairwise comparison checks are stored separately in <i>{escape(appendix_filename)}</i> to keep this buyer report concise.",
                s["muted"],
            ),
        ]

    # ── OPTIONAL TECHNICAL APPENDIX BUILDERS ────────────────────────────────────
    def _appendix_extracted_fields(self, analysis: Dict[str, Any], s: Dict[str, ParagraphStyle]) -> List[Any]:
        elements: List[Any] = [Paragraph("Appendix A — Detailed Extracted Fields by Document", s["h2"])]
        for d in analysis.get("documents", []):
            fields = d.get("extraction", {}).get("fields", {})
            rows = [[
                _p("Field", s["cell_header"]),
                _p("Extracted / Effective Value", s["cell_header"]),
                _p("Pg", s["cell_header"]),
                _p("Conf.", s["cell_header"]),
                _p("Status", s["cell_header"]),
            ]]
            for fname, finfo in fields.items():
                val = finfo.get("effective_value", "Unable to extract")
                prov = "Manual Override" if finfo.get("is_corrected") else finfo.get("extraction_status", "extracted")
                rows.append([
                    _p(fname.replace("_", " ").title(), s["cell_bold"]),
                    _p(val, s["cell"]),
                    _p(str(finfo.get("page_number") or "-"), s["cell"]),
                    _p(f"{finfo.get('confidence', 0):.0%}", s["cell"]),
                    _p(prov, s["cell"]),
                ])
            elements.append(Paragraph(f"{escape(str(d.get('document_type')))} — {escape(str(d.get('original_filename')))}", s["body_bold"]))
            elements.append(self._styled_table(rows, [38 * mm, 82 * mm, 12 * mm, 16 * mm, 34 * mm]))
            elements.append(Spacer(1, 3 * mm))
        return elements

    def _appendix_cross_comparisons(self, analysis: Dict[str, Any], s: Dict[str, ParagraphStyle]) -> List[Any]:
        comp = analysis.get("cross_document_comparisons", {})
        table = comp.get("discrepancy_table", [])
        rows = [[
            _p("Category & Field", s["cell_header"]),
            _p("Document A / Ref", s["cell_header"]),
            _p("Document B", s["cell_header"]),
            _p("Outcome", s["cell_header"]),
            _p("Evidence & Page", s["cell_header"]),
        ]]
        for r in table:
            rows.append([
                _p(f"{r.get('category', '')}\n{r['field']}", s["cell_bold"]),
                _p(f"{r['document_a']}: {r['document_a_value']}", s["cell"]),
                _p(f"{r['document_b']}: {r['document_b_value']}", s["cell"]),
                _p(r["result"], s["cell_bold"]),
                _p(f"{r.get('evidence') or r.get('note', '')} (p.{r.get('document_a_page') or '-'} / p.{r.get('document_b_page') or '-'})", s["cell"]),
            ])
        if len(rows) == 1:
            rows.append([_p("Comparisons", s["cell_bold"]), _p("-", s["cell"]), _p("-", s["cell"]), _p("MISSING INFORMATION", s["cell_bold"]), _p(comp.get("comparison_status", "Insufficient extracted data."), s["cell"])])
        return [
            Paragraph("Appendix B — Document-by-Document Cross-Comparison Matrix", s["h2"]),
            self._styled_table(rows, [34 * mm, 42 * mm, 42 * mm, 26 * mm, 38 * mm]),
        ]
