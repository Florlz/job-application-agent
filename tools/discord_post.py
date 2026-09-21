"""Post jobs from the database to Discord in one consistent layout. Reads the DB only.

  python discord_post.py <channel> "<heading>" [APP-ID ...] [--summary "<line>"] [--dry-run]
  python discord_post.py <channel> "<heading>" <APP-ID> --letter <cover-letter.md> --attach <pdf> <docx>
  python discord_post.py <channel> "<heading>" <APP-ID> --package <brief.json> --letter <md> --attach <files...>

<channel>: job-inbox, ready-to-apply, job-review, applications, interviews, alerts, job-tracker.
If the channel has a webhook in JobAgent\\secrets-discord.json, jobs are posted as colored
embeds (one per stage, one full-width field per job, up to 6000 characters per message). Otherwise plain text via
`hermes send`. Either way: grouped by stage, URLs hidden behind titles, headers never repeated.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import job_db

WEBHOOKS_FILE = Path(__file__).resolve().parent.parent / "secrets-discord.json"
TEXT_LIMIT = 1900          # Discord: 2000 characters per text message
MESSAGE_EMBED_LIMIT = 5800  # Discord: 6000 across all embeds of one message
MAX_EMBEDS = 10
MAX_FIELDS = 25             # Discord: 25 fields per embed


def _status(*names):
    return lambda a: a["status"] in names


# (title, test, show notes?, color). First match wins; list order is display order.
GROUPS = [
    ("🎉 Offer", _status("OFFER"), False, 0xF1C40F),
    ("🗓️ Interview", _status("INTERVIEW", "FINAL_INTERVIEW"), False, 0x9B59B6),
    ("📝 Assessment", _status("ASSESSMENT"), False, 0xE67E22),
    ("📞 Recruiter screen", _status("RECRUITER_SCREEN"), False, 0x1ABC9C),
    ("⚠️ Needs review", lambda a: a["status"] == "REVIEW" or a["needs_review"], True, 0xF39C12),
    ("📦 Ready to apply", _status("READY_TO_APPLY"), False, 0x2ECC71),
    ("✅ Prepare", lambda a: a["status"] == "FOUND" and (a["next_action"] or "").startswith("PREPARE"), False, 0x2ECC71),
    ("🔎 Check posting", _status("FOUND"), False, 0x3498DB),
    ("📨 Applied", _status("APPLIED"), False, 0x5865F2),
    ("❌ Rejected", _status("REJECTED"), False, 0xE74C3C),
    ("↩️ Withdrawn", _status("WITHDRAWN"), False, 0x95A5A6),
    ("⏭️ Skipped", _status("CLOSED"), True, 0x95A5A6),
]
OTHER = ("📌 Other", None, True, 0x95A5A6)
# Stages where next_action is the useful subtext (what Florian has to do next).
ACTION_STAGES = {"🎉 Offer", "🗓️ Interview", "📝 Assessment", "📞 Recruiter screen", "📦 Ready to apply"}


def short(text, limit=110):
    text = " ".join((text or "").split())
    cut = text.split(". ")[0].rstrip(".")
    return cut if len(cut) <= limit else cut[: limit - 1].rstrip() + "…"


def display_url(a):
    """Short canonical link when the posting ID is known; tracking URLs otherwise."""
    pid, src = a["posting_id"], (a["source"] or "").lower()
    if pid and "indeed" in src:
        return f"https://ph.indeed.com/viewjob?jk={pid}"
    if pid and "linkedin" in src:
        return f"https://www.linkedin.com/jobs/view/{pid}"
    return a["job_url"]


def job_line(a, group):
    """Plain-text fallback line for one job."""
    title = a["position"].replace("[", "(").replace("]", ")")  # brackets would break the masked link
    url = display_url(a)
    link = f"[{title}](<{url}>)" if url else title
    meta = [a["company"], a["source"], f"`{a['id']}`"]
    if a["interview_date"] and a["status"] in ("INTERVIEW", "FINAL_INTERVIEW"):
        meta.insert(0, f"📅 {a['interview_date']}")
    line = f"**{link}**\n" + " · ".join(x for x in meta if x)
    sub = a["next_action"] if group[0] in ACTION_STAGES else (a["notes"] if group[2] else None)
    if sub:
        line += f"\n-# {short(sub)}"
    return line


def grouped(apps):
    out = {}
    for a in apps:
        g = next((g for g in GROUPS if g[1](a)), OTHER)
        out.setdefault(g, []).append(a)
    return [(g, out[g]) for g in GROUPS + [OTHER] if g in out]


def job_field(a, group):
    """One full-width embed field per job: title as the name; company, source, ID, link and next step below."""
    meta = [a["company"], a["source"], f"`{a['id']}`"]
    if a["interview_date"] and a["status"] in ("INTERVIEW", "FINAL_INTERVIEW"):
        meta.insert(0, f"📅 {a['interview_date']}")
    url = display_url(a)
    if url:
        meta.append(f"[Open posting]({url})")
    value = " · ".join(x for x in meta if x)
    if group[0] in ACTION_STAGES or group[0] == "✅ Prepare":
        if a["next_action"]:
            value += f"\n**Next step:** {short(a['next_action'])}"
    elif group[2] and a["notes"]:
        value += f"\n**{'Review reason' if group[0] == '⚠️ Needs review' else 'Reason'}:** {short(a['notes'])}"
    return {"name": a["position"][:256], "value": value[:1024], "inline": False}


def embed_size(e):
    """Characters Discord counts toward its 6000-per-message embed limit."""
    return (len(e.get("title", "")) + len(e.get("description", "")) + len(e.get("footer", {}).get("text", ""))
            + sum(len(f["name"]) + len(f["value"]) for f in e.get("fields", [])))


def render_embeds(heading, apps, summary):
    """Returns Discord webhook payloads: one embed per stage (one field per job), split only when a limit forces it."""
    embeds = []
    for g, items in grouped(apps):
        embed = {"title": f"{g[0]} · {len(items)}", "color": g[3], "fields": []}
        for a in items:
            field = job_field(a, g)
            if embed["fields"] and (len(embed["fields"]) == MAX_FIELDS
                                    or embed_size(embed) + len(field["name"]) + len(field["value"]) > MESSAGE_EMBED_LIMIT):
                embeds.append(embed)
                embed = {"color": g[3], "fields": []}  # continuation: no repeated title
            embed["fields"].append(field)
        embeds.append(embed)

    content = f"## {heading}" + (f"\n{summary}" if summary else "")
    payloads, batch, size = [], [], 0
    for e in embeds:
        n = embed_size(e)
        if batch and (len(batch) == MAX_EMBEDS or size + n > MESSAGE_EMBED_LIMIT):
            payloads.append({"embeds": batch})
            batch, size = [], 0
        batch.append(e)
        size += n
    if batch or not payloads:
        payloads.append({"embeds": batch})
    payloads[0]["content"] = content
    return payloads


def render_text(heading, apps, summary):
    """Plain-text fallback: heading once, section titles once, continuation messages just continue."""
    messages, current = [], f"## {heading}" + (f"\n{summary}" if summary else "")
    for g, items in grouped(apps):
        for i, a in enumerate(items):
            block = (f"\n### {g[0]} ({len(items)})" if i == 0 else "") + "\n" + job_line(a, g)
            if len(current) + len(block) > TEXT_LIMIT:
                messages.append(current)
                current = block.lstrip("\n")
            else:
                current += block
    messages.append(current)
    return messages


def send_webhook(url, payload, files=()):
    body = json.dumps(dict(payload, username="JobAgent", allowed_mentions={"parse": []})).encode()
    headers = {"User-Agent": "JobAgent (discord_post.py)"}
    if files:  # multipart: payload_json + files[n]
        boundary = "JobAgentBoundary7d2f"
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
                 f"Content-Type: application/json\r\n\r\n".encode() + body + b"\r\n"]
        for i, path in enumerate(files):
            p = Path(path)
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files[{i}]"; filename="{p.name}"\r\n'
                         f"Content-Type: application/octet-stream\r\n\r\n".encode() + p.read_bytes() + b"\r\n")
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    else:
        headers["Content-Type"] = "application/json"
    urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST", headers=headers), timeout=60).close()
    time.sleep(0.6)  # webhooks allow ~5 requests per 2 seconds


STANDARD_RESUME = Path(__file__).resolve().parent.parent / "profile" / "standard-resume.json"


def resume_skills():
    sel = json.loads(STANDARD_RESUME.read_text(encoding="utf-8"))
    return {s.lower() for items in sel["skills"].values() for s in items}


def bullets(items):
    return "\n".join(f"• {i}" for i in items)[:1024] or "—"


def post_package(channel, heading, app, brief_path, letter_md=None, attach=(), dry_run=False):
    """One message: an application brief card, the cover letter card, and the files attached.
    brief.json: {"fit": str, "highlight": [skills on the standard resume], "gaps": [str], "check": [str]}"""
    brief = json.loads(Path(brief_path).read_text(encoding="utf-8"))
    unknown = [s for s in brief.get("highlight", []) if s.lower() not in resume_skills()]
    if unknown:
        raise SystemExit(f"highlight skills not on the standard resume: {unknown}")
    card = {"title": f"{app['position']} · {app['company']}"[:256], "description": brief.get("fit", "")[:4096],
            "color": 0x2ECC71, "fields": [
                {"name": "✅ Skills to highlight", "value": " ".join(f"`{s}`" for s in brief.get("highlight", []))[:1024] or "—"},
                {"name": "📚 Gaps to prepare for", "value": bullets(brief.get("gaps", []))},
                {"name": "🔍 Before you submit", "value": bullets(brief.get("check", []))},
                {"name": "📎 Attached", "value": " · ".join(Path(f).name for f in attach)[:1024] or "no files"},
            ], "footer": {"text": f"{app['id']} · {app['source'] or ''}".strip(" ·")}}
    url = display_url(app)
    if url:
        card["url"] = url
    embeds = [card]
    if letter_md:
        embeds.append({"title": "✉️ Cover letter", "description": Path(letter_md).read_text(encoding="utf-8").strip()[:4096],
                       "color": 0x0E7C7B})
    payload = {"content": f"## {heading}", "embeds": embeds}
    hook = webhook_for(channel)
    if dry_run:
        print(json.dumps(dict(payload, files=[str(f) for f in attach]), indent=1, ensure_ascii=False))
    elif hook:
        send_webhook(hook, payload, attach)
    else:
        lines = [f"## {heading}", f"**{card['title']}**", card["description"]]
        lines += [f"**{f['name']}**\n{f['value']}" for f in card["fields"]]
        send_text(channel, "\n".join(lines + [f"MEDIA:{f}" for f in attach]))
    return f"{'previewed' if dry_run else 'posted'} package for {app['id']} to #{channel}"


def post_letter(channel, heading, app, letter_md, attach=(), dry_run=False):
    """One message: the cover letter as an embed (readable/copyable on a phone) with its files attached."""
    text = Path(letter_md).read_text(encoding="utf-8").strip()
    embed = {"title": f"✉️ {app['position']} · {app['company']}"[:256], "description": text[:4096],
             "color": 0x2ECC71, "footer": {"text": f"{app['id']} · {Path(letter_md).name}"}}
    url = webhook_for(channel)
    if dry_run:
        print(json.dumps({"content": f"## {heading}", "embeds": [embed], "files": [str(f) for f in attach]},
                         indent=1, ensure_ascii=False))
    elif url:
        send_webhook(url, {"content": f"## {heading}", "embeds": [embed]}, attach)
    else:  # hermes send attaches files given as MEDIA:<path>
        send_text(channel, "\n".join([f"## {heading}", f"**{embed['title']}**", text] + [f"MEDIA:{f}" for f in attach]))
    return f"{'previewed' if dry_run else 'posted'} cover letter for {app['id']} to #{channel}"


def send_text(channel, message):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(message)
    try:
        subprocess.run(["hermes", "send", "-q", "-t", f"discord:{channel}", "-f", f.name], check=True)
    finally:
        os.unlink(f.name)


def webhook_for(channel):
    try:
        return json.loads(WEBHOOKS_FILE.read_text(encoding="utf-8")).get(channel) or None
    except FileNotFoundError:
        return None


def post(channel, heading, apps, summary=None, dry_run=False):
    url = webhook_for(channel)
    if url:
        payloads = render_embeds(heading, apps, summary)
        for p in payloads:
            print(json.dumps(p, indent=1, ensure_ascii=False)) if dry_run else send_webhook(url, p)
    else:
        payloads = render_text(heading, apps, summary)
        for m in payloads:
            print(m + "\n" + "-" * 40) if dry_run else send_text(channel, m)
    return f"{'previewed' if dry_run else 'posted'} {len(payloads)} message(s) to #{channel} as {'embeds' if url else 'text'}"


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("channel")
    p.add_argument("heading")
    p.add_argument("ids", nargs="*")
    p.add_argument("--summary", help="one line under the heading, e.g. counts")
    p.add_argument("--package", help="brief.json: post an application package (brief + --letter + --attach) for one APP-ID")
    p.add_argument("--letter", help="cover letter .md: post it as an embed for the single APP-ID given")
    p.add_argument("--attach", nargs="*", default=[], help="files to attach with --letter (PDF, DOCX)")
    p.add_argument("--dry-run", action="store_true", help="print instead of sending")
    a = p.parse_args()

    conn = sqlite3.connect(f"{job_db.DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    marks = ",".join("?" * len(a.ids))
    rows = {r["id"]: dict(r) for r in conn.execute(f"SELECT * FROM applications WHERE id IN ({marks})", a.ids)}
    missing = [i for i in a.ids if i not in rows]
    if missing:
        raise SystemExit(f"unknown application id(s): {missing}")
    if (a.package or a.letter) and len(a.ids) != 1:
        raise SystemExit("--package / --letter need exactly one APP-ID")
    if a.package:
        print(post_package(a.channel, a.heading, rows[a.ids[0]], a.package, a.letter, a.attach, a.dry_run))
    elif a.letter:
        print(post_letter(a.channel, a.heading, rows[a.ids[0]], a.letter, a.attach, a.dry_run))
    else:
        print(post(a.channel, a.heading, [rows[i] for i in a.ids], a.summary, a.dry_run))


if __name__ == "__main__":
    main()
