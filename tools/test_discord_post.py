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

# embeds: within limits, heading only in the first message, each stage titled once
payloads = dp.render_embeds("New jobs", apps, "**71 found**")
assert payloads[0]["content"].startswith("## New jobs") and all("content" not in p for p in payloads[1:])
for p in payloads:
    assert len(p["embeds"]) <= dp.MAX_EMBEDS
    assert sum(len(e.get("title", "")) + len(e["description"]) for e in p["embeds"]) <= 6000
    assert all(len(e["description"]) <= 4096 for e in p["embeds"])
titles = [e["title"] for p in payloads for e in p["embeds"] if "title" in e]
assert titles == ["⚠️ Needs review (10)", "✅ Prepare (3)", "🔎 Check posting (58)"], titles
text = "".join(e["description"] for p in payloads for e in p["embeds"])
assert text.count("**[") == len(apps)                      # every job, once
assert "ph.indeed.com/viewjob?jk=abc123" in text           # canonical short link
assert "Relevant title" not in text                         # no boilerplate on check-posting jobs
assert "*Needs 3+ years of .NET*" in text                   # review reason shown

# text fallback: under 2000 chars, headers never repeated
msgs = dp.render_text("New jobs", apps, "**71 found**")
assert all(len(m) <= 2000 for m in msgs)
joined = "\n".join(msgs)
assert joined.count("## New jobs") == 1 and joined.count("### 🔎 Check posting") == 1
print(f"all discord_post checks passed ({len(payloads)} embed message(s), {len(msgs)} text message(s))")
