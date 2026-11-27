"""OCR and PDF/Image preprocessing service (PyMuPDF/pypdf/pdfplumber + OpenCV/Pillow + Tesseract)."""
import importlib.util
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from modules.land_document_analyzer.backend.config.settings import Settings
from modules.land_document_analyzer.backend.utils.security import get_safe_logger

logger = get_safe_logger(__name__)

# Detect library availability without importing heavy native binaries (OpenCV/PyMuPDF/PDFium) at startup
CV2_AVAILABLE = importlib.util.find_spec("cv2") is not None
PYMUPDF_AVAILABLE = (importlib.util.find_spec("pymupdf") is not None) or (importlib.util.find_spec("fitz") is not None)
PDFPLUMBER_AVAILABLE = importlib.util.find_spec("pdfplumber") is not None
PYPDF_AVAILABLE = importlib.util.find_spec("pypdf") is not None
PYPDFIUM_AVAILABLE = importlib.util.find_spec("pypdfium2") is not None

cv2 = None
fitz = None
pdfplumber = None
PdfReader = None
pdfium = None
np = None
pytesseract = None


def _get_np():
    global np
    if np is None:
        import numpy as _np
        np = _np
    return np


_TESSERACT_CMD_RESOLVED = ""


def _get_pytesseract():
    global pytesseract
    if pytesseract is None:
        import pytesseract as _pt
        if _TESSERACT_CMD_RESOLVED:
            _pt.pytesseract.tesseract_cmd = _TESSERACT_CMD_RESOLVED
        pytesseract = _pt
    return pytesseract


def _get_cv2():
    global cv2
    if cv2 is None and CV2_AVAILABLE:
        import cv2 as _cv2
        cv2 = _cv2
    return cv2


def _get_fitz():
    global fitz
    if fitz is None and PYMUPDF_AVAILABLE:
        try:
            import pymupdf as _fitz
        except ImportError:
            import fitz as _fitz
        fitz = _fitz
    return fitz


def _get_pdfplumber():
    global pdfplumber
    if pdfplumber is None and PDFPLUMBER_AVAILABLE:
        import pdfplumber as _pdfplumber
        pdfplumber = _pdfplumber
    return pdfplumber


def _get_pypdf_reader():
    global PdfReader
    if PdfReader is None and PYPDF_AVAILABLE:
        from pypdf import PdfReader as _PdfReader
        PdfReader = _PdfReader
    return PdfReader


def _get_pdfium():
    global pdfium
    if pdfium is None and PYPDFIUM_AVAILABLE:
        import pypdfium2 as _pdfium
        pdfium = _pdfium
    return pdfium


class OCRService:
    """
    Processes digital PDFs (direct embedded text extraction without unnecessary OCR),
    scanned multi-page PDFs (rasterization + preprocessing + Tesseract OCR), and JPEG/PNG images.
    Preserves per-page text, page numbers, method, confidence, processing_status, and errors.
    """

    def __init__(self, languages: Optional[str] = None):
        self.requested_languages = languages or Settings.OCR_LANGUAGES
        self.tesseract_available = self._configure_tesseract()
        self.available_languages = self._detect_installed_languages() if self.tesseract_available else []
        self.active_language = self._resolve_language(self.requested_languages) if self.tesseract_available else "unavailable"

    @staticmethod
    def _configure_tesseract() -> bool:
        global _TESSERACT_CMD_RESOLVED
        cmd = (Settings.TESSERACT_CMD or "").strip()
        resolved = ""
        if cmd:
            if Path(cmd).exists():
                resolved = cmd
            else:
                resolved = shutil.which(cmd) or ""
        if not resolved:
            resolved = shutil.which("tesseract") or ""
        if resolved:
            _TESSERACT_CMD_RESOLVED = resolved
            if pytesseract is not None:
                pytesseract.pytesseract.tesseract_cmd = resolved
            return True
        return False

    @staticmethod
    def _detect_installed_languages() -> List[str]:
        if _TESSERACT_CMD_RESOLVED:
            try:
                import subprocess
                out = subprocess.run(
                    [_TESSERACT_CMD_RESOLVED, "--list-langs"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                lines = [ln.strip() for ln in (out.stdout or "").splitlines()[1:] if ln.strip()]
                if lines:
                    return lines
            except Exception:
                pass
        try:
            pt = _get_pytesseract()
            langs = pt.get_languages(config="")
            return langs or ["eng"]
        except Exception:
            return ["eng"]

    def _resolve_language(self, requested: str) -> str:
        parts = [p.strip() for p in requested.split("+") if p.strip()]
        valid = [p for p in parts if p in self.available_languages]
        if valid:
            return "+".join(valid)
        return Settings.OCR_FALLBACK_LANGUAGE

    def process_file(self, file_path: str) -> Dict[str, Any]:
        """Processes a PDF or image file cleanly, isolating corrupt/empty/unreadable files."""
        path = Path(file_path)
        if not path.exists():
            return self._failed_result(
                engine_used="file_missing",
                status="corrupted_or_failed",
                error=f"Stored document file not found: {file_path}",
            )

        if path.stat().st_size == 0:
            return self._failed_result(
                engine_used="empty_file",
                status="empty",
                error="Uploaded file contains 0 bytes and cannot be read.",
            )

        ext = path.suffix.lower()
        if ext == ".pdf":
            return self._process_pdf(path)
        if ext in {".jpg", ".jpeg", ".png"}:
            return self._process_image(path)
        return self._failed_result(
            engine_used="unsupported_extension",
            status="corrupted_or_failed",
            error=f"Unsupported file type for OCR: {ext}",
        )

    def _failed_result(self, engine_used: str, status: str, error: str) -> Dict[str, Any]:
        return {
            "engine_used": engine_used,
            "processing_status": status,
            "text_extraction_method": "failed",
            "ocr_applied": False,
            "tesseract_available": self.tesseract_available,
            "opencv_available": CV2_AVAILABLE,
            "ocr_language_active": self.active_language,
            "kannada_ocr_installed": "kan" in self.available_languages,
            "page_count": 0,
            "average_confidence": 0.0,
            "ocr_confidence": 0.0,
            "unreadable_pages": [],
            "low_confidence_pages": [],
            "pages": [],
            "raw_text": "",
            "errors": [error],
            "warnings": [error],
        }

    def _process_pdf(self, path: Path) -> Dict[str, Any]:
        pages_output: List[Dict[str, Any]] = []
        errors: List[str] = []
        engine_used = "pymupdf" if PYMUPDF_AVAILABLE else "pdfplumber_pypdf"

        if PYMUPDF_AVAILABLE:
            fitz_mod = _get_fitz()
            doc = None
            try:
                doc = fitz_mod.open(str(path))
                if getattr(doc, "needs_pass", False):
                    return self._failed_result(
                        engine_used="pymupdf",
                        status="corrupted_or_failed",
                        error="PDF is password-protected or encrypted; remove password protection before uploading.",
                    )
                if len(doc) == 0:
                    return self._failed_result(
                        engine_used="pymupdf",
                        status="empty",
                        error="PDF contains zero pages.",
                    )
                for idx, page in enumerate(doc, start=1):
                    try:
                        digital_text = (page.get_text("text") or "").strip()
                        if len(digital_text) >= 40:
                            pages_output.append(
                                {
                                    "page_number": idx,
                                    "text": digital_text,
                                    "method": "digital_pdf_text",
                                    "confidence": 0.98,
                                    "readability": "readable",
                                    "processing_status": "processed",
                                    "rotation_corrected_deg": 0,
                                    "errors": [],
                                }
                            )
                        else:
                            # Attempt scanned OCR; if Tesseract is unavailable, retain any short digital text honestly
                            pix = page.get_pixmap(dpi=Settings.OCR_DPI)
                            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            ocr_res = self._ocr_pil_image(img, page_number=idx)
                            if digital_text and len(ocr_res.get("text", "")) < len(digital_text):
                                pages_output.append(
                                    {
                                        "page_number": idx,
                                        "text": digital_text,
                                        "method": "digital_pdf_text_sparse",
                                        "confidence": 0.72,
                                        "readability": "low_confidence",
                                        "processing_status": "partially_readable",
                                        "rotation_corrected_deg": 0,
                                        "errors": [],
                                        "warning": "Page contains very sparse digital text; verify visually.",
                                    }
                                )
                            else:
                                pages_output.append(ocr_res)
                    except Exception as page_exc:
                        err_msg = f"Page {idx} processing error: {type(page_exc).__name__}"
                        errors.append(err_msg)
                        pages_output.append(
                            {
                                "page_number": idx,
                                "text": "",
                                "method": "page_error",
                                "confidence": 0.0,
                                "readability": "unreadable",
                                "processing_status": "failed",
                                "rotation_corrected_deg": 0,
                                "errors": [err_msg],
                            }
                        )
            except Exception as exc:
                logger.warning("Corrupted or unreadable PDF %s: %s", path.name, type(exc).__name__)
                return self._failed_result(
                    engine_used="pymupdf",
                    status="corrupted_or_failed",
                    error=f"Corrupted or unreadable PDF file ({type(exc).__name__}).",
                )
            finally:
                if doc is not None:
                    try:
                        doc.close()
                    except Exception:
                        pass
        else:
            try:
                digital_pages = self._extract_digital_pdf_fallback(path)
                rendered_images: Optional[List[Image.Image]] = None
                for idx, dtext in enumerate(digital_pages, start=1):
                    clean_dtext = (dtext or "").strip()
                    if len(clean_dtext) >= 40:
                        pages_output.append(
                            {
                                "page_number": idx,
                                "text": clean_dtext,
                                "method": "digital_pdf_text",
                                "confidence": 0.98,
                                "readability": "readable",
                                "processing_status": "processed",
                                "rotation_corrected_deg": 0,
                                "errors": [],
                            }
                        )
                    else:
                        if rendered_images is None:
                            rendered_images = self._render_pdf_pages(path)
                        if idx - 1 < len(rendered_images):
                            ocr_res = self._ocr_pil_image(rendered_images[idx - 1], page_number=idx)
                            pages_output.append(ocr_res)
                        else:
                            pages_output.append(
                                {
                                    "page_number": idx,
                                    "text": clean_dtext,
                                    "method": "ocr_unavailable",
                                    "confidence": 0.0,
                                    "readability": "unreadable",
                                    "processing_status": "ocr_unavailable",
                                    "rotation_corrected_deg": 0,
                                    "errors": ["No OCR renderer/Tesseract available for scanned PDF page."],
                                }
                            )
            except Exception as exc:
                return self._failed_result(
                    engine_used=engine_used,
                    status="corrupted_or_failed",
                    error=f"Corrupted or unreadable PDF file ({type(exc).__name__}).",
                )

        return self._compile_ocr_result(pages_output, engine_used=engine_used, errors=errors)

    @staticmethod
    def _extract_digital_pdf_fallback(path: Path) -> List[str]:
        if PDFPLUMBER_AVAILABLE:
            plumber_mod = _get_pdfplumber()
            with plumber_mod.open(str(path)) as pdf:
                return [(p.extract_text() or "") for p in pdf.pages]
        if PYPDF_AVAILABLE:
            reader_cls = _get_pypdf_reader()
            reader = reader_cls(str(path))
            return [(p.extract_text() or "") for p in reader.pages]
        return [""]

    @staticmethod
    def _render_pdf_pages(path: Path) -> List[Image.Image]:
        images: List[Image.Image] = []
        if PYPDFIUM_AVAILABLE:
            pdfium_mod = _get_pdfium()
            pdf = pdfium_mod.PdfDocument(str(path))
            scale = Settings.OCR_DPI / 72.0
            for i in range(len(pdf)):
                page = pdf[i]
                bitmap = page.render(scale=scale)
                images.append(bitmap.to_pil().convert("RGB"))
            pdf.close()
        return images

    def _process_image(self, path: Path) -> Dict[str, Any]:
        try:
            with Image.open(path) as opened:
                img = opened.convert("RGB")
        except (UnidentifiedImageError, OSError, Exception) as exc:
            return self._failed_result(
                engine_used="pillow",
                status="corrupted_or_failed",
                error=f"Corrupted or unreadable image file ({type(exc).__name__}).",
            )

        page_res = self._ocr_pil_image(img, page_number=1)
        if not self.tesseract_available:
            engine = "ocr_unavailable_no_tesseract"
        elif CV2_AVAILABLE:
            engine = "opencv_tesseract"
        else:
            engine = "pillow_tesseract"
        return self._compile_ocr_result([page_res], engine_used=engine, errors=page_res.get("errors", []))

    @staticmethod
    def _ocr_unavailable_page(page_number: int) -> Dict[str, Any]:
        msg = (
            "Tesseract OCR binary is not installed on the server. "
            "Embedded digital PDF text is supported; scanned PDF/image OCR requires Tesseract."
        )
        return {
            "page_number": page_number,
            "text": "",
            "method": "ocr_unavailable_no_tesseract",
            "confidence": 0.0,
            "readability": "unreadable",
            "processing_status": "ocr_unavailable",
            "rotation_corrected_deg": 0,
            "errors": [msg],
            "warning": msg,
        }

    def _ocr_pil_image(self, pil_image: Image.Image, page_number: int) -> Dict[str, Any]:
        """Applies orientation correction + OpenCV/Pillow preprocessing + Tesseract OCR."""
        if not self.tesseract_available:
            return self._ocr_unavailable_page(page_number)

        try:
            np_mod = _get_np()
            cv2_mod = _get_cv2()
            if CV2_AVAILABLE and cv2_mod is not None:
                cv_img = cv2_mod.cvtColor(np_mod.array(pil_image), cv2_mod.COLOR_RGB2BGR)
                rotation_deg = self._detect_orientation(cv_img)
                if rotation_deg in (90, 180, 270):
                    cv_img = self._rotate_right_angle(cv_img, rotation_deg)

                gray = cv2_mod.cvtColor(cv_img, cv2_mod.COLOR_BGR2GRAY)
                h, w = gray.shape[:2]
                if max(h, w) < 1200:
                    scale = 1400.0 / max(h, w)
                    gray = cv2_mod.resize(gray, None, fx=scale, fy=scale, interpolation=cv2_mod.INTER_CUBIC)

                denoised = cv2_mod.fastNlMeansDenoising(gray, h=10)
                thresh = cv2_mod.adaptiveThreshold(
                    denoised, 255, cv2_mod.ADAPTIVE_THRESH_GAUSSIAN_C, cv2_mod.THRESH_BINARY, 31, 11
                )
                method_name = "opencv_tesseract_ocr"
            else:
                work_img = ImageOps.exif_transpose(pil_image)
                rotation_deg = self._detect_orientation(np_mod.array(work_img))
                if rotation_deg in (90, 180, 270):
                    work_img = work_img.rotate(-rotation_deg, expand=True)
                gray_pil = ImageOps.autocontrast(work_img.convert("L"))
                w, h = gray_pil.size
                if max(w, h) < 1200:
                    scale = 1400.0 / max(w, h)
                    gray_pil = gray_pil.resize(
                        (max(1, int(w * scale)), max(1, int(h * scale))),
                        resample=Image.Resampling.BICUBIC,
                    )
                denoised_pil = gray_pil.filter(ImageFilter.MedianFilter(size=3))
                denoised = np_mod.array(denoised_pil)
                cutoff = float(np_mod.percentile(denoised, 45))
                thresh = np_mod.where(denoised > cutoff, 255, 0).astype(np_mod.uint8)
                method_name = "pillow_tesseract_ocr"

            text_a, conf_a = self._run_tesseract_with_conf(denoised)
            text_b, conf_b = self._run_tesseract_with_conf(thresh)
        except Exception as exc:
            pt = _get_pytesseract()
            if isinstance(exc, pt.TesseractNotFoundError):
                self.tesseract_available = False
                return self._ocr_unavailable_page(page_number)
            logger.warning("Tesseract OCR error on page %s: %s", page_number, type(exc).__name__)
            return {
                "page_number": page_number,
                "text": "",
                "method": "ocr_error",
                "confidence": 0.0,
                "readability": "unreadable",
                "processing_status": "failed",
                "rotation_corrected_deg": 0,
                "errors": [f"OCR error on page {page_number}: {type(exc).__name__}"],
            }

        if (len(text_b.strip()) > len(text_a.strip()) * 0.85 and conf_b >= conf_a) or (
            len(text_a.strip()) < 20 and len(text_b.strip()) >= 20
        ):
            final_text, final_conf = text_b, conf_b
        else:
            final_text, final_conf = text_a, conf_a

        cleaned = final_text.strip()
        if len(cleaned) < 15 or final_conf < 0.35:
            readability = "unreadable"
            p_status = "empty" if not cleaned else "partially_readable"
        elif final_conf < 0.65:
            readability = "low_confidence"
            p_status = "partially_readable"
        else:
            readability = "readable"
            p_status = "processed"

        return {
            "page_number": page_number,
            "text": cleaned,
            "method": method_name,
            "confidence": round(final_conf, 3),
            "readability": readability,
            "processing_status": p_status,
            "rotation_corrected_deg": rotation_deg,
            "errors": [],
        }

    @staticmethod
    def _detect_orientation(cv_img: Any) -> int:
        try:
            pt = _get_pytesseract()
            osd = pt.image_to_osd(cv_img)
            match = re.search(r"Rotate:\s*(\d+)", osd)
            if match:
                return int(match.group(1)) % 360
        except Exception:
            pass
        return 0

    @staticmethod
    def _rotate_right_angle(cv_img: Any, degrees: int) -> Any:
        cv2_mod = _get_cv2()
        if cv2_mod is None:
            return cv_img
        if degrees == 90:
            return cv2_mod.rotate(cv_img, cv2_mod.ROTATE_90_CLOCKWISE)
        if degrees == 180:
            return cv2_mod.rotate(cv_img, cv2_mod.ROTATE_180)
        if degrees == 270:
            return cv2_mod.rotate(cv_img, cv2_mod.ROTATE_90_COUNTERCLOCKWISE)
        return cv_img

    def _run_tesseract_with_conf(self, gray_img: Any) -> Tuple[str, float]:
        config = "--oem 3 --psm 6"
        pt = _get_pytesseract()
        data = pt.image_to_data(
            gray_img, lang=self.active_language, config=config, output_type=pt.Output.DICT
        )
        words = []
        confs = []
        for txt, conf in zip(data.get("text", []), data.get("conf", [])):
            t = (txt or "").strip()
            try:
                c = float(conf)
            except (TypeError, ValueError):
                c = -1.0
            if t and c >= 0:
                words.append(t)
                confs.append(c / 100.0)
        raw_text = pytesseract.image_to_string(gray_img, lang=self.active_language, config=config)
        avg_conf = (sum(confs) / len(confs)) if confs else 0.0
        return raw_text, avg_conf

    def _compile_ocr_result(
        self,
        pages: List[Dict[str, Any]],
        engine_used: str,
        errors: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        full_text = "\n\n".join(
            f"--- PAGE {p['page_number']} ---\n{p['text']}" for p in pages
        )
        confidences = [p["confidence"] for p in pages]
        avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
        unreadable_pages = [p["page_number"] for p in pages if p["readability"] == "unreadable"]
        low_conf_pages = [p["page_number"] for p in pages if p["readability"] == "low_confidence"]
        methods = {p.get("method") for p in pages}
        ocr_applied = any("tesseract" in str(m) for m in methods)

        all_errors = list(errors or [])
        all_warnings: List[str] = []
        for p in pages:
            for e in p.get("errors", []) or []:
                if e not in all_errors:
                    all_errors.append(e)
            if p.get("warning") and p["warning"] not in all_warnings:
                all_warnings.append(p["warning"])

        if not pages:
            overall_status = "empty"
        elif len(unreadable_pages) == len(pages):
            if "ocr_unavailable_no_tesseract" in methods:
                overall_status = "ocr_unavailable"
            elif not full_text.strip():
                overall_status = "empty"
            else:
                overall_status = "partially_readable"
        elif unreadable_pages or low_conf_pages:
            overall_status = "partially_readable"
        else:
            overall_status = "processed"

        if "eng" in self.requested_languages and "kan" in self.requested_languages and "kan" not in self.available_languages:
            all_warnings.append(
                "Kannada OCR language pack ('kan') is not installed on the server; Kannada scanned text cannot be OCR-decoded locally."
            )

        extraction_method_desc = (
            "Digital PDF text extraction (OCR not performed)"
            if methods == {"digital_pdf_text"}
            else ("Tesseract OCR + Preprocessing" if ocr_applied else ", ".join(sorted(m for m in methods if m)))
        )

        # Strictly separate text-layer extraction quality from actual raster OCR confidence
        digital_confs = [p["confidence"] for p in pages if str(p.get("method", "")).startswith("digital_pdf")]
        ocr_page_confs = [p["confidence"] for p in pages if "tesseract" in str(p.get("method", ""))]
        text_quality = round(sum(digital_confs) / len(digital_confs), 3) if digital_confs else avg_conf
        ocr_only_conf = round(sum(ocr_page_confs) / len(ocr_page_confs), 3) if ocr_page_confs else None
        ocr_status_label = (
            "OCR Performed"
            if ocr_applied
            else ("Not Performed (Digital PDF text layer used)" if methods == {"digital_pdf_text"} else "OCR Unavailable")
        )

        return {
            "engine_used": engine_used,
            "processing_status": overall_status,
            "text_extraction_method": extraction_method_desc,
            "text_extraction_quality": text_quality,
            "ocr_applied": ocr_applied,
            "ocr_status_label": ocr_status_label,
            "tesseract_available": self.tesseract_available,
            "opencv_available": CV2_AVAILABLE,
            "ocr_language_active": self.active_language,
            "kannada_ocr_installed": "kan" in self.available_languages,
            "page_count": len(pages),
            "average_confidence": avg_conf,
            "ocr_confidence": ocr_only_conf,
            "unreadable_pages": unreadable_pages,
            "low_confidence_pages": low_conf_pages,
            "pages": pages,
            "raw_text": full_text,
            "errors": all_errors,
            "warnings": all_warnings,
        }
