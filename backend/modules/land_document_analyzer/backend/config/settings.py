"""Environment-driven configuration for AI Land Document Analyzer."""
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
HOST_BACKEND_DIR = Path(__file__).resolve().parents[4]


def _resolve_tesseract_cmd() -> str:
    env_cmd = os.getenv("TESSERACT_CMD", "").strip()
    if env_cmd:
        return env_cmd
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return ""


class Settings:
    """Central application settings loaded from environment variables."""

    APP_NAME = "AI Land Document Analyzer — Karnataka Property Due-Diligence System"
    APP_VERSION = "1.0.0"
    ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = int(os.getenv("FLASK_PORT", "5050"))

    # Security & Auth
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-env")
    API_AUTH_REQUIRED = os.getenv("API_AUTH_REQUIRED", "false").lower() == "true"
    API_BEARER_TOKEN = os.getenv("API_BEARER_TOKEN", "")
    ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

    # Upload & Storage (aligned cleanly with smart-land-eval/backend/storage/doc_analyzer)
    STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", str(HOST_BACKEND_DIR / "storage" / "doc_analyzer")))
    UPLOAD_DIR = STORAGE_ROOT / "uploads"
    REPORT_DIR = STORAGE_ROOT / "reports"
    LOCAL_DB_DIR = STORAGE_ROOT / "local_db"
    MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "25"))
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
    MAX_FILES_PER_ANALYSIS = int(os.getenv("MAX_FILES_PER_ANALYSIS", "30"))
    RETENTION_DAYS = int(os.getenv("DOCUMENT_RETENTION_DAYS", "30"))

    # Allowed MIME types and extensions (executables strictly blocked)
    ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "image/jpeg",
        "image/png",
    }
    BLOCKED_EXTENSIONS = {
        ".exe", ".dll", ".bat", ".cmd", ".sh", ".ps1", ".msi", ".jar",
        ".js", ".vbs", ".scr", ".com", ".elf", ".bin", ".py", ".php", ".html", ".htm",
    }

    # MongoDB
    MONGODB_URI = os.getenv("MONGODB_URI", "")
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "karnataka_land_due_diligence")

    # Pluggable AI Provider Interface (only used when user explicitly consents)
    AI_PROVIDER = os.getenv("AI_PROVIDER", "local_heuristic")  # local_heuristic | gemini | openai | custom
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_MODEL = os.getenv("AI_MODEL", "gemini-2.5-flash")

    # OCR settings
    TESSERACT_CMD = _resolve_tesseract_cmd()
    OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "eng+kan")
    OCR_FALLBACK_LANGUAGE = "eng"
    OCR_DPI = int(os.getenv("OCR_DPI", "220"))

    # Official Karnataka Portals (reference URLs — never scraped or CAPTCHA-bypassed)
    PORTALS = {
        "bhoomi": "https://landrecords.karnataka.gov.in/",
        "kaveri": "https://kaveri.karnataka.gov.in/",
        "mda_mysuru": "https://mdamysuru.uda.gov.in/",
        "bhu_yojane": "https://bhu-yojane.karnataka.gov.in/NIRMANA2",
        "karnataka_rera": "https://rera.karnataka.gov.in/",
        "ecourts": "https://services.ecourts.gov.in/ecourtindia_v6/casestatus/",
    }

    @classmethod
    def ensure_directories(cls) -> None:
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        cls.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOCAL_DB_DIR.mkdir(parents=True, exist_ok=True)
