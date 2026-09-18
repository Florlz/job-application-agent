"""Read-only snapshot of the job database for Discord #job-tracker. No LLM, no writes.
Run: python tracker_report.py [--dry-run]

With a job-tracker webhook in secrets-discord.json it posts an embed itself and prints nothing
(the no-agent cron then stays silent). Without one it prints text for the cron to deliver.
"""
import datetime
import json
import sqlite3
import sys

import discord_post
import job_db

EMOJI = {"FOUND": "🔎", "REVIEW": "⚠️", "READY_TO_APPLY": "📦", "APPLIED": "📨", "RECRUITER_SCREEN": "📞",
         "ASSESSMENT": "📝", "INTERVIEW": "🗓️", "FINAL_INTERVIEW": "🗓️", "OFFER": "🎉", "REJECTED": "❌",
         "WITHDRAWN": "↩️", "CLOSED": "⏭️"}

conn = sqlite3.connect(f"{job_db.DB_PATH.as_uri()}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
today = datetime.date.today().isoformat()
now = datetime.datetime.now()
stamp = f"{now:%b} {now.day}, {now:%I:%M %p}".replace(" 0", " ")

counts = dict(conn.execute("SELECT status, COUNT(*) FROM applications GROUP BY status").fetchall())
review = conn.execute("SELECT COUNT(*) FROM applications WHERE needs_review = 1").fetchone()[0]
added = conn.execute("SELECT COUNT(*) FROM applications WHERE created_at >= datetime('now', '-1 day')").fetchone()[0]
followups = job_db.list_followups(conn, today)
stale = job_db.list_stale(conn)
interviews = [dict(r) for r in conn.execute(
    "SELECT * FROM applications WHERE interview_date >= ? "
    "AND status NOT IN ('REJECTED', 'WITHDRAWN', 'CLOSED') ORDER BY interview_date", (today,))]


def item(a, when):
    return f"**{when}** · {a['position']} · {a['company']} · `{a['id']}`"


interview_lines = [item(a, a["interview_date"]) for a in interviews] or ["*none scheduled*"]
followup_lines = [item(a, a["follow_up_date"]) + (f"\n*{a['next_action']}*" if a["next_action"] else "")
                  for a in followups[:10]] or ["*none due*"]
if len(followups) > 10:
    followup_lines.append(f"*…and {len(followups) - 10} more*")
stale_lines = [item(a, (a["last_contact"] or a["date_applied"] or "")[:10]) for a in stale[:10]]
if len(stale) > 10:
    stale_lines.append(f"*…and {len(stale) - 10} more*")
if stale:
    stale_lines.append("-# Tell Hermes \"close APP-…\" for the ones that are dead, or ignore to keep them.")

heading = f"📊 Job tracker · {stamp}"
summary = f"{added} added in the last 24h · {review} need review → #job-review"
webhook = discord_post.webhook_for("job-tracker")

if webhook:
    payload = {"content": f"## {heading}\n{summary}", "embeds": [
        {"title": "Pipeline", "color": 0x5865F2, "fields": [
            {"name": f"{EMOJI[s]} {s.replace('_', ' ').title()}", "value": f"**{counts[s]}**", "inline": True}
            for s in job_db.STATUSES if counts.get(s)]},
        {"title": f"🗓️ Upcoming interviews ({len(interviews)})", "color": 0x9B59B6, "description": "\n".join(interview_lines)[:4000]},
        {"title": f"⏰ Follow-ups due ({len(followups)})", "color": 0xE67E22, "description": "\n".join(followup_lines)[:4000]},
    ] + ([{"title": f"💤 No response in 30+ days ({len(stale)})", "color": 0x95A5A6,
           "description": "\n".join(stale_lines)[:4000]}] if stale else [])}
    if "--dry-run" in sys.argv:
        print(json.dumps(payload, indent=1, ensure_ascii=False))
    else:
        discord_post.send_webhook(webhook, payload)
else:
    pipeline = " · ".join(f"{EMOJI[s]} {s} **{counts[s]}**" for s in job_db.STATUSES if counts.get(s))
    print("\n".join([f"## {heading}", f"-# {summary}", "### Pipeline", pipeline or "empty",
                     f"### 🗓️ Upcoming interviews ({len(interviews)})", *interview_lines,
                     f"### ⏰ Follow-ups due ({len(followups)})", *followup_lines,
                     *([f"### 💤 No response in 30+ days ({len(stale)})", *stale_lines] if stale else [])]))
