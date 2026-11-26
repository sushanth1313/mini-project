"""Jurisdiction-aware Karnataka land approval, conversion, planning authority, and RERA verification service."""
from typing import Any, Dict, List

from modules.land_document_analyzer.backend.config.settings import Settings
from modules.land_document_analyzer.backend.models.schemas import (
    PENDING_OFFICIAL_VERIFICATION,
    UNABLE_TO_EXTRACT,
    USER_PROVIDED_UNVERIFIED_LABEL,
)

# Mysuru District taluk -> likely planning authority mapping (never hardcodes MUDA for every location)
MYSURU_TALUK_AUTHORITIES = {
    "mysuru": "Mysuru Development Authority (MDA / erstwhile MUDA) or Mysuru City Corporation (MCC) — confirm Local Planning Area boundary",
    "mysore": "Mysuru Development Authority (MDA / erstwhile MUDA) or Mysuru City Corporation (MCC) — confirm Local Planning Area boundary",
    "nanjangud": "Nanjangud Planning Authority / Department of Town and Country Planning (DTCP) — verify if parcel falls inside MDA LPA or Nanjangud LPA",
    "t. narasipura": "Department of Town and Country Planning (DTCP) / Town Municipal Council, T. Narasipura",
    "tirumakudalu narasipura": "Department of Town and Country Planning (DTCP) / Town Municipal Council, T. Narasipura",
    "hunsur": "Hunsur Planning Authority / DTCP Mysuru Division",
    "h.d. kote": "Department of Town and Country Planning (DTCP) / Town Panchayat, H.D. Kote",
    "heggadadevanakote": "Department of Town and Country Planning (DTCP) / Town Panchayat, H.D. Kote",
    "k.r. nagar": "K.R. Nagar Planning Authority / DTCP Mysuru Division",
    "krishnarajanagara": "K.R. Nagar Planning Authority / DTCP Mysuru Division",
    "periyapatna": "Department of Town and Country Planning (DTCP) / Town Panchayat, Periyapatna",
    "saragur": "Department of Town and Country Planning (DTCP) / Gram Panchayat (for rural non-LPA parcels)",
    "saligrama": "Department of Town and Country Planning (DTCP) / Gram Panchayat (for rural non-LPA parcels)",
}


class ApprovalVerificationService:
    """
    Evaluates Land Conversion (Sec. 95 KLR Act), Layout Approval, Building Plan Approval,
    jurisdiction-appropriate planning authority, and RERA applicability.
    Marks unconfirmed approvals as 'Pending Official Verification'.
    """

    def resolve_competent_authority(self, property_info: Dict[str, Any]) -> Dict[str, Any]:
        district = (property_info.get("district") or "").strip()
        taluk = (property_info.get("taluk") or "").strip()
        prop_type = (property_info.get("property_type") or "residential_plot").strip().lower()
        is_agricultural = prop_type.startswith("agricult")

        if is_agricultural:
            authority = "Revenue Department (Tahsildar / Assistant Commissioner / Deputy Commissioner under Karnataka Land Revenue Act)"
            portals = [{"name": "Karnataka Bhoomi", "url": Settings.PORTALS["bhoomi"]}]
        elif district.lower() in ("mysuru", "mysore"):
            authority = MYSURU_TALUK_AUTHORITIES.get(
                taluk.lower(),
                "Verify competent jurisdiction between Mysuru Development Authority (MDA), DTCP Mysuru Division, or local Gram/Town Panchayat based on Master Plan LPA boundary",
            )
            portals = [
                {"name": "Mysuru Development Authority (MDA)", "url": Settings.PORTALS["mda_mysuru"]},
                {"name": "Karnataka Bhu-Yojane (NIRMANA2)", "url": Settings.PORTALS["bhu_yojane"]},
                {"name": "Karnataka RERA", "url": Settings.PORTALS["karnataka_rera"]},
            ]
        else:
            authority = (
                f"Local Urban Development Authority / Department of Town and Country Planning (DTCP) for {district or 'Karnataka'} "
                "(confirm exact Local Planning Area jurisdiction)"
            )
            portals = [
                {"name": "Karnataka Bhu-Yojane (NIRMANA2)", "url": Settings.PORTALS["bhu_yojane"]},
                {"name": "Karnataka RERA", "url": Settings.PORTALS["karnataka_rera"]},
            ]

        return {
            "district": district or "Not specified",
            "taluk": taluk or "Not specified",
            "property_type": prop_type,
            "estimated_competent_authority": authority,
            "jurisdiction_disclaimer": (
                "Planning jurisdiction depends on the notified Local Planning Area (LPA) and Master Plan boundary. "
                "Never assume MUDA/MDA applies solely because a parcel is in Mysuru district."
            ),
            "official_portals": portals,
        }

    def analyze_approvals(
        self,
        property_info: Dict[str, Any],
        uploaded_documents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        jurisdiction = self.resolve_competent_authority(property_info)
        prop_type = (property_info.get("property_type") or "residential_plot").strip().lower()

        conversion_docs = [d for d in uploaded_documents if d.get("document_type") == "Land Conversion Order"]
        layout_docs = [d for d in uploaded_documents if d.get("document_type") == "Approved Layout Plan"]
        building_docs = [d for d in uploaded_documents if d.get("document_type") == "Building Approval"]
        rera_docs = [d for d in uploaded_documents if d.get("document_type") == "RERA Registration Document"]
        rtc_docs = [d for d in uploaded_documents if d.get("document_type") == "RTC / Pahani"]

        is_apartment = prop_type in ("apartment", "flat", "apartment / flat")
        is_agricultural = prop_type.startswith("agricult")

        # Land Conversion analysis
        conversion_analysis = {
            "applicable": (not is_agricultural) and (not is_apartment),
            "document_uploaded": bool(conversion_docs),
            "status": (
                "Not Applicable (Agricultural Land Workflow)"
                if is_agricultural
                else "Conditional (Project-Level Parent Land Conversion — Verify OC/RERA)"
                if is_apartment
                else (PENDING_OFFICIAL_VERIFICATION if conversion_docs else "Missing — Land Conversion Order Not Provided")
            ),
            "details": [],
        }
        for doc in conversion_docs:
            f = doc.get("extraction", {}).get("fields", {})
            conversion_analysis["details"].append(
                {
                    "document_id": doc.get("document_id"),
                    "conversion_order_number": f.get("conversion_order_number", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "order_date": f.get("order_date", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "approved_land_use": f.get("approved_land_use", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "converted_extent": f.get("converted_extent", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "issuing_authority": f.get("issuing_authority", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "verification_status": PENDING_OFFICIAL_VERIFICATION,
                }
            )

        # Layout Approval analysis
        layout_analysis = {
            "applicable": prop_type in ("residential_plot", "commercial", "industrial"),
            "document_uploaded": bool(layout_docs),
            "status": (
                "Not Applicable"
                if prop_type == "agricultural"
                else "Not Applicable (Building Plan & CC/OC Apply Instead)"
                if is_apartment
                else (PENDING_OFFICIAL_VERIFICATION if layout_docs else "Missing — Approved Layout Plan Not Provided")
            ),
            "details": [],
        }
        for doc in layout_docs:
            f = doc.get("extraction", {}).get("fields", {})
            layout_analysis["details"].append(
                {
                    "document_id": doc.get("document_id"),
                    "layout_name": f.get("layout_name", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "approval_number": f.get("approval_number", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "approval_date": f.get("approval_date", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "issuing_authority": f.get("issuing_authority", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "survey_number": f.get("survey_number", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "plot_number": f.get("plot_number", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "property_extent": f.get("property_extent", {}).get("effective_value", UNABLE_TO_EXTRACT),
                    "verification_status": PENDING_OFFICIAL_VERIFICATION,
                }
            )

        # Land-use consistency check between RTC classification and property type / conversion
        land_use_concerns: List[str] = []
        for rtc in rtc_docs:
            cls_val = rtc.get("extraction", {}).get("fields", {}).get("recorded_land_classification", {}).get("effective_value", "")
            if cls_val and cls_val != UNABLE_TO_EXTRACT:
                if "agri" in cls_val.lower() and not is_agricultural and not conversion_docs:
                    land_use_concerns.append(
                        f"RTC records land classification as '{cls_val}' while property type is '{prop_type}', and no NA Conversion Order was uploaded."
                    )

        return {
            "jurisdiction": jurisdiction,
            "land_conversion": conversion_analysis,
            "layout_approval": layout_analysis,
            "building_approval_uploaded": bool(building_docs),
            "rera_registration": {
                "document_uploaded": bool(rera_docs),
                "portal_url": Settings.PORTALS["karnataka_rera"],
                "status": PENDING_OFFICIAL_VERIFICATION if rera_docs else "Conditional — Verify RERA Applicability (>500 sq.m or >8 units)",
            },
            "land_use_concerns": land_use_concerns,
            "independently_verified": False,
            "verification_label": USER_PROVIDED_UNVERIFIED_LABEL,
            "warning_note": (
                "An uploaded approval or conversion document alone is not proof that the approval is valid, "
                "unrevoked, or current. Verify approval numbers directly with the competent authority."
            ),
        }
