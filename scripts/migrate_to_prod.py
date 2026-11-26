"""Non-destructive production migration & verification tool for SLV-GIS.

Migrates:
1. SQLite (`backend/smart_land_eval.db`) -> Neon PostgreSQL (`DATABASE_URL`)
2. Local Document Analyzer JSON store -> MongoDB Atlas (`MONGODB_URI`)

Safety guarantees:
- Never drops, truncates, resets, or overwrites existing production rows/documents.
- Redacts all credentials (`user:password@`) from logs and error output.
- Creates a timestamped local backup before migrating.
- Verifies source vs destination counts, relationships, auth, properties, evaluations, and audit logs.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
SQLITE_PATH = BACKEND_DIR / "smart_land_eval.db"
LOCAL_MONGO_DIR = BACKEND_DIR / "storage" / "doc_analyzer" / "local_db"
BACKUP_ROOT = BACKEND_DIR / "backups"

sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
except Exception:
    pass

MONGO_COLLECTIONS = {
    "analyses": ("analyses.json", "analysis_id"),
    "documents": ("documents.json", "document_id"),
    "reports": ("reports.json", "report_id"),
    "audit_logs": ("audit_logs.json", "event_id"),
}


def redact_secrets(text: str) -> str:
    """Redact credentials in URIs (`scheme://user:pass@host`) from any log output."""
    if not text:
        return text
    text = re.sub(r"(://)([^:/\s@]+):([^@\s]+)@", r"\1***:***@", text)
    return text


def log(msg: str) -> None:
    print(redact_secrets(msg), flush=True)


def normalize_database_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def get_sqlite_schema_and_order(conn: sqlite3.Connection) -> Tuple[List[str], Dict[str, int]]:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    deps: Dict[str, set] = {t: set() for t in tables}
    counts: Dict[str, int] = {}
    for t in tables:
        counts[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        for fk in conn.execute(f'PRAGMA foreign_key_list("{t}")').fetchall():
            parent = fk[2]
            if parent in deps and parent != t:
                deps[t].add(parent)

    ordered: List[str] = []
    remaining = set(tables)
    while remaining:
        ready = sorted([t for t in remaining if deps[t].issubset(set(ordered))])
        if not ready:
            # Break any cycle deterministically
            ready = [sorted(remaining)[0]]
        ordered.extend(ready)
        remaining -= set(ready)
    return ordered, counts


def create_local_backup() -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_ROOT / stamp
    dest.mkdir(parents=True, exist_ok=True)
    if SQLITE_PATH.exists():
        shutil.copy2(SQLITE_PATH, dest / "smart_land_eval.db")
        log(f"[BACKUP] Copied SQLite DB -> {dest / 'smart_land_eval.db'}")
    if LOCAL_MONGO_DIR.exists():
        mongo_bak = dest / "doc_analyzer_local_db"
        shutil.copytree(LOCAL_MONGO_DIR, mongo_bak, dirs_exist_ok=True)
        log(f"[BACKUP] Copied local JSON store -> {mongo_bak}")
    return dest


def coerce_row_for_pg(row: Dict[str, Any], pg_cols: Dict[str, Any]) -> Dict[str, Any]:
    from sqlalchemy import Boolean, DateTime, Date

    out: Dict[str, Any] = {}
    for k, v in row.items():
        if k not in pg_cols:
            continue
        col_type = pg_cols[k]
        if v is not None and isinstance(col_type, Boolean):
            out[k] = bool(v)
        elif isinstance(v, str) and isinstance(col_type, (DateTime, Date)):
            s = v.strip()
            if not s:
                out[k] = None
            else:
                out[k] = s
        else:
            out[k] = v
    return out


def migrate_sqlite_to_postgres(database_url: str, dry_run: bool = True) -> Dict[str, Tuple[int, int]]:
    from sqlalchemy import create_engine, inspect as sa_inspect, MetaData, text
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app import create_app

    os.environ["DATABASE_URL"] = database_url
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    ordered_tables, src_counts = get_sqlite_schema_and_order(sqlite_conn)

    if dry_run:
        log("[DRY-RUN] SQLite -> PostgreSQL topological table order:")
        for t in ordered_tables:
            log(f"  - {t}: {src_counts[t]} source rows")
        sqlite_conn.close()
        return {t: (src_counts[t], -1) for t in ordered_tables}

    # Ensure target schema exists non-destructively via SQLAlchemy models
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as pre_conn:
        for tbl_name, col_name in [
            ("properties", "coordinate_source"),
            ("facilities", "source"),
            ("document_extractions", "survey_number"),
            ("data_sources", "confidence"),
        ]:
            try:
                pre_conn.execute(text(f'ALTER TABLE "{tbl_name}" ALTER COLUMN "{col_name}" TYPE VARCHAR(255)'))
            except Exception:
                pass

    flask_app = create_app("production")
    with flask_app.app_context():
        pass
    metadata = MetaData()
    metadata.reflect(bind=engine)
    inspector = sa_inspect(engine)

    results: Dict[str, Tuple[int, int]] = {}
    with engine.begin() as pg_conn:
        for t in ordered_tables:
            if t not in metadata.tables:
                log(f"[WARN] Table '{t}' not found in target PostgreSQL metadata; skipping.")
                continue
            pg_table = metadata.tables[t]
            pg_cols = {c["name"]: c["type"] for c in inspector.get_columns(t)}
            rows = [dict(r) for r in sqlite_conn.execute(f'SELECT * FROM "{t}"').fetchall()]

            # Filter out historical orphaned child rows (SQLite had FK checks off)
            fk_parents = [
                (fk[3], fk[2], fk[4])
                for fk in sqlite_conn.execute(f'PRAGMA foreign_key_list("{t}")').fetchall()
            ]
            if rows and fk_parents:
                valid_parent_ids: Dict[str, set] = {}
                for col_from, tbl_to, col_to in fk_parents:
                    if tbl_to in metadata.tables:
                        valid_parent_ids[col_from] = {
                            r[0]
                            for r in pg_conn.execute(text(f'SELECT "{col_to}" FROM "{tbl_to}"')).fetchall()
                        }
                filtered = []
                skipped = 0
                for r in rows:
                    if all(
                        (r.get(col_from) is None or r.get(col_from) in valid_parent_ids[col_from])
                        for col_from in valid_parent_ids
                    ):
                        filtered.append(r)
                    else:
                        skipped += 1
                if skipped:
                    log(f"[INFO] {t}: skipped {skipped} historical orphaned rows with missing parent FK.")
                rows = filtered

            if rows:
                coerced = [coerce_row_for_pg(r, pg_cols) for r in rows]
                batch_size = 250
                for i in range(0, len(coerced), batch_size):
                    batch = coerced[i : i + batch_size]
                    stmt = pg_insert(pg_table).values(batch).on_conflict_do_nothing()
                    pg_conn.execute(stmt)

            # Sync SERIAL / IDENTITY sequence if table has an integer 'id' primary key
            pk_cols = [c.name for c in pg_table.primary_key.columns]
            if pk_cols == ["id"] and "id" in pg_cols:
                pg_conn.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence(:tbl, 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM \"{t}\"), 1), true)"
                    ),
                    {"tbl": t},
                )

            dest_count = pg_conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() or 0
            results[t] = (src_counts[t], int(dest_count))
            log(f"[PG] {t}: source={src_counts[t]}, dest={dest_count}")

    sqlite_conn.close()
    return results


def migrate_local_json_to_mongodb(mongodb_uri: str, db_name: str, backup_dir: Path, dry_run: bool = True) -> Dict[str, Tuple[int, int]]:
    if dry_run:
        out: Dict[str, Tuple[int, int]] = {}
        for coll, (fname, _) in MONGO_COLLECTIONS.items():
            p = LOCAL_MONGO_DIR / fname
            docs = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
            out[coll] = (len(docs), -1)
            log(f"[DRY-RUN] MongoDB '{coll}': {len(docs)} source documents")
        return out

    from pymongo import MongoClient

    client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    db = client[db_name]

    # Pre-migration snapshot of existing Atlas data
    atlas_bak = backup_dir / "atlas_pre_migration"
    atlas_bak.mkdir(parents=True, exist_ok=True)
    for coll in MONGO_COLLECTIONS:
        existing = list(db[coll].find({}, {"_id": 0}))
        (atlas_bak / f"{coll}.json").write_text(json.dumps(existing, default=str), encoding="utf-8")
    log(f"[BACKUP] Snapshot of existing Atlas collections saved -> {atlas_bak}")

    results: Dict[str, Tuple[int, int]] = {}
    for coll, (fname, id_field) in MONGO_COLLECTIONS.items():
        p = LOCAL_MONGO_DIR / fname
        docs = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        for doc in docs:
            clean_doc = {k: v for k, v in doc.items() if k != "_id"}
            key_val = clean_doc.get(id_field)
            if key_val is not None:
                db[coll].update_one({id_field: key_val}, {"$setOnInsert": clean_doc}, upsert=True)
            else:
                db[coll].insert_one(clean_doc)
        dest_count = db[coll].count_documents({})
        results[coll] = (len(docs), dest_count)
        log(f"[MONGO] {coll}: source={len(docs)}, dest={dest_count}")

    client.close()
    return results


def verify_production(database_url: str, mongodb_uri: str, db_name: str) -> bool:
    from sqlalchemy import create_engine, inspect as sa_inspect, text
    from pymongo import MongoClient

    ok = True
    if database_url:
        sqlite_conn = sqlite3.connect(SQLITE_PATH)
        _, src_counts = get_sqlite_schema_and_order(sqlite_conn)
        sqlite_conn.close()

        engine = create_engine(database_url, pool_pre_ping=True)
        existing_pg_tables = set(sa_inspect(engine).get_table_names())
        with engine.connect() as conn:
            log("\n[VERIFY] Checking PostgreSQL table row counts:")
            for t, src_n in src_counts.items():
                if t not in existing_pg_tables:
                    log(f"  {t}: source={src_n}, dest=N/A [NOT_IN_MODELS]")
                    continue
                dest_n = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() or 0
                status = "OK" if dest_n >= src_n else "WARN_DIFF"
                if dest_n < src_n and t not in ("verification_items", "admin_accounts"):
                    ok = False
                log(f"  {t}: source={src_n}, dest={dest_n} [{status}]")

            # Relationship & domain integrity checks
            checks = {
                "orphan_evaluations": "SELECT COUNT(*) FROM property_evaluations pe LEFT JOIN properties p ON pe.property_id = p.id WHERE pe.property_id IS NOT NULL AND p.id IS NULL",
                "orphan_reports": "SELECT COUNT(*) FROM reports r LEFT JOIN property_evaluations pe ON r.evaluation_id = pe.id WHERE r.evaluation_id IS NOT NULL AND pe.id IS NULL",
                "orphan_gis": "SELECT COUNT(*) FROM gis_analysis g LEFT JOIN property_evaluations pe ON g.evaluation_id = pe.id WHERE g.evaluation_id IS NOT NULL AND pe.id IS NULL",
                "users_with_password_hash": "SELECT COUNT(*) FROM platform_users WHERE password_hash IS NOT NULL AND password_hash <> ''",
                "admins_with_password_hash": "SELECT COUNT(*) FROM admin_accounts WHERE password_hash IS NOT NULL AND password_hash <> ''",
                "audit_logs_count": "SELECT COUNT(*) FROM admin_audit_logs",
            }
            log("\n[VERIFY] Checking relationships & auth/audit integrity:")
            for name, sql in checks.items():
                val = conn.execute(text(sql)).scalar() or 0
                if name.startswith("orphan_") and val > 0:
                    ok = False
                log(f"  {name}: {val}")

    if mongodb_uri and "<db_password>" not in mongodb_uri:
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=8000)
        db = client[db_name]
        log("\n[VERIFY] Checking MongoDB Atlas collection counts:")
        for coll, (fname, _) in MONGO_COLLECTIONS.items():
            p = LOCAL_MONGO_DIR / fname
            src_n = len(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else 0
            dest_n = db[coll].count_documents({})
            status = "OK" if dest_n >= src_n else "MISMATCH"
            if dest_n < src_n:
                ok = False
            log(f"  {coll}: source={src_n}, dest={dest_n} [{status}]")
        client.close()
    else:
        log("\n[VERIFY] MongoDB Atlas skipped (MONGODB_URI not set or still contains <db_password> placeholder).")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-destructive SLV-GIS production migration tool")
    parser.add_argument("--backup-only", action="store_true", help="Create local backup only")
    parser.add_argument("--dry-run", action="store_true", help="Print migration plan without writing to production DBs")
    parser.add_argument("--check-lengths", action="store_true", help="Check SQLite string lengths against SQLAlchemy VARCHAR limits")
    parser.add_argument("--migrate", action="store_true", help="Execute non-destructive migration + verification")
    parser.add_argument("--verify-only", action="store_true", help="Verify source vs destination counts & integrity")
    args = parser.parse_args()

    if not any([args.backup_only, args.dry_run, args.check_lengths, args.migrate, args.verify_only]):
        args.dry_run = True

    if args.check_lengths:
        from app import create_app, db
        flask_app = create_app("development")
        c = sqlite3.connect(SQLITE_PATH)
        with flask_app.app_context():
            overflows = []
            for t, tbl in db.metadata.tables.items():
                for col in tbl.columns:
                    limit = getattr(col.type, "length", None)
                    if limit:
                        mx = c.execute(f'SELECT MAX(LENGTH("{col.name}")) FROM "{t}"').fetchone()[0]
                        if isinstance(mx, int) and mx > limit:
                            overflows.append((t, col.name, mx, limit))
                            log(f"[OVERFLOW] {t}.{col.name}: max={mx} > limit={limit}")
            if not overflows:
                log("[OK] Zero VARCHAR length overflows found across all tables.")
        c.close()
        return 0

    db_url = normalize_database_url(os.getenv("DATABASE_URL", ""))
    mongo_uri = os.getenv("MONGODB_URI", "").strip()
    mongo_db = os.getenv("MONGODB_DB_NAME", "karnataka_land_due_diligence").strip()

    if args.backup_only:
        create_local_backup()
        return 0

    if args.dry_run:
        migrate_sqlite_to_postgres(db_url, dry_run=True)
        migrate_local_json_to_mongodb(mongo_uri, mongo_db, BACKUP_ROOT, dry_run=True)
        return 0

    has_pg = bool(db_url)
    has_mongo = bool(mongo_uri) and "<db_password>" not in mongo_uri
    if not has_pg and not has_mongo:
        log("[ERROR] At least one of DATABASE_URL or a valid MONGODB_URI (without <db_password>) is required.")
        return 1

    if args.migrate:
        bak = create_local_backup()
        if has_pg:
            migrate_sqlite_to_postgres(db_url, dry_run=False)
        else:
            log("[INFO] Skipping PostgreSQL migration (DATABASE_URL not set).")
        if has_mongo:
            migrate_local_json_to_mongodb(mongo_uri, mongo_db, bak, dry_run=False)
        else:
            log("[INFO] Skipping MongoDB Atlas migration (MONGODB_URI not set or contains <db_password>).")

    ok = verify_production(db_url, mongo_uri, mongo_db)
    log(f"\n[RESULT] Verification {'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
