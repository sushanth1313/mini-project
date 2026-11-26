"""Kaveri Online Services (kaveri.karnataka.gov.in) Encumbrance Certificate & registration service."""
import re
from typing import Any, Dict, List

from modules.land_document_analyzer.backend.config.settings import Settings
from modules.land_document_analyzer.backend.models.schemas import UNABLE_TO_EXTRACT, USER_PROVIDED_UNVERIFIED_LABEL


class ECVerificationService:
    """
    Analyzes uploaded Encumbrance Certificates (Form 15 / Form 16) and guides verification on Kaveri Online Services.
    Never treats an empty EC period as proof of clear title or absence of litigation.
    Never fabricates registration verification or bypasses Kaveri authentication.
    """

    PORTAL_URL = Settings.PORTALS["kaveri"]

    def verify(
        self,
        property_info: Dict[str, Any],
        uploaded_documents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        ec_docs = [
            d for d in uploaded_documents
            if d.get("document_type") == "Encumbrance Certificate (EC)" and not d.get("is_duplicate")
        ]
        sale_deeds = [
            d for d in uploaded_documents
            if d.get("document_type") == "Sale Deed" and not d.get("is_duplicate")
        ]

        fields_to_verify = [
            "Obtain an official digitally signed EC (Form 15 / Form 16) from Kaveri Online Services covering at least 15–30 years.",
            "Confirm Sale Deed document number, registration date, and Sub-Registrar Office match Kaveri index.",
            "Verify whether any active mortgage, equitable deposit of title deeds, agreement to sell, or court attachment appears.",
            "For any historical mortgage, verify a corresponding registered Discharge / Release / Cancellation Deed.",
        ]

        if not ec_docs:
            return {
                "portal_name": "Kaveri Online Services (Department of Stamps & Registration, Karnataka)",
                "portal_url": self.PORTAL_URL,
                "official_api_status": "Automated Official API Unavailable — Portal Login Required",
                "verification_status": "Not Verified — Encumbrance Certificate Not Uploaded",
                "independently_verified": False,
                "provenance": "Information not verified",
                "ec_summaries": [],
                "encumbrance_indicators": [],
                "sale_deed_ref_found_in_ec": None,
                "fields_to_verify_on_portal": fields_to_verify,
                "notes": "No Encumbrance Certificate was uploaded. Request Form 15/16 via Kaveri Online Services and upload it for analysis.",
            }

        encumbrance_indicators: List[Dict[str, Any]] = []
        ec_summaries: List[Dict[str, Any]] = []
        sale_doc_nums = []
        for sd in sale_deeds:
            sd_fields = sd.get("extraction", {}).get("fields", {})
            for key in ("document_number", "registration_number"):
                val = sd_fields.get(key, {}).get("effective_value")
                if val and val != UNABLE_TO_EXTRACT:
                    sale_doc_nums.append(val.strip())

        sale_ref_matched = False

        for ec in ec_docs:
            fields = ec.get("extraction", {}).get("fields", {})
            raw_text = (ec.get("ocr", {}).get("raw_text") or "").lower()
            mortgages = fields.get("mortgages_or_charges", {}).get("effective_value", UNABLE_TO_EXTRACT)
            releases = fields.get("release_or_cancellation_entries", {}).get("effective_value", UNABLE_TO_EXTRACT)
            search_period = fields.get("search_period", {}).get("effective_value", UNABLE_TO_EXTRACT)
            doc_nums = fields.get("document_numbers", {}).get("effective_value", UNABLE_TO_EXTRACT)
            reg_tx = fields.get("registered_transactions", {}).get("effective_value", UNABLE_TO_EXTRACT)

            if any(num.lower() in raw_text for num in sale_doc_nums):
                sale_ref_matched = True

            combined_entry_text = f"{mortgages} {reg_tx}"
            is_nil_ec = bool(
                re.search(
                    r"\b(nil|none|no\s+mortgage|no\s+encumbrance|no\s+registered\s+encumbrance)\b",
                    combined_entry_text,
                    re.I,
                )
            )
            has_court_or_attachment = bool(
                re.search(
                    r"\b(civil\s+suit|o\.?s\.?\s*(?:no\.?\s*)?\d+|interim\s+order|attachment|stay\s+order|injunction)\b",
                    combined_entry_text,
                    re.I,
                )
            )
            is_simulated = bool(
                re.search(r"\b(simulated\s+entry|invented\s+test\s+data|fictional)\b", combined_entry_text, re.I)
            )
            has_mortgage_signal = (
                mortgages != UNABLE_TO_EXTRACT
                and not is_nil_ec
                and not has_court_or_attachment
            )
            has_release = (
                releases != UNABLE_TO_EXTRACT
                and not re.search(r"\b(nil|none|not\s+applicable|n/a|no\s+entry)\b", releases, re.I)
            )

            pg = (
                fields.get("mortgages_or_charges", {}).get("page_number")
                or fields.get("registered_transactions", {}).get("page_number")
                or 1
            )

            if has_court_or_attachment:
                prefix = "[Simulated Test Data — Document-Extracted] " if is_simulated else "[Document-Extracted] "
                encumbrance_indicators.append(
                    {
                        "document_id": ec.get("document_id"),
                        "page_number": pg,
                        "indicator": f"{prefix}Court Suit / Attachment Entry Cited in EC Search Result",
                        "evidence": reg_tx if reg_tx != UNABLE_TO_EXTRACT else mortgages,
                        "severity": "Critical",
                        "recommendation": "Verify certified court order and eCourts case status before proceeding; confirm whether attachment applies to subject land.",
                    }
                )
            elif has_mortgage_signal and not has_release:
                encumbrance_indicators.append(
                    {
                        "document_id": ec.get("document_id"),
                        "page_number": pg,
                        "indicator": "Active Mortgage / Charge Indicator Without Release Entry",
                        "evidence": mortgages,
                        "severity": "High",
                        "recommendation": "Verify bank NOC and registered Discharge/Release Deed at the Sub-Registrar Office.",
                    }
                )
            elif has_mortgage_signal and has_release:
                encumbrance_indicators.append(
                    {
                        "document_id": ec.get("document_id"),
                        "page_number": pg,
                        "indicator": "Historical Mortgage With Release Entry Noted",
                        "evidence": f"Charge: {mortgages} | Release: {releases}",
                        "severity": "Informational",
                        "recommendation": "Confirm original Release Deed and bank closure letter.",
                    }
                )

            ec_summaries.append(
                {
                    "document_id": ec.get("document_id"),
                    "filename": ec.get("original_filename"),
                    "search_period": search_period,
                    "document_numbers": doc_nums,
                    "search_result": reg_tx,
                    "mortgages_or_charges": mortgages,
                    "release_or_cancellation_entries": releases,
                    "nil_encumbrance_shown_in_period": is_nil_ec,
                    "verification_label": USER_PROVIDED_UNVERIFIED_LABEL,
                }
            )

        return {
            "portal_name": "Kaveri Online Services (Department of Stamps & Registration, Karnataka)",
            "portal_url": self.PORTAL_URL,
            "official_api_status": "Automated Official API Unavailable — User-Provided EC Analyzed",
            "verification_status": USER_PROVIDED_UNVERIFIED_LABEL,
            "independently_verified": False,
            "provenance": "Information extracted from uploaded documents",
            "ec_summaries": ec_summaries,
            "encumbrance_indicators": encumbrance_indicators,
            "sale_deed_ref_found_in_ec": sale_ref_matched if sale_doc_nums else None,
            "fields_to_verify_on_portal": fields_to_verify,
            "notes": (
                "EC findings reflect only entries extracted from the user-uploaded EC for the stated search period. "
                "An empty/nil EC never establishes free title or absence of pending litigation; independent Kaveri Online Services verification is required."
            ),
        }
