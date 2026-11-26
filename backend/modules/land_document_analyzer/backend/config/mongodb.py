"""MongoDB persistence layer with automatic TTL retention and offline local JSON fallback."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.land_document_analyzer.backend.config.settings import Settings
from modules.land_document_analyzer.backend.utils.security import get_safe_logger

logger = get_safe_logger(__name__)

try:
    from pymongo import ASCENDING, DESCENDING, MongoClient
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False


class LocalCollection:
    """File-backed collection mirroring basic PyMongo CRUD for local/offline execution."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_all([])

    def _read_all(self) -> List[Dict[str, Any]]:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_all(self, docs: List[Dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(docs, f, indent=2, default=str)

    def insert_one(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        docs = self._read_all()
        docs.append(doc)
        self._write_all(docs)
        return doc

    def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for doc in self._read_all():
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    def find(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        docs = self._read_all()
        if not query:
            return docs
        return [d for d in docs if all(d.get(k) == v for k, v in query.items())]

    def update_one(self, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> bool:
        docs = self._read_all()
        for idx, doc in enumerate(docs):
            if all(doc.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    doc.update(update["$set"])
                else:
                    doc.update(update)
                docs[idx] = doc
                self._write_all(docs)
                return True
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", update))
            docs.append(new_doc)
            self._write_all(docs)
            return True
        return False

    def delete_one(self, query: Dict[str, Any]) -> bool:
        docs = self._read_all()
        new_docs = [d for d in docs if not all(d.get(k) == v for k, v in query.items())]
        if len(new_docs) != len(docs):
            self._write_all(new_docs)
            return True
        return False


class DatabaseManager:
    """Manages MongoDB collections (analyses, documents, reports, audit_logs) with local fallback."""

    COLLECTIONS = ("analyses", "documents", "reports", "audit_logs")

    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        Settings.ensure_directories()
        self.uri = uri if uri is not None else Settings.MONGODB_URI
        self.db_name = db_name or Settings.MONGODB_DB_NAME
        self.backend_mode = "local_json"
        self.client = None
        self.db = None
        self._local_collections: Dict[str, LocalCollection] = {}

        require_mongo = os.getenv("REQUIRE_MONGODB", "false").lower() == "true"
        if self.uri and PYMONGO_AVAILABLE:
            try:
                self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
                self.client.admin.command("ping")
                self.db = self.client[self.db_name]
                self.backend_mode = "mongodb"
                self._ensure_indexes()
                logger.info("Connected to MongoDB database: %s", self.db_name)
            except Exception as exc:
                if require_mongo:
                    raise RuntimeError(f"MongoDB connection required in production but failed: {exc}") from exc
                logger.warning("MongoDB unavailable (%s); using local JSON store fallback.", type(exc).__name__)
                self._init_local_store()
        else:
            if require_mongo:
                raise RuntimeError("MONGODB_URI is required when REQUIRE_MONGODB=true (and pymongo must be installed).")
            self._init_local_store()

    def _init_local_store(self) -> None:
        self.backend_mode = "local_json"
        for name in self.COLLECTIONS:
            self._local_collections[name] = LocalCollection(Settings.LOCAL_DB_DIR / f"{name}.json")

    def _ensure_indexes(self) -> None:
        if self.db is None:
            return
        ttl_seconds = Settings.RETENTION_DAYS * 86400
        self.db["analyses"].create_index([("analysis_id", ASCENDING)], unique=True)
        self.db["analyses"].create_index([("property_id", ASCENDING)])
        self.db["analyses"].create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
        self.db["documents"].create_index([("document_id", ASCENDING)], unique=True)
        self.db["documents"].create_index([("analysis_id", ASCENDING)])
        self.db["documents"].create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
        self.db["reports"].create_index([("report_id", ASCENDING)], unique=True)
        self.db["audit_logs"].create_index([("created_at", DESCENDING)], expireAfterSeconds=ttl_seconds)

    def collection(self, name: str):
        if self.backend_mode == "mongodb" and self.db is not None:
            return self.db[name]
        if name not in self._local_collections:
            self._local_collections[name] = LocalCollection(Settings.LOCAL_DB_DIR / f"{name}.json")
        return self._local_collections[name]

    @staticmethod
    def retention_expiry(days: Optional[int] = None) -> str:
        ttl_days = days if days is not None else Settings.RETENTION_DAYS
        return (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
