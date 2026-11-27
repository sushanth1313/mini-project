"""
Regression tests for BSON ObjectId serialization across Document Analyzer API routes.
Runs strictly in-memory against isolated fake PyMongo-like collections without touching
production MongoDB or SQLite/Postgres databases.
"""
import io
import json
import sys
import tempfile
from pathlib import Path

from bson import ObjectId

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from modules.land_document_analyzer.backend.app import create_app
from modules.land_document_analyzer.backend import app as doc_app_mod
from modules.land_document_analyzer.backend.config.settings import Settings
from modules.land_document_analyzer.backend.utils.security import sanitize_for_json


class _FakeMongoCollection:
    """Mimics PyMongo insert_one mutating the inserted dict in-place with an ObjectId _id."""

    def __init__(self):
        self.rows = []

    def insert_one(self, doc):
        doc["_id"] = ObjectId()
        self.rows.append(doc)
        return doc

    def find(self, query=None):
        if not query:
            return list(self.rows)
        return [r for r in self.rows if all(r.get(k) == v for k, v in query.items())]

    def find_one(self, query):
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                return r
        return None

    def update_one(self, query, update, upsert=False):
        target = self.find_one(query)
        if target is not None:
            payload = update.get("$set", update)
            assert "_id" not in payload, "$set must never overwrite immutable Mongo _id"
            target.update(payload)
            return True
        if upsert:
            rec = dict(query)
            rec.update(update.get("$set", update))
            rec["_id"] = ObjectId()
            self.rows.append(rec)
            return True
        return False

    def delete_one(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not all(r.get(k) == v for k, v in query.items())]
        return len(self.rows) != before


class _FakeDbManager:
    backend_mode = "mongodb"

    def __init__(self):
        self.cols = {n: _FakeMongoCollection() for n in ("analyses", "documents", "reports", "audit_logs")}

    def collection(self, name):
        return self.cols[name]

    @staticmethod
    def retention_expiry():
        return "2027-01-01T00:00:00+00:00"


def test_sanitize_for_json_nested_non_mutating():
    top_oid = ObjectId()
    nested_oid_1 = ObjectId()
    nested_oid_2 = ObjectId()
    raw = {
        "_id": top_oid,
        "documents": [
            {"document_id": "d1", "_id": nested_oid_1, "nested": {"ref_id": nested_oid_2}},
        ],
        "meta": ("tag", nested_oid_2),
    }

    cleaned = sanitize_for_json(raw)
    dumped = json.dumps(cleaned)
    parsed = json.loads(dumped)

    assert parsed["_id"] == str(top_oid)
    assert parsed["documents"][0]["_id"] == str(nested_oid_1)
    assert parsed["documents"][0]["nested"]["ref_id"] == str(nested_oid_2)
    assert parsed["meta"] == ["tag", str(nested_oid_2)]
    # Original MongoDB objects must remain untouched
    assert isinstance(raw["_id"], ObjectId)
    assert isinstance(raw["documents"][0]["_id"], ObjectId)
    assert isinstance(raw["documents"][0]["nested"]["ref_id"], ObjectId)


def test_document_analysis_routes_handle_nested_objectids():
    fake_db = _FakeDbManager()
    orig_db = doc_app_mod._pipeline.db
    orig_token = Settings.API_BEARER_TOKEN
    orig_upload_dir = Settings.UPLOAD_DIR
    orig_report_dir = Settings.REPORT_DIR

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            Settings.API_BEARER_TOKEN = "test-doc-analyzer-token"
            auth_hdr = {"Authorization": "Bearer test-doc-analyzer-token"}
            Settings.UPLOAD_DIR = Path(tmpdir) / "uploads"
            Settings.REPORT_DIR = Path(tmpdir) / "reports"
            Settings.ensure_directories()
            doc_app_mod._pipeline.db = fake_db

            flask_app = create_app()
            client = flask_app.test_client()

            # Preserve authentication guard when token is absent
            unauth = client.get("/api/document-analysis")
            assert unauth.status_code == 401

            # Build minimal valid PNG bytes so upload validation passes cleanly without external PDFs
            from PIL import Image
            buf = io.BytesIO()
            Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
            buf.seek(0)

            res = client.post(
                "/api/document-analysis/analyze",
                data={
                    "property_label": "Serialization Regression Plot",
                    "district": "Mysuru",
                    "taluk": "Mysuru",
                    "village": "Sathagalli",
                    "uploaded_documents": (buf, "sale_deed_sample.png"),
                },
                headers=auth_hdr,
                content_type="multipart/form-data",
            )
            assert res.status_code == 200, res.get_data(as_text=True)
            body = res.get_json()
            assert body and body.get("analysis_id"), body
            anl_id = body["analysis_id"]
            doc_id = body["documents"][0]["document_id"]

            # Inject nested ObjectIds into stored Mongo analysis record (simulating legacy stored records)
            stored_anl = fake_db.collection("analyses").find_one({"analysis_id": anl_id})
            assert isinstance(stored_anl["_id"], ObjectId)
            stored_anl["documents"][0]["_id"] = ObjectId()
            stored_anl["documents"][0]["nested_meta"] = {"child_oid": ObjectId()}

            r_list = client.get("/api/document-analysis", headers=auth_hdr)
            assert r_list.status_code == 200

            r_get = client.get(f"/api/document-analysis/{anl_id}", headers=auth_hdr)
            assert r_get.status_code == 200
            get_json = r_get.get_json()
            assert isinstance(get_json["_id"], str)
            assert isinstance(get_json["documents"][0]["_id"], str)
            assert isinstance(get_json["documents"][0]["nested_meta"]["child_oid"], str)

            r_cls = client.patch(
                f"/api/document-analysis/{anl_id}/documents/{doc_id}/classification",
                json={"document_type": "Sale Deed"},
                headers=auth_hdr,
            )
            assert r_cls.status_code == 200, r_cls.get_data(as_text=True)
            assert isinstance(r_cls.get_json()["documents"][0]["_id"], str)

            r_cor = client.patch(
                f"/api/document-analysis/{anl_id}/documents/{doc_id}/corrections",
                json={"corrections": {"village": "Sathagalli"}},
                headers=auth_hdr,
            )
            assert r_cor.status_code == 200, r_cor.get_data(as_text=True)
            assert isinstance(r_cor.get_json()["documents"][0]["_id"], str)

            r_del = client.delete(f"/api/document-analysis/{anl_id}/documents/{doc_id}", headers=auth_hdr)
            assert r_del.status_code == 200, r_del.get_data(as_text=True)
        finally:
            doc_app_mod._pipeline.db = orig_db
            Settings.API_BEARER_TOKEN = orig_token
            Settings.UPLOAD_DIR = orig_upload_dir
            Settings.REPORT_DIR = orig_report_dir


if __name__ == "__main__":
    test_sanitize_for_json_nested_non_mutating()
    test_document_analysis_routes_handle_nested_objectids()
    print("Document analysis BSON ObjectId serialization tests PASSED.")
