"""End-to-end due-diligence orchestration pipeline coordinating all 11 backend services."""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.land_document_analyzer.backend.config.mongodb import DatabaseManager
from modules.land_document_analyzer.backend.models.schemas import MANDATORY_LEGAL_DISCLAIMER
from modules.land_document_analyzer.backend.services.approval_verification_service import ApprovalVerificationService
from modules.land_document_analyzer.backend.services.bhoomi_verification_service import BhoomiVerificationService
from modules.land_document_analyzer.backend.services.comparison_service import ComparisonService
from modules.land_document_analyzer.backend.services.document_classification_service import DocumentClassificationService
from modules.land_document_analyzer.backend.services.document_upload_service import DocumentUploadService
from modules.land_document_analyzer.backend.services.ec_verification_service import ECVerificationService
from modules.land_document_analyzer.backend.services.extraction_service import ExtractionService
from modules.land_document_analyzer.backend.services.litigation_service import LitigationService
from modules.land_document_analyzer.backend.services.ocr_service import OCRService
from modules.land_document_analyzer.backend.services.report_generation_service import ReportGenerationService
from modules.land_document_analyzer.backend.services.risk_engine import RiskEngine


class DueDiligencePipeline:
    """Orchestrates upload, OCR, classification, extraction, comparison, verification, risk, and PDF generation."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.upload_service = DocumentUploadService()
        self.ocr_service = OCRService()
        self.classification_service = DocumentClassificationService()
        self.extraction_service = ExtractionService()
        self.comparison_service = ComparisonService()
        self.bhoomi_service = BhoomiVerificationService()
        self.ec_service = ECVerificationService()
        self.approval_service = ApprovalVerificationService()
        self.litigation_service = LitigationService()
        self.risk_engine = RiskEngine()
        self.report_service = ReportGenerationService()

    def run_analysis(
        self,
        property_info: Dict[str, Any],
        uploaded_files: List[Tuple[str, bytes, Optional[str]]],
        manual_cases: Optional[List[Dict[str, Any]]] = None,
        external_ai_consent: bool = False,
        ai_provider: Optional[str] = None,
        generate_pdf: bool = True,
    ) -> Dict[str, Any]:
        analysis_id = f"anl_{uuid.uuid4().hex[:12]}"
        report_id = f"rpt_{uuid.uuid4().hex[:12]}"
        processed_docs: List[Dict[str, Any]] = []
        seen_hashes: Dict[str, Tuple[str, str]] = {}

        uploaded_files_count = len(uploaded_files)
        for filename, content, declared_type in uploaded_files:
            base_doc = self.upload_service.save_document(
                analysis_id=analysis_id,
                filename=filename,
                content=content,
                user_declared_type=declared_type,
            )
            file_hash = base_doc.get("sha256", "")
            is_duplicate = file_hash in seen_hashes
            dup_info = seen_hashes.get(file_hash)

            ocr_res = self.ocr_service.process_file(base_doc["stored_path"])
            if not is_duplicate and file_hash:
                seen_hashes[file_hash] = (base_doc["document_id"], base_doc["original_filename"])

            segments = (
                []
                if is_duplicate
                else self.classification_service.segment_multi_document_pages(
                    ocr_res.get("pages") or [],
                    fallback_filename=base_doc["original_filename"],
                    user_declared_type=declared_type,
                )
            )

            if is_duplicate or len(segments) <= 1:
                cls_res = (
                    segments[0]["classification"]
                    if segments
                    else self.classification_service.classify(
                        text=ocr_res["raw_text"],
                        filename=base_doc["original_filename"],
                        user_declared_type=declared_type,
                    )
                )
                doc_type = cls_res["document_type"]
                ext_res = self.extraction_service.extract_fields(
                    document_type=doc_type,
                    ocr_result=ocr_res,
                    ai_provider_name=ai_provider,
                    external_ai_consent=external_ai_consent,
                )
                doc_proc_status = ocr_res.get("processing_status", "processed")
                pcount = int(ocr_res.get("page_count", len(ocr_res.get("pages") or [])))
                base_doc.update(
                    {
                        "document_type": doc_type,
                        "page_range": f"Pages 1–{pcount}" if pcount > 1 else "Page 1",
                        "is_segmented_from_bundle": False,
                        "is_duplicate": is_duplicate,
                        "duplicate_of_document_id": dup_info[0] if dup_info else None,
                        "duplicate_of_filename": dup_info[1] if dup_info else None,
                        "classification": cls_res,
                        "ocr": ocr_res,
                        "extraction": ext_res,
                        "processing_status": doc_proc_status,
                        "extraction_status": "completed" if ext_res.get("extracted_count", 0) > 0 else doc_proc_status,
                        "expires_at": self.db.retention_expiry(),
                    }
                )
                self.db.collection("documents").insert_one(base_doc)
                processed_docs.append(base_doc)
            else:
                for seg_idx, seg in enumerate(segments):
                    seg_doc = dict(base_doc)
                    seg_doc["document_id"] = base_doc["document_id"] if seg_idx == 0 else f"{base_doc['document_id']}_p{seg_idx + 1}"
                    seg_pages = seg["pages"]
                    seg_ocr = dict(ocr_res)
                    seg_ocr["pages"] = seg_pages
                    seg_ocr["page_count"] = len(seg_pages)
                    seg_ocr["raw_text"] = seg["text"]
                    seg_cls = seg["classification"]
                    doc_type = seg_cls["document_type"]
                    ext_res = self.extraction_service.extract_fields(
                        document_type=doc_type,
                        ocr_result=seg_ocr,
                        ai_provider_name=ai_provider,
                        external_ai_consent=external_ai_consent,
                    )
                    doc_proc_status = seg_ocr.get("processing_status", "processed")
                    seg_doc.update(
                        {
                            "document_type": doc_type,
                            "page_range": seg["page_range"],
                            "page_numbers": seg["page_numbers"],
                            "is_segmented_from_bundle": True,
                            "source_upload_document_id": base_doc["document_id"],
                            "is_duplicate": False,
                            "duplicate_of_document_id": None,
                            "duplicate_of_filename": None,
                            "classification": seg_cls,
                            "ocr": seg_ocr,
                            "extraction": ext_res,
                            "processing_status": doc_proc_status,
                            "extraction_status": "completed" if ext_res.get("extracted_count", 0) > 0 else doc_proc_status,
                            "expires_at": self.db.retention_expiry(),
                        }
                    )
                    self.db.collection("documents").insert_one(seg_doc)
                    processed_docs.append(seg_doc)

        result = self._recompute_analysis(
            analysis_id=analysis_id,
            report_id=report_id,
            property_info=property_info,
            processed_docs=processed_docs,
            manual_cases=manual_cases or [],
            generate_pdf=generate_pdf,
            uploaded_file_count=uploaded_files_count,
        )
        self.db.collection("analyses").insert_one(result)
        return result

    def _recompute_analysis(
        self,
        analysis_id: str,
        report_id: str,
        property_info: Dict[str, Any],
        processed_docs: List[Dict[str, Any]],
        manual_cases: List[Dict[str, Any]],
        generate_pdf: bool = True,
        uploaded_file_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        comparison = self.comparison_service.compare_documents(processed_docs, reference_property=property_info)
        bhoomi = self.bhoomi_service.verify(property_info, processed_docs)
        ec = self.ec_service.verify(property_info, processed_docs)
        approvals = self.approval_service.analyze_approvals(property_info, processed_docs)
        litigation = self.litigation_service.analyze(property_info, processed_docs, manual_cases=manual_cases)
        checklist = self.risk_engine.build_checklist(
            property_info.get("property_type", "residential_plot"),
            processed_docs,
            property_info=property_info,
        )
        risk = self.risk_engine.evaluate(
            property_info=property_info,
            uploaded_documents=processed_docs,
            comparison_result=comparison,
            bhoomi_result=bhoomi,
            ec_result=ec,
            approval_result=approvals,
            litigation_result=litigation,
            checklist_result=checklist,
        )

        extracted_fields_by_doc = {
            d["document_id"]: d["extraction"]["fields"] for d in processed_docs
        }
        document_types = [
            {
                "document_id": d["document_id"],
                "original_filename": d["original_filename"],
                "document_type": d["document_type"],
                "confidence": d["classification"]["confidence"],
                "requires_confirmation": bool(d["classification"].get("requires_confirmation")),
            }
            for d in processed_docs
        ]

        unique_docs = [d for d in processed_docs if not d.get("is_duplicate")]
        comp_sum = comparison.get("summary", {})
        tot_schema = sum(d.get("extraction", {}).get("total_fields", len(d.get("extraction", {}).get("fields", {}))) for d in unique_docs)
        tot_ext = sum(d.get("extraction", {}).get("extracted_count", 0) for d in unique_docs)
        text_quals = [float(d.get("ocr", {}).get("text_extraction_quality", d.get("ocr", {}).get("average_confidence", 0.0))) for d in unique_docs]
        ocr_actuals = [float(d.get("ocr", {}).get("ocr_confidence")) for d in unique_docs if d.get("ocr", {}).get("ocr_applied") and d.get("ocr", {}).get("ocr_confidence") is not None]
        cls_confs = [float(d.get("classification", {}).get("confidence", 0.0)) for d in unique_docs]
        fld_confs = [float(d.get("extraction", {}).get("field_extraction_confidence", 0.0)) for d in unique_docs]
        docs_processed_ok = sum(
            1 for d in unique_docs
            if d.get("ocr", {}).get("processing_status", "processed") in ("processed", "partially_readable")
        )

        distinct_uploads = len({d.get("sha256") or d.get("original_filename") for d in processed_docs})
        processing_summary = {
            "files_received": len(processed_docs),
            "uploaded_file_count": uploaded_file_count if uploaded_file_count is not None else distinct_uploads,
            "identified_document_count": len(unique_docs),
            "unique_files": len(unique_docs),
            "documents_processed_successfully": docs_processed_ok,
            "duplicate_files": len(processed_docs) - len(unique_docs),
            "files_classified": sum(1 for d in unique_docs if not d.get("classification", {}).get("requires_confirmation")),
            "files_requiring_confirmation": sum(1 for d in unique_docs if d.get("classification", {}).get("requires_confirmation")),
            "files_failed_or_empty": sum(
                1 for d in unique_docs
                if d.get("ocr", {}).get("processing_status") in ("corrupted_or_failed", "empty", "ocr_unavailable")
            ),
            "pages_processed": sum(int(d.get("ocr", {}).get("page_count", 0)) for d in unique_docs),
            "pages_unreadable": sum(len(d.get("ocr", {}).get("unreadable_pages", [])) for d in unique_docs),
            "total_schema_fields": tot_schema,
            "fields_extracted": tot_ext,
            "fields_unable_to_extract": max(0, tot_schema - tot_ext),
            "field_extraction_rate": round(tot_ext / tot_schema, 3) if tot_schema else 0.0,
            "text_extraction_quality": round(sum(text_quals) / len(text_quals), 3) if text_quals else 0.0,
            "ocr_performed_on_any_document": bool(ocr_actuals),
            "avg_ocr_confidence": round(sum(ocr_actuals) / len(ocr_actuals), 3) if ocr_actuals else None,
            "ocr_status_note": (
                f"Tesseract OCR applied ({round(sum(ocr_actuals) / len(ocr_actuals) * 100)}%)"
                if ocr_actuals
                else "Not Applicable — Digital PDF text extraction used (OCR not performed)"
            ),
            "avg_classification_confidence": round(sum(cls_confs) / len(cls_confs), 3) if cls_confs else 0.0,
            "avg_field_extraction_confidence": round(sum(fld_confs) / len(fld_confs), 3) if fld_confs else 0.0,
            "confidence_disclaimer": (
                "Text extraction, OCR, classification, and field extraction confidences measure automated parsing quality only "
                "and do NOT represent legal verification confidence or government record authenticity."
            ),
            "comparisons_total": comp_sum.get("total_checks", 0),
            "comparisons_matched": comp_sum.get("matches", 0),
            "confirmed_mismatches": comp_sum.get("confirmed_mismatches", comp_sum.get("mismatches", 0)),
            "comparisons_mismatched": comp_sum.get("confirmed_mismatches", comp_sum.get("mismatches", 0)),
            "unable_to_compare": comp_sum.get("unable_to_compare", 0),
            "missing_information": comp_sum.get("missing_information", 0),
            "incomplete_comparisons": comp_sum.get("incomplete_comparisons", 0),
            "comparisons_incomplete": comp_sum.get("incomplete_comparisons", 0),
            "official_verification_status": "Pending Manual Verification (Karnataka Bhoomi, Kaveri, eCourts, Planning Authority)",
        }

        result = {
            "analysis_id": analysis_id,
            "report_id": report_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": self.db.retention_expiry(),
            "property_info": property_info,
            "documents": processed_docs,
            "document_types": document_types,
            "processing_summary": processing_summary,
            "extracted_fields": extracted_fields_by_doc,
            "cross_document_comparisons": comparison,
            "official_verification_status": {
                "bhoomi": bhoomi,
                "kaveri_ec": ec,
                "approvals_and_planning": approvals["jurisdiction"],
            },
            "approval_analysis": approvals,
            "litigation_findings": litigation,
            "risk_assessment": risk,
            "risk_findings": risk["findings"],
            "missing_documents": checklist,
            "overall_assessment": risk["overall_assessment"],
            "manual_cases": manual_cases,
            "legal_disclaimer": MANDATORY_LEGAL_DISCLAIMER,
        }

        if generate_pdf:
            pdf_path = self.report_service.generate_pdf(result)
            result["report_pdf_path"] = str(pdf_path)
            self.db.collection("reports").update_one(
                {"report_id": report_id},
                {
                    "$set": {
                        "report_id": report_id,
                        "analysis_id": analysis_id,
                        "pdf_path": str(pdf_path),
                        "generated_at": result["generated_at"],
                    }
                },
                upsert=True,
            )

        return result

    def reclassify_document(
        self,
        analysis_id: str,
        document_id: str,
        new_document_type: str,
        reclassified_by: str = "user",
    ) -> Optional[Dict[str, Any]]:
        """Re-classifies an already-uploaded document without re-upload and re-runs schema extraction cleanly."""
        analysis = self.db.collection("analyses").find_one({"analysis_id": analysis_id})
        if not analysis:
            return None

        docs = analysis.get("documents", [])
        target_doc = None
        for doc in docs:
            if doc.get("document_id") == document_id:
                target_doc = doc
                break

        if not target_doc:
            return None

        cls_info = target_doc.get("classification", {})
        prev_type = target_doc.get("document_type")
        history = list(cls_info.get("classification_history") or [])
        history.append({
            "previous_type": prev_type,
            "new_type": new_document_type,
            "changed_by": reclassified_by,
            "changed_at": datetime.now(timezone.utc).isoformat(),
        })
        cls_info.setdefault("original_classified_type", prev_type)
        cls_info["document_type"] = new_document_type
        cls_info["corrected_type"] = new_document_type
        cls_info["classification_status"] = "Manually Reclassified"
        cls_info["requires_confirmation"] = False
        cls_info["confirmation_message"] = None
        cls_info["classification_method"] = "manual_user_reclassification"
        cls_info["classification_history"] = history

        target_doc["document_type"] = new_document_type
        target_doc["classification"] = cls_info
        target_doc["extraction"] = self.extraction_service.extract_fields(
            document_type=new_document_type,
            ocr_result=target_doc.get("ocr", {}),
            ai_provider_name=target_doc.get("extraction", {}).get("ai_provider_used"),
            external_ai_consent=False,
        )
        self.db.collection("documents").update_one({"document_id": document_id}, {"$set": target_doc})

        recomputed = self._recompute_analysis(
            analysis_id=analysis_id,
            report_id=analysis["report_id"],
            property_info=analysis["property_info"],
            processed_docs=docs,
            manual_cases=analysis.get("manual_cases", []),
            generate_pdf=True,
        )
        self.db.collection("analyses").update_one({"analysis_id": analysis_id}, {"$set": recomputed})
        return recomputed

    def apply_manual_correction(
        self, analysis_id: str, document_id: str, corrections: Dict[str, str], corrected_by: str = "user"
    ) -> Optional[Dict[str, Any]]:
        analysis = self.db.collection("analyses").find_one({"analysis_id": analysis_id})
        if not analysis:
            return None

        docs = analysis.get("documents", [])
        updated = False
        for doc in docs:
            if doc.get("document_id") == document_id:
                for field_name, val in corrections.items():
                    self.extraction_service.apply_manual_correction(doc["extraction"], field_name, val, corrected_by)
                self.db.collection("documents").update_one({"document_id": document_id}, {"$set": doc})
                updated = True
                break

        if not updated:
            return None

        recomputed = self._recompute_analysis(
            analysis_id=analysis_id,
            report_id=analysis["report_id"],
            property_info=analysis["property_info"],
            processed_docs=docs,
            manual_cases=analysis.get("manual_cases", []),
            generate_pdf=True,
        )
        self.db.collection("analyses").update_one({"analysis_id": analysis_id}, {"$set": recomputed})
        return recomputed

    def delete_document(self, analysis_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        analysis = self.db.collection("analyses").find_one({"analysis_id": analysis_id})
        if not analysis:
            return None

        remaining = []
        for doc in analysis.get("documents", []):
            if doc.get("document_id") == document_id:
                self.upload_service.delete_document_file(doc.get("stored_path"))
                self.db.collection("documents").delete_one({"document_id": document_id})
            else:
                remaining.append(doc)

        recomputed = self._recompute_analysis(
            analysis_id=analysis_id,
            report_id=analysis["report_id"],
            property_info=analysis["property_info"],
            processed_docs=remaining,
            manual_cases=analysis.get("manual_cases", []),
            generate_pdf=True,
        )
        self.db.collection("analyses").update_one({"analysis_id": analysis_id}, {"$set": recomputed})
        return recomputed

    def get_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        return self.db.collection("analyses").find_one({"analysis_id": analysis_id})

    def get_report_path(self, analysis_id: str) -> Optional[Path]:
        analysis = self.get_analysis(analysis_id)
        if not analysis:
            return None
        path_str = analysis.get("report_pdf_path")
        if path_str and Path(path_str).exists():
            return Path(path_str)
        return self.report_service.generate_pdf(analysis)
