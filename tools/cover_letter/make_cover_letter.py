"""Validate and build a tailored cover letter (DOCX + PDF + MD) for one application.

  python make_cover_letter.py <draft.json> <applications\\APP-ID> [--check-only]

The application folder must hold posting.txt; company.txt (text saved from the company's own
website) is optional. The letter may only claim what Florian's standard resume shows, listed in
profile\\standard-resume.json (the facts, skills and projects on profile\\Florian_Monte_Resume.pdf). Draft format:
{
  "role": "Junior Software QA Tester", "company": "Northwind Software Inc.",
  "greeting": "Dear Hiring Team,",
  "paragraphs": ["...", "...", "..."],
  "claims": [{"claim": "built a Supabase admin workspace", "facts": ["<verified fact, exact>"]}],
  "company_claims": [{"claim": "they test payroll software", "source": "posting|company", "quote": "<exact text>"}]
}
Checks: 250-320 words; every cited fact is on the standard resume; every company quote is in
posting.txt / company.txt; every
number in the letter appears in the cited facts or quotes; every profile technology named in the
letter is covered by a cited fact, a selected skill, a selected project's stack, or a quote.
Never overwrites: saves Florian_Monte_Cover_Letter_<Company>.*, then _v2, _v3 ... plus <name>_claims.json.
Prints JSON {"md", "docx", "pdf", "words", "pages"}; exits 1 with {"errors": [...]} on any failure.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE.parent.parent / "profile"
PROFILE = PROFILE_DIR / "career-profile.yaml"
STANDARD_RESUME = PROFILE_DIR / "standard-resume.json"
MIN_WORDS, MAX_WORDS = 250, 320
GENERIC_TOKENS = {"API", "APIs", "AI", "IT", "UI", "UX", "CSS3", "HTML5"}  # too generic to count as a claim
NUMBER = re.compile(r"\d+(?:[.,/:-]\d+)*%?")


def norm(text):
    return " ".join(str(text).split()).lower()


def tech_terms(profile):
    """Case-sensitive technology tokens from the profile (e.g. React, C#, Next.js, VBA)."""
    items = [i for k, v in profile["skills"].items() for i in v]
    items += [t for p in profile["projects"] for t in (p.get("technologies") or [])]
    terms = set()
    for item in items:
        for tok in re.split(r"[\s/]+", str(item)):
            tok = tok.strip(",;()")
            if tok and tok not in GENERIC_TOKENS and (any(c.isupper() for c in tok) or any(c in tok for c in "#+.")):
                terms.add(tok)
    return terms


def mentions(term, text):
    return re.search(rf"(?<![\w#+.]){re.escape(term)}(?![\w#+])", text) is not None


def header(profile):
    """(NAME IN CAPS, [location, phone, email, linkedin, github])."""
    ident = profile["identity"]
    contact = [ident.get("resume_location") or ident["location"], ident.get("phone"), ident.get("email"),
               ident.get("linkedin_url"), ident.get("github_url")]
    return (ident.get("resume_name") or ident["name"]).upper(), [c for c in contact if c]


def to_pdf_and_count_pages(docx, pdf):
    """Word (COM) converts the DOCX to PDF and reports the page count."""
    ps = f"""
$w = New-Object -ComObject Word.Application
try {{
  $d = $w.Documents.Open('{docx}', $false, $true)
  $n = $d.ComputeStatistics(2)
  $d.SaveAs2('{pdf}', 17)
  $d.Close($false)
  Write-Output $n
}} finally {{ $w.Quit() }}
"""
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, check=True)
    return int(out.stdout.strip().splitlines()[-1])


def selection_scope(profile, _app_dir=None, resume=STANDARD_RESUME):
    """Facts, skills and project stacks that Florian's standard resume shows."""
    sel = json.loads(Path(resume).read_text(encoding="utf-8"))
    facts = {f for kind in ("projects", "experience") for pick in sel.get(kind, [])
             for bullet in pick.get("bullets", []) for f in bullet}
    skills = [i for items in (sel.get("skills") or {}).values() for i in items]
    picked = {p["id"] for p in sel.get("projects", [])}
    stacks = [t for p in profile["projects"] if p["id"] in picked for t in (p.get("technologies") or [])]
    return facts, skills, stacks


def validate(draft, profile, app_dir):
    errors = []
    body = "\n".join(draft.get("paragraphs") or [])
    for key in ("role", "company", "greeting"):
        if not str(draft.get(key) or "").strip():
            errors.append(f"missing {key}")
    words = len(body.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        errors.append(f"body is {words} words; must be {MIN_WORDS}-{MAX_WORDS}")

    facts, skills, stacks = selection_scope(profile, app_dir)
    cited = []
    for c in draft.get("claims") or []:
        for f in c.get("facts") or []:
            if f not in facts:
                errors.append(f"claim {c.get('claim')!r}: fact not on the standard resume: {f!r}")
            cited.append(f)
        if not c.get("facts"):
            errors.append(f"claim {c.get('claim')!r} cites no fact")

    sources = {"posting": app_dir / "posting.txt", "company": app_dir / "company.txt"}
    quotes = []
    for c in draft.get("company_claims") or []:
        src = sources.get(c.get("source"))
        if not src or not src.exists():
            errors.append(f"company claim {c.get('claim')!r}: source must be 'posting' or 'company' and the file must exist")
        elif norm(c.get("quote", "")) not in norm(src.read_text(encoding="utf-8")) or not c.get("quote"):
            errors.append(f"company claim {c.get('claim')!r}: quote not found in {src.name}")
        quotes.append(c.get("quote", ""))

    support = " ".join(cited + quotes + [draft.get("role", ""), draft.get("company", "")])
    for n in sorted(set(NUMBER.findall(body))):
        if n not in support:
            errors.append(f"number {n!r} is not in any cited fact or quote")
    covered = " ".join([support] + skills + stacks)
    for t in sorted(tech_terms(profile)):
        if mentions(t, body) and not mentions(t, covered):
            errors.append(f"technology {t!r} is named but not backed by a cited fact, selected skill or project stack")
    return errors, words


LEGAL_WORDS = {"inc", "corp", "corporation", "co", "company", "ltd", "limited", "llc", "opc", "the", "philippines", "phils"}


def company_slug(company):
    """'Northwind Software Inc.' -> 'Northwind_Software'; 'Contoso Philippines Inc.' -> 'Contoso'."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", company) if w.lower() not in LEGAL_WORDS]
    return "_".join(words[:3]) or "Company"


def next_name(app_dir, company):
    """Florian_Monte_Cover_Letter_<Company>, then _v2, _v3 ...; never reuses an existing name."""
    base = f"Florian_Monte_Cover_Letter_{company_slug(company)}"
    n = 1
    while True:
        name = base if n == 1 else f"{base}_v{n}"
        if not any((app_dir / f"{name}{ext}").exists() for ext in (".md", ".docx", ".pdf", "_claims.json")):
            return name
        n += 1


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("draft")
    p.add_argument("app_dir")
    p.add_argument("--check-only", action="store_true", help="validate without writing files")
    a = p.parse_args()

    app_dir = Path(a.app_dir)
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    draft = json.loads(Path(a.draft).read_text(encoding="utf-8"))
    if not (app_dir / "posting.txt").exists():
        print(json.dumps({"errors": [f"{app_dir} has no posting.txt; save the posting text first"]}, indent=2))
        sys.exit(1)
    errors, words = validate(draft, profile, app_dir)
    if errors or a.check_only:
        print(json.dumps({"errors": errors, "words": words} if errors else {"ok": True, "words": words}, indent=2))
        sys.exit(1 if errors else 0)

    name, contact = header(profile)
    today = datetime.date.today()
    letter = {"name": name, "contact": contact, "headline": profile["identity"].get("headline", ""),
              "date": f"{today:%B} {today.day}, {today.year}",
              "company": draft["company"], "role": draft["role"], "greeting": draft["greeting"],
              "paragraphs": draft["paragraphs"], "signature": name.title()}
    base = next_name(app_dir, draft["company"])
    md = app_dir / f"{base}.md"
    docx, pdf = app_dir / f"{base}.docx", app_dir / f"{base}.pdf"

    md.write_text("\n\n".join([letter["greeting"], *letter["paragraphs"], f"Sincerely,\n{letter['signature']}"]) + "\n",
                  encoding="utf-8")
    (app_dir / f"{base}_claims.json").write_text(
        json.dumps({"claims": draft.get("claims", []), "company_claims": draft.get("company_claims", [])},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(letter, f)
    try:
        subprocess.run(["node", str(HERE / "build_cover_letter.js"), f.name, str(docx)], check=True, cwd=HERE.parent)
    finally:
        Path(f.name).unlink()
    pages = to_pdf_and_count_pages(docx, pdf)
    print(json.dumps({"md": str(md), "docx": str(docx), "pdf": str(pdf), "words": words, "pages": pages}, indent=2))


if __name__ == "__main__":
    main()
