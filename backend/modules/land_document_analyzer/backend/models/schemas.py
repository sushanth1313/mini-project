"""Canonical domain schemas, document types, severities, and mandatory disclaimer."""
from typing import Dict, List

MANDATORY_LEGAL_DISCLAIMER = (
    "This report is an AI-assisted preliminary document-analysis and due-diligence tool intended "
    "for academic and informational purposes. It does not constitute legal advice, certified title "
    "verification, government approval confirmation, a court-certified litigation search, or a "
    "guarantee that a property is free from encumbrances or disputes. Automated document extraction "
    "and comparison may contain errors. Official records may be incomplete or unavailable. "
    "Independent verification by the relevant authorities and review by a qualified property lawyer "
    "are strongly recommended before any property transaction."
)

DOCUMENT_TYPES: List[str] = [
    "Sale Deed",
    "Mother Deed / Parent Deed",
    "RTC / Pahani",
    "Mutation Register Extract",
    "Encumbrance Certificate (EC)",
    "Khata Certificate",
    "Khata Extract",
    "Property Tax Receipt",
    "Land Conversion Order",
    "Approved Layout Plan",
    "Survey Sketch",
    "11E Sketch",
    "Survey Settlement Records",
    "Building Approval",
    "RERA Registration Document",
    "Court Order / Litigation Document",
    "Other Supporting Document",
]

SEVERITY_LEVELS: List[str] = [
    "Critical",
    "High",
    "Medium",
    "Low",
    "Informational",
    "Unverified",
]

OVERALL_ASSESSMENT_STATUSES: List[str] = [
    "Significant Issues Identified",
    "Further Verification Required",
    "Documents Appear Consistent — Official Checks Pending",
    "Preliminary Checks Completed — Legal Review Recommended",
    "Insufficient Documents",
]

LITIGATION_STATUSES: List[str] = [
    "Potential Case Found",
    "Court Document Uploaded",
    "Match Requires Review",
    "No Match Found in Searched Records",
    "Search Unavailable",
    "Not Verified",
]

PROVENANCE_CATEGORIES: Dict[str, str] = {
    "EXTRACTED": "Information extracted from uploaded documents",
    "OFFICIAL_VERIFIED": "Information independently verified from official sources",
    "USER_PROVIDED": "Information provided manually by the user",
    "UNVERIFIED": "Information not verified",
    "AI_OBSERVATION": "AI-generated observations",
}

UNABLE_TO_EXTRACT = "Unable to extract"
USER_PROVIDED_UNVERIFIED_LABEL = "User-provided document — official verification not independently completed."
PENDING_OFFICIAL_VERIFICATION = "Pending Official Verification"
