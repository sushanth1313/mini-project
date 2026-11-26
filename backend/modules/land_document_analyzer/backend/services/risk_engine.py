"""Explainable grouped risk engine and context-aware Karnataka dynamic document checklist."""
import re
from typing import Any, Dict, List, Optional

from modules.land_document_analyzer.backend.services.comparison_service import (
    OUTCOME_MATCH,
    OUTCOME_MISMATCH,
    OUTCOME_MISSING_INFO,
    OUTCOME_UNABLE_TO_COMPARE,
)

# Canonical Requirement Levels (Requirement #3)
REQ_WORKFLOW = "Workflow Required"
REQ_CONDITIONAL = "Conditional"
REQ_RECOMMENDED = "Recommended"
REQ_NOT_APPLICABLE = "Not applicable"

# Urban City / Municipal centers in Mysuru District vs predominantly rural/peri-urban taluks
_URBAN_TALUK_OR_HUBS = {"mysuru", "mysore", "nanjangud", "hunsur"}


class RiskEngine:
    """
    Produces deduplicated, evidence-backed due-diligence risk findings grouped by underlying issue,
    and builds a context-aware dynamic document checklist.
    Differentiates:
      - Confirmed document mismatch
      - Missing information
      - Possible legal concern
      - Official verification pending
      - AI-generated observation
    """

    def build_checklist(
        self,
        property_type: str,
        uploaded_documents: List[Dict[str, Any]],
        property_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prop_info = property_info or {}
        ptype = (property_type or "residential_plot").strip().lower()
        docs_by_type: Dict[str, List[Dict[str, Any]]] = {}
        for d in uploaded_documents:
            if not d.get("is_duplicate"):
                docs_by_type.setdefault(d.get("document_type") or "Other Supporting Document", []).append(d)

        # Infer land classification & urban/rural context from uploaded docs + metadata
        rtc_docs = docs_by_type.get("RTC / Pahani", [])
        conv_docs = docs_by_type.get("Land Conversion Order", [])
        layout_docs = docs_by_type.get("Approved Layout Plan", [])
        recorded_land_class = ""
        for rtc in rtc_docs:
            val = (
                rtc.get("extraction", {})
                .get("fields", {})
                .get("recorded_land_classification", {})
                .get("effective_value", "")
            )
            if val and val != "Unable to extract":
                recorded_land_class = val
                break

        taluk_lower = (prop_info.get("taluk") or "").strip().lower()
        is_urban_context = taluk_lower in _URBAN_TALUK_OR_HUBS
        is_agricultural = ptype.startswith("agricult")
        is_apartment = ptype in ("apartment", "flat", "apartment / flat")

        if is_agricultural:
            spec = [
                ("Sale Deed", REQ_WORKFLOW, "Primary registered conveyance deed transferring agricultural title."),
                ("RTC / Pahani", REQ_WORKFLOW, "Core Bhoomi revenue record confirming Khatedar, survey extent, and liabilities."),
                ("Mutation Register Extract", REQ_WORKFLOW, "Verifies revenue mutation entry and any pending objections."),
                ("Encumbrance Certificate (EC)", REQ_WORKFLOW, "Form 15/16 checking registered transfers, mortgages, or attachments."),
                ("Mother Deed / Parent Deed", REQ_RECOMMENDED, "Prior title deed tracing 15–30 year chain of ownership; missing copy is an information gap, not an automatic title defect."),
                ("Survey Sketch", REQ_RECOMMENDED, "Aakarband / Tippani sketch confirming survey boundaries and measurements."),
                ("11E Sketch", REQ_CONDITIONAL, "Statutorily required only when purchasing a sub-divided / part-survey parcel in Karnataka."),
                ("Survey Settlement Records", REQ_RECOMMENDED, "Confirms soil classification and Kharab A/B exclusions."),
                ("Land Conversion Order", REQ_NOT_APPLICABLE, "Not applicable while maintaining agricultural land classification."),
                ("Approved Layout Plan", REQ_NOT_APPLICABLE, "Not applicable to agricultural parcels."),
                ("Khata Certificate", REQ_NOT_APPLICABLE, "Urban municipal Khata applies only after non-agricultural conversion/urbanization."),
                ("RERA Registration Document", REQ_NOT_APPLICABLE, "RERA does not apply to agricultural land transactions."),
            ]
        elif is_apartment:
            spec = [
                ("Sale Deed", REQ_WORKFLOW, "Registered apartment conveyance deed."),
                ("Encumbrance Certificate (EC)", REQ_WORKFLOW, "Form 15/16 screening registered mortgages and prior unit transfers."),
                ("Khata Certificate", REQ_WORKFLOW, "Municipal A-Khata / e-Khata assessment for the apartment unit."),
                ("Property Tax Receipt", REQ_WORKFLOW, "Confirms municipal tax compliance."),
                ("Building Approval", REQ_WORKFLOW, "Sanctioned building plan along with Commencement / Occupancy Certificate (CC/OC)."),
                ("Mother Deed / Parent Deed", REQ_RECOMMENDED, "Traces builder/landowner parent title history."),
                ("Land Conversion Order", REQ_CONDITIONAL, "Required at parent-project level unless situated inside pre-urbanized municipal limits."),
                ("RERA Registration Document", REQ_CONDITIONAL, "Mandatory under Karnataka RERA only for projects >500 sq.m or >8 units."),
                ("Approved Layout Plan", REQ_NOT_APPLICABLE, "Replaced by sanctioned building plan for multi-storey apartment projects."),
                ("RTC / Pahani", REQ_NOT_APPLICABLE, "Typically superseded once urbanized and converted to municipal Khata."),
            ]
        elif ptype in ("commercial", "industrial"):
            conv_req = REQ_NOT_APPLICABLE if "non-agricultural" in recorded_land_class.lower() else REQ_WORKFLOW
            spec = [
                ("Sale Deed", REQ_WORKFLOW, "Primary registered commercial/industrial conveyance deed."),
                ("Encumbrance Certificate (EC)", REQ_WORKFLOW, "Checks registered leases, mortgages, and charges."),
                ("Land Conversion Order", conv_req, "Deputy Commissioner Section 95 NA/commercial/industrial conversion order."),
                ("Khata Certificate", REQ_WORKFLOW, "Local authority assessment / e-Khata record."),
                ("Property Tax Receipt", REQ_WORKFLOW, "Latest municipal / industrial authority tax receipt."),
                ("Mother Deed / Parent Deed", REQ_RECOMMENDED, "Traces 15–30 year title chain prior to current deed."),
                ("Approved Layout Plan", REQ_CONDITIONAL, "Required when situated in an industrial/commercial layout or KIADB/MDA estate."),
                ("Building Approval", REQ_CONDITIONAL, "Required only if an existing commercial/industrial building is part of the transaction."),
                ("RTC / Pahani", REQ_CONDITIONAL, "Applicable where revenue survey records remain active prior to municipal amalgamation."),
                ("Mutation Register Extract", REQ_CONDITIONAL, "Applicable when RTC revenue records are still referenced."),
                ("RERA Registration Document", REQ_CONDITIONAL, "Applicable only to regulated commercial developments exceeding RERA thresholds."),
            ]
        else:  # residential_plot (urban or rural Gramathana / converted layout)
            conv_note = (
                "Required under Sec. 95 KLR Act for agricultural survey land converted to residential plot (unless ancestral Gramathana site)."
                if not conv_docs
                else "Conversion Order uploaded; verify authenticity on Bhoomi / Bhu-Yojane."
            )
            layout_note = (
                f"Sanctioned plan from competent planning authority ({'MDA / DTCP / ULB' if is_urban_context else 'DTCP / Gram Panchayat'}) unless ancestral village site."
                if not layout_docs
                else "Layout plan uploaded; verify final release order."
            )
            spec = [
                ("Sale Deed", REQ_WORKFLOW, "Current registered residential plot conveyance deed."),
                ("Encumbrance Certificate (EC)", REQ_WORKFLOW, "Form 15/16 checking registered transfers, mortgages, and charges."),
                ("Khata Certificate", REQ_WORKFLOW, "Local authority e-Khata / A-Khata / Form 9 & 11B assessment record."),
                ("Property Tax Receipt", REQ_WORKFLOW, "Confirms latest property tax paid to MCC / ULB / Gram Panchayat."),
                ("Land Conversion Order", REQ_CONDITIONAL if not rtc_docs else REQ_WORKFLOW, conv_note),
                ("Approved Layout Plan", REQ_CONDITIONAL, layout_note),
                ("Mother Deed / Parent Deed", REQ_RECOMMENDED, "Prior link deeds establishing 15–30 year chain of ownership."),
                ("Khata Extract", REQ_RECOMMENDED, "Assessment register extract listing plot dimensions."),
                ("RTC / Pahani", REQ_CONDITIONAL, "Applicable for recently converted or peri-urban survey-numbered parcels."),
                ("Mutation Register Extract", REQ_CONDITIONAL, "Applicable where revenue RTC survey records remain referenced."),
                ("Survey Sketch", REQ_RECOMMENDED, "Confirms site boundaries, road access width, and measurements."),
                ("RERA Registration Document", REQ_CONDITIONAL, "Applicable only if residential layout exceeds 500 sq.m or >8 plots."),
            ]

        items = []
        missing_workflow_required = []
        failed_or_unconfirmed = []

        for doc_type, requirement_level, rationale in spec:
            matching_docs = docs_by_type.get(doc_type, [])
            if matching_docs:
                statuses = {d.get("ocr", {}).get("processing_status", "processed") for d in matching_docs}
                any_readable = any(s in ("processed", "partially_readable") for s in statuses)
                any_unconfirmed = any(d.get("classification", {}).get("requires_confirmation") for d in matching_docs)
                if not any_readable:
                    status = "Provided — processing failed"
                    failed_or_unconfirmed.append(doc_type)
                elif any_unconfirmed:
                    status = "Verification required"
                    failed_or_unconfirmed.append(doc_type)
                else:
                    status = "Provided"
            elif requirement_level == REQ_NOT_APPLICABLE:
                status = "Not applicable"
            elif requirement_level == REQ_CONDITIONAL:
                status = "Conditional"
            elif requirement_level == REQ_RECOMMENDED:
                status = "Recommended"
            else:
                status = "Not provided"
                missing_workflow_required.append(doc_type)

            items.append({
                "document_type": doc_type,
                "requirement_level": requirement_level,
                "status": status,
                "uploaded_files": [d.get("original_filename") for d in matching_docs],
                "rationale": rationale,
            })

        return {
            "property_type": ptype,
            "land_classification_detected": recorded_land_class or ("Agricultural" if is_agricultural else "Non-Agricultural / Plot"),
            "location_context": "Urban / Municipal Hub" if is_urban_context else "Peri-Urban / Rural Context",
            "items": items,
            "missing_mandatory_documents": missing_workflow_required,
            "processing_or_confirmation_pending": failed_or_unconfirmed,
            "checklist_disclaimer": (
                "Checklist rules adapt to property type, detected land classification, and jurisdiction context. "
                "A missing Recommended or Conditional document is an information gap, not automatically a legal defect."
            ),
        }

    def evaluate(
        self,
        property_info: Dict[str, Any],
        uploaded_documents: List[Dict[str, Any]],
        comparison_result: Dict[str, Any],
        bhoomi_result: Dict[str, Any],
        ec_result: Dict[str, Any],
        approval_result: Dict[str, Any],
        litigation_result: Dict[str, Any],
        checklist_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        unique_docs = [d for d in uploaded_documents if not d.get("is_duplicate")]

        # Helper to build structured, categorized findings
        def _add_finding(
            *,
            finding_type: str,
            risk_category: str,
            severity: str,
            description: str,
            documents_involved: List[str],
            page_numbers: List[int],
            extracted_evidence: str,
            why_it_matters: str,
            recommended_verification_step: str,
            confirmation_status: str,
        ) -> None:
            findings.append({
                "finding_type": finding_type,
                "risk_category": risk_category,
                "severity": severity,
                "description": description,
                "documents_involved": list(dict.fromkeys(documents_involved)),
                "page_numbers": sorted({p for p in page_numbers if isinstance(p, int) and p > 0}),
                "extracted_evidence": extracted_evidence,
                "why_it_matters": why_it_matters,
                "recommended_verification_step": recommended_verification_step,
                "confirmation_status": confirmation_status,
            })

        # 1. File Processing Issues / Duplicates / Unconfirmed Classifications (AI Observations & Missing Info)
        dup_files = [d for d in uploaded_documents if d.get("is_duplicate")]
        if dup_files:
            _add_finding(
                finding_type="AI-generated observation",
                risk_category="Duplicate Uploaded Files Excluded",
                severity="Low",
                description=f"{len(dup_files)} binary-duplicate file(s) detected and excluded from duplicate comparisons.",
                documents_involved=[f"{d.get('original_filename')} (dup of {d.get('duplicate_of_filename')})" for d in dup_files],
                page_numbers=[],
                extracted_evidence="Identical SHA-256 content hash detected.",
                why_it_matters="Duplicate uploads add no independent verification.",
                recommended_verification_step="Ensure distinct intended documents were uploaded.",
                confirmation_status="Confirmed Discrepancy",
            )

        for doc in unique_docs:
            p_status = doc.get("ocr", {}).get("processing_status", "processed")
            errors = doc.get("ocr", {}).get("errors", [])
            if p_status in ("corrupted_or_failed", "empty", "ocr_unavailable"):
                _add_finding(
                    finding_type="Missing information",
                    risk_category="Unreadable / Failed Document Processing",
                    severity="High",
                    description=f"'{doc.get('original_filename')}' could not be parsed automatically ({p_status}).",
                    documents_involved=[doc.get("original_filename", "Uploaded File")],
                    page_numbers=[],
                    extracted_evidence="; ".join(errors) if errors else f"Status: {p_status}",
                    why_it_matters="Comparisons against an unreadable or unscanned file cannot be performed.",
                    recommended_verification_step="Upload a clear PDF/300-DPI scan or enter verified values in the Technical tab.",
                    confirmation_status="Missing Information",
                )

            cls_info = doc.get("classification", {})
            if cls_info.get("requires_confirmation"):
                _add_finding(
                    finding_type="AI-generated observation",
                    risk_category="Document Type Requires Confirmation",
                    severity="Medium",
                    description=f"'{doc.get('original_filename')}' tentatively classified as '{doc.get('document_type')}' ({cls_info.get('confidence', 0):.0%}).",
                    documents_involved=[doc.get("original_filename", "Uploaded File")],
                    page_numbers=[1],
                    extracted_evidence=f"Alternatives: {', '.join(a['document_type'] for a in cls_info.get('alternatives', [])) or 'None'}",
                    why_it_matters="Classification drives which field schema and checklist rules are applied.",
                    recommended_verification_step="Confirm or reclassify the document type without re-uploading.",
                    confirmation_status="Review Required",
                )

            ext_info = doc.get("extraction", {})
            if ext_info.get("total_fields", 0) > 0 and ext_info.get("extracted_count", 0) == 0 and p_status == "processed":
                _add_finding(
                    finding_type="Missing information",
                    risk_category="No Structured Fields Extracted",
                    severity="Medium",
                    description=f"Text layer read from '{doc.get('original_filename')}', but 0 schema fields matched automatically.",
                    documents_involved=[doc.get("original_filename", "Uploaded File")],
                    page_numbers=[1],
                    extracted_evidence="0 extracted schema fields (not a confirmed title mismatch).",
                    why_it_matters="Cross-document checks remain incomplete until structured values are populated.",
                    recommended_verification_step="Review raw text or fill key values in Technical Field Edits.",
                    confirmation_status="Missing Information",
                )

        # 2. GROUPED Reference Property Mismatches (Location, Survey, Normalized Extent — NO duplicate alerts per doc!)
        ref_groups: Dict[str, List[Dict[str, Any]]] = {}
        for mm in comparison_result.get("reference_mismatches", []):
            ref_groups.setdefault(mm["field"], []).append(mm)

        for field_label, items in ref_groups.items():
            docs_list = [f"{i['document_type']} ({i.get('filename')})" for i in items]
            pages = [i["page_number"] for i in items if i.get("page_number")]
            ref_val = items[0]["reference_value"]
            doc_vals = sorted({f"{i['document_type']}: '{i['document_value']}'" for i in items})
            max_sev = "Critical" if any(i.get("severity") == "Critical" for i in items) else "High"
            _add_finding(
                finding_type="Confirmed document mismatch",
                risk_category=f"Property-Reference Mismatch: {field_label}",
                severity=max_sev,
                description=(
                    f"User-entered {field_label} ('{ref_val}') does not match {len(items)} uploaded document(s). "
                    "Entered property metadata has been preserved separately."
                ),
                documents_involved=["User-Entered Property Profile"] + docs_list,
                page_numbers=pages,
                extracted_evidence="; ".join(doc_vals),
                why_it_matters=(
                    "A large discrepancy in location or land extent between the property profile and uploaded papers "
                    "may indicate wrong parcel documents or valuation area errors."
                ),
                recommended_verification_step="Confirm whether these uploaded papers correspond to the target property before relying on valuation or title checks.",
                confirmation_status="Confirmed Document Mismatch",
            )

        # 3. Internal Conflicts inside uploaded documents
        for ic in comparison_result.get("internal_conflicts", []):
            _add_finding(
                finding_type="Confirmed document mismatch",
                risk_category=f"Internal Document Conflict: {ic['field']}",
                severity="High",
                description=ic["note"],
                documents_involved=[f"{ic['document_type']} ({ic['filename']})"],
                page_numbers=[ic["page_number"]] if ic.get("page_number") else [],
                extracted_evidence=f"{ic['field']}: {ic['value']}",
                why_it_matters="Self-contradictory values inside a record indicate an unresolved area or transfer discrepancy.",
                recommended_verification_step="Reconcile physical measurement against certified Sub-Registrar and Bhoomi records.",
                confirmation_status="Confirmed Document Mismatch",
            )

        # 4. GROUPED Cross-Document Mismatches (Identity, Extent, Ownership, Dates)
        grouped_xd: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for row in comparison_result.get("discrepancy_table", []):
            if row.get("category") == "Reference Property Input":
                continue
            if row.get("result") in (OUTCOME_MISMATCH, OUTCOME_UNABLE_TO_COMPARE):
                grouped_xd.setdefault((row["category"], row["field"]), []).append(row)

        for (cat, fld), rows in grouped_xd.items():
            has_mismatch = any(r["result"] == OUTCOME_MISMATCH for r in rows)
            docs_involved = []
            pages = []
            evidences = []
            for r in rows:
                docs_involved.extend([r["document_a"], r["document_b"]])
                if r.get("document_a_page"):
                    pages.append(r["document_a_page"])
                if r.get("document_b_page"):
                    pages.append(r["document_b_page"])
                evidences.append(f"{r['document_a']} vs {r['document_b']}: {r.get('evidence', r['note'])}")

            if has_mismatch:
                sev = "Critical" if cat == "Ownership Consistency" or fld in ("Survey Number", "Village / Locality") else "High"
                _add_finding(
                    finding_type="Confirmed document mismatch",
                    risk_category=f"{cat} Mismatch: {fld}",
                    severity=sev,
                    description=f"Confirmed {fld.lower()} mismatch across {len(rows)} document comparison pair(s).",
                    documents_involved=docs_involved,
                    page_numbers=pages,
                    extracted_evidence=" | ".join(evidences[:3]),
                    why_it_matters="Conflicting identity, area, ownership, or reference numbers undermine title continuity.",
                    recommended_verification_step="Reconcile original registered deeds and certified Bhoomi/Kaveri extracts with a property lawyer.",
                    confirmation_status="Confirmed Document Mismatch",
                )
            else:
                _add_finding(
                    finding_type="AI-generated observation",
                    risk_category=f"{cat}: Unable to Compare {fld}",
                    severity="Low",
                    description=f"{len(rows)} comparison pair(s) for {fld} require manual comparison due to name/unit variation.",
                    documents_involved=docs_involved,
                    page_numbers=pages,
                    extracted_evidence=" | ".join(evidences[:2]),
                    why_it_matters="Automated normalization was inconclusive; does not prove a defect on its own.",
                    recommended_verification_step="Visually confirm matching names, dates, or area units on source documents.",
                    confirmation_status="Unable to Compare Automatically",
                )

        # 5. Unified Mutation Pending Objection / Disputed Ownership Check (combine RTC + Mutation so zero duplicate Critical rows!)
        dispute_docs: List[str] = []
        dispute_pages: List[int] = []
        dispute_notes: List[str] = []
        for doc in unique_docs:
            if doc.get("document_type") in ("Mutation Register Extract", "RTC / Pahani"):
                flds = doc.get("extraction", {}).get("fields", {})
                status_txt = str(flds.get("recorded_status", {}).get("effective_value") or "")
                note_txt = str(flds.get("cultivation_details", {}).get("effective_value") or "")
                mr_txt = str(flds.get("mutation_number", {}).get("effective_value") or "")
                combined = f"{status_txt} {note_txt} {mr_txt}".strip()
                if re.search(r"\b(pending\s+objection|not\s+shown\s+as\s+certified|ownership\s+entry\s+disputed|objection\s+received)\b", combined, re.I):
                    dispute_docs.append(f"{doc.get('document_type')} ({doc.get('original_filename')})")
                    pg = flds.get("recorded_status", {}).get("page_number") or flds.get("cultivation_details", {}).get("page_number") or 1
                    dispute_pages.append(pg)
                    dispute_notes.append(f"{doc.get('document_type')}: {combined}")

        if dispute_docs:
            _add_finding(
                finding_type="Possible legal concern",
                risk_category="Revenue Objection / Uncertified Mutation Entry",
                severity="Critical",
                description="Revenue records indicate a pending mutation objection or disputed ownership entry.",
                documents_involved=dispute_docs,
                page_numbers=dispute_pages,
                extracted_evidence=" | ".join(dispute_notes),
                why_it_matters="Pending revenue objections mean ownership mutation has not been certified and may face an adverse claim.",
                recommended_verification_step="Inspect the Tahsildar objection register and obtain certified Bhoomi Mutation Status.",
                confirmation_status="Possible Legal Concern — Requires Lawyer Review",
            )

        # 6. Deduplicated Court / Encumbrance / Litigation Indicators
        seen_lit_cases = set()
        for lit in litigation_result.get("findings", []):
            case_key = (lit.get("case_number") or "").strip().lower()
            if case_key in seen_lit_cases and case_key:
                continue
            # Avoid duplicating pure revenue-objection rows already grouped above
            ctype_low = (lit.get("case_type") or "").lower()
            if ("mutation" in ctype_low or "revenue objection" in ctype_low) and dispute_docs:
                continue
            if case_key:
                seen_lit_cases.add(case_key)
            sim_tag = " [Simulated Test Entry]" if lit.get("is_simulated_entry") else ""
            _add_finding(
                finding_type="Possible legal concern",
                risk_category=f"Court Suit / Litigation Citation{sim_tag}",
                severity="Critical",
                description=f"{lit['status']}: {lit.get('case_number')} ({lit.get('court_name')}). {lit.get('lawyer_review_note')}",
                documents_involved=[lit.get("source", "Document / Court Record")],
                page_numbers=[lit["page_number"]] if lit.get("page_number") else [],
                extracted_evidence=f"Detail: {lit.get('nature_of_dispute')}",
                why_it_matters="Pending suits, interim orders, or attachments can restrict transferability under Section 52 of the Transfer of Property Act.",
                recommended_verification_step="Obtain certified court docket/order copies via eCourts and review with a property advocate.",
                confirmation_status="Possible Legal Concern — Requires Lawyer Review",
            )

        for ind in ec_result.get("encumbrance_indicators", []):
            ev_low = (ind.get("evidence") or "").lower()
            # Skip if already represented cleanly inside grouped Litigation / Court citation above
            if any(ck and ck in ev_low for ck in seen_lit_cases):
                continue
            _add_finding(
                finding_type="Possible legal concern",
                risk_category="Encumbrance Certificate Charge Indicator",
                severity=ind.get("severity", "High"),
                description=ind.get("indicator", "Encumbrance entry flagged"),
                documents_involved=["Encumbrance Certificate (EC)"],
                page_numbers=[ind["page_number"]] if ind.get("page_number") else [],
                extracted_evidence=ind.get("evidence", ""),
                why_it_matters="Undischarged mortgages or charges create third-party lender claims.",
                recommended_verification_step=ind.get("recommendation", "Verify latest Kaveri EC and Release Deed."),
                confirmation_status="Possible Legal Concern — Requires Lawyer Review",
            )

        # 7. Approvals & Missing Workflow-Required Documents (NOT treated as legal defects!)
        for concern in approval_result.get("land_use_concerns", []):
            _add_finding(
                finding_type="Possible legal concern",
                risk_category="Land-Use / Conversion Alignment Check",
                severity="High",
                description=concern,
                documents_involved=["RTC / Pahani", "Property Profile"],
                page_numbers=[],
                extracted_evidence=concern,
                why_it_matters="Non-agricultural development on agricultural land without Section 95 KLR conversion attracts statutory restrictions.",
                recommended_verification_step="Confirm official conversion status and Master Plan zoning on Bhu-Yojane.",
                confirmation_status="Possible Legal Concern — Requires Lawyer Review",
            )

        missing_workflow = checklist_result.get("missing_mandatory_documents", [])
        if missing_workflow:
            _add_finding(
                finding_type="Missing information",
                risk_category="Missing Workflow-Required Documents",
                severity="Medium",
                description=f"{len(missing_workflow)} workflow-required document(s) not provided: {', '.join(missing_workflow)}.",
                documents_involved=missing_workflow,
                page_numbers=[],
                extracted_evidence="Absent from uploaded set (informational gap, not an automatic title defect).",
                why_it_matters="Certain statutory checks remain incomplete until these documents are supplied.",
                recommended_verification_step="Obtain applicable documents from the seller or issuing Karnataka authority prior to sale agreement.",
                confirmation_status="Missing Information",
            )

        # 8. Official Portal Verification Pending (Single authoritative status finding)
        _add_finding(
            finding_type="Official verification pending",
            risk_category="Official Government Records Verification Pending",
            severity="Unverified",
            description="No automated live verification with Karnataka Bhoomi, Kaveri, Planning Authority, or eCourts was performed.",
            documents_involved=["Karnataka Portals (Bhoomi, Kaveri, MDA/DTCP, eCourts)"],
            page_numbers=[],
            extracted_evidence="Document parsing & cross-checks used uploaded files only.",
            why_it_matters="Uploaded files may predate subsequent mutations, charges, or court orders; extraction confidence is NOT legal verification confidence.",
            recommended_verification_step="Verify original records directly on official Karnataka portals and engage a qualified property lawyer.",
            confirmation_status="Official Verification Pending",
        )

        overall_assessment = self._determine_overall_assessment(unique_docs, comparison_result, findings)
        severity_counts = {
            lvl: sum(1 for f in findings if f["severity"] == lvl)
            for lvl in ("Critical", "High", "Medium", "Low", "Informational", "Unverified")
        }
        type_counts = {
            ft: sum(1 for f in findings if f["finding_type"] == ft)
            for ft in (
                "Confirmed document mismatch",
                "Missing information",
                "Possible legal concern",
                "Official verification pending",
                "AI-generated observation",
            )
        }

        return {
            "overall_assessment": overall_assessment,
            "assessment_note": (
                "Preliminary due-diligence summary based on uploaded documents. Does not establish legal title, "
                "confirm authenticity of uploaded files, or guarantee absence of litigation."
            ),
            "severity_counts": severity_counts,
            "finding_type_counts": type_counts,
            "total_findings": len(findings),
            "findings": findings,
        }

    @staticmethod
    def _determine_overall_assessment(
        uploaded_documents: List[Dict[str, Any]],
        comparison_result: Dict[str, Any],
        findings: List[Dict[str, Any]],
    ) -> str:
        readable_docs = [
            d for d in uploaded_documents
            if d.get("ocr", {}).get("processing_status", "processed") in ("processed", "partially_readable")
        ]
        if len(readable_docs) < 2:
            return "Insufficient Readable Documents"
        confirmed_mm = comparison_result.get("summary", {}).get("confirmed_mismatches", 0)
        severities = {f["severity"] for f in findings}
        if confirmed_mm > 0 or "Critical" in severities:
            return "Significant Issues Identified"
        if "High" in severities or "Medium" in severities:
            return "Further Verification Required"
        return "Documents Appear Consistent — Official Checks Pending"
