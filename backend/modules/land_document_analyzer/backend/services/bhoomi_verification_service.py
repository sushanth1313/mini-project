"""Karnataka Bhoomi (landrecords.karnataka.gov.in) assisted verification service."""
from typing import Any, Dict, List, Optional

from modules.land_document_analyzer.backend.config.settings import Settings
from modules.land_document_analyzer.backend.models.schemas import UNABLE_TO_EXTRACT, USER_PROVIDED_UNVERIFIED_LABEL
from modules.land_document_analyzer.backend.utils.text_utils import normalize_survey_number


class BhoomiVerificationService:
    """
    Provides structured verification workflow for Karnataka Bhoomi RTC / Pahani & Mutation records.
    Does not scrape, bypass CAPTCHA, or claim 'Government Verified' without an official API response.
    """

    PORTAL_URL = Settings.PORTALS["bhoomi"]

    def verify(
        self,
        property_info: Dict[str, Any],
        uploaded_documents: List[Dict[str, Any]],
        portal_api_available: bool = False,
    ) -> Dict[str, Any]:
        rtc_docs = [d for d in uploaded_documents if d.get("document_type") == "RTC / Pahani"]
        mutation_docs = [d for d in uploaded_documents if d.get("document_type") == "Mutation Register Extract"]

        checklist_to_verify = [
            "Match District, Taluk, Hobli, Village, Survey Number, and Hissa Number on Bhoomi View RTC.",
            "Verify current Khatedar (Owner) name(s) in Column 9 against the Sale Deed.",
            "Check Column 11 (Other Rights & Liabilities) for bank loans, court stays, PTCL, or acquisition notes.",
            "Confirm latest Mutation Register (MR) number and status in Bhoomi Mutation Status.",
            "Verify recorded total land extent and Kharab (A/B) area.",
        ]

        if not rtc_docs and not mutation_docs:
            return {
                "portal_name": "Karnataka Bhoomi (Land Records)",
                "portal_url": self.PORTAL_URL,
                "official_api_status": "Public API Not Available — Guided Portal Verification Required",
                "verification_status": "Not Verified — No RTC or Mutation Document Uploaded",
                "independently_verified": False,
                "provenance": "Information not verified",
                "reference_query": {
                    "district": property_info.get("district") or "Not specified",
                    "taluk": property_info.get("taluk") or "Not specified",
                    "village": property_info.get("village") or property_info.get("locality") or "Not specified",
                    "survey_number": property_info.get("survey_number") or "Not specified",
                    "hissa_number": property_info.get("hissa_number") or "Not specified",
                },
                "fields_to_verify_on_portal": checklist_to_verify,
                "comparisons": [],
                "notes": (
                    "Bhoomi does not offer an open public verification API without portal authentication/CAPTCHA. "
                    "Download the latest RTC/Pahani and MR Extract from the official Bhoomi portal and upload them here for cross-checking."
                ),
            }

        comparisons = []
        ref_sy = normalize_survey_number(property_info.get("survey_number"))
        for doc in rtc_docs + mutation_docs:
            fields = doc.get("extraction", {}).get("fields", {})
            doc_sy = fields.get("survey_number", {}).get("effective_value", UNABLE_TO_EXTRACT)
            doc_owner = (
                fields.get("owner_names", {}).get("effective_value")
                or fields.get("new_owner", {}).get("effective_value")
                or UNABLE_TO_EXTRACT
            )
            sy_match = (
                "Matches Reference"
                if ref_sy and doc_sy != UNABLE_TO_EXTRACT and normalize_survey_number(doc_sy) == ref_sy
                else ("Mismatch with Reference" if ref_sy and doc_sy != UNABLE_TO_EXTRACT else "Review Required")
            )
            comparisons.append(
                {
                    "document_id": doc.get("document_id"),
                    "document_type": doc.get("document_type"),
                    "extracted_survey_number": doc_sy,
                    "extracted_owner": doc_owner,
                    "survey_comparison_with_reference": sy_match,
                    "record_status": USER_PROVIDED_UNVERIFIED_LABEL,
                }
            )

        return {
            "portal_name": "Karnataka Bhoomi (Land Records)",
            "portal_url": self.PORTAL_URL,
            "official_api_status": (
                "Official API Connected"
                if portal_api_available
                else "Automated Official API Unavailable — User-Provided Document Cross-Checked"
            ),
            "verification_status": USER_PROVIDED_UNVERIFIED_LABEL,
            "independently_verified": False,
            "provenance": "Information extracted from uploaded documents",
            "reference_query": {
                "district": property_info.get("district") or "Not specified",
                "taluk": property_info.get("taluk") or "Not specified",
                "village": property_info.get("village") or property_info.get("locality") or "Not specified",
                "survey_number": property_info.get("survey_number") or "Not specified",
                "hissa_number": property_info.get("hissa_number") or "Not specified",
            },
            "fields_to_verify_on_portal": checklist_to_verify,
            "comparisons": comparisons,
            "notes": (
                "Uploaded Bhoomi-type records were cross-checked against property inputs, but independent "
                "live verification against the Karnataka Bhoomi server was not completed. Please confirm on the official portal."
            ),
        }
