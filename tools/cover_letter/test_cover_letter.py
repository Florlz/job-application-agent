"""Self-check for make_cover_letter.py. Builds into a temp folder; nothing in applications\\ is touched.
Run: python test_cover_letter.py   (needs Word for the PDF step)
"""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

import make_cover_letter as mcl

HERE = Path(__file__).resolve().parent
profile = yaml.safe_load(mcl.PROFILE.read_text(encoding="utf-8"))
proj = {p["id"]: p["verified_facts"] for p in profile["projects"]}
toyota, arsafe, ojt = proj["crystal_toyota"], proj["capstone"], proj["ojt_weekly_reporting"]
off_resume = profile["experience"][0]["verified_facts"][3]  # verified, but not on the standard resume

app = Path(tempfile.mkdtemp()) / "APP-TEST"
app.mkdir()
(app / "posting.txt").write_text("Junior Software QA Tester. Responsibilities include writing test cases and "
                                 "reporting defects clearly to the development team.", encoding="utf-8")

good = {
    "role": "Junior Software QA Tester", "company": "Northwind Software Inc.", "greeting": "Dear Hiring Team,",
    "paragraphs": [
        "Northwind's opening for a Junior Software QA Tester caught my attention because the role centres on careful "
        "testing, clear documentation, and close work with developers, which is how I already like to work. I recently "
        "completed my BS in Information Technology, and the software I have shipped so far only went out once its "
        "quality checks passed.",
        "For a client, I built a responsive Toyota marketing website with React, TypeScript, and Supabase, and it "
        "shipped only after catalog-integrity, lint, build, and responsive checks passed. Its protected admin workspace "
        "supports 24 model families and 53 variants, with publishing, archive and restore workflows, and access "
        "controls, so correctness mattered on every screen rather than only on the happy path.",
        "Testing and debugging also shaped my other work. As lead developer of an offline AR disaster-preparedness "
        "application built with Unity and C#, I covered scenario logic, navigation guidance, testing, and debugging, "
        "and the capstone earned a final grade of 1.1. During my internship I wrote VBA macros that consolidated "
        "seven days of hourly records into weekly documentation, which taught me to check data before anyone relies on it.",
        "Your posting mentions writing test cases and reporting defects clearly. I would bring the same habits to "
        "your team: reproduce the issue, document each step, and confirm the fix before closing it. I am ready to "
        "learn your test management tools quickly, and glad to start with manual testing while building toward "
        "automation where it genuinely helps the team. I would welcome "
        "the chance to discuss how I can support your QA work.",
    ],
    "claims": [
        {"claim": "Toyota site shipped after checks", "facts": [toyota[0], toyota[3]]},
        {"claim": "24 model families, 53 variants", "facts": [toyota[1]]},
        {"claim": "ARSAFE lead, testing, grade 1.1", "facts": arsafe},
        {"claim": "VBA weekly documentation", "facts": [ojt[0]]},
    ],
    "company_claims": [{"claim": "QA duties", "source": "posting", "quote": "writing test cases and reporting defects clearly"}],
}


def run(draft, check_only=False):
    f = app.parent / "draft.json"
    f.write_text(json.dumps(draft), encoding="utf-8")
    args = [sys.executable, str(HERE / "make_cover_letter.py"), str(f), str(app)] + (["--check-only"] if check_only else [])
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, json.loads(r.stdout)


def expect_error(mutate, needle):
    d = copy.deepcopy(good)
    mutate(d)
    code, out = run(d, check_only=True)
    assert code == 1 and any(needle in e for e in out["errors"]), (needle, out)


code, out = run(good, check_only=True)
assert code == 0, out
expect_error(lambda d: d["paragraphs"].__setitem__(1, d["paragraphs"][1].replace("53 variants", "60 variants")), "'60'")
expect_error(lambda d: d["paragraphs"].__setitem__(3, d["paragraphs"][3] + " I also know Spring Boot."), "'Spring'")
expect_error(lambda d: d["claims"].append({"claim": "invented", "facts": ["Led a team of ten engineers."]}), "not on the standard resume")
expect_error(lambda d: d["company_claims"][0].__setitem__("quote", "a fast-growing fintech"), "quote not found")
expect_error(lambda d: d.__setitem__("paragraphs", d["paragraphs"][:1]), "words")
# a fact that exists in the profile but is not on the standard resume is rejected too
assert off_resume not in mcl.selection_scope(profile)[0]
expect_error(lambda d: d["claims"].append({"claim": "VBA reporting", "facts": [off_resume]}), "not on the standard resume")

# build twice: second build is versioned, nothing overwritten
code, first = run(good)
assert code == 0 and first["pages"] == 1 and first["md"].endswith("Florian_Monte_Cover_Letter_Northwind_Software.md"), first
code, second = run(good)
assert code == 0 and second["md"].endswith("Florian_Monte_Cover_Letter_Northwind_Software_v2.md"), second
assert (app / "Florian_Monte_Cover_Letter_Northwind_Software_claims.json").exists() and (app / "Florian_Monte_Cover_Letter_Northwind_Software_v2_claims.json").exists()
assert mcl.company_slug("Contoso Philippines Inc.") == "Contoso"

# the longest allowed letter still fits on one page
longest = copy.deepcopy(good)
filler = " I care about clear communication, careful reviews, and steady improvement over time."
while len(" ".join(longest["paragraphs"]).split()) + len(filler.split()) <= mcl.MAX_WORDS:
    i = len(" ".join(longest["paragraphs"]).split()) % 4
    longest["paragraphs"][i] += filler
code, out = run(longest)
assert code == 0 and out["pages"] == 1, out
print(f"all cover letter checks passed ({first['words']} words, {first['pages']} page) -> {app}")
