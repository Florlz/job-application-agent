"""Self-check for job_db.py. Runs against a temporary DB; the real job-hunt.db is untouched.
Run: python test_job_db.py
"""
import datetime
import os
import sqlite3
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["JOB_DB"] = str(tmp)
import job_db  # noqa: E402  (must import after JOB_DB is set)

conn = job_db.connect()
job_db.init(conn)
year = datetime.date.today().year

# IDs are allocated sequentially per year
assert job_db.allocate_id(conn) == f"APP-{year}-0001"
app_id = job_db.create_application(conn, {"company": "Test Corp", "position": "Junior Developer",
                                          "normalized_position": "junior developer", "source": "test"})
assert app_id == f"APP-{year}-0002", app_id

# read back
app = job_db.get_application(conn, app_id)
assert app["company"] == "Test Corp" and app["status"] == "FOUND" and app["needs_review"] == 0

# status change is logged
job_db.update_application(conn, app_id, {"status": "APPLIED", "follow_up_date": "2000-01-01"}, source="test")
log = conn.execute("SELECT * FROM activity_log WHERE application_id = ? ORDER BY id", (app_id,)).fetchall()
assert [r["event_type"] for r in log] == ["CREATED", "STATUS_CHANGE"]
assert (log[1]["old_status"], log[1]["new_status"]) == ("FOUND", "APPLIED")

# invalid status and unknown columns are rejected
for bad in ({"status": "SUBMITTED"}, {"id": "APP-X"}):
    try:
        job_db.update_application(conn, app_id, bad)
        raise AssertionError(f"accepted {bad}")
    except (sqlite3.IntegrityError, ValueError):
        pass
assert job_db.get_application(conn, app_id)["status"] == "APPLIED"

# duplicate Gmail message IDs are blocked
evt = {"application_id": app_id, "event_type": "EMAIL", "email_message_id": "msg-1", "summary": "confirmation"}
assert job_db.add_activity(conn, evt) is not None
assert job_db.add_activity(conn, evt) is None  # same message, same application
assert conn.execute("SELECT COUNT(*) FROM activity_log WHERE email_message_id = 'msg-1'").fetchone()[0] == 1

# one digest email can log activity for several applications
app2 = job_db.create_application(conn, {"company": "Other Corp", "position": "Web Developer"})
assert job_db.add_activity(conn, {**evt, "application_id": app2}) is not None
assert job_db.mark_message_processed(conn, "msg-1") is True
assert job_db.mark_message_processed(conn, "msg-1") is False
assert job_db.message_processed(conn, "msg-1")
# once processed, the message is ignored even for a new application
app3 = job_db.create_application(conn, {"company": "Third Corp", "position": "Developer"})
assert job_db.add_activity(conn, {**evt, "application_id": app3}) is None
assert conn.execute("SELECT COUNT(*) FROM activity_log WHERE email_message_id = 'msg-1'").fetchone()[0] == 2

# activity for a nonexistent application is rejected (foreign key)
try:
    job_db.add_activity(conn, {"application_id": "APP-0000-0000", "event_type": "X"})
    raise AssertionError("foreign key not enforced")
except sqlite3.IntegrityError:
    pass

# follow-ups: due APPLIED shows up, terminal statuses don't
assert [a["id"] for a in job_db.list_followups(conn)] == [app_id]  # app2/app3 have no follow_up_date
job_db.update_application(conn, app_id, {"status": "REJECTED"})
assert job_db.list_followups(conn) == []

# backfill import: only marked rows, dry run writes nothing, re-run is a no-op
import csv  # noqa: E402
prev, act = tmp.parent / "p.csv", tmp.parent / "a.csv"
P_COLS = ["Import?", "Preview Key", "Company", "Position", "Normalized Position", "Approx Applied Date",
          "Latest Status", "Last Activity", "Source", "Evidence Count", "Confidence", "Needs Review", "Notes"]
A_COLS = ["Timestamp", "Preview Key", "Event Type", "Old Status", "New Status", "Source",
          "Email Thread ID", "Email Message ID", "Summary", "Confidence", "Needs Review"]
with open(prev, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, P_COLS); w.writeheader()
    w.writerow(dict(zip(P_COLS, ["y", "P-001", "Acme", "Jr. Dev", "junior dev", "2026-08-01", "REJECTED",
                                 "2026-08-05T01:02:03.000Z", "Jobstreet", "2", "HIGH", "FALSE", ""])))
    w.writerow(dict(zip(P_COLS, ["", "P-002", "Skipped Co", "Dev", "dev", "2026-08-02", "APPLIED",
                                 "", "Indeed", "1", "HIGH", "FALSE", ""])))
    w.writerow(dict(zip(P_COLS, ["yes", "P-003", "Beta", "Web Dev", "web dev", "2026-08-03", "REVIEW",
                                 "", "LinkedIn", "1", "LOW", "TRUE", "unclear"])))
with open(act, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, A_COLS); w.writeheader()
    for key, typ, new, msg in [("P-001", "APPLICATION_CONFIRMATION", "APPLIED", "m-a"),
                               ("P-001", "REJECTION", "REJECTED", "m-digest"),
                               ("P-003", "APPLICATION_CONFIRMATION", "APPLIED", "m-digest"),
                               ("P-002", "APPLICATION_CONFIRMATION", "APPLIED", "m-skip")]:
        w.writerow(dict(zip(A_COLS, ["2026-08-05T01:02:03.000Z", key, typ, "", new, "Jobstreet", "t", msg, "s", "HIGH", "FALSE"])))

before = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
dry = job_db.import_backfill(conn, prev, act, dry_run=True)
assert set(dry["imported"]) == {"P-001", "P-003"} and dry["activities"] == 3
assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == before  # rolled back
assert not job_db.message_processed(conn, "m-a")

res = job_db.import_backfill(conn, prev, act)
a1 = job_db.get_application(conn, res["imported"]["P-001"])
assert (a1["status"], a1["date_applied"], a1["last_contact"]) == ("REJECTED", "2026-08-01", "2026-08-05")
assert job_db.get_application(conn, res["imported"]["P-003"])["needs_review"] == 1
assert res["activities"] == 3 and res["messages_processed"] == 2  # m-a, m-digest; m-skip untouched
assert not job_db.message_processed(conn, "m-skip")
assert conn.execute("SELECT created_at FROM activity_log WHERE email_message_id = 'm-a'").fetchone()[0] == "2026-08-05 01:02:03"
again = job_db.import_backfill(conn, prev, act)
assert again["imported"] == {} and sorted(again["skipped_existing"]) == ["P-001", "P-003"]

# stale: APPLIED with no contact for 30 days (last_contact wins over date_applied)
s1 = job_db.create_application(conn, {"company": "Old Co", "position": "Dev", "status": "APPLIED", "date_applied": "2026-07-01"})
s2 = job_db.create_application(conn, {"company": "Talking Co", "position": "Dev", "status": "APPLIED",
                                      "date_applied": "2026-07-01", "last_contact": "2026-08-25 10:00"})
s3 = job_db.create_application(conn, {"company": "Rejected Co", "position": "Dev", "status": "REJECTED", "date_applied": "2026-07-01"})
stale = [a["id"] for a in job_db.list_stale(conn, 30, on="2026-09-18")]
assert s1 in stale and s2 not in stale and s3 not in stale, stale

conn.close()
for p in (prev, act, tmp):
    p.unlink()
print("all job_db checks passed")
