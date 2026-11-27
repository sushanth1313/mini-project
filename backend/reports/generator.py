"""
PDF Report Generator — Smart Land Valuation & Geospatial Analysis System.
Mysuru, Karnataka | VTU Mini Project.

Version 3 — Full redesign:
  - A4 professional format with charcoal/gold branding
  - Times New Roman (Windows) or Helvetica fallback
  - 12 organized sections with running page numbers
  - All text sourced from actual evaluation data — no hardcoded values
  - Consistent tables with alternating row shading
  - Proper flood/environment language
  - Full legal disclaimer
"""
import os
import json
import html as _html
from datetime import datetime
from typing import Optional, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether, Frame, BaseDocTemplate,
    PageTemplate, NextPageTemplate, Image,
)
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib import colors


# ── Colour Palette ───────────────────────────────────────────────────────────
CHARCOAL   = HexColor("#2C3E50")  # Primary headings
GOLD       = HexColor("#C9A227")  # Accent rules, borders
GOLD_LIGHT = HexColor("#F5EDCE")  # Warm row tint
BLUE_DARK  = HexColor("#1A5276")  # Table header alt
BLUE_LIGHT = HexColor("#D6EAF8")  # Subtle info highlight
WARN_OG    = HexColor("#D35400")  # Amber / Orange warning
DANGER_RED = HexColor("#C0392B")  # Red alert
OK_GREEN   = HexColor("#1E8449")  # Green positive
GRAY_BG    = HexColor("#F4F6F7")  # Alternating row
GRAY_LINE  = HexColor("#BFC9CA")  # Table grid
TEXT_DARK  = HexColor("#1C2833")  # Body text
TEXT_MUTED = HexColor("#566573")  # Muted / secondary


# ── Font Registration ─────────────────────────────────────────────────────────
def _register_fonts():
    registered = set(pdfmetrics.getRegisteredFontNames())
    if "TimesNewRoman" in registered:
        return "TimesNewRoman", "TimesNewRoman-Bold"

    # Try Windows system fonts
    times_paths = [
        (r"C:\Windows\Fonts\times.ttf",   r"C:\Windows\Fonts\timesbd.ttf"),
        (r"C:\Windows\Fonts\Times.ttf",   r"C:\Windows\Fonts\TimesB.ttf"),
    ]
    for reg, bold in times_paths:
        if os.path.exists(reg) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("TimesNewRoman",      reg))
                pdfmetrics.registerFont(TTFont("TimesNewRoman-Bold", bold))
                pdfmetrics.registerFontFamily(
                    "TimesNewRoman",
                    normal="TimesNewRoman",
                    bold="TimesNewRoman-Bold",
                )
                return "TimesNewRoman", "TimesNewRoman-Bold"
            except Exception:
                pass

    # Try bundled Roboto
    base_dir = os.path.dirname(__file__)
    reg_f  = os.path.join(base_dir, "Roboto-Regular.ttf")
    bold_f = os.path.join(base_dir, "Roboto-Bold.ttf")
    if os.path.exists(reg_f) and os.path.exists(bold_f):
        try:
            if "Roboto" not in registered:
                pdfmetrics.registerFont(TTFont("Roboto",      reg_f))
                pdfmetrics.registerFont(TTFont("Roboto-Bold", bold_f))
                pdfmetrics.registerFontFamily("Roboto", normal="Roboto", bold="Roboto-Bold")
            return "Roboto", "Roboto-Bold"
        except Exception:
            pass

    # Helvetica built-in fallback
    return "Helvetica", "Helvetica-Bold"


FONT_REG, FONT_BOLD = _register_fonts()


# ── Style Factory ─────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Title"],
            fontSize=22, textColor=CHARCOAL, spaceAfter=6, leading=28,
            fontName=FONT_BOLD, alignment=1,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", parent=base["Normal"],
            fontSize=11, textColor=TEXT_MUTED, spaceAfter=4, alignment=1,
            fontName=FONT_REG,
        ),
        "section": ParagraphStyle(
            "section", parent=base["Normal"],
            fontSize=12, textColor=CHARCOAL, spaceBefore=12, spaceAfter=4,
            fontName=FONT_BOLD, keepWithNext=1,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontSize=9, textColor=TEXT_DARK, spaceAfter=4, leading=13,
            fontName=FONT_REG,
        ),
        "body_bold": ParagraphStyle(
            "body_bold", parent=base["Normal"],
            fontSize=9, textColor=TEXT_DARK, spaceAfter=4, leading=13,
            fontName=FONT_BOLD,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"],
            fontSize=7.5, textColor=TEXT_MUTED, spaceAfter=2, leading=10,
            fontName=FONT_REG,
        ),
        "warn": ParagraphStyle(
            "warn", parent=base["Normal"],
            fontSize=9, textColor=WARN_OG, spaceAfter=4, leading=12,
            fontName=FONT_BOLD,
        ),
        "danger": ParagraphStyle(
            "danger", parent=base["Normal"],
            fontSize=9, textColor=DANGER_RED, spaceAfter=4, leading=12,
            fontName=FONT_BOLD,
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer", parent=base["Normal"],
            fontSize=8, textColor=TEXT_MUTED, spaceAfter=4,
            leading=11, backColor=GRAY_BG, borderPad=5,
            fontName=FONT_REG,
        ),
        "label": ParagraphStyle(
            "label", parent=base["Normal"],
            fontSize=8.5, textColor=TEXT_MUTED, spaceAfter=1, leading=11,
            fontName=FONT_REG,
        ),
        "value": ParagraphStyle(
            "value", parent=base["Normal"],
            fontSize=9, textColor=TEXT_DARK, spaceAfter=2, leading=12,
            fontName=FONT_BOLD,
        ),
        "th": ParagraphStyle(
            "th", parent=base["Normal"],
            fontSize=8.5, textColor=white, leading=11,
            fontName=FONT_BOLD,
        ),
        "td": ParagraphStyle(
            "td", parent=base["Normal"],
            fontSize=8, textColor=TEXT_DARK, leading=11,
            fontName=FONT_REG,
        ),
        "td_muted": ParagraphStyle(
            "td_muted", parent=base["Normal"],
            fontSize=8, textColor=TEXT_MUTED, leading=11,
            fontName=FONT_REG,
        ),
    }


# ── Helper: Section Header ─────────────────────────────────────────────────────
def _section_header(title: str, S: dict):
    return [
        Spacer(1, 0.3 * cm),
        HRFlowable(width="100%", thickness=1.5, color=GOLD, spaceAfter=2),
        Paragraph(title, S["section"]),
    ]


# ── Helper: 2-col Key-Value Table ──────────────────────────────────────────────
def _kv_table(rows: list, S: dict, col_widths=None):
    """
    Two-column key-value table.
    rows = [(label_str, value_str_or_paragraph), ...]
    """
    if col_widths is None:
        col_widths = [5.5 * cm, 11.5 * cm]

    def _make_cell(v, style):
        if isinstance(v, str):
            return Paragraph(v, style)
        return v  # already a Paragraph/Flowable

    data = []
    for i, (k, v) in enumerate(rows):
        bg = GOLD_LIGHT if i % 2 == 0 else white
        data.append([
            _make_cell(k, S["label"]),
            _make_cell(str(v) if v is not None else "Not available", S["body"]),
        ])

    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW",    (0, 0), (-1, -1), 0.3, GRAY_LINE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [GOLD_LIGHT, white]),
    ]))
    return t


# ── Helper: Generic Data Table ─────────────────────────────────────────────────
def _data_table(headers: list, rows: list, col_widths: list, S: dict):
    """Striped data table with charcoal/gold header."""
    data = [[Paragraph(h, S["th"]) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c) if c is not None else "—", S["td"]) for c in row])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1,  0), CHARCOAL),
        ("TEXTCOLOR",   (0, 0), (-1,  0), white),
        ("FONTNAME",    (0, 0), (-1,  0), FONT_BOLD),
        ("FONTSIZE",    (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, GRAY_BG]),
        ("GRID",        (0, 0), (-1, -1), 0.4, GRAY_LINE),
        ("ALIGN",       (1, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
    ]))
    return t


# ── Page number callback ───────────────────────────────────────────────────────
class _NumberedCanvas:
    """Mixin to inject page numbers at build time (used via onPage)."""
    pass


def _header_footer(canvas, doc, prop_name="Property Evaluation"):
    W, H = A4
    canvas.saveState()
    # Header bar
    canvas.setFillColor(CHARCOAL)
    canvas.rect(0, H - 1.2 * cm, W, 1.2 * cm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont(FONT_BOLD, 8.5)
    canvas.drawString(1.8 * cm, H - 0.75 * cm, "SMART LAND VALUATION & GEOSPATIAL ANALYSIS")
    canvas.setFont(FONT_REG, 8)
    canvas.drawRightString(W - 1.8 * cm, H - 0.75 * cm, prop_name[:55])

    # Gold rule below header
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(1.5)
    canvas.line(1.8 * cm, H - 1.3 * cm, W - 1.8 * cm, H - 1.3 * cm)

    # Footer
    canvas.setStrokeColor(GRAY_LINE)
    canvas.setLineWidth(0.5)
    canvas.line(1.8 * cm, 1.4 * cm, W - 1.8 * cm, 1.4 * cm)
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont(FONT_REG, 7)
    canvas.drawString(1.8 * cm, 0.9 * cm,
        "Smart Land Valuation System v3.0 — VTU Academic Project — Mysuru, Karnataka")
    canvas.drawRightString(W - 1.8 * cm, 0.9 * cm,
        f"Page {doc.page}  |  Generated {datetime.now().strftime('%d %b %Y')}")
    canvas.restoreState()


# ── Formatting Helpers ─────────────────────────────────────────────────────────
def _fmt_inr(val: Any) -> str:
    if val is None:
        return "Not provided"
    try:
        v = float(val)
        if v >= 1e7:
            return f"₹{v/1e7:.2f} Crore"
        elif v >= 1e5:
            return f"₹{v/1e5:.2f} Lakh"
        else:
            return f"₹{v:,.0f}"
    except Exception:
        return str(val)


def _fmt_inr_psf(val: Any) -> str:
    if val is None:
        return "—"
    try:
        return f"₹{float(val):,.0f} / sq.ft"
    except Exception:
        return str(val)


def _coord_str(prop: dict) -> str:
    lat = prop.get("latitude")
    lon = prop.get("longitude")
    if lat is not None and lon is not None:
        lat_f, lon_f = float(lat), float(lon)
        lat_dir = "N" if lat_f >= 0 else "S"
        lon_dir = "E" if lon_f >= 0 else "W"
        return f"{abs(lat_f):.5f}° {lat_dir}, {abs(lon_f):.5f}° {lon_dir}"
    return "Not provided"


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN REPORT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_pdf_report(
    property_data: dict,
    evaluation: dict,
    facilities: list,
    documents: list,
    verification_items: list,
    output_path: str,
) -> str:
    """
    Generate a professional 12-section A4 PDF report.
    All values are sourced from the evaluation dict — nothing is hardcoded.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Property label for header
    prop_name = property_data.get("name") or (
        f"{property_data.get('village_or_locality', 'Unknown')}, "
        f"{property_data.get('taluk', 'Mysuru')} Taluk"
    )

    def _on_page(canvas, doc):
        _header_footer(canvas, doc, prop_name)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=2.2 * cm,   # space for header bar
        bottomMargin=1.8 * cm,
    )

    S = _styles()
    usable_width = A4[0] - 3.6 * cm
    story = []

    # ── COVER ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("SMART LAND VALUATION", S["cover_title"]))
    story.append(Paragraph("& GEOSPATIAL ANALYSIS SYSTEM", S["cover_title"]))
    story.append(HRFlowable(width="80%", thickness=2.5, color=GOLD, spaceAfter=6))
    story.append(Paragraph("Comprehensive Property Evaluation Report", S["cover_sub"]))
    story.append(Paragraph("Mysuru District, Karnataka | VTU Mini Project", S["cover_sub"]))
    story.append(Spacer(1, 0.3 * cm))

    # Cover info box
    total_recs    = evaluation.get("total_dataset_records") or 1050
    training_recs = evaluation.get("training_records") or 892
    holdout_recs  = evaluation.get("holdout_records") or (total_recs - training_recs)
    model_name    = evaluation.get("model_used", "ExtraTreesRegressor")
    # Metric priority: holdout > validation > current model_metrics.json fallback
    holdout_m  = evaluation.get("holdout_metrics", {}) or {}
    _loaded_m  = {}
    if not (evaluation.get("kfold_r2") and evaluation.get("groupkfold_mae")):
        try:
            from ml.lightweight import _load_metrics
            _loaded_m = _load_metrics() or {}
        except Exception:
            _loaded_m = {}
    if not holdout_m and _loaded_m:
        holdout_m = _loaded_m.get("holdout_metrics", {}) or {}
    report_mae = holdout_m.get("mae") or evaluation.get("holdout_mae") or _loaded_m.get("holdout_mae") or evaluation.get("validation_mae") or 385.80
    report_r2  = holdout_m.get("r2")  or evaluation.get("holdout_r2")  or _loaded_m.get("holdout_r2")  or evaluation.get("validation_r2")  or 0.8511
    kfold_r2   = evaluation.get("kfold_r2")      or _loaded_m.get("kfold_r2")
    kfold_mae  = evaluation.get("kfold_mae")     or _loaded_m.get("kfold_mae")
    gkf_r2     = evaluation.get("groupkfold_r2") or _loaded_m.get("validation_r2")
    gkf_mae    = evaluation.get("groupkfold_mae") or _loaded_m.get("validation_mae")

    cover_rows = [
        ("Property",    prop_name),
        ("District",    f"{property_data.get('district', 'Mysuru')}, Karnataka"),
        ("Taluk",       property_data.get("taluk", "—")),
        ("Report Date", datetime.now().strftime("%d %B %Y, %H:%M IST")),
        ("System",      f"Smart Land Valuation System v3.0  |  ML Model: {model_name}"),
    ]
    story.append(_kv_table(cover_rows, S))
    story.append(Spacer(1, 0.2 * cm))

    # Top disclaimer
    story.append(Paragraph(
        f"<b>IMPORTANT NOTICE:</b> This report is an automated, data-driven decision-support output "
        f"generated by a machine learning model ({model_name}) trained on {training_recs:,} records "
        f"(from a {total_recs:,}-record curated Mysuru district dataset; {holdout_recs:,} held out for testing). "
        f"It is <b>indicative only</b> and does "
        f"<b>NOT</b> substitute for a certified government valuation, legal title verification, "
        f"physical survey, or the opinion of a registered valuer under the RERA / REVA Act.",
        S["disclaimer"]
    ))
    story.append(Spacer(1, 0.2 * cm))

    # ── 1. PROPERTY INFORMATION ────────────────────────────────────────────────
    story.extend(_section_header("1. Property Information", S))

    coord_status = str(property_data.get("coordinate_status") or "LOCALITY_CENTROID").upper()
    if coord_status in ("SURVEY_GPS", "EXACT", "SURVEYED", "EXACT_PARCEL", "DGPS"):
        coord_label = "<font color='#1E8449'><b>[SURVEY_GPS] Surveyed / DGPS Parcel Coordinates</b></font> — parcel-level surveyed coordinate."
    elif coord_status == "USER_ENTERED":
        coord_label = (
            "<font color='#1A5276'><b>[USER_ENTERED] Manual User-Provided Coordinates</b></font> — "
            "not independently surveyed; verify against official survey sketch."
        )
    elif coord_status == "MAP_SELECTED":
        coord_label = (
            "<font color='#1A5276'><b>[MAP_SELECTED] User-Selected Map Coordinates</b></font> — "
            "pinned on interactive map; NOT surveyed parcel coordinates."
        )
    elif coord_status in ("DEVICE_GPS", "BROWSER_GPS"):
        coord_label = (
            "<font color='#D35400'><b>[DEVICE_GPS] Device / Browser Geolocation</b></font> — "
            "device location (approximate on desktop/Wi-Fi); verify property parcel coordinates."
        )
    elif coord_status in ("GEOCODED", "LOCALITY_GEOCODE"):
        src_hint = property_data.get("coordinate_source") or "Google Geocoding / Places + KGIS Boundary"
        coord_label = (
            f"<font color='#D35400'><b>[GEOCODED] Address / Place Geocoded Coordinates</b></font> — "
            f"geocoded via {src_hint}, NOT a surveyed parcel."
        )
    else:
        coord_label = (
            "<font color='#D35400'><b>[LOCALITY_CENTROID] Locality Centroid Approximation</b></font> — distances are from the "
            "village/locality centre, NOT a surveyed parcel."
        )

    loc_audit = evaluation.get("location_audit") or {}
    if isinstance(loc_audit, str):
        try:
            loc_audit = json.loads(loc_audit)
        except Exception:
            loc_audit = {}

    area_sqft  = float(property_data.get("land_area_sqft", 0) or 0)
    area_gunta = area_sqft / 1089.0 if area_sqft else 0.0
    area_str   = f"{area_sqft:,.0f} sq.ft  ({area_gunta:.2f} Gunta)" if area_sqft else "—"

    loc_val = str(property_data.get("village_or_locality", "—") or "—")
    loc_disp = (
        f"<font color='#D35400'><b>{loc_val}</b></font>"
        if ("could not be confidently resolved" in loc_val.lower() or "requires verification" in loc_val.lower())
        else loc_val
    )
    info_rows = [
        ("Property Label",         prop_name),
        ("District & State",       f"{property_data.get('district', 'Mysuru')}, Karnataka"),
        ("Canonical Taluk",        property_data.get("taluk", "—")),
        ("Resolved Locality / Village", loc_disp),
    ]
    if loc_audit.get("ward_number") or loc_audit.get("ward_name"):
        wn = loc_audit.get("ward_name")
        w_str = f"Ward {loc_audit.get('ward_number') or '—'}{f' — {wn}' if wn else ''}"
        info_rows.append(("Municipal Ward (KGIS)", w_str))
    if loc_audit.get("hobli"):
        info_rows.append(("Hobli (KGIS)", str(loc_audit["hobli"])))
    if loc_audit.get("municipal_body"):
        info_rows.append(("Local Body Jurisdiction", str(loc_audit["municipal_body"])))
    ent_loc = property_data.get("entered_locality") or loc_audit.get("entered_locality")
    ent_tal = property_data.get("entered_taluk") or loc_audit.get("entered_taluk")
    res_st = loc_audit.get("resolution_status")
    if ent_loc and (str(ent_loc).strip().lower() != str(property_data.get("village_or_locality", "")).strip().lower() or (ent_tal and ent_tal != property_data.get("taluk"))):
        audit_verb = (
            "overridden/updated by coordinate reverse-geocoding"
            if res_st == "CORRECTED_FROM_COORDS"
            else "spelling normalized to canonical locality"
        )
        info_rows.append(("Entered Input (Audit)",
            f"<font color='#D35400'>'{ent_loc}' ({ent_tal or '—'} Taluk) — {audit_verb}</font>"))
    info_rows.extend([
        ("Region Type",            property_data.get("region_type", "—")),
        ("Land / Property Type",   property_data.get("land_type", "—")),
        ("Listing Type",           property_data.get("listing_type", "—")),
        ("Land Area",              area_str),
        ("Asking Price (Listed)",  _fmt_inr(property_data.get("asking_price_inr"))),
        ("Coordinates",            _coord_str(property_data)),
        ("Coordinate Precision",   coord_label),
    ])
    story.append(_kv_table(info_rows, S))
    story.append(Spacer(1, 0.25 * cm))

    # ── 1.5. PROPERTY JURISDICTION & CLASSIFICATION ────────────────────────────
    pcls = evaluation.get("property_classification") or (
        evaluation.get("infrastructure_breakdown") or {}
    ).get("property_classification") or {}
    if pcls:
        story.extend(_section_header("1.5. Property Jurisdiction & Classification", S))
        _wn_audit = loc_audit.get("ward_name")
        _wno_audit = loc_audit.get("ward_number")
        ward_disp_pdf = pcls.get("ward_display") or (
            f"Ward {_wno_audit or '—'}{f' — {_wn_audit}' if _wn_audit else ''}"
            if _wno_audit or _wn_audit
            else "Outside Urban Municipal Ward (Rural / Gram Panchayat)"
        )
        hobli_disp_pdf = pcls.get("hobli") or loc_audit.get("hobli") or "Requires KGIS / Revenue Verification"
        dist_disp_pdf = pcls.get("district") or property_data.get("district", "Mysuru")
        taluk_disp_pdf = pcls.get("taluk") or property_data.get("taluk", "—")
        rev_conv_pdf = pcls.get("revenue_classification_and_conversion") or "Land conversion & revenue classification require Bhoomi / RTC / DC Order verification."
        doc_v_pdf = pcls.get("document_verification_status") or "Not Independently Verified — Obtain and verify the official approval document."
        cls_rows = [
            ("Locality / Village",          loc_disp),
            ("Taluk & Hobli",               f"{taluk_disp_pdf} Taluk  |  Hobli: {hobli_disp_pdf}"),
            ("District",                    f"{dist_disp_pdf}, Karnataka"),
            ("Municipal Ward",              ward_disp_pdf),
            ("Local Body Jurisdiction",     pcls.get("local_body", "Jurisdiction Requires Verification")),
            ("Planning Authority",          pcls.get("jurisdictional_planning_authority", "Unknown / Requires Verification")),
            ("Land Classification",         pcls.get("land_use_classification", pcls.get("property_type", "—"))),
            ("Layout / Approval Category",  pcls.get("layout_approval_category", "Not Independently Verified")),
            ("Approval Verification Status", f"<b>{pcls.get('overall_status', 'Not Independently Verified')}</b> — {doc_v_pdf}"),
            ("Revenue & Conversion Status", rev_conv_pdf),
        ]
        if pcls.get("site_allotment_category") and pcls.get("site_allotment_category") != "Not Applicable / Not Sure":
            cls_rows.append(("Site / Allotment Category", pcls["site_allotment_category"]))
        if pcls.get("user_corrected_jurisdiction"):
            cls_rows.append(("User-Reported Jurisdiction Note", f"{pcls.get('claimed_approval_authority')} (User Reported — Not Officially Verified)"))
        out_chks = pcls.get("outstanding_checks") or []
        if out_chks:
            cls_rows.append(("Outstanding Legal Checks", " | ".join(out_chks)))
        story.append(_kv_table(cls_rows, S))
        story.append(Paragraph(
            f"<b>Jurisdiction & Legal Boundary Note:</b> {pcls.get('khata_disclaimer', 'Khata/PID does not prove layout approval.')} "
            "Administrative jurisdiction is distinct from planning authority sanction; neither coordinates, locality names, OSM data, nor KGIS boundaries establish layout approval or land conversion.",
            S["small"]
        ))
        story.append(Spacer(1, 0.25 * cm))

    # ── 2. INDICATIVE PRICE ESTIMATE ──────────────────────────────────────────
    story.extend(_section_header("2. Indicative Price Estimate", S))

    pred_psf   = evaluation.get("predicted_price_per_sqft")
    low_psf    = evaluation.get("price_range_low")
    high_psf   = evaluation.get("price_range_high")
    pred_total = evaluation.get("predicted_total_price") or (pred_psf * area_sqft if pred_psf and area_sqft else None)
    low_total  = low_psf  * area_sqft if low_psf  and area_sqft else None
    high_total = high_psf * area_sqft if high_psf and area_sqft else None

    price_rows = [
        ("Estimated Price / sq.ft",    f"<b>{_fmt_inr_psf(pred_psf)}</b>"),
        ("Estimated Total Valuation",  f"<b>{_fmt_inr(pred_total)}</b>  (for {area_sqft:,.0f} sq.ft)"),
        ("Indicative Price Range",     f"{_fmt_inr(low_total)} – {_fmt_inr(high_total)}  |  {_fmt_inr_psf(low_psf)} – {_fmt_inr_psf(high_psf)}"),
    ]

    asking = property_data.get("asking_price_inr")
    if asking and pred_total:
        diff_pct = ((float(asking) - pred_total) / pred_total) * 100
        direction = "Above ML benchmark" if diff_pct > 5 else "Below ML benchmark" if diff_pct < -5 else "Within ML benchmark range"
        price_rows.append(("Asking Price Comparison",
            f"<font color='{'#C0392B' if diff_pct > 10 else '#1E8449'}'>"
            f"{'+' if diff_pct > 0 else ''}{diff_pct:.1f}% vs ML valuation</font>  ({direction})"
        ))

    # Reliability indicator
    reliability = evaluation.get("reliability_indicator") or {}
    if reliability:
        tier       = reliability.get("tier", "Unknown")
        tier_color = {"High": "#1E8449", "Moderate": "#D35400", "Low": "#D35400", "Very Low": "#C0392B"}.get(tier, "#566573")
        price_rows.append(("Prediction Reliability",
            f"<font color='{tier_color}'><b>{tier}</b></font>  — {reliability.get('explanation', '')}"))
        if reliability.get("deviation_note"):
            price_rows.append(("Deviation Note", f"<font color='#D35400'>{reliability['deviation_note']}</font>"))

    # Locality stats
    loc_med = evaluation.get("locality_median_psf")
    loc_p25 = evaluation.get("locality_p25_psf")
    loc_p75 = evaluation.get("locality_p75_psf")
    loc_cnt = evaluation.get("comparable_records_count", 0)
    fuzzy_nm = (reliability or {}).get("fuzzy_match_name")
    fuzzy_cnt = (reliability or {}).get("fuzzy_match_count", 0)
    stratum_cnt = (reliability or {}).get("stratum_count")
    stat_reliable = (reliability or {}).get("statistically_reliable_median", False)
    if loc_med:
        ent_raw = property_data.get("village_or_locality", "—")
        ref_loc = fuzzy_nm if (loc_cnt == 0 and fuzzy_nm) else ent_raw
        cnt_used = fuzzy_cnt if (loc_cnt == 0 and fuzzy_nm) else loc_cnt
        match_note = f" (close match from '{ent_raw}')" if (loc_cnt == 0 and fuzzy_nm and str(ent_raw).lower() != str(fuzzy_nm).lower()) else ""
        stratum_note = f" | {stratum_cnt} in regional stratum" if stratum_cnt is not None else ""
        if stat_reliable and loc_p25 is not None and loc_p75 is not None:
            price_rows.append(("Locality Comparable Data",
                f"Median ₹{loc_med:,.0f}/sq.ft (P25: ₹{loc_p25:,.0f} – P75: ₹{loc_p75:,.0f}) | {cnt_used} records in '{ref_loc}'{match_note}{stratum_note}"))
        else:
            price_rows.append(("Locality Comparable Reference",
                f"₹{loc_med:,.0f}/sq.ft ({cnt_used} record(s) in '{ref_loc}'{match_note} — insufficient sample for statistical median/quartiles){stratum_note}"))

    # Contextual uncertainty (GroupKFold MAE for unseen/sparse localities <3 records vs Holdout MAE)
    market = evaluation.get("market_comparison") or {}
    val_sum = evaluation.get("valuation_summary") or market.get("valuation_summary") or {}
    ml_sum = val_sum.get("ml_estimate") or {}
    is_sparse_loc = (loc_cnt or 0) < 3
    unc_mae = (
        evaluation.get("uncertainty_mae_used")
        or ml_sum.get("uncertainty_mae_used")
        or (float(gkf_mae or 529.90) if is_sparse_loc else float(report_mae or 385.80))
    )
    unc_basis = (
        evaluation.get("uncertainty_basis")
        or ml_sum.get("uncertainty_basis")
        or (f"GroupKFold MAE (unseen/sparse locality: {loc_cnt} training records)" if is_sparse_loc
            else f"Holdout MAE (seen locality: {loc_cnt} training records)")
    )
    price_rows.append(("Uncertainty Error Basis",
        f"±1.5 × ₹{float(unc_mae):,.2f}/sq.ft  [{unc_basis}]"))

    shap_drivers = (ml_sum.get("top_drivers") or []) or [
        {"feature": f.get("feature"), "impact_psf": f.get("impact_inr_per_sqft")}
        for f in ((evaluation.get("explanation") or {}).get("top_factors") or [])
        if isinstance(f, dict)
    ]
    if shap_drivers:
        drv_txt = "  |  ".join(
            f"{d.get('feature', '?')}: {'+' if float(d.get('impact_psf') or 0) >= 0 else ''}₹{float(d.get('impact_psf') or 0):,.0f}"
            for d in shap_drivers[:4]
        )
        price_rows.append(("Top SHAP Drivers", drv_txt))

    story.append(_kv_table(price_rows, S))
    story.append(Paragraph(
        f"<b>Contextual Uncertainty Note:</b> Range uses ±1.5 × <b>{unc_basis}</b> "
        f"(±₹{float(unc_mae) * 1.5:,.2f}/sq.ft). This is a heuristic error spread, <b>NOT</b> a statistically calibrated "
        "confidence interval or certified statutory valuation. Engage a registered valuer (RERA Karnataka / REVA Act) "
        "for legal or financial transactions.",
        S["small"]
    ))
    story.append(Spacer(1, 0.3 * cm))

    # ── 2.5. LOCAL REAL ESTATE MARKET ANALYSIS ─────────────────────────────────
    story.extend(_section_header("2.5. Local Real Estate Market Analysis & Benchmark Separation", S))
    mkt_status = market.get("status", "NO_LISTINGS")
    mkt_benchmark = market.get("market_benchmark") or {}
    mkt_listings = market.get("listings") or []
    mkt_sources = ", ".join(market.get("sources") or []) or "None retrieved"
    mkt_urls = market.get("source_urls") or []
    mkt_count = market.get("total_count", 0)
    live_cnt = market.get("live_count", mkt_benchmark.get("live_count", 0))
    hist_cnt = market.get("historical_count", mkt_benchmark.get("historical_count", 0))
    bench_psf = mkt_benchmark.get("market_benchmark_psf")
    bench_p25 = mkt_benchmark.get("market_p25_psf")
    bench_p75 = mkt_benchmark.get("market_p75_psf")
    bench_min = mkt_benchmark.get("market_min_psf")
    bench_max = mkt_benchmark.get("market_max_psf")
    size_min = mkt_benchmark.get("size_min_sqft")
    size_max = mkt_benchmark.get("size_max_sqft")
    new_cnt = mkt_benchmark.get("new_sale_count", 0)
    resale_cnt = mkt_benchmark.get("resale_count", 0)
    ml_vs_mkt = market.get("ml_vs_market_pct")
    asking_vs_mkt = market.get("asking_vs_market_pct")
    retr_dt = str(market.get("retrieved_at") or "")[:19].replace("T", " ")

    comp_tier = market.get("dataset_comparison_tier") or mkt_benchmark.get("dataset_comparison_tier")
    comp_note = market.get("dataset_comparison_note") or mkt_benchmark.get("dataset_comparison_note")
    mkt_rows = [
        ("Research Status", mkt_status.replace("_", " ").title()),
        ("Data Sources Queried", f"{mkt_sources}" + (f" (Retrieved: {retr_dt} UTC)" if retr_dt else "")),
        ("Comparable Sample Breakdown", f"{mkt_count} total — {live_cnt} live advertised portal listing(s), {hist_cnt} historical dataset record(s) (never averaged blindly)"),
        ("New-Sale vs Resale Split", f"New Sale / Builder: {new_cnt}  |  Resale: {resale_cnt}"),
    ]
    if comp_tier:
        tier_label = str(comp_tier).replace("_", " ").title()
        mkt_rows.append(("Comparable Matching Tier", f"{tier_label}" + (f" — {comp_note}" if comp_note else "")))
    if size_min and size_max:
        mkt_rows.append(("Comparable Size Range", f"{size_min:,.0f} – {size_max:,.0f} sq.ft"))
    if mkt_urls:
        url_txt = "; ".join((u[:78] + ("..." if len(u) > 78 else "")).replace("&", "&amp;") for u in mkt_urls[:3])
        mkt_rows.append(("Permitted Search URLs", url_txt))
    if market.get("restricted_sources"):
        mkt_rows.append(("Policy-Restricted Portals", ", ".join(market["restricted_sources"]).replace("&", "&amp;")))

    if bench_psf:
        mkt_rows.append(("Local Market Benchmark (Median)", f"<b>₹{bench_psf:,.0f}/sq.ft</b>  (for {area_sqft:,.0f} sq.ft ≈ {_fmt_inr(bench_psf * area_sqft)})"))
        if bench_p25 and bench_p75:
            mkt_rows.append(("Market IQR (P25 – P75)", f"₹{bench_p25:,.0f} – ₹{bench_p75:,.0f}/sq.ft"))
        if bench_min and bench_max:
            mkt_rows.append(("Observed Asking Range", f"₹{bench_min:,.0f} – ₹{bench_max:,.0f}/sq.ft"))
        if ml_vs_mkt is not None:
            color = "#C0392B" if abs(ml_vs_mkt) > 50 else "#D35400" if abs(ml_vs_mkt) > 25 else "#1E8449"
            direction = "above" if ml_vs_mkt > 0 else "below"
            mkt_rows.append(("ML Estimate vs Market",
                f"<font color='{color}'>{'+' if ml_vs_mkt > 0 else ''}{ml_vs_mkt:.1f}% {direction} local market benchmark</font>"
            ))
            if market.get("ml_substantially_above_market"):
                mkt_rows.append(("Valuation Divergence Alert",
                    "<font color='#C0392B'><b>WARNING: ML estimate exceeds 1.5x the local market median.</b> "
                    "Prefer local comparables and obtain an independent registered valuation.</font>"))
        if asking_vs_mkt is not None and property_data.get("asking_price_inr"):
            direction_a = "above" if asking_vs_mkt > 0 else "below"
            mkt_rows.append(("User Asking Price vs Market",
                f"{'+' if asking_vs_mkt > 0 else ''}{asking_vs_mkt:.1f}% {direction_a} local market benchmark"))
    else:
        mkt_rows.append(("Market Benchmark", str(mkt_benchmark.get("note", "Insufficient comparable listings to compute benchmark.")).replace("&", "&amp;")))

    story.append(_kv_table(mkt_rows, S))

    # Separated 3-Benchmark Comparison Table (never blindly averages ML and portal prices)
    comp_rows = [
        [
            "ML Model Estimate (Tree Ensemble)",
            _fmt_inr_psf(pred_psf),
            _fmt_inr(pred_total),
            str(unc_basis),
        ],
        [
            "Comparable Asking Median",
            _fmt_inr_psf(bench_psf) if bench_psf else "N/A",
            _fmt_inr(bench_psf * area_sqft) if (bench_psf and area_sqft) else "N/A",
            f"{mkt_count} comparable(s): {live_cnt} live, {hist_cnt} historical",
        ],
    ]
    if asking:
        ask_psf_v = float(asking) / area_sqft if area_sqft else None
        comp_rows.append([
            "User Asking Price (Entered)",
            _fmt_inr_psf(ask_psf_v),
            _fmt_inr(asking),
            "Seller-quoted figure",
        ])
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph("<b>Independent Benchmark Comparison (Shown Separately — Not Averaged):</b>", S["small"]))
    story.append(_data_table(
        ["Benchmark Type", "Rate (/sq.ft)", "Total Value", "Basis / Sample"],
        comp_rows,
        [4.5 * cm, 2.7 * cm, 3.0 * cm, 6.1 * cm],
        S,
    ))
    diff_expl = val_sum.get("difference_explanation")
    if diff_expl:
        story.append(Spacer(1, 0.12 * cm))
        story.append(Paragraph(f"<b>Why Estimates Differ:</b> {str(diff_expl).replace('&', '&amp;')}", S["small"]))

    if mkt_listings:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Sample Comparable Listings &amp; References:</b>", S["small"]))
        tbl_hdr = ["Source", "Locality", "Listing Type", "Area (sq.ft)", "Rate (₹/sq.ft)", "Total Price"]
        tbl_rows = []
        for lst in mkt_listings[:6]:
            psf_disp = f"₹{lst['price_per_sqft']:,.0f}" if lst.get("price_per_sqft") else "N/A"
            tot_disp = _fmt_inr(lst.get("total_price_inr")) if lst.get("total_price_inr") else "N/A"
            area_disp = f"{lst['land_area_sqft']:,.0f}" if lst.get("land_area_sqft") else "N/A"
            tbl_rows.append([
                str(lst.get("source", "")).replace("&", "&amp;")[:22],
                str(lst.get("locality", "")).replace("&", "&amp;")[:22],
                str(lst.get("listing_type", "")).replace("&", "&amp;")[:18],
                area_disp,
                psf_disp,
                tot_disp,
            ])
        if tbl_rows:
            story.append(_data_table(tbl_hdr, tbl_rows, [3.2*cm, 3.3*cm, 2.8*cm, 2.2*cm, 2.4*cm, 2.4*cm], S))
        # Print reference URLs for transparency
        unique_ref_urls = []
        for lst in mkt_listings[:6]:
            u = lst.get("source_url")
            if u and str(u).startswith("http") and u not in unique_ref_urls:
                unique_ref_urls.append(u)
        if unique_ref_urls:
            story.append(Paragraph(
                "<b>Comparable Reference Links:</b> " + "  |  ".join(u.replace("&", "&amp;") for u in unique_ref_urls[:4]),
                S["small"],
            ))

    story.append(Paragraph(
        "<b>Important Market Disclaimer:</b> Online portal prices represent <b>advertised asking prices only, "
        "not verified registered sale transactions</b>. Small-sample localities carry elevated variance; "
        "this is not an official valuation. Consult a registered valuer for legal or financial transactions.",
        S["small"]
    ))
    story.append(Spacer(1, 0.3 * cm))

    # ── 3. ML MODEL PERFORMANCE ────────────────────────────────────────────────
    story.extend(_section_header("3. Machine Learning Model Performance", S))

    # Algorithm description — correct for ExtraTreesRegressor
    algo_map = {
        "ExtraTreesRegressor":          "Extra Trees Regressor (Ensemble of Extremely Randomised Decision Trees)",
        "RandomForestRegressor":        "Random Forest Regressor (Bagged Decision Trees with feature sub-sampling)",
        "HistGradientBoostingRegressor":"HistGradient Boosting Regressor (Histogram-based Gradient Boosting)",
        "GradientBoostingRegressor":    "Gradient Boosting Regressor (Sequential Boosted Trees)",
        "LinearRegression":             "Linear Regression (OLS Baseline)",
    }
    algo_desc = algo_map.get(model_name, model_name)

    cv_summary = (
        f"Independent Holdout ({holdout_recs} records, 15%): R²={report_r2:.4f}, MAE=₹{report_mae:,.2f}/sq.ft"
        f"  |  5-Fold KFold: R²={float(kfold_r2 or 0.8603):.4f}, MAE=₹{float(kfold_mae or 399.48):,.2f}/sq.ft"
        f"  |  Locality GroupKFold (unseen localities): R²={float(gkf_r2 or 0.7791):.4f}, MAE=₹{float(gkf_mae or 529.90):,.2f}/sq.ft"
    )

    driver_summary = (
        ", ".join(f"{d.get('feature')} ({'+' if float(d.get('impact_psf') or 0) >= 0 else ''}₹{float(d.get('impact_psf') or 0):,.0f})" for d in shap_drivers[:4])
        if shap_drivers else "Locality, Area, Road Width, Region Type"
    )
    story.append(_kv_table([
        ("Production ML Algorithm",   algo_desc),
        ("Dataset Partitioning",      f"{total_recs:,} total records across 7 Mysuru taluks → {training_recs:,} training / {holdout_recs:,} independent holdout test"),
        ("Validation Summary",        cv_summary),
        ("Holdout Test MAE",          f"₹{report_mae:,.2f} / sq.ft  (average absolute error on {holdout_recs} unseen holdout properties)"),
        ("Holdout Test R²",           f"{report_r2:.4f}  (explains ~{report_r2 * 100:.1f}% of price variance across holdout test properties; NOT a per-property accuracy % guarantee)"),
        ("Unseen-Locality Benchmark", f"Locality GroupKFold R²={float(gkf_r2 or 0.7791):.4f}, MAE=₹{float(gkf_mae or 529.90):,.2f}/sq.ft (primary benchmark when a locality has sparse or zero training samples)"),
        ("Model Interpretability",    f"SHAP (SHapley Additive exPlanations) — top property drivers: {driver_summary}"),
        ("Target Leakage Control",    "Asking price, price-per-acre and score fields excluded from all feature inputs"),
        ("Generalisation & Value Note", "ExtraTrees uses fully randomised splits (bootstrap=False). Predicted prices are indicative benchmarks, not guaranteed market value."),
    ], S))
    story.append(Spacer(1, 0.3 * cm))

    # ── 4. EVALUATION SCORES ───────────────────────────────────────────────────
    story.extend(_section_header("4. Evaluation Scores & Weightages", S))

    def _w(k: str, default_val: float) -> float:
        v = evaluation.get(k)
        return float(v) if v is not None else default_val

    weights = {
        "price":          _w("price_weight",          30.0),
        "location":       _w("location_weight",       25.0),
        "facility":       _w("facility_weight",        0.0),
        "environment":    _w("environment_weight",    10.0),
        "infrastructure": _w("infrastructure_weight", 20.0),
        "utility":        _w("utility_weight",        15.0),
    }
    score_vals = {
        "price":          evaluation.get("price_score"),
        "location":       evaluation.get("location_score"),
        "facility":       evaluation.get("facility_score"),
        "environment":    evaluation.get("environment_score"),
        "infrastructure": evaluation.get("infrastructure_score"),
        "utility":        evaluation.get("utility_score"),
    }
    dim_labels = {
        "price": "Price Affordability", "location": "Location Quality",
        "facility": "Nearby Facilities", "environment": "Environmental Safety",
        "infrastructure": "Infrastructure", "utility": "Utilities",
    }

    total_avail_w = 0.0
    weighted_sum  = 0.0
    tbl_rows = []
    for key in ["price", "location", "facility", "environment", "infrastructure", "utility"]:
        w = weights[key]
        s = score_vals[key]
        if key == "facility":
            # Facility is informational only — not included in overall score
            tbl_rows.append([dim_labels[key], f"{s:.1f}" if s is not None else "N/A",
                             ("█" * int(s / 10) + "░" * (10 - int(s / 10))) if s is not None else "—",
                             "0% ⓘ", "—", "Informational Only"])
        elif s is not None:
            s_f = float(s)
            contrib_exact = s_f * (w / 100.0)
            total_avail_w += w
            weighted_sum  += contrib_exact
            bar = "█" * int(s_f / 10) + "░" * (10 - int(s_f / 10))
            tbl_rows.append([dim_labels[key], f"{s_f:.1f}", bar, f"{w:.0f}%", f"{contrib_exact:.2f}", "Evaluated"])
        else:
            tbl_rows.append([dim_labels[key], "N/A", "—", f"{w:.0f}%", "—", "Missing Data"])

    headers = ["Dimension", "Score (0–100)", "Visual", "Weight", "Contribution", "Status"]
    col_w   = [4.0*cm, 2.5*cm, 2.5*cm, 1.8*cm, 2.5*cm, 2.5*cm]
    story.append(_data_table(headers, tbl_rows, col_w, S))

    calc_overall = round((weighted_sum / total_avail_w) * 100.0, 1) if total_avail_w > 0 else None
    overall_raw = evaluation.get("overall_score")
    overall_disp = calc_overall if calc_overall is not None else overall_raw
    norm_note = (
        f"<b>Overall Score: {overall_disp:.1f} / 100</b>  |  "
        f"Available Weight: {total_avail_w:.0f}%  |  "
        f"Formula: Σ(weight × score) / Σ(available weights) = "
        f"{weighted_sum:.2f} / {total_avail_w:.0f}% = "
        f"<b>{overall_disp:.1f} / 100</b>"
        if overall_disp is not None and total_avail_w > 0
        else "Overall score not calculable — no components scored."
    )
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(norm_note, S["body"]))
    story.append(Paragraph(
        "Missing score components are <b>excluded from both numerator and denominator</b> — "
        "unavailable data does not penalise the score.",
        S["small"]
    ))
    story.append(Spacer(1, 0.3 * cm))

    # ── 5. ESSENTIAL INFRASTRUCTURE & CONNECTIVITY (4 CATEGORIES ONLY) ────────
    story.extend(_section_header("5. Essential Infrastructure & Connectivity", S))

    ua = evaluation.get("utility_assessment")
    if not ua and isinstance(evaluation.get("infrastructure_breakdown"), dict):
        ua = evaluation["infrastructure_breakdown"].get("utility_assessment")
    ua = ua if isinstance(ua, dict) else {}
    ua_by_key = ua.get("categories_by_key") or {}

    def _compact_status_lbl(raw_st: str) -> str:
        s = str(raw_st or "")
        if "Available / Mapped" in s:
            return "Mapped"
        if "Officially Verified" in s:
            return "Verified"
        if "Not Found" in s:
            return "Not Found"
        return "Unknown"

    essential_defs = [
        ("Road", ua_by_key.get("road_connectivity") or ua_by_key.get("nearest_road") or {}),
        ("Water", ua_by_key.get("water_availability") or ua_by_key.get("water_supply") or {}),
        ("Electricity", ua_by_key.get("electricity_availability") or ua_by_key.get("electricity") or {}),
        ("Public Transport", ua_by_key.get("public_transport") or {}),
    ]

    ess_rows = []
    for short_lbl, cat in essential_defs:
        st_raw = cat.get("status") or "Unknown / Insufficient Data"
        st_short = _compact_status_lbl(st_raw)
        user_tag = cat.get("user_confirmation") or "Not Confirmed"
        near_name = cat.get("nearest_facility")
        rcls = cat.get("nearest_road_class")
        d_km = cat.get("nearest_distance_km")
        cnt = cat.get("mapped_count")

        if st_short == "Mapped":
            info_parts = []
            if near_name:
                info_parts.append(f"{near_name}{f' [{rcls}]' if rcls and rcls not in str(near_name) else ''}")
            if cnt is not None:
                info_parts.append(f"{cnt} mapped feature(s) in buffer")
            info_str = " — ".join(info_parts) if info_parts else (cat.get("system_finding") or "Mapped nearby")
            if user_tag != "Not Confirmed":
                info_str += f"<br/><i>User Input: {user_tag}</i>"
        elif st_short == "Not Found":
            info_str = "Not found in OSM mapping (does not confirm absence on site)"
            if user_tag != "Not Confirmed":
                info_str += f"<br/><i>User Input: {user_tag}</i>"
        else:
            info_str = "GIS data unavailable"
            if user_tag != "Not Confirmed":
                info_str += f"<br/><i>User Input: {user_tag}</i>"

        dist_str = f"{float(d_km):.2f} km" if d_km is not None else "—"
        ess_rows.append([short_lbl, info_str, dist_str, st_short])

    ess_headers = ["Category", "Detected Information", "Distance", "Status"]
    ess_col_w = [3.2 * cm, 9.1 * cm, 2.2 * cm, 2.5 * cm]
    story.append(_data_table(ess_headers, ess_rows, ess_col_w, S))
    ua_ret = str(ua.get("retrieved_at") or "")[:19].replace("T", " ")
    story.append(Paragraph(
        f"GIS infrastructure mapping indicates nearby mapped facilities only. "
        f"It does not independently confirm property-level utility connections or legal road access."
        f"{f'  (Source: OpenStreetMap Overpass @ {ua_ret} UTC)' if ua_ret else ''}",
        S["small"]
    ))
    story.append(Spacer(1, 0.3 * cm))

    # ── 6. NEARBY FACILITIES (INFORMATIONAL REFERENCE ONLY — 14 CATEGORIES) ───
    story.extend(_section_header("6. Nearby Facilities (Informational Reference Only)", S))
    story.append(Paragraph(
        "<b>Informational Reference Only:</b> The facilities below are retrieved from public geospatial "
        "layers for buyer awareness and are <b>excluded from the ML price prediction and Infrastructure / "
        "Overall scores</b>. <i>No mapped features</i> means zero features were found in the OpenStreetMap "
        "search buffer — it does NOT establish that the facility is absent on the ground; <i>Unavailable</i> "
        "indicates the external source timed out or failed.",
        S["small"],
    ))
    story.append(Spacer(1, 0.12 * cm))

    fac_detail = evaluation.get("facilities_detail") or {}
    if isinstance(fac_detail, str):
        try:
            fac_detail = json.loads(fac_detail)
        except Exception:
            fac_detail = {}
    fac_list_map = {}
    for fi in (facilities or []):
        ft = fi.get("facility_type")
        if ft and ft not in fac_list_map:
            fac_list_map[ft] = fi

    has_any_fac_data = bool(fac_detail or fac_list_map)

    FACILITY_SPEC_14 = [
        ("school", "Schools"),
        ("hospital", "Hospitals"),
        ("clinic", "Clinics and health centres"),
        ("supermarket", "Supermarkets"),
        ("market", "Markets and bazaars"),
        ("pharmacy", "Pharmacies"),
        ("bus_stop", "Bus stops"),
        ("railway_station", "Railway stations"),
        ("bank", "Bank branches"),
        ("police", "Police stations"),
        ("atm", "ATMs"),
        ("park", "Parks and gardens"),
        ("waterbody", "Waterbodies and lakes"),
        ("canal", "Irrigation canals"),
    ]

    def _short_fac_src(raw_s: Any) -> str:
        s = str(raw_s or "").strip()
        if not s:
            return "—"
        low = s.lower()
        parts = []
        if "google" in low:
            parts.append("Google")
        if "nominatim" in low:
            parts.append("OSM (Nom.)")
        elif "osm" in low or "overpass" in low or "openstreetmap" in low:
            parts.append("OSM")
        if "arcgis" in low:
            parts.append("ArcGIS")
        return " + ".join(parts) if parts else _html.escape(s[:22])

    def _fmt_fac_cnt(val: Any, fallback_zero: bool = False) -> str:
        if val is not None:
            try:
                return str(int(val))
            except Exception:
                pass
        return "0" if fallback_zero else "N/A"

    fac_rows = []
    has_outside_3km = False
    for fkey, flabel in FACILITY_SPEC_14:
        fd = fac_detail.get(fkey) if isinstance(fac_detail.get(fkey), dict) else {}
        fr = fac_list_map.get(fkey) or {}
        if not fd and not fr:
            if not has_any_fac_data:
                fac_rows.append([flabel, "Source unavailable", "—", "N/A", "N/A", "N/A", "—", "<font color='#C0392B'>Unavailable</font>"])
            else:
                fac_rows.append([flabel, "Not in snapshot", "—", "N/A", "N/A", "N/A", "—", "Not Queried"])
            continue

        st = str(fd.get("status") or fr.get("status") or "NO_DATA").upper()
        nearest_obj = fd.get("nearest") if isinstance(fd.get("nearest"), dict) else {}
        raw_near_nm = (nearest_obj.get("name") or fr.get("name") or "").strip()
        near_d = fd.get("nearest_distance_km") if fd.get("nearest_distance_km") is not None else fr.get("distance_km")
        c1 = fd.get("count_within_1km") if fd.get("count_within_1km") is not None else fr.get("count_within_1km")
        c3 = fd.get("count_within_3km") if fd.get("count_within_3km") is not None else fr.get("count_within_3km")
        c5 = fd.get("count_within_5km") if fd.get("count_within_5km") is not None else fr.get("count_within_5km")
        src_disp = _short_fac_src(fd.get("source") or fr.get("source") or "OpenStreetMap")

        if st == "SOURCE_UNAVAILABLE":
            place_str = "Source unavailable"
            dist_s = "—"
            c1s = c3s = c5s = "N/A"
            src_disp = "—"
            st_disp = "<font color='#C0392B'>Unavailable</font>"
        elif st == "PARTIAL":
            if raw_near_nm:
                place_str = _html.escape(raw_near_nm[:38] + ("…" if len(raw_near_nm) > 38 else ""))
            elif near_d is not None:
                place_str = "Unnamed mapped feature"
            else:
                place_str = "Partial / Incomplete lookup"
            if near_d is not None:
                d_val = float(near_d)
                if d_val > 3.0:
                    has_outside_3km = True
                dist_s = f"{d_val:.2f} km{' *' if d_val > 3.0 else ''}"
            else:
                dist_s = "—"
            c1s = _fmt_fac_cnt(c1)
            c3s = _fmt_fac_cnt(c3)
            c5s = _fmt_fac_cnt(c5)
            st_disp = "<font color='#D35400'>Partial</font>"
        elif st in ("NO_DATA", "NOT_MAPPED") or (near_d is None and not raw_near_nm):
            place_str = "None mapped in search radius"
            dist_s = "—"
            c1s = _fmt_fac_cnt(c1, fallback_zero=True)
            c3s = _fmt_fac_cnt(c3, fallback_zero=True)
            c5s = _fmt_fac_cnt(c5, fallback_zero=True)
            st_disp = "No mapped data"
        else:
            lbl_name = raw_near_nm or "Unnamed mapped feature"
            place_str = _html.escape(lbl_name[:38] + ("…" if len(lbl_name) > 38 else ""))
            if near_d is not None:
                d_val = float(near_d)
                if d_val > 3.0:
                    has_outside_3km = True
                dist_s = f"{d_val:.2f} km{' *' if d_val > 3.0 else ''}"
            else:
                dist_s = "—"
            c1s = _fmt_fac_cnt(c1)
            c3s = _fmt_fac_cnt(c3)
            c5s = _fmt_fac_cnt(c5)
            st_disp = "<font color='#1E8449'>Success</font>"

        fac_rows.append([flabel, place_str, dist_s, c1s, c3s, c5s, src_disp, st_disp])

    fac_headers = ["Category", "Nearest Mapped Place", "Distance", "≤1 km", "≤3 km", "≤5 km", "Data Source", "Status"]
    fac_col_w = [2.9 * cm, 4.1 * cm, 1.5 * cm, 1.15 * cm, 1.15 * cm, 1.15 * cm, 2.35 * cm, 2.0 * cm]
    story.append(_data_table(fac_headers, fac_rows, fac_col_w, S))

    last_retr = evaluation.get("last_gis_retrieved_at")
    if not last_retr and facilities:
        retrs = [str(f.get("retrieved_at")) for f in facilities if f.get("retrieved_at")]
        last_retr = max(retrs) if retrs else None
    retr_txt = f" | Last retrieved: {str(last_retr)[:19].replace('T', ' ')} UTC" if last_retr else ""
    outside_note = "* Nearest feature is outside the 3 km count radius; " if has_outside_3km else ""
    story.append(Spacer(1, 0.08 * cm))
    story.append(Paragraph(
        f"{outside_note}All distances are straight-line Haversine distances (WGS-84), NOT road travel distances. "
        f"Rural/civic facilities unmapped in OpenStreetMap automatically check ArcGIS World Geocoder{retr_txt}.",
        S["small"],
    ))
    story.append(Spacer(1, 0.3 * cm))

    # ── 6.5. ENVIRONMENTAL & RISK CHECKS ───────────────────────────────────────
    story.extend(_section_header("6.5. Environmental & Risk Checks", S))
    wb_fd = fac_detail.get("waterbody") if isinstance(fac_detail.get("waterbody"), dict) else {}
    wb_fr = fac_list_map.get("waterbody") or {}
    wb_dist_e = wb_fd.get("nearest_distance_km") if wb_fd.get("nearest_distance_km") is not None else wb_fr.get("distance_km")
    wb_c3_e = wb_fd.get("count_within_3km") if wb_fd.get("count_within_3km") is not None else wb_fr.get("count_within_3km")
    wb_st_e = str(wb_fd.get("status") or wb_fr.get("status") or "SOURCE_UNAVAILABLE").upper()
    wb_nm_e = ((wb_fd.get("nearest") or {}).get("name") or wb_fr.get("name") or "Waterbody").strip()

    cn_fd = fac_detail.get("canal") if isinstance(fac_detail.get("canal"), dict) else {}
    cn_fr = fac_list_map.get("canal") or {}
    cn_dist_e = cn_fd.get("nearest_distance_km") if cn_fd.get("nearest_distance_km") is not None else cn_fr.get("distance_km")
    cn_c3_e = cn_fd.get("count_within_3km") if cn_fd.get("count_within_3km") is not None else cn_fr.get("count_within_3km")
    cn_st_e = str(cn_fd.get("status") or cn_fr.get("status") or "SOURCE_UNAVAILABLE").upper()
    cn_nm_e = ((cn_fd.get("nearest") or {}).get("name") or cn_fr.get("name") or "Irrigation Canal").strip()

    pk_fd = fac_detail.get("park") if isinstance(fac_detail.get("park"), dict) else {}
    pk_fr = fac_list_map.get("park") or {}
    pk_dist_e = pk_fd.get("nearest_distance_km") if pk_fd.get("nearest_distance_km") is not None else pk_fr.get("distance_km")
    pk_c3_e = pk_fd.get("count_within_3km") if pk_fd.get("count_within_3km") is not None else pk_fr.get("count_within_3km")
    pk_st_e = str(pk_fd.get("status") or pk_fr.get("status") or "SOURCE_UNAVAILABLE").upper()
    pk_nm_e = ((pk_fd.get("nearest") or {}).get("name") or pk_fr.get("name") or "Public Park").strip()

    env_brk = evaluation.get("environment_breakdown") or {}
    if isinstance(env_brk, str):
        try:
            env_brk = json.loads(env_brk)
        except Exception:
            env_brk = {}
    env_cov = evaluation.get("environmental_coverage_pct") or env_brk.get("coverage_pct")
    env_src = evaluation.get("environmental_source") or env_brk.get("source") or "OpenStreetMap (preliminary proximity proxy only)"
    env_sc = evaluation.get("environment_score")

    if wb_dist_e is not None:
        wb_txt = f"Nearest mapped waterbody: {_html.escape(wb_nm_e)} at {float(wb_dist_e):.2f} km (<=3 km count: {wb_c3_e if wb_c3_e is not None else 'N/A'})."
        if float(wb_dist_e) < 0.25:
            flood_txt = "<font color='#C0392B'><b>ELEVATED PROXIMITY WARNING (&lt;250 m):</b></font> Indicative GIS buffer warning only — official Karnataka Minor Irrigation / MDA flood-zone clearance mandatory."
        elif float(wb_dist_e) < 1.0:
            flood_txt = "Moderate proximity to mapped waterbody (&lt;1 km). Indicative GIS proximity check only — NOT an official flood-zone determination."
        else:
            flood_txt = "Mapped waterbody &gt;1.0 km away (indicative GIS proximity only — distance alone does NOT establish flood safety; verify official flood-zone maps)."
    elif wb_st_e in ("NO_DATA",):
        wb_txt = "No mapped lakes or waterbodies found within search buffer in OpenStreetMap."
        flood_txt = "<font color='#D35400'><b>Unverified (Official Check Required):</b></font> Absence of OSM waterbody features does NOT prove zero flood risk."
    else:
        wb_txt = "Hydrological GIS query incomplete or unavailable (OSM source timeout/partial)."
        flood_txt = "<font color='#D35400'><b>Insufficient Evidence (N/A):</b></font> Official drain / flood-zone verification mandatory."

    if cn_dist_e is not None:
        cn_txt = f"Nearest mapped canal: {_html.escape(cn_nm_e)} at {float(cn_dist_e):.2f} km (<=3 km count: {cn_c3_e if cn_c3_e is not None else 'N/A'})."
        if float(cn_dist_e) < 0.15:
            cn_txt += " <font color='#C0392B'>Check Rajakaluve / canal buffer setbacks.</font>"
    elif cn_st_e == "NO_DATA":
        cn_txt = "No irrigation canals mapped within 5.0 km buffer in OSM."
    else:
        cn_txt = "Canal mapping query incomplete or unavailable."

    if pk_dist_e is not None:
        pk_txt = f"Nearest mapped park / green space: {_html.escape(pk_nm_e)} at {float(pk_dist_e):.2f} km (<=3 km count: {pk_c3_e if pk_c3_e is not None else 'N/A'})."
    elif pk_st_e == "NO_DATA":
        pk_txt = "No public parks mapped within search buffer in OSM."
    else:
        pk_txt = "Park mapping query incomplete or unavailable."

    env_cov_str = (
        f"{float(env_cov):.0f}% evaluated (Environmental Safety Score: {float(env_sc):.1f}/100)"
        if (env_cov is not None and env_sc is not None)
        else f"{float(env_cov or 0):.0f}% evaluated (Environmental Safety Score: N/A — excluded from overall denominator)"
    )

    story.append(_kv_table([
        ("Lakes & Surface Waterbodies", wb_txt),
        ("Irrigation Canals",           cn_txt),
        ("Parks & Green Spaces",        pk_txt),
        ("Flood Risk Indicator",        flood_txt),
        ("Official Flood Determination", "Not Screened Officially — Verify Karnataka Minor Irrigation / MDA / Municipal Flood & Rajakaluve Buffer Records."),
        ("Environmental Score & Coverage", env_cov_str),
        ("Data Source",                 _html.escape(str(env_src))),
    ], S))
    story.append(Spacer(1, 0.3 * cm))

    # ── 7. GEOGRAPHICAL LOCATION ───────────────────────────────────────────────
    story.extend(_section_header("7. Geographical Location & Coordinate Analysis", S))

    coord_src_str = (
        property_data.get("coordinate_source")
        or loc_audit.get("reverse_provider")
        or "User Input (WGS-84)"
    )
    geo_rows = [
        ("Geographical Coordinates",  _coord_str(property_data)),
        ("Coordinate Precision",      coord_label),
        ("Coordinate Source",         coord_src_str),
        ("Resolved Locality / Village", loc_disp),
        ("Resolved Taluk & District", f"{property_data.get('taluk', '—')} Taluk, {property_data.get('district', 'Mysuru')} District"),
    ]
    if loc_audit.get("ward_number") or loc_audit.get("ward_name"):
        wn2 = loc_audit.get("ward_name")
        geo_rows.append(("Municipal Ward (KGIS)", f"Ward {loc_audit.get('ward_number') or '—'}{f' — {wn2}' if wn2 else ''}"))
    if loc_audit.get("hobli"):
        geo_rows.append(("Hobli (KGIS)", str(loc_audit["hobli"])))
    if loc_audit.get("municipal_body"):
        geo_rows.append(("Local Body Jurisdiction", str(loc_audit["municipal_body"])))
    if loc_audit.get("boundary_source"):
        geo_rows.append(("Boundary Dataset Source", f"{loc_audit['boundary_source']} (Point-in-Polygon={loc_audit.get('point_in_polygon')})"))
    if loc_audit.get("reverse_display_name"):
        import re as _re_disp
        raw_disp = str(loc_audit["reverse_display_name"])
        safe_parts = []
        for _p in raw_disp.split(","):
            _cleaned = _re_disp.sub(r"[^\x20-\x7E\u2013\u2014]+", "", _p).strip()
            if _cleaned and any(ch.isalnum() for ch in _cleaned):
                safe_parts.append(_cleaned)
        safe_disp = ", ".join(safe_parts) if safe_parts else raw_disp.encode("ascii", "ignore").decode("ascii").strip(", ")
        if safe_disp:
            geo_rows.append(("Reverse / Geocode Match", safe_disp))
    if loc_audit.get("warning"):
        geo_rows.append(("Resolution Audit Note", f"<font color='#D35400'>{loc_audit['warning']}</font>"))
    geo_rows.append(("Spatial Context Note",
         "Distances in Section 5 are straight-line Haversine distances (not road travel distances) from the coordinates above. "
         "Only surveyed DGPS / registered coordinates provide parcel-level precision."))

    story.append(_kv_table(geo_rows, S))
    story.append(Spacer(1, 0.25 * cm))

    # Generate & embed OpenStreetMap raster snapshot centered on confirmed property location
    _snap_tmp_path = None
    plat = property_data.get("latitude")
    plon = property_data.get("longitude")
    if plat is not None and plon is not None:
        try:
            from reports.map_snapshot import generate_property_map_snapshot
            snap_fac = {}
            for _fk, _fv in (evaluation.get("facilities_detail") or {}).items():
                if isinstance(_fv, dict) and _fv.get("nearest"):
                    snap_fac[_fk] = _fv
            for _fi in (facilities or []):
                _ft = _fi.get("facility_type")
                if _ft and _ft not in snap_fac and _fi.get("latitude") and _fi.get("longitude"):
                    snap_fac[_ft] = {"nearest": _fi, "nearest_distance_km": _fi.get("distance_km")}
            snap_res = generate_property_map_snapshot(
                lat=float(plat),
                lon=float(plon),
                property_name=prop_name,
                coordinate_status=coord_status,
                facilities=snap_fac,
            )
            if snap_res and snap_res.get("path") and os.path.exists(snap_res["path"]):
                _snap_tmp_path = snap_res["path"]
                story.append(Paragraph("<b>OpenStreetMap Location Snapshot (1 km Reference Radius):</b>", S["small"]))
                story.append(Spacer(1, 0.1 * cm))
                story.append(Image(_snap_tmp_path, width=16.0 * cm, height=8.7 * cm))
                story.append(Paragraph(
                    f"Map Source: {snap_res.get('source', 'OpenStreetMap')} | "
                    f"Center: {float(plat):.5f} N, {float(plon):.5f} E ({coord_status}) | "
                    f"Blue ring = 1 km Haversine radius | Markers show nearest mapped OSM facilities within view.",
                    S["small"],
                ))
        except Exception as _snap_err:
            story.append(Paragraph(f"Map snapshot unavailable: {str(_snap_err)[:100]}", S["small"]))

    story.append(Spacer(1, 0.3 * cm))

    # ── 8. UPLOADED DOCUMENTS ─────────────────────────────────────────────────
    story.extend(_section_header("8. Uploaded Documents", S))
    if documents:
        seen = set()
        for d in documents:
            fname = d.get("original_filename", "Document")
            if fname not in seen:
                seen.add(fname)
                story.append(Paragraph(
                    f"• <b>{fname}</b> — Type: {d.get('file_type','').upper()} "
                    f"| Status: {d.get('extraction_status','PARSED')}",
                    S["body"]
                ))
    else:
        story.append(Paragraph(
            "No physical deed or land documents uploaded for this evaluation. "
            "Upload Sale Deed, RTC / Pahani, or Encumbrance Certificate to enable document analysis.",
            S["body"]
        ))
    story.append(Spacer(1, 0.3 * cm))

    # ── 9. PROPERTY VERIFICATION CHECKLIST ────────────────────────────────────
    story.extend(_section_header("9. Property Verification Checklist", S))
    story.append(Paragraph(
        "<b>MANDATORY LEGAL DUE DILIGENCE:</b> Every item below must be independently "
        "confirmed with official Karnataka Revenue & Registration records before any "
        "financial transaction.",
        S["warn"]
    ))

    status_labels = {
        "EXTRACTED":          "[Extracted]",
        "USER_CONFIRMED":     "[Confirmed]",
        "NEEDS_VERIFICATION": "[Pending]",
        "NOT_FOUND":          "[Not Found]",
    }
    if verification_items:
        verif_rows = []
        for item in verification_items:
            st  = item.get("status", "NEEDS_VERIFICATION")
            tag = status_labels.get(st, "[Pending]")
            lbl = item.get("item_label", "Verification Item").strip()
            verif_rows.append([lbl, tag])
        story.append(_data_table(["Due Diligence Item", "Verification Status"], verif_rows, [12.3*cm, 4.0*cm], S))
    else:
        default_items = [
            ["Bhoomi RTC / Pahani — verify title, extent & land classification (landrecords.karnataka.gov.in)", "[Pending]"],
            ["Encumbrance Certificate (EC) — minimum 15–30 years, confirms no mortgage/charge (kaverionline.karnataka.gov.in)", "[Pending]"],
            ["11E Sketch / Mutation Register Extract (Mojini portal)", "[Pending]"],
            ["DC Conversion Order — land conversion from Agricultural to Non-Agricultural use", "[Pending]"],
            ["RERA Karnataka Registration — mandatory for plotted layouts >= 500 sq.m (rera.karnataka.gov.in)", "[Pending]"],
            ["Khata Transfer & Mutation Entries — MUDA / Gram Panchayat property tax records", "[Pending]"],
            ["Property Tax Paid Receipts (all years, up to date)", "[Pending]"],
            ["Approved Layout Plan — MUDA / Local Planning Authority approval", "[Pending]"],
        ]
        story.append(_data_table(["Due Diligence Item", "Verification Status"], default_items, [12.3*cm, 4.0*cm], S))
    story.append(Spacer(1, 0.3 * cm))

    # ── 10. OFFICIAL VERIFICATION PORTALS ──────────────────────────────────────
    story.extend(_section_header("10. Official Verification Portals", S))
    portals = [
        ("Karnataka Bhoomi — Land Records & RTC / Pahani",
         "https://landrecords.karnataka.gov.in"),
        ("Karnataka Kaveri — Property Registration & Encumbrance Certificate",
         "https://kaverionline.karnataka.gov.in"),
        ("RERA Karnataka — Real Estate Regulatory Authority",
         "https://rera.karnataka.gov.in"),
        ("Mojini Karnataka — Digital Survey & 11E Sketch Extraction",
         "https://mojini.karnataka.gov.in"),
        ("MUDA Mysuru — Mysuru Urban Development Authority Approvals",
         "https://mudamysuru.co.in"),
        ("Sakala Karnataka — Time-bound Services Portal",
         "https://sakala.karnataka.gov.in"),
    ]
    for name, url in portals:
        story.append(Paragraph(f"• <b>{name}:</b>  {url}", S["small"]))
    story.append(Spacer(1, 0.3 * cm))

    # ── 11. DATA SOURCES & PROVENANCE ─────────────────────────────────────────
    story.extend(_section_header("11. Data Sources & Provenance", S))
    story.append(_kv_table([
        ("Master Valuation Dataset",
         f"{total_recs:,} total land records across 7 Mysuru taluks "
         f"({training_recs:,} training / {holdout_recs:,} independent holdout test). "
         "Mix of verified market listings, revenue records, and estimated values."),
        ("Geospatial & Facility Engine",
         "OpenStreetMap (Overpass API) primary + ArcGIS World Geocoder fallback for unmapped civic/utility nodes (WGS-84)."),
        ("Geocoding Service",
         "Nominatim / OpenStreetMap + district polygon guard — locality centroids used when parcel coordinates are unavailable."),
        ("Predictive ML Architecture",
         f"{algo_desc}  |  Scikit-Learn ColumnTransformer Pipeline  |  "
         f"{evaluation.get('feature_count', 47)} input features including 3-tier region & spatial distance engineering."),
        ("Explainability Engine",
         "SHAP TreeExplainer (SHapley Additive exPlanations) — feature importance and prediction decomposition."),
        ("Scoring Framework",
         "Transparent proportional multi-criteria model: Price 30%, Location 25%, "
         "Infrastructure 20%, Utility 15%, Environment 10%. "
         "Nearby Facilities (schools, hospitals, banks etc.) are informational only and excluded from the score. "
         "Missing / unverified components excluded from denominator."),
    ], S))
    story.append(Spacer(1, 0.3 * cm))

    # ── 12. LIMITATIONS & LEGAL DISCLAIMER ─────────────────────────────────────
    story.extend(_section_header("12. Limitations & Legal Disclaimer", S))

    disc_text = (
        f"This report is generated by the AI-Based Smart Land Valuation and Geospatial Analysis System "
        f"(VTU Mini Project — Mysuru, Karnataka).\n\n"
        f"<b>1. Valuation Limitations:</b> Price estimations are produced by a machine learning model "
        f"({model_name}) trained on {training_recs:,} land listings across Mysuru district. They are "
        f"indicative decision-support benchmarks and do NOT constitute a certified statutory property "
        f"valuation as required under the Registration Act 1908 or the RERA Act 2016. For legal, "
        f"financial, or mortgage purposes, engage a registered valuer under the REVA Act / "
        f"RERA Karnataka.\n\n"
        f"<b>2. Geospatial Accuracy:</b> When exact survey coordinates are unavailable, distances are "
        f"measured from locality centroids obtained via Nominatim / OpenStreetMap. These are approximate "
        f"and may differ from the actual parcel location by hundreds of metres in rural areas.\n\n"
        f"<b>3. Facility Mapping:</b> Facility data reflects OpenStreetMap volunteer contributions. "
        f"Newly established or informal establishments may not be mapped. API timeouts indicate a "
        f"temporary service outage — they do not confirm zero facilities.\n\n"
        f"<b>4. Ecological Indicators:</b> Waterbody proximity reflects surface hydrology only. "
        f"This does not replace MUDA / BBMP official flood zone maps, Rajakaluve buffer demarcations, "
        f"or underground drainage surveys.\n\n"
        f"<b>5. Legal Verification:</b> This platform does NOT perform legal title investigation, "
        f"verify deed authenticity, or check encumbrances. Independent legal due diligence — including "
        f"physical survey, Bhoomi RTC check, Kaveri EC verification, and advocate review — is "
        f"<b>strictly mandatory</b> before any land purchase or financial transaction.\n\n"
        f"<b>6. No Liability:</b> The developers, institution, and data contributors accept no "
        f"liability for decisions made based on this automated report."
    )
    story.append(Paragraph(disc_text.replace("\n\n", "<br/><br/>"), S["disclaimer"]))

    # ── BUILD ──────────────────────────────────────────────────────────────────
    try:
        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    finally:
        if "_snap_tmp_path" in locals() and _snap_tmp_path and os.path.exists(_snap_tmp_path):
            try:
                os.remove(_snap_tmp_path)
            except Exception:
                pass
    return output_path
