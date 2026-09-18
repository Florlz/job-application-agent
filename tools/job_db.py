"""JobAgent SQLite helper. Hermes is the only writer of this database.

CLI (all output is JSON):
  python job_db.py init
  python job_db.py allocate_id
  python job_db.py create_application '{"company": "...", "position": "..."}'
  python job_db.py get_application APP-2026-0001
  python job_db.py update_application APP-2026-0001 '{"status": "APPLIED"}'
  python job_db.py list_applications [--status REVIEW] [--needs-review]
  python job_db.py add_activity '{"application_id": "...", "event_type": "...", "email_message_id": "..."}'
  python job_db.py message_processed <message_id>
  python job_db.py mark_message_processed <message_id>
  python job_db.py list_followups [--date YYYY-MM-DD]
  python job_db.py list_stale [--days 30]
  python job_db.py import_backfill <backfill-preview.csv> <backfill-activity-preview.csv> [--dry-run]

Set JOB_DB to use a different database file (e.g. for tests).
"""
import argparse
import csv
import datetime
import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("JOB_DB", Path.home() / "JobAgent" / "data" / "job-hunt.db"))

STATUSES = (
    "FOUND", "REVIEW", "READY_TO_APPLY", "APPLIED", "RECRUITER_SCREEN", "ASSESSMENT",
    "INTERVIEW", "FINAL_INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN", "CLOSED",
)
NO_FOLLOWUP = ("OFFER", "REJECTED", "WITHDRAWN", "CLOSED")
_status_list = ", ".join(f"'{s}'" for s in STATUSES)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    position TEXT NOT NULL,
    normalized_position TEXT,
    job_url TEXT,
    posting_id TEXT,
    source TEXT,
    location TEXT,
    work_setup TEXT,
    date_found TEXT,
    date_applied TEXT,
    status TEXT NOT NULL DEFAULT 'FOUND' CHECK (status IN ({_status_list})),
    recruiter TEXT,
    recruiter_email TEXT,
    last_contact TEXT,
    next_action TEXT,
    follow_up_date TEXT,
    interview_date TEXT,
    application_folder TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id TEXT REFERENCES applications(id),
    event_type TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    source TEXT,
    email_thread_id TEXT,
    email_message_id TEXT,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app_sequence (
    year INTEGER PRIMARY KEY,
    last_number INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_app_identity ON applications(company, normalized_position);
CREATE INDEX IF NOT EXISTS idx_activity_app ON activity_log(application_id);
-- One email (e.g. a Jobstreet digest) can concern several applications, but never logs twice for the same one.
CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_msg_app ON activity_log(email_message_id, application_id)
    WHERE email_message_id IS NOT NULL;
"""

APP_COLUMNS = {
    "company", "position", "normalized_position", "job_url", "posting_id", "source", "location",
    "work_setup", "date_found", "date_applied", "status", "recruiter", "recruiter_email",
    "last_contact", "next_action", "follow_up_date", "interview_date", "application_folder",
    "needs_review", "notes",
}
ACTIVITY_COLUMNS = {
    "application_id", "event_type", "old_status", "new_status", "source",
    "email_thread_id", "email_message_id", "summary",
}


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: we issue BEGIN IMMEDIATE ourselves so writes take the lock up front.
    conn = sqlite3.connect(DB_PATH, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class tx:
    """Write transaction: BEGIN IMMEDIATE, commit on success, rollback on error."""
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, *_):
        self.conn.execute("ROLLBACK" if exc_type else "COMMIT")


def _check_columns(fields, allowed):
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"unknown field(s): {sorted(bad)}")


def init(conn):
    conn.executescript(SCHEMA)
    return {"db": str(DB_PATH)}


def _next_id(conn, year):
    n = conn.execute(
        "INSERT INTO app_sequence(year, last_number) VALUES (?, 1) "
        "ON CONFLICT(year) DO UPDATE SET last_number = last_number + 1 RETURNING last_number",
        (year,),
    ).fetchone()[0]
    return f"APP-{year}-{n:04d}"


def allocate_id(conn, year=None):
    with tx(conn):
        return _next_id(conn, year or datetime.date.today().year)


def _insert_activity(conn, fields):
    _check_columns(fields, ACTIVITY_COLUMNS)
    cols = ", ".join(fields)
    marks = ", ".join("?" * len(fields))
    return conn.execute(f"INSERT INTO activity_log ({cols}) VALUES ({marks})", tuple(fields.values())).lastrowid


def _create_application(conn, fields, source=None):
    _check_columns(fields, APP_COLUMNS)
    app_id = _next_id(conn, datetime.date.today().year)
    row = {"id": app_id, **fields}
    cols = ", ".join(row)
    marks = ", ".join("?" * len(row))
    conn.execute(f"INSERT INTO applications ({cols}) VALUES ({marks})", tuple(row.values()))
    _insert_activity(conn, {"application_id": app_id, "event_type": "CREATED",
                            "new_status": fields.get("status", "FOUND"), "source": source or fields.get("source")})
    return app_id


def create_application(conn, fields):
    """Allocates the ID and inserts the row in one transaction, so a failed insert burns no ID."""
    with tx(conn):
        return _create_application(conn, fields)


def get_application(conn, app_id):
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    return dict(row) if row else None


def update_application(conn, app_id, fields, source=None):
    """Updates fields; a status change is logged to activity_log in the same transaction."""
    _check_columns(fields, APP_COLUMNS)
    with tx(conn):
        row = conn.execute("SELECT status FROM applications WHERE id = ?", (app_id,)).fetchone()
        if row is None:
            raise KeyError(app_id)
        sets = ", ".join(f"{c} = ?" for c in fields)
        conn.execute(f"UPDATE applications SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                     (*fields.values(), app_id))
        new = fields.get("status")
        if new and new != row["status"]:
            _insert_activity(conn, {"application_id": app_id, "event_type": "STATUS_CHANGE",
                                    "old_status": row["status"], "new_status": new, "source": source})
    return get_application(conn, app_id)


def list_applications(conn, status=None, needs_review=None):
    sql, args = "SELECT * FROM applications WHERE 1=1", []
    if status:
        sql += " AND status = ?"
        args.append(status)
    if needs_review is not None:
        sql += " AND needs_review = ?"
        args.append(int(needs_review))
    return [dict(r) for r in conn.execute(sql + " ORDER BY id", args)]


def add_activity(conn, fields):
    """Logs an event. Returns None (writes nothing) if its email_message_id is already
    marked processed, or was already logged for this application. One message may log
    events for several applications; call mark_message_processed once all are logged."""
    with tx(conn):
        msg = fields.get("email_message_id")
        if msg and message_processed(conn, msg):
            return None
        try:
            return _insert_activity(conn, fields)
        except sqlite3.IntegrityError as e:
            if msg and "UNIQUE" in str(e):
                return None
            raise


def message_processed(conn, message_id):
    return conn.execute("SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,)).fetchone() is not None


def mark_message_processed(conn, message_id):
    """True if newly marked, False if it was already processed."""
    with tx(conn):
        return conn.execute("INSERT OR IGNORE INTO processed_messages(message_id) VALUES (?)",
                            (message_id,)).rowcount == 1


IMPORT_YES = {"y", "yes", "x", "true", "1"}


def _read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def import_backfill(conn, preview_csv, activity_csv, dry_run=False):
    """Imports the preview rows marked in "Import?" plus their activity, in one transaction.
    Rows whose company + normalized position already exist are skipped, so re-running is safe.
    With dry_run, everything is rolled back and only the summary is returned."""
    chosen = [r for r in _read_csv(preview_csv) if r["Import?"].strip().lower() in IMPORT_YES]
    missing = [r["Preview Key"] for r in chosen if not r["Company"].strip() or not r["Position"].strip()]
    if missing:
        raise ValueError(f"fill in Company and Position before importing: {missing}")
    activity = {}
    for a in _read_csv(activity_csv):
        activity.setdefault(a["Preview Key"], []).append(a)

    result = {"dry_run": dry_run, "imported": {}, "skipped_existing": [], "activities": 0, "messages_processed": 0}
    messages = set()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for r in chosen:
            norm = (r["Normalized Position"] or r["Position"]).strip()
            if conn.execute("SELECT 1 FROM applications WHERE lower(company) = lower(?) "
                            "AND lower(normalized_position) = lower(?)", (r["Company"].strip(), norm)).fetchone():
                result["skipped_existing"].append(r["Preview Key"])
                continue
            app_id = _create_application(conn, {
                "company": r["Company"].strip(),
                "position": r["Position"].strip(),
                "normalized_position": norm,
                "source": r["Source"] or None,
                "date_applied": r["Approx Applied Date"] or None,
                "last_contact": (r.get("Last Activity") or "")[:10] or None,
                "status": r["Latest Status"],
                "needs_review": int(r["Needs Review"].strip().upper() == "TRUE"),
                "notes": r["Notes"] or None,
            }, source="backfill")
            result["imported"][r["Preview Key"]] = app_id
            for a in activity.get(r["Preview Key"], []):
                cur = conn.execute(
                    "INSERT OR IGNORE INTO activity_log (application_id, event_type, old_status, new_status, source, "
                    "email_thread_id, email_message_id, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (app_id, a["Event Type"], a["Old Status"] or None, a["New Status"] or None, a["Source"] or None,
                     a["Email Thread ID"] or None, a["Email Message ID"] or None, a["Summary"] or None,
                     a["Timestamp"].replace("T", " ")[:19] or None))
                result["activities"] += cur.rowcount
                if a["Email Message ID"]:
                    messages.add(a["Email Message ID"])
        # Only messages tied to an imported application are marked; the rest stay unprocessed.
        for m in messages:
            result["messages_processed"] += conn.execute(
                "INSERT OR IGNORE INTO processed_messages(message_id) VALUES (?)", (m,)).rowcount
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("ROLLBACK" if dry_run else "COMMIT")
    return result


def list_followups(conn, on_or_before=None):
    day = on_or_before or datetime.date.today().isoformat()
    marks = ", ".join("?" * len(NO_FOLLOWUP))
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM applications WHERE follow_up_date IS NOT NULL AND follow_up_date <= ? "
        f"AND status NOT IN ({marks}) ORDER BY follow_up_date",
        (day, *NO_FOLLOWUP))]


def list_stale(conn, days=30, on=None):
    """APPLIED applications with no contact for `days` days (last_contact, else date_applied).
    Candidates to close; nothing is changed."""
    cutoff = (datetime.date.fromisoformat(on) if on else datetime.date.today()) - datetime.timedelta(days=days)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM applications WHERE status = 'APPLIED' "
        "AND substr(COALESCE(last_contact, date_applied), 1, 10) <= ? ORDER BY COALESCE(last_contact, date_applied)",
        (cutoff.isoformat(),))]


def main():
    p = argparse.ArgumentParser(description="JobAgent SQLite helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("allocate_id")
    sub.add_parser("create_application").add_argument("fields")
    sub.add_parser("get_application").add_argument("id")
    u = sub.add_parser("update_application")
    u.add_argument("id")
    u.add_argument("fields")
    u.add_argument("--source")
    la = sub.add_parser("list_applications")
    la.add_argument("--status")
    la.add_argument("--needs-review", action="store_true", default=None)
    sub.add_parser("add_activity").add_argument("fields")
    sub.add_parser("message_processed").add_argument("message_id")
    sub.add_parser("mark_message_processed").add_argument("message_id")
    sub.add_parser("list_followups").add_argument("--date")
    ls = sub.add_parser("list_stale")
    ls.add_argument("--days", type=int, default=30)
    ib = sub.add_parser("import_backfill")
    ib.add_argument("preview_csv")
    ib.add_argument("activity_csv")
    ib.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    conn = connect()
    init(conn)  # idempotent; guarantees the schema exists
    result = {
        "init": lambda: {"db": str(DB_PATH)},
        "allocate_id": lambda: allocate_id(conn),
        "create_application": lambda: create_application(conn, json.loads(a.fields)),
        "get_application": lambda: get_application(conn, a.id),
        "update_application": lambda: update_application(conn, a.id, json.loads(a.fields), a.source),
        "list_applications": lambda: list_applications(conn, a.status, a.needs_review),
        "add_activity": lambda: add_activity(conn, json.loads(a.fields)),
        "message_processed": lambda: message_processed(conn, a.message_id),
        "mark_message_processed": lambda: mark_message_processed(conn, a.message_id),
        "list_followups": lambda: list_followups(conn, a.date),
        "list_stale": lambda: list_stale(conn, a.days),
        "import_backfill": lambda: import_backfill(conn, a.preview_csv, a.activity_csv, a.dry_run),
    }[a.cmd]()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
