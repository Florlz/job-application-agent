"""Build Florian's standard resume (DOCX + PDF) from the verified profile.

  python build_resume.py [out_dir]      (default: output\\resume-preview)

Content comes only from profile\\career-profile.yaml; profile\\standard-resume.json decides which
facts, skills and projects appear (the same list cover letters are checked against).
Prints JSON {"docx", "pdf", "pages"}; the resume must stay on one page.
"""
import datetime
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "cover_letter"))
import make_cover_letter as mcl  # noqa: E402  (shared: to_pdf_and_count_pages)

SKILL_LABELS = {"frontend": "Frontend", "backend_apis": "Backend & APIs", "data_cloud": "Databases & Cloud",
                "languages": "Languages", "tools_testing": "Tools & Testing", "ai_automation": "AI & Automation",
                "other": "Other"}
# Layout knobs (half-points / twips). Tuned so the page is full but stays one page.
LAYOUT = {"body": 20, "line": 232, "bulletAfter": 4, "entryBefore": 45, "sectionBefore": 80,
          "margin": {"top": 500, "bottom": 460, "left": 720, "right": 720}}


def month(v):
    try:
        return datetime.datetime.strptime(str(v), "%Y-%m").strftime("%b %Y")
    except ValueError:
        return str(v)


def resolve(profile, sel):
    ident = profile["identity"]
    contact = [{"text": ident.get("resume_location") or ident["location"]}, {"text": ident.get("phone", "")},
               {"text": ident["email"], "url": f"mailto:{ident['email']}"},
               {"text": ident.get("linkedin_url", ""), "url": f"https://{ident.get('linkedin_url', '')}"},
               {"text": ident.get("github_url", ""), "url": f"https://{ident.get('github_url', '')}"}]
    contact = [item for item in contact if item["text"]]
    projects = {p["id"]: p for p in profile["projects"]}
    exp = {e["id"]: e for e in profile["experience"]}

    def facts_ok(entry, bullets):
        allowed = set(entry.get("verified_facts") or [])
        bad = [f for b in bullets for f in b if f not in allowed]
        if bad:
            raise SystemExit(f"standard-resume.json has facts not in career-profile.yaml: {bad}")
        return [" ".join(b) for b in bullets]

    proj_entries = []
    for pick in sel["projects"]:
        p = projects[pick["id"]]
        proj_entries.append({"title": p["name"].replace(" - ", " – "), "url": p.get("url"), "date": month(p.get("date", "")).replace(" - ", " – "),
                             "subtitle": " | ".join(x for x in (p.get("role"), ", ".join(p.get("technologies") or [])) if x),
                             "bullets": facts_ok(p, pick["bullets"])})
    exp_entries = []
    for pick in sel["experience"]:
        e = exp[pick["id"]]
        exp_entries.append({"title": e["company"].replace(" - ", " – "), "date": f"{month(e.get('start', ''))} – {month(e.get('end', ''))}",
                            "subtitle": e["title"], "bullets": facts_ok(e, pick["bullets"])})
    edu = [{"title": e["school"], "date": f"{e.get('start', '')} – {e.get('end', '')}",
            "subtitle": " | ".join(filter(None, (e["degree"], e.get("location", "")))),
            "bullets": ["  |  ".join(f.rstrip(".") for f in e["verified_facts"])]} for e in profile["education"]]
    lead = [{"title": e["organization"].replace(" - ", " – "), "date": str(e.get("date", "")).replace(" - ", " – "), "subtitle": e["title"],
             "bullets": e["verified_facts"]} for e in profile["leadership"]]

    return {"name": (ident.get("resume_name") or ident["name"]).upper(), "headline": ident.get("headline", ""), "contact": contact, "layout": LAYOUT,
            "sections": [
                {"kind": "text", "title": "Professional Summary", "text": " ".join(profile.get("summary", "").split())},
                {"kind": "skills", "title": "Technical Skills",
                 "lines": [{"label": SKILL_LABELS.get(k, k.replace("_", " ").title()), "items": v} for k, v in sel["skills"].items()]},
                {"kind": "entries", "title": "Projects & Client Work", "entries": proj_entries},
                {"kind": "entries", "title": "Professional Experience", "entries": exp_entries},
                {"kind": "entries", "title": "Education", "entries": edu},
                {"kind": "entries", "title": "Leadership", "entries": lead},
            ]}


def main():
    out = (Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "output" / "resume-preview").resolve()
    out.mkdir(parents=True, exist_ok=True)
    profile = yaml.safe_load((ROOT / "profile" / "career-profile.yaml").read_text(encoding="utf-8"))
    sel = json.loads((ROOT / "profile" / "standard-resume.json").read_text(encoding="utf-8"))
    person = "_".join(re.findall(r"[\w-]+", profile["identity"].get("resume_name") or profile["identity"]["name"])) or "Applicant"
    docx, pdf = out / f"{person}_Resume.docx", out / f"{person}_Resume.pdf"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(resolve(profile, sel), f)
    try:
        subprocess.run(["node", str(HERE / "build_resume.js"), f.name, str(docx)], check=True, cwd=HERE.parent)
    finally:
        Path(f.name).unlink()
    pages = mcl.to_pdf_and_count_pages(docx, pdf)
    print(json.dumps({"docx": str(docx), "pdf": str(pdf), "pages": pages}, indent=2))
    if pages != 1:
        sys.exit(1)


if __name__ == "__main__":
    main()
