"""Cross-document verification engine for Karnataka property due diligence."""
import re
from typing import Any, Dict, List, Optional, Tuple

from modules.land_document_analyzer.backend.models.schemas import UNABLE_TO_EXTRACT
from modules.land_document_analyzer.backend.utils.text_utils import (
    compare_names,
    normalize_survey_number,
    parse_area_to_sqft,
    parse_date,
)

# Parenthetical annotations commonly found in test/clarification extracts that do not alter place identity
_PLACE_NOISE_RE = re.compile(
    r"\s*\((?:fictional\s+test\s+\w+|test\s+\w+|illustrative|sale\s+deed\s+\w+|rtc|sample)\)",
    re.IGNORECASE,
)

OUTCOME_MATCH = "MATCH"
OUTCOME_MISMATCH = "MISMATCH"
OUTCOME_UNABLE_TO_COMPARE = "UNABLE TO COMPARE"
OUTCOME_MISSING_INFO = "MISSING INFORMATION"


def _get_field(doc: Dict[str, Any], *field_names: str) -> Tuple[Optional[str], Optional[int]]:
    fields = doc.get("extraction", {}).get("fields", {})
    for name in field_names:
        info = fields.get(name)
        if info:
            val = info.get("effective_value")
            if val and val != UNABLE_TO_EXTRACT:
                return str(val).strip(), info.get("page_number")
    return None, None


def _normalize_place(value: Optional[str]) -> str:
    if not value:
        return ""
    s = _PLACE_NOISE_RE.sub("", str(value))
    s = re.sub(r"\b(?:taluk|taluka|district|hobli|village|locality|karnataka)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^A-Za-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _places_match(place_a: Optional[str], place_b: Optional[str]) -> bool:
    norm_a = _normalize_place(place_a)
    norm_b = _normalize_place(place_b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    return bool(
        re.search(rf"\b{re.escape(norm_a)}\b", norm_b)
        or re.search(rf"\b{re.escape(norm_b)}\b", norm_a)
    )


def _normalize_person(value: Optional[str]) -> str:
    if not value:
        return ""
    s = _PLACE_NOISE_RE.sub("", str(value))
    return re.sub(r"\s+", " ", s).strip()


def _normalize_doc_ref(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Za-z0-9/\-]", "", str(value)).upper()


def _extract_primary_extent_sqft(extent_text: str) -> Tuple[Optional[float], List[Tuple[str, float]]]:
    """Parses primary sq.ft. value and detects multi-extent internal slash splits if any."""
    slash_parts = [p.strip() for p in re.split(r"\s*/\s*", extent_text) if parse_area_to_sqft(p) is not None]
    if slash_parts:
        parsed_parts = [(p, float(parse_area_to_sqft(p) or 0.0)) for p in slash_parts]
        return parsed_parts[0][1], parsed_parts
    single = parse_area_to_sqft(extent_text)
    return single, ([(extent_text, single)] if single is not None else [])


class ComparisonService:
    """
    Compares extracted information across all unique uploaded documents and against reference property metadata.
    Uses 4 strict comparison outcomes: MATCH, MISMATCH, UNABLE TO COMPARE, MISSING INFORMATION.
    Never counts UNABLE TO COMPARE or MISSING INFORMATION as confirmed mismatches.
    Never claims that name matching proves legal ownership.
    """

    def compare_documents(
        self,
        documents: List[Dict[str, Any]],
        reference_property: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        unique_docs = [d for d in documents if not d.get("is_duplicate")]

        discrepancy_table: List[Dict[str, Any]] = []
        ownership_checks: List[Dict[str, Any]] = []
        extent_checks: List[Dict[str, Any]] = []
        date_checks: List[Dict[str, Any]] = []
        identity_checks: List[Dict[str, Any]] = []
        reference_checks: List[Dict[str, Any]] = []
        boundary_checks: List[Dict[str, Any]] = []
        reference_mismatches: List[Dict[str, Any]] = []
        internal_conflicts: List[Dict[str, Any]] = []

        same_property_warning = False

        # 1. Land Identification Consistency across all document pairs
        id_fields = [
            ("survey_number", "Survey Number"),
            ("hissa_number", "Hissa Number"),
            ("village", "Village / Locality"),
            ("hobli", "Hobli"),
            ("taluk", "Taluk"),
            ("district", "District"),
            ("plot_number", "Plot Number"),
        ]

        for field_key, label in id_fields:
            applicable_docs = [
                d for d in unique_docs if field_key in (d.get("extraction", {}).get("fields") or {})
            ]
            for i in range(len(applicable_docs)):
                for j in range(i + 1, len(applicable_docs)):
                    doc_a = applicable_docs[i]
                    doc_b = applicable_docs[j]
                    val_a, page_a = _get_field(doc_a, field_key)
                    val_b, page_b = _get_field(doc_b, field_key)

                    if not val_a or not val_b:
                        row = self._build_row(
                            category="Land Identification",
                            field=label,
                            doc_a=doc_a,
                            val_a=val_a or UNABLE_TO_EXTRACT,
                            page_a=page_a,
                            doc_b=doc_b,
                            val_b=val_b or UNABLE_TO_EXTRACT,
                            page_b=page_b,
                            result=OUTCOME_MISSING_INFO,
                            evidence=f"{label}: {val_a or UNABLE_TO_EXTRACT} vs {val_b or UNABLE_TO_EXTRACT}",
                            note=f"Insufficient extracted data to compare {label}; missing in one or both documents.",
                        )
                        discrepancy_table.append(row)
                        identity_checks.append(row)
                        continue

                    if field_key in ("survey_number", "hissa_number", "plot_number"):
                        norm_a = normalize_survey_number(val_a)
                        norm_b = normalize_survey_number(val_b)
                    else:
                        norm_a = _normalize_place(val_a)
                        norm_b = _normalize_place(val_b)

                    if not norm_a or not norm_b:
                        row = self._build_row(
                            category="Land Identification",
                            field=label,
                            doc_a=doc_a,
                            val_a=val_a,
                            page_a=page_a,
                            doc_b=doc_b,
                            val_b=val_b,
                            page_b=page_b,
                            result=OUTCOME_UNABLE_TO_COMPARE,
                            evidence=f"{val_a} vs {val_b}",
                            note=f"Values extracted for {label}, but format normalization was inconclusive.",
                        )
                        discrepancy_table.append(row)
                        identity_checks.append(row)
                        continue

                    match = norm_a == norm_b
                    result = OUTCOME_MATCH if match else OUTCOME_MISMATCH
                    if not match and field_key in ("survey_number", "village"):
                        same_property_warning = True

                    row = self._build_row(
                        category="Land Identification",
                        field=label,
                        doc_a=doc_a,
                        val_a=val_a,
                        page_a=page_a,
                        doc_b=doc_b,
                        val_b=val_b,
                        page_b=page_b,
                        result=result,
                        evidence=f"{val_a} (p.{page_a or '-'}) vs {val_b} (p.{page_b or '-'})",
                        note=(
                            f"{label} matches across documents."
                            if match
                            else f"{label} mismatch detected ({val_a} vs {val_b}). Do not assume these documents refer to the same property."
                        ),
                    )
                    discrepancy_table.append(row)
                    identity_checks.append(row)

        # 2. Land Extent Consistency & Internal Conflict Screening
        extent_candidates: List[Tuple[Dict[str, Any], Optional[str], Optional[float], Optional[int]]] = []
        for doc in unique_docs:
            fields = doc.get("extraction", {}).get("fields") or {}
            has_extent_schema = any(
                k in fields for k in ("property_extent", "total_land_extent", "converted_extent", "plot_dimensions")
            )
            val, page = _get_field(doc, "property_extent", "total_land_extent", "converted_extent", "plot_dimensions")
            if val:
                sqft, parsed_parts = _extract_primary_extent_sqft(val)
                if len(parsed_parts) >= 2:
                    sq0, sq1 = parsed_parts[0][1], parsed_parts[1][1]
                    if max(sq0, sq1) > 0 and abs(sq0 - sq1) / max(sq0, sq1) > 0.015:
                        internal_conflicts.append({
                            "document_id": doc.get("document_id"),
                            "document_type": doc.get("document_type"),
                            "filename": doc.get("original_filename"),
                            "field": "Land Extent",
                            "page_number": page,
                            "value": val,
                            "note": (
                                f"Document cites two conflicting extents: '{parsed_parts[0][0]}' ({sq0:,.0f} sq.ft.) "
                                f"vs '{parsed_parts[1][0]}' ({sq1:,.0f} sq.ft.)."
                            ),
                        })
                extent_candidates.append((doc, val, sqft, page))
            elif has_extent_schema:
                extent_candidates.append((doc, None, None, None))

        for i in range(len(extent_candidates)):
            for j in range(i + 1, len(extent_candidates)):
                doc_a, val_a, sqft_a, page_a = extent_candidates[i]
                doc_b, val_b, sqft_b, page_b = extent_candidates[j]
                if not val_a or not val_b:
                    row = self._build_row(
                        category="Land Extent",
                        field="Property Extent",
                        doc_a=doc_a,
                        val_a=val_a or UNABLE_TO_EXTRACT,
                        page_a=page_a,
                        doc_b=doc_b,
                        val_b=val_b or UNABLE_TO_EXTRACT,
                        page_b=page_b,
                        result=OUTCOME_MISSING_INFO,
                        evidence=f"Extent missing in {doc_a.get('document_type') if not val_a else doc_b.get('document_type')}",
                        note="Extent cannot be compared because one or both documents do not state a readable land area.",
                    )
                    discrepancy_table.append(row)
                    extent_checks.append(row)
                    continue

                if sqft_a is not None and sqft_b is not None:
                    diff_pct = abs(sqft_a - sqft_b) / max(sqft_a, sqft_b, 1.0)
                    is_parent_vs_site = (
                        ("parent survey" in val_a.lower() or "parent survey" in val_b.lower()
                         or doc_a.get("document_type") == "RTC / Pahani"
                         or doc_b.get("document_type") == "RTC / Pahani")
                        and max(sqft_a, sqft_b) > 10000
                        and min(sqft_a, sqft_b) <= 10000
                        and ("seller claim" in val_a.lower() or "seller claim" in val_b.lower()
                             or doc_a.get("document_type") in ("Sale Deed", "Mutation Register Extract")
                             or doc_b.get("document_type") in ("Sale Deed", "Mutation Register Extract"))
                    )
                    if diff_pct <= 0.015:
                        res = OUTCOME_MATCH
                        note = f"Normalized extents match (~{sqft_a:,.0f} sq.ft. vs ~{sqft_b:,.0f} sq.ft.)."
                    elif is_parent_vs_site:
                        res = OUTCOME_UNABLE_TO_COMPARE
                        note = (
                            f"Unable to Verify Subdivision / Site Extent: parent survey extent ({val_a if sqft_a > sqft_b else val_b}) "
                            f"differs from individual site claim ({val_b if sqft_a > sqft_b else val_a}) without supporting 11E/subdivision or layout sanction."
                        )
                    else:
                        res = OUTCOME_MISMATCH
                        note = (
                            f"Property extent mismatch detected ({val_a} [{sqft_a:,.0f} sq.ft.] vs "
                            f"{val_b} [{sqft_b:,.0f} sq.ft.])."
                        )
                elif val_a.lower() == val_b.lower():
                    res = OUTCOME_MATCH
                    note = "Textual extent matches verbatim."
                else:
                    res = OUTCOME_UNABLE_TO_COMPARE
                    note = f"Extent units could not be normalized automatically ({val_a} vs {val_b}); manual verification required."

                row = self._build_row(
                    category="Land Extent",
                    field="Property Extent",
                    doc_a=doc_a,
                    val_a=val_a,
                    page_a=page_a,
                    doc_b=doc_b,
                    val_b=val_b,
                    page_b=page_b,
                    result=res,
                    evidence=f"{val_a} vs {val_b}",
                    note=note,
                )
                discrepancy_table.append(row)
                extent_checks.append(row)

        # 3. Ownership & Party Continuity across Sale Deed, RTC, Mutation, EC, Mother Deed
        sale_deeds = [d for d in unique_docs if d.get("document_type") == "Sale Deed"]
        mother_deeds = [d for d in unique_docs if d.get("document_type") == "Mother Deed / Parent Deed"]
        rtcs = [d for d in unique_docs if d.get("document_type") == "RTC / Pahani"]
        mutations = [d for d in unique_docs if d.get("document_type") == "Mutation Register Extract"]
        ecs = [d for d in unique_docs if d.get("document_type") == "Encumbrance Certificate (EC)"]

        def _compare_owner_pair(
            field_label: str,
            doc_a: Dict[str, Any],
            name_a: Optional[str],
            pg_a: Optional[int],
            doc_b: Dict[str, Any],
            name_b: Optional[str],
            pg_b: Optional[int],
            match_msg: str,
            mismatch_msg: str,
        ) -> None:
            if not name_a or not name_b:
                row = self._build_row(
                    category="Ownership Consistency",
                    field=field_label,
                    doc_a=doc_a,
                    val_a=name_a or UNABLE_TO_EXTRACT,
                    page_a=pg_a,
                    doc_b=doc_b,
                    val_b=name_b or UNABLE_TO_EXTRACT,
                    page_b=pg_b,
                    result=OUTCOME_MISSING_INFO,
                    evidence=f"{name_a or UNABLE_TO_EXTRACT} vs {name_b or UNABLE_TO_EXTRACT}",
                    note=f"Insufficient party information to compare {field_label}.",
                )
            else:
                status, sim = compare_names(_normalize_person(name_a), _normalize_person(name_b))
                if status == "Consistent":
                    res_label = OUTCOME_MATCH
                    note = match_msg
                elif status == "Spelling Variation":
                    res_label = OUTCOME_UNABLE_TO_COMPARE
                    note = f"Minor spelling/initial variation detected (similarity {sim:.0%}); human verification needed."
                else:
                    res_label = OUTCOME_MISMATCH
                    note = mismatch_msg
                row = self._build_row(
                    category="Ownership Consistency",
                    field=field_label,
                    doc_a=doc_a,
                    val_a=name_a,
                    page_a=pg_a,
                    doc_b=doc_b,
                    val_b=name_b,
                    page_b=pg_b,
                    result=res_label,
                    evidence=f"{name_a} vs {name_b} (sim {sim:.0%})",
                    note=note,
                )
                row["similarity"] = sim
            discrepancy_table.append(row)
            ownership_checks.append(row)

        for sd in sale_deeds:
            buyer, buyer_pg = _get_field(sd, "buyer_names")
            seller, seller_pg = _get_field(sd, "seller_names")
            sd_doc_num, sd_doc_pg = _get_field(sd, "document_number", "registration_number")

            for rtc in rtcs:
                rtc_owner, rtc_pg = _get_field(rtc, "owner_names")
                _compare_owner_pair(
                    "Sale Deed Buyer vs RTC Owner",
                    sd, buyer, buyer_pg, rtc, rtc_owner, rtc_pg,
                    "Buyer name in Sale Deed aligns with RTC/Pahani recorded holder (informational check only).",
                    "Sale Deed buyer differs from RTC/Pahani recorded holder — mutation may be incomplete or disputed.",
                )

            for md in mother_deeds:
                md_buyer, md_pg = _get_field(md, "buyer_names", "owner_names")
                _compare_owner_pair(
                    "Parent Deed Owner vs Sale Deed Seller",
                    md, md_buyer, md_pg, sd, seller, seller_pg,
                    "Parent Deed owner aligns with current Sale Deed seller.",
                    "Parent Deed owner differs from Sale Deed seller; verify intermediate link deeds.",
                )

            for mut in mutations:
                mut_new, mut_pg = _get_field(mut, "new_owner", "applicant")
                _compare_owner_pair(
                    "Sale Deed Buyer vs Mutation Claimant/Owner",
                    sd, buyer, buyer_pg, mut, mut_new, mut_pg,
                    "Mutation applicant/transferee matches Sale Deed buyer.",
                    "Mutation claimant/new owner differs from Sale Deed buyer.",
                )

                mut_ref, mut_ref_pg = _get_field(mut, "linked_document_reference", "mutation_reason")
                if sd_doc_num and mut_ref:
                    sd_norm = _normalize_doc_ref(sd_doc_num)
                    ref_norm = _normalize_doc_ref(mut_ref)
                    ref_ok = bool(sd_norm and (sd_norm in ref_norm or ref_norm in sd_norm))
                    discrepancy_table.append(
                        self._build_row(
                            category="Document References",
                            field="Sale Deed Ref vs Mutation Basis",
                            doc_a=sd,
                            val_a=sd_doc_num,
                            page_a=sd_doc_pg,
                            doc_b=mut,
                            val_b=mut_ref,
                            page_b=mut_ref_pg,
                            result=OUTCOME_MATCH if ref_ok else OUTCOME_MISMATCH,
                            evidence=f"Sale Deed: {sd_doc_num} | Mutation Ref: {mut_ref}",
                            note=(
                                "Mutation extract cites the matching Sale Deed document number."
                                if ref_ok
                                else "Mutation extract reference differs from the Sale Deed document number."
                            ),
                        )
                    )

            for ec in ecs:
                ec_app, ec_app_pg = _get_field(ec, "applicant_name")
                if ec_app:
                    _compare_owner_pair(
                        "Sale Deed Buyer vs EC Applicant",
                        sd, buyer, buyer_pg, ec, ec_app, ec_app_pg,
                        "EC applicant matches Sale Deed buyer.",
                        "EC applicant differs from Sale Deed buyer — confirm who requested the EC search.",
                    )

        for rtc in rtcs:
            rtc_owner, rtc_pg = _get_field(rtc, "owner_names")
            rtc_mr, rtc_mr_pg = _get_field(rtc, "mutation_references")
            for mut in mutations:
                mut_new, mut_pg = _get_field(mut, "new_owner", "applicant")
                _compare_owner_pair(
                    "RTC Holder vs Mutation Claimant/Owner",
                    rtc, rtc_owner, rtc_pg, mut, mut_new, mut_pg,
                    "RTC recorded holder matches Mutation extract claimant/new owner.",
                    "RTC recorded holder differs from Mutation extract claimant/new owner.",
                )
                mut_no, mut_no_pg = _get_field(mut, "mutation_number")
                if rtc_mr and mut_no:
                    mr_ok = _normalize_doc_ref(rtc_mr) in _normalize_doc_ref(mut_no) or _normalize_doc_ref(mut_no) in _normalize_doc_ref(rtc_mr)
                    discrepancy_table.append(
                        self._build_row(
                            category="Mutation References",
                            field="RTC Mutation Ref vs MR Extract No.",
                            doc_a=rtc,
                            val_a=rtc_mr,
                            page_a=rtc_mr_pg,
                            doc_b=mut,
                            val_b=mut_no,
                            page_b=mut_no_pg,
                            result=OUTCOME_MATCH if mr_ok else OUTCOME_MISMATCH,
                            evidence=f"RTC: {rtc_mr} | MR Extract: {mut_no}",
                            note=(
                                "RTC and Mutation Extract cite the same Mutation Reference number."
                                if mr_ok
                                else "Mutation numbers differ between RTC note and Mutation Extract."
                            ),
                        )
                    )

        # 4. Date Chronology Checks
        date_checks = self._check_chronology(unique_docs)
        discrepancy_table.extend(date_checks)

        # 5. Boundary Consistency Checks
        boundary_docs = []
        for doc in unique_docs:
            bnd, pg = _get_field(doc, "property_boundaries")
            if bnd:
                boundary_docs.append((doc, bnd, pg))
        for i in range(len(boundary_docs)):
            for j in range(i + 1, len(boundary_docs)):
                doc_a, bnd_a, pg_a = boundary_docs[i]
                doc_b, bnd_b, pg_b = boundary_docs[j]
                match = bnd_a.lower() == bnd_b.lower()
                row = self._build_row(
                    category="Boundaries",
                    field="Property Boundaries",
                    doc_a=doc_a,
                    val_a=bnd_a,
                    page_a=pg_a,
                    doc_b=doc_b,
                    val_b=bnd_b,
                    page_b=pg_b,
                    result=OUTCOME_MATCH if match else OUTCOME_UNABLE_TO_COMPARE,
                    evidence=f"{bnd_a} vs {bnd_b}",
                    note=(
                        "Schedule boundaries match verbatim."
                        if match
                        else "Boundary text varies; confirm physical site boundaries manually."
                    ),
                )
                boundary_checks.append(row)
                discrepancy_table.append(row)

        # 6. User-Entered Reference Property Comparison (Location + Survey + Normalized Extent!)
        if reference_property:
            ref_rows, ref_mm = self._compare_against_reference(unique_docs, reference_property)
            reference_checks.extend(ref_rows)
            reference_mismatches.extend(ref_mm)
            discrepancy_table.extend(ref_rows)

        match_count = sum(1 for r in discrepancy_table if r["result"] == OUTCOME_MATCH)
        mismatch_count = sum(1 for r in discrepancy_table if r["result"] == OUTCOME_MISMATCH)
        unable_compare_count = sum(1 for r in discrepancy_table if r["result"] == OUTCOME_UNABLE_TO_COMPARE)
        missing_info_count = sum(1 for r in discrepancy_table if r["result"] == OUTCOME_MISSING_INFO)
        incomplete_total = unable_compare_count + missing_info_count
        comparable_count = match_count + mismatch_count

        if len(unique_docs) < 2 and not reference_checks:
            comp_status = "Comparison incomplete — upload at least two documents to cross-check."
        elif comparable_count == 0:
            comp_status = "Comparison incomplete — insufficient extracted information."
        elif mismatch_count > 0 or len(internal_conflicts) > 0:
            comp_status = (
                f"Confirmed discrepancies detected ({mismatch_count} confirmed mismatch(es), "
                f"{incomplete_total} incomplete/missing comparison(s))."
            )
        elif incomplete_total > 0:
            comp_status = (
                f"{match_count} compared item(s) matched; {incomplete_total} comparison(s) could not be completed "
                f"({unable_compare_count} unable to compare, {missing_info_count} missing information)."
            )
        else:
            comp_status = f"All {match_count} compared fields MATCH across uploaded documents (official portal verification still required)."

        return {
            "property_identity_consistent": not same_property_warning and not reference_mismatches,
            "property_identity_warning": (
                "Property location, extent, or survey details differ between user-entered inputs and uploaded documents (or across documents). Do not assume all records describe the same property."
                if (same_property_warning or reference_mismatches)
                else None
            ),
            "comparison_status": comp_status,
            "summary": {
                "total_checks": len(discrepancy_table),
                "comparable_checks": comparable_count,
                "confirmed_mismatches": mismatch_count,
                "mismatches": mismatch_count,
                "matches": match_count,
                "consistent": match_count,
                "unable_to_compare": unable_compare_count,
                "missing_information": missing_info_count,
                "incomplete_comparisons": incomplete_total,
                "unable_to_extract": missing_info_count,
                "partial_matches": unable_compare_count,
                "review_required": unable_compare_count,
                "internal_conflicts": len(internal_conflicts),
                "reference_mismatches": len(reference_mismatches),
            },
            "ownership_checks": ownership_checks,
            "identity_checks": identity_checks,
            "extent_checks": extent_checks,
            "date_checks": date_checks,
            "boundary_checks": boundary_checks,
            "reference_checks": reference_checks,
            "reference_mismatches": reference_mismatches,
            "internal_conflicts": internal_conflicts,
            "discrepancy_table": discrepancy_table,
        }

    @staticmethod
    def _build_row(
        *,
        category: str,
        field: str,
        doc_a: Dict[str, Any],
        val_a: str,
        page_a: Optional[int],
        doc_b: Dict[str, Any],
        val_b: str,
        page_b: Optional[int],
        result: str,
        evidence: str,
        note: str,
    ) -> Dict[str, Any]:
        return {
            "category": category,
            "field": field,
            "document_a": doc_a.get("document_type", doc_a.get("original_filename")),
            "document_a_filename": doc_a.get("original_filename"),
            "document_a_id": doc_a.get("document_id"),
            "document_a_value": val_a,
            "document_a_page": page_a,
            "document_b": doc_b.get("document_type", doc_b.get("original_filename")),
            "document_b_filename": doc_b.get("original_filename"),
            "document_b_id": doc_b.get("document_id"),
            "document_b_value": val_b,
            "document_b_page": page_b,
            "result": result,
            "evidence": evidence,
            "note": note,
        }

    @classmethod
    def _check_chronology(cls, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []
        dates_by_type: Dict[str, List[Tuple[Dict[str, Any], str, Any, Optional[int]]]] = {}
        date_fields = ("registration_date", "mutation_date", "order_date", "approval_date", "record_date")

        for doc in documents:
            dtype = doc.get("document_type", "Other")
            for df in date_fields:
                raw, pg = _get_field(doc, df)
                if raw:
                    parsed = parse_date(raw)
                    if parsed:
                        dates_by_type.setdefault(dtype, []).append((doc, raw, parsed, pg))
                        break

        for md, md_raw, md_dt, md_pg in dates_by_type.get("Mother Deed / Parent Deed", []):
            for sd, sd_raw, sd_dt, sd_pg in dates_by_type.get("Sale Deed", []):
                ok = md_dt <= sd_dt
                checks.append(
                    cls._build_row(
                        category="Chronology",
                        field="Parent Deed vs Sale Deed Date",
                        doc_a=md,
                        val_a=md_raw,
                        page_a=md_pg,
                        doc_b=sd,
                        val_b=sd_raw,
                        page_b=sd_pg,
                        result=OUTCOME_MATCH if ok else OUTCOME_MISMATCH,
                        evidence=f"Parent Deed: {md_raw} | Sale Deed: {sd_raw}",
                        note=(
                            "Parent Deed predates current Sale Deed."
                            if ok
                            else "Chronology mismatch: Parent Deed date is later than current Sale Deed date."
                        ),
                    )
                )

        for conv, conv_raw, conv_dt, conv_pg in dates_by_type.get("Land Conversion Order", []):
            for lay, lay_raw, lay_dt, lay_pg in dates_by_type.get("Approved Layout Plan", []):
                ok = conv_dt <= lay_dt
                checks.append(
                    cls._build_row(
                        category="Chronology",
                        field="Conversion Order vs Layout Approval Date",
                        doc_a=conv,
                        val_a=conv_raw,
                        page_a=conv_pg,
                        doc_b=lay,
                        val_b=lay_raw,
                        page_b=lay_pg,
                        result=OUTCOME_MATCH if ok else OUTCOME_MISMATCH,
                        evidence=f"Conversion: {conv_raw} | Layout: {lay_raw}",
                        note=(
                            "Land Conversion Order predates Layout Approval."
                            if ok
                            else "Chronology mismatch: Layout Approval precedes Land Conversion Order."
                        ),
                    )
                )

        for sd, sd_raw, sd_dt, sd_pg in dates_by_type.get("Sale Deed", []):
            for mut, mut_raw, mut_dt, mut_pg in dates_by_type.get("Mutation Register Extract", []):
                ok = mut_dt >= sd_dt
                checks.append(
                    cls._build_row(
                        category="Chronology",
                        field="Sale Deed vs Mutation Date",
                        doc_a=sd,
                        val_a=sd_raw,
                        page_a=sd_pg,
                        doc_b=mut,
                        val_b=mut_raw,
                        page_b=mut_pg,
                        result=OUTCOME_MATCH if ok else OUTCOME_UNABLE_TO_COMPARE,
                        evidence=f"Sale Deed: {sd_raw} | Mutation: {mut_raw}",
                        note=(
                            "Mutation recorded on or after Sale Deed execution/registration date."
                            if ok
                            else "Mutation date predates Sale Deed date; verify if mutation corresponds to an earlier instrument."
                        ),
                    )
                )

        return checks

    @staticmethod
    def _compare_against_reference(
        documents: List[Dict[str, Any]], ref: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        all_rows: List[Dict[str, Any]] = []
        mismatches: List[Dict[str, Any]] = []
        ref_map = [
            (("survey_number",), "survey_number", "Survey Number"),
            (("hissa_number",), "hissa_number", "Hissa Number"),
            (("village",), "locality", "Village / Locality"),
            (("taluk",), "taluk", "Taluk"),
            (("district",), "district", "District"),
        ]

        for doc in documents:
            fields = doc.get("extraction", {}).get("fields") or {}
            # A. Location & Survey checks vs user-entered property input
            for doc_fields, ref_key, label in ref_map:
                ref_val = ref.get(ref_key) or ref.get(doc_fields[0])
                if not ref_val or not str(ref_val).strip():
                    continue
                if not any(f in fields for f in doc_fields):
                    continue
                doc_val, pg = _get_field(doc, *doc_fields)
                if not doc_val:
                    all_rows.append({
                        "category": "Reference Property Input",
                        "field": f"Reference {label}",
                        "document_a": "User-Entered Property Profile",
                        "document_a_filename": "User Input",
                        "document_a_id": "reference_property",
                        "document_a_value": str(ref_val),
                        "document_a_page": None,
                        "document_b": doc.get("document_type"),
                        "document_b_filename": doc.get("original_filename"),
                        "document_b_id": doc.get("document_id"),
                        "document_b_value": UNABLE_TO_EXTRACT,
                        "document_b_page": None,
                        "result": OUTCOME_MISSING_INFO,
                        "evidence": f"Entered: {ref_val} vs Document: {UNABLE_TO_EXTRACT}",
                        "note": f"{label} could not be extracted from {doc.get('document_type')} to compare against '{ref_val}'.",
                    })
                    continue

                if doc_fields[0] in ("survey_number", "hissa_number"):
                    same = normalize_survey_number(doc_val) == normalize_survey_number(str(ref_val))
                else:
                    same = _places_match(str(ref_val), doc_val)

                res = OUTCOME_MATCH if same else OUTCOME_MISMATCH
                row = {
                    "category": "Reference Property Input",
                    "field": f"Reference {label}",
                    "document_a": "User-Entered Property Profile",
                    "document_a_filename": "User Input",
                    "document_a_id": "reference_property",
                    "document_a_value": str(ref_val),
                    "document_a_page": None,
                    "document_b": doc.get("document_type"),
                    "document_b_filename": doc.get("original_filename"),
                    "document_b_id": doc.get("document_id"),
                    "document_b_value": doc_val,
                    "document_b_page": pg,
                    "result": res,
                    "evidence": f"Entered: {ref_val} vs Document: {doc_val} (p.{pg or '-'})",
                    "note": (
                        f"Document {label} matches user-entered property profile."
                        if same
                        else f"Uploaded {doc.get('document_type')} specifies {label} '{doc_val}', differing from user-entered '{ref_val}'."
                    ),
                }
                all_rows.append(row)
                if not same:
                    mismatches.append({
                        "field": label,
                        "severity": "Critical" if label in ("Survey Number", "Village / Locality") else "High",
                        "reference_value": str(ref_val),
                        "document_type": doc.get("document_type"),
                        "filename": doc.get("original_filename"),
                        "document_id": doc.get("document_id"),
                        "document_value": doc_val,
                        "page_number": pg,
                        "note": row["note"],
                    })

            # B. Normalized Property Extent comparison vs user-entered extent (Requirement #1)
            ref_area_raw = ref.get("land_area") or ref.get("property_extent")
            has_extent_field = any(k in fields for k in ("property_extent", "total_land_extent", "converted_extent", "plot_dimensions"))
            if ref_area_raw and str(ref_area_raw).strip() and has_extent_field:
                doc_ext, pg = _get_field(doc, "property_extent", "total_land_extent", "converted_extent", "plot_dimensions")
                ref_sqft = parse_area_to_sqft(str(ref_area_raw), default_unit_sqft=True)
                if not doc_ext:
                    all_rows.append({
                        "category": "Reference Property Input",
                        "field": "Reference Property Extent",
                        "document_a": "User-Entered Property Profile",
                        "document_a_filename": "User Input",
                        "document_a_id": "reference_property",
                        "document_a_value": str(ref_area_raw),
                        "document_a_page": None,
                        "document_b": doc.get("document_type"),
                        "document_b_filename": doc.get("original_filename"),
                        "document_b_id": doc.get("document_id"),
                        "document_b_value": UNABLE_TO_EXTRACT,
                        "document_b_page": None,
                        "result": OUTCOME_MISSING_INFO,
                        "evidence": f"Entered: {ref_area_raw} vs Document: {UNABLE_TO_EXTRACT}",
                        "note": f"Document extent could not be extracted from {doc.get('document_type')} to compare against user-entered '{ref_area_raw}'.",
                    })
                else:
                    doc_sqft, _ = _extract_primary_extent_sqft(doc_ext)
                    if ref_sqft is None or doc_sqft is None:
                        all_rows.append({
                            "category": "Reference Property Input",
                            "field": "Reference Property Extent",
                            "document_a": "User-Entered Property Profile",
                            "document_a_filename": "User Input",
                            "document_a_id": "reference_property",
                            "document_a_value": str(ref_area_raw),
                            "document_a_page": None,
                            "document_b": doc.get("document_type"),
                            "document_b_filename": doc.get("original_filename"),
                            "document_b_id": doc.get("document_id"),
                            "document_b_value": doc_ext,
                            "document_b_page": pg,
                            "result": OUTCOME_UNABLE_TO_COMPARE,
                            "evidence": f"Entered: {ref_area_raw} vs Document: {doc_ext}",
                            "note": "Unable to normalize entered extent or document extent units for automated comparison.",
                        })
                    else:
                        diff_pct = abs(ref_sqft - doc_sqft) / max(ref_sqft, doc_sqft, 1.0)
                        same_area = diff_pct <= 0.015
                        ratio = max(ref_sqft, doc_sqft) / max(min(ref_sqft, doc_sqft), 1.0)
                        # Check if doc_ext is a parent agricultural RTC survey while target property is a smaller site in the same village
                        doc_vil, _ = _get_field(doc, "village", "locality")
                        ref_vil = str(ref.get("village") or ref.get("locality") or "").strip()
                        same_village = (not _normalize_place(ref_vil) or not _normalize_place(doc_vil) or _places_match(ref_vil, doc_vil))
                        is_parent_rtc_vs_site = (
                            same_village
                            and not same_area
                            and ref_sqft <= 10000
                            and doc_sqft > 10000
                            and (doc.get("document_type") == "RTC / Pahani" or "parent survey" in doc_ext.lower())
                        )
                        if is_parent_rtc_vs_site:
                            row = {
                                "category": "Reference Property Input",
                                "field": "Reference Property Extent",
                                "document_a": "User-Entered Property Profile",
                                "document_a_filename": "User Input",
                                "document_a_id": "reference_property",
                                "document_a_value": f"{ref_area_raw} ({ref_sqft:,.0f} sq.ft.)",
                                "document_a_page": None,
                                "document_b": doc.get("document_type"),
                                "document_b_filename": doc.get("original_filename"),
                                "document_b_id": doc.get("document_id"),
                                "document_b_value": f"{doc_ext} ({doc_sqft:,.0f} sq.ft.)",
                                "document_b_page": pg,
                                "result": OUTCOME_UNABLE_TO_COMPARE,
                                "evidence": f"Entered site {ref_sqft:,.0f} sq.ft. vs parent {doc.get('document_type')} {doc_sqft:,.0f} sq.ft. (p.{pg or '-'})",
                                "note": (
                                    f"Unable to Verify Subdivision / Site Extent: {doc.get('document_type')} records parent survey extent "
                                    f"({doc_sqft:,.0f} sq.ft.), whereas entered site is {ref_sqft:,.0f} sq.ft.; subdivision/11E/layout approval proof required."
                                ),
                            }
                            all_rows.append(row)
                        else:
                            note = (
                                f"Normalized extent matches (~{ref_sqft:,.0f} sq.ft. vs ~{doc_sqft:,.0f} sq.ft.)."
                                if same_area
                                else (
                                    f"Major property-reference extent mismatch: user entered {ref_area_raw} ({ref_sqft:,.0f} sq.ft.) "
                                    f"whereas {doc.get('document_type')} records {doc_ext} ({doc_sqft:,.0f} sq.ft., {ratio:,.1f}x difference)."
                                )
                            )
                            row = {
                                "category": "Reference Property Input",
                                "field": "Reference Property Extent",
                                "document_a": "User-Entered Property Profile",
                                "document_a_filename": "User Input",
                                "document_a_id": "reference_property",
                                "document_a_value": f"{ref_area_raw} ({ref_sqft:,.0f} sq.ft.)",
                                "document_a_page": None,
                                "document_b": doc.get("document_type"),
                                "document_b_filename": doc.get("original_filename"),
                                "document_b_id": doc.get("document_id"),
                                "document_b_value": f"{doc_ext} ({doc_sqft:,.0f} sq.ft.)",
                                "document_b_page": pg,
                                "result": OUTCOME_MATCH if same_area else OUTCOME_MISMATCH,
                                "evidence": f"Entered {ref_sqft:,.0f} sq.ft. vs Document {doc_sqft:,.0f} sq.ft. (p.{pg or '-'})",
                                "note": note,
                            }
                            all_rows.append(row)
                            if not same_area:
                                mismatches.append({
                                    "field": "Property Extent",
                                    "severity": "Critical" if (diff_pct >= 0.25 or ratio >= 1.5) else "High",
                                    "reference_value": f"{ref_area_raw} ({ref_sqft:,.0f} sq.ft.)",
                                    "document_type": doc.get("document_type"),
                                    "filename": doc.get("original_filename"),
                                    "document_id": doc.get("document_id"),
                                    "document_value": f"{doc_ext} ({doc_sqft:,.0f} sq.ft.)",
                                    "page_number": pg,
                                    "note": note,
                                })

        return all_rows, mismatches
