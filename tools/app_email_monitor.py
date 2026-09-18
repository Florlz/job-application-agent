"""Cheap monitor for the application-email processor (Hermes cron monitor mode). No LLM, no writes.

Asks n8n for recent application-related emails and prints the ones not yet processed, one per line.
Hermes only wakes the model when this output changes, so identical output = no tokens spent.
The date line makes a stuck (unprocessed) email retry at least once a day.
Run: python app_email_monitor.py
"""
import datetime
import json
import sqlite3
import urllib.error
import urllib.request

import job_db

WEBHOOK = "http://localhost:5678/webhook/jobagent-backfill-fetch"
QUERY = ("("
         'label:"Job Search/Application Updates" OR label:"Job Search/Interviews & Offers" '
         'OR (label:"Job Search/Job Alerts" (subject:"successfully submitted" OR subject:"has closed" OR subject:"application update")) '
         "OR (in:sent (application OR applying OR interview OR withdraw OR position))"
         ") newer_than:7d")

req = urllib.request.Request(WEBHOOK, data=json.dumps({"queries": [QUERY]}).encode(), method="POST",
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        messages = json.load(r)
except urllib.error.URLError:
    # Docker/n8n may be intentionally offline. Treat that as "nothing to do"
    # so the monitor retries quietly on the next scheduled run.
    messages = []

conn = sqlite3.connect(f"{job_db.DB_PATH.as_uri()}?mode=ro", uri=True)
done = {row[0] for row in conn.execute("SELECT message_id FROM processed_messages")}
new = sorted((m for m in messages if m["message_id"] not in done), key=lambda m: m["date"])

if new:
    print(f"{len(new)} unprocessed application email(s) as of {datetime.date.today()}:")
    for m in new:
        print(f"{m['message_id']} | {m['date'][:16]} | {m['from']} | {m['subject']}")
