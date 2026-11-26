"""
Comprehensive Mysuru District Property Classification, Planning Jurisdiction,
Allotment & Legal/Approval Status Builder (Workstream B).

Strict integrity rules:
- Supports all Mysuru urban, peri-urban, and rural land/site/authority categories.
- Never infers layout/conversion approval from GPS, OSM, locality name, or Khata/PID alone.
- Never modifies ML feature expectations (provides map_land_type_for_ml separately).
- Never claims a property is legally approved, regularised, safe, or litigation-free.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

STATUS_VERIFIED_DOC = "Verified from Uploaded Document"
STATUS_OFFICIAL = "Officially Verified"
STATUS_USER_REPORTED = "User Reported"
STATUS_NOT_INDEPENDENT = "Not Independently Verified"
STATUS_MISSING = "Missing Information"
STATUS_MISMATCH = "Mismatch"
STATUS_LEGAL_VERIF = "Requires Legal Verification"

PROPERTY_CATEGORIES = [
    "Residential Plot",
    "Residential House",
    "Commercial Plot / Property",
    "Industrial Plot / Property",
    "Agricultural Land",
    "Converted Agricultural Land",
    "Unconverted Agricultural Land",
    "Mixed-Use Property",
    "Government-Allotted Site",
    "Other / Custom",
]

PLANNING_AUTHORITIES = [
    "Approval status unknown",
    "No approval details supplied",
    "Mysuru Development Authority (MDA; legacy MUDA approvals)",
    "Directorate of Town and Country Planning (DTCP)",
    "Jurisdictional Local Planning Authority",
    "Gram Panchayat jurisdiction",
    "Town Panchayat",
    "City Municipal Council",
    "City Corporation",
    "Karnataka Housing Board (KHB)",
    "Karnataka Industrial Areas Development Board (KIADB)",
    "Other statutory development or planning authority",
    "Private developer layout",
    "Approval disputed / requires verification",
]

SITE_ALLOTMENT_CATEGORIES = [
    "Not Applicable / Not Sure",
    "General allotment",
    "EWS",
    "LIG",
    "MIG",
    "HIG",
    "Government scheme allotment",
    "KHB allotment",
    "Development authority allotment",
    "Private developer allotment",
    "Revenue-site claim",
    "Other / Custom",
]


def map_land_type_for_ml(land_type: Optional[str]) -> str:
    """Map rich Mysuru categories back onto the exact ML-trained categories without altering predictions."""
    s = str(land_type or "Residential Plot").strip().lower()
    if "unconverted" in s or s == "agricultural land" or s.startswith("agricult"):
        return "Agricultural/Farm"
    if "commercial" in s:
        return "Commercial"
    if "industrial" in s:
        return "Industrial"
    return "Residential Plot"


def build_property_classification_assessment(
    raw_data: Optional[Dict[str, Any]] = None,
    location_audit: Optional[Dict[str, Any]] = None,
    uploaded_documents: Optional[List[Dict[str, Any]]] = None,
    prop_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build structured Property Classification & Approval Status summary."""
    raw = raw_data or {}
    loc = location_audit or {}
    prop = prop_dict or {}
    docs = uploaded_documents or []

    land_cat = str(raw.get("land_category") or raw.get("land_type") or prop.get("land_type") or "Residential Plot").strip()
    custom_cat = str(raw.get("custom_land_type") or "").strip()
    if land_cat.lower().startswith("other") and custom_cat:
        land_cat_disp = f"Other ({custom_cat})"
    else:
        land_cat_disp = land_cat

    site_allot = str(raw.get("site_allotment_category") or "Not Applicable / Not Sure").strip()
    custom_allot = str(raw.get("custom_allotment_category") or "").strip()
    if site_allot.lower().startswith("other") and custom_allot:
        site_allot = f"Other ({custom_allot})"

    local_body = loc.get("municipal_body") or loc.get("local_body") or "Jurisdiction Requires Verification"
    jurisdiction_auth = loc.get("likely_planning_authority") or "Unknown / Requires Verification"

    raw_claimed_auth = str(raw.get("planning_authority") or "").strip()
    user_corrected_auth = bool(
        raw_claimed_auth and raw_claimed_auth.lower() not in ("approval status unknown", "auto", "not sure", "")
    )
    claimed_auth = raw_claimed_auth if user_corrected_auth else f"Auto-Detected from GIS Boundary ({jurisdiction_auth})"
    approval_ref = str(raw.get("approval_reference_no") or "").strip()

    def _norm_status_field(key: str, default_val: str = "Not Sure / Not Supplied") -> Dict[str, str]:
        v = str(raw.get(key) or "").strip()
        if not v or v.lower() in ("unknown", "not sure", "not supplied", "not sure / not supplied"):
            return {"value": default_val, "status": STATUS_MISSING}
        return {"value": v, "status": STATUS_USER_REPORTED}

    legal_fields = {
        "land_conversion_status": _norm_status_field("land_conversion_status"),
        "land_use_zoning": _norm_status_field("land_use_zoning"),
        "layout_sanction_status": _norm_status_field("layout_sanction_status"),
        "layout_release_status": _norm_status_field("layout_release_status", "Not Applicable / Not Supplied"),
        "building_plan_approval": _norm_status_field("building_plan_approval", "Not Applicable / Not Supplied"),
        "khata_status": _norm_status_field("khata_status"),
        "property_tax_status": _norm_status_field("property_tax_status"),
        "rera_registration": _norm_status_field("rera_registration", "Not Applicable / Not Sure"),
        "allotment_conditions": _norm_status_field("allotment_conditions", "Not Applicable / Not Supplied"),
        "acquisition_concerns": _norm_status_field("acquisition_concerns", "Not Screened Officially"),
    }

    # Cross-check uploaded documents if present (never treat Khata/PID as layout sanction!)
    doc_types_present = []
    for d in docs:
        dt = d.get("document_type") or (d.get("extraction") or {}).get("document_type") or ""
        if dt:
            doc_types_present.append(dt)
    doc_types_lower = " ".join(doc_types_present).lower()

    if "approved layout" in doc_types_lower or "layout plan" in doc_types_lower or "release order" in doc_types_lower:
        doc_verif_status = f"{STATUS_VERIFIED_DOC} (Layout/Approval File Uploaded — {STATUS_NOT_INDEPENDENT})"
    elif "conversion" in doc_types_lower:
        doc_verif_status = f"{STATUS_VERIFIED_DOC} (Conversion Order Uploaded — {STATUS_NOT_INDEPENDENT})"
    elif doc_types_present:
        doc_verif_status = f"{STATUS_NOT_INDEPENDENT} ({len(doc_types_present)} uploaded doc(s); layout/approval order not confirmed)"
    elif approval_ref:
        doc_verif_status = f"{STATUS_USER_REPORTED} (Ref: {approval_ref} — {STATUS_NOT_INDEPENDENT})"
    else:
        doc_verif_status = "Not Independently Verified — Obtain and verify the official approval document."

    # Derive explicit Layout / Approval Category without inventing statutory sanction from coordinates
    lay_sanc = legal_fields["layout_sanction_status"]["value"].lower()
    if "khb" in site_allot.lower() or "kiadb" in land_cat_disp.lower() or "government" in land_cat_disp.lower() or "government" in site_allot.lower():
        layout_approval_cat = "KHB / KIADB / Government Authority Layout (User Reported — Verify Allotment Order)"
    elif "revenue" in site_allot.lower() or "unapproved" in lay_sanc:
        layout_approval_cat = "Revenue Site / Unapproved Layout (Requires Legal Regularisation Check)"
    elif "approved layout" in lay_sanc or "provisional" in lay_sanc:
        auth_low = (raw_claimed_auth + " " + jurisdiction_auth).lower()
        if "mda" in auth_low or "muda" in auth_low:
            layout_approval_cat = "MDA-Approved Layout (User Reported — Not Independently Verified)"
        elif "dtcp" in auth_low:
            layout_approval_cat = "DTCP-Approved Layout (User Reported — Not Independently Verified)"
        elif "gram panchayat" in local_body.lower():
            layout_approval_cat = "Gram Panchayat Layout (User Reported — Verify LPA / Conversion)"
        else:
            layout_approval_cat = "Approved Layout Claimed (User Reported — Not Independently Verified)"
    elif "private" in site_allot.lower():
        layout_approval_cat = "Private Developer Layout (Approval Not Independently Verified)"
    elif user_corrected_auth:
        layout_approval_cat = f"{raw_claimed_auth} (User Reported — Not Independently Verified)"
    else:
        layout_approval_cat = "Not Independently Verified"

    # Flag potential risk when user claims Khata only without layout sanction
    outstanding: List[str] = []
    kh_v = legal_fields["khata_status"]["value"].lower()
    lay_v = legal_fields["layout_sanction_status"]["value"].lower()
    if any(k in kh_v for k in ("khata", "e-khata", "pid", "yes", "available")) and any(k in lay_v for k in ("not sure", "no", "unapproved", "missing", "none")):
        outstanding.append("Khata/PID alone does NOT prove planning authority layout sanction — verify approved layout plan & release order.")
    if "revenue" in site_allot.lower():
        outstanding.append("Revenue-site claim requires strict verification of Sec. 95 KLR conversion, 11E/subdivision, and layout legality.")
    if any(x in land_cat_disp.lower() for x in ("unconverted", "agricultural")):
        outstanding.append("Agricultural / unconverted land requires Revenue RTC, Mutation, Bhoomi check, and DC Conversion Order before non-agricultural use.")
    if any(x in land_cat_disp.lower() for x in ("kiadb", "khb", "government")) or any(x in site_allot.lower() for x in ("ews", "lig", "khb", "government", "authority")):
        outstanding.append("Verify Allotment Letter, Possession Certificate, non-alienation/lease lock-in conditions, and NOC from issuing authority.")
    if not outstanding:
        outstanding.append("Verify zoning, Sec. 95 conversion, layout sanction/release, Khata, tax receipts, and eCourts/Bhoomi records legally.")

    # Land-use classification label
    if "agricultural" in land_cat_disp.lower() and "converted" not in land_cat_disp.lower():
        land_use_class = "Agricultural / Revenue Land (Verify RTC & Sec. 95 KLR Status)"
    elif "converted agricultural" in land_cat_disp.lower():
        land_use_class = "DC Converted Non-Agricultural Land (Verify Conversion Order)"
    elif "commercial" in land_cat_disp.lower():
        land_use_class = "Commercial Zone (Verify CDP / Master Plan Zoning)"
    elif "industrial" in land_cat_disp.lower():
        land_use_class = "Industrial Zone (Verify KIADB / KSPCB / Master Plan)"
    elif "mixed" in land_cat_disp.lower():
        land_use_class = "Mixed-Use Zone (Verify Permitted Floor/Use Approvals)"
    else:
        land_use_class = f"{land_cat_disp} (Verify Master Plan Zoning & Conversion)"

    overall_approval_status = (
        STATUS_LEGAL_VERIF
        if claimed_auth in ("Approval disputed / requires verification",) or "revenue" in site_allot.lower()
        else STATUS_NOT_INDEPENDENT
    )

    hobli_val = loc.get("hobli") or prop.get("hobli") or "Requires KGIS / Revenue Verification"
    district_val = loc.get("resolved_district") or prop.get("district") or "Mysuru"
    taluk_val = loc.get("canonical_taluk") or loc.get("resolved_taluk") or prop.get("taluk") or "Mysuru"
    locality_val = loc.get("canonical_locality") or loc.get("resolved_locality") or prop.get("village_or_locality") or "—"
    ward_no = loc.get("ward_number")
    ward_nm = loc.get("ward_name")
    ward_disp = (
        f"Ward {ward_no}{f' — {ward_nm}' if ward_nm else ''}"
        if ward_no or ward_nm
        else "Outside Urban Municipal Ward (Rural / Gram Panchayat)"
    )
    conv_st = legal_fields["land_conversion_status"]["value"]
    zoning_st = legal_fields["land_use_zoning"]["value"]
    khata_st = legal_fields["khata_status"]["value"]
    if "agricultural" in land_cat_disp.lower() and "converted" not in land_cat_disp.lower():
        rev_conv_summary = f"Agricultural / Revenue Land — DC Conversion (Sec. 95 KLR): {conv_st}; Zoning: {zoning_st}; Khata: {khata_st}"
    elif "converted agricultural" in land_cat_disp.lower():
        rev_conv_summary = f"Converted Non-Agricultural Claimed — Conversion: {conv_st}; Zoning: {zoning_st}; Khata: {khata_st}"
    else:
        rev_conv_summary = f"Land Conversion: {conv_st}; Zoning: {zoning_st}; Khata: {khata_st} (Verify Bhoomi / RTC / Official Orders)"

    return {
        "property_type": land_cat_disp,
        "locality_or_village": locality_val,
        "taluk": taluk_val,
        "hobli": hobli_val,
        "district": district_val,
        "ward_display": ward_disp,
        "ward_number": ward_no,
        "ward_name": ward_nm,
        "gram_panchayat_lgd_code": loc.get("gram_panchayat_lgd_code"),
        "ml_mapped_land_type": map_land_type_for_ml(land_cat),
        "land_use_classification": land_use_class,
        "revenue_classification_and_conversion": rev_conv_summary,
        "site_allotment_category": site_allot,
        "layout_approval_category": layout_approval_cat,
        "local_body": local_body,
        "jurisdictional_planning_authority": jurisdiction_auth,
        "claimed_approval_authority": claimed_auth,
        "user_corrected_jurisdiction": user_corrected_auth,
        "approval_reference_no": approval_ref or "Not Supplied",
        "document_verification_status": doc_verif_status,
        "overall_status": overall_approval_status,
        "legal_and_planning_statuses": legal_fields,
        "outstanding_checks": outstanding,
        "khata_disclaimer": "Local body Khata / e-Khata / PID does NOT establish planning-authority layout approval.",
    }
