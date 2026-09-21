"""Self-check for discord_post.py rendering against Discord's limits. Run: python test_discord_post.py"""
import discord_post as dp

LONG = "https://url.jobstreet.com/uni/ss/c/" + "x" * 300  # Jobstreet tracking URLs are ~330 chars


def app(i, status="FOUND", next_action="Check posting", notes="Relevant title. More words here.", source="Jobstreet"):
    return {"id": f"APP-2026-{i:04d}", "position": f"Software Engineer [{i}]", "company": f"Company {i}",
            "source": source, "status": status, "next_action": next_action, "notes": notes, "needs_review": 0,
            "job_url": LONG, "posting_id": None, "interview_date": None}


apps = ([app(i, next_action="PREPARE: build application package") for i in range(3)]
        + [app(i) for i in range(3, 60)]
        + [app(i, status="REVIEW", notes="Needs 3+ years of .NET. Extra.") for i in range(60, 70)]
        + [app(70, source="Indeed")])
apps[-1]["posting_id"] = "abc123"

# embeds: readable cards with one full-width field per job, within Discord's limits
payloads = dp.render_embeds("New jobs", apps, "**71 found**")
assert payloads[0]["content"].startswith("## New jobs") and all("content" not in p for p in payloads[1:])
for p in payloads:
    assert len(p["embeds"]) <= dp.MAX_EMBEDS
    assert sum(dp.embed_size(e) for e in p["embeds"]) <= 6000
for e in (e for p in payloads for e in p["embeds"]):
    assert len(e.get("description", "")) <= 4096
    assert len(e.get("fields", [])) <= 25
    assert all(f.get("inline") is False for f in e.get("fields", []))
titles = [e["title"] for p in payloads for e in p["embeds"] if "title" in e]
assert titles == ["⚠️ Needs review · 10", "✅ Prepare · 3", "🔎 Check posting · 58"], titles
fields = [f for p in payloads for e in p["embeds"] for f in e.get("fields", [])]
assert len(fields) == len(apps)                               # every job, once
assert sum("Software Engineer" in f["name"] for f in fields) == len(apps)
field_text = "\n".join(f["name"] + "\n" + f["value"] for f in fields)
assert "ph.indeed.com/viewjob?jk=abc123" in field_text       # canonical short link
assert "Relevant title" not in field_text                    # no boilerplate on check-posting jobs
assert "**Review reason:** Needs 3+ years of .NET" in field_text
assert "**Next step:** PREPARE: build application package" in field_text

# text fallback: under 2000 chars, headers never repeated
msgs = dp.render_text("New jobs", apps, "**71 found**")
assert all(len(m) <= 2000 for m in msgs)
joined = "\n".join(msgs)
assert joined.count("## New jobs") == 1 and joined.count("### 🔎 Check posting") == 1
print(f"all discord_post checks passed ({len(payloads)} embed message(s), {len(msgs)} text message(s))")
