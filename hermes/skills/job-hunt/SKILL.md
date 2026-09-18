---
name: job-hunt
description: Manage Florian's job search - evaluate job postings, write application briefs and verified cover letters, draft application answers, classify recruiter emails, and track applications in the JobAgent SQLite database. Never submits applications or sends email.
---

# Job Hunt Agent

## Purpose

Manage Florian's job-search workflow while keeping Florian in control of submissions and outbound communication.

## System boundaries

- SQLite is the application source of truth: `C:\Users\monte\JobAgent\data\job-hunt.db`.
- Hermes is the sole writer of that database. n8n never writes to it.
- n8n owns Gmail access, schedules, and deterministic workflows. Hermes uses n8n through MCP.
- Hermes owns local files and reasoning.
- Discord is the human interface.
- Florian manually submits job applications.
- Recruiter emails may be drafted automatically but must never be sent automatically.

## Local workspace

Use:

`C:\Users\monte\JobAgent`

Canonical sources:

- `profile\career-profile.yaml`
- `profile\answer-bank.yaml`
- `profile\Florian_Monte_Resume.pdf` (Florian's standard resume, used for every application; `.docx` beside it)
- `profile\standard-resume.json` (the facts, skills and projects on that resume)

Application files are created only for jobs selected as PREPARE (see Application IDs), in one folder per application:

```
applications\APP-YYYY-NNNN\
  posting.txt        job posting text as found
  company.txt        company website text, only if fetched
  brief.json         application brief (fit, skills to highlight, gaps, checks)
  answers.md         application answers, only if the posting has questions
  Florian_Monte_Cover_Letter_<Company>.md|.docx|.pdf   (+ _claims.json; revisions add _v2, _v3)
```

After Florian confirms submission, never modify or overwrite the submitted artifacts:
- answers.md
- Florian_Monte_Cover_Letter_<Company>.* files, if submitted

Other files may be added later for recruiter communication, assessments, or interview preparation.

Never regenerate a submitted artifact in place. If a corrected version is needed, create a new explicitly versioned file (the cover letter tool adds `_v2`, `_v3` itself).

## Statuses

- FOUND
- REVIEW
- READY_TO_APPLY
- APPLIED
- RECRUITER_SCREEN
- ASSESSMENT
- INTERVIEW
- FINAL_INTERVIEW
- OFFER
- REJECTED
- WITHDRAWN
- CLOSED

## Job database

Path: `C:\Users\monte\JobAgent\data\job-hunt.db`

Access it only through the helper, which prints JSON:

```
python C:\Users\monte\JobAgent\tools\job_db.py <command> ...
```

| command | use |
|---|---|
| `create_application '<json>'` | allocate an ID and insert the row in one transaction; returns the ID |
| `get_application <id>` | read one application |
| `update_application <id> '<json>' [--source X]` | change fields; status changes are logged to `activity_log` automatically |
| `list_applications [--status S] [--needs-review]` | list applications |
| `add_activity '<json>'` | log an event; returns `null` if its `email_message_id` is already processed or already logged for that application |
| `message_processed <message_id>` | has this Gmail message been handled? |
| `mark_message_processed <message_id>` | mark handled; `false` if it already was |
| `list_followups [--date YYYY-MM-DD]` | applications due for follow-up |
| `list_stale [--days 30]` | APPLIED with no contact for N days (candidates to close) |
| `import_backfill <preview.csv> <activity.csv> [--dry-run]` | import the backfill rows Florian marked in `Import?`, all or nothing; only after Florian approves, and always `--dry-run` first |

Tables: `applications`, `activity_log`, `processed_messages`, `app_sequence`.

Rules:
- Never write to the database with raw SQL or any other tool; read-only queries are fine.
- Never touch Hermes' own internal database or state.
- `status` must be one of the Statuses; the database rejects anything else.
- Before creating an application, check for an existing one with the same company + normalized position (and posting ID when known).

## Application IDs

Hermes allocates `APP-YYYY-NNNN` IDs transactionally through SQLite (`create_application`). Never infer the next ID from folder names or filesystem state, and never invent a temporary ID.

For a job selected as PREPARE:

1. If no application row exists, `create_application` (status `REVIEW`) to get its ID.
2. Create `applications\<id>\` and the artifacts; set `application_folder`.
3. Validate the artifacts.
4. Only after validation succeeds, `update_application` to `READY_TO_APPLY`.

## Job evaluation

Use a balanced policy.

PREPARE when:
- role is junior / entry-level / early-career;
- most important requirements match verified skills;
- missing skills are reasonably learnable;
- experience is roughly 0-3 years;
- location/work setup is acceptable;
- there is no hard blocker.

REVIEW when fit is plausible but important ambiguity exists.

SKIP when clearly senior, unrelated, or blocked by a hard requirement.

Status mapping:
- PREPARE -> `READY_TO_APPLY`, but only after "prepare" produced a validated cover letter. Until then, `FOUND`.
- REVIEW -> `REVIEW`
- SKIP -> `CLOSED`

Never use fake precision such as arbitrary percentage match scores.

## Job alert discovery

Sources: `Job Search/Job Alerts` messages (LinkedIn "X is hiring Y", Indeed and Jobstreet digests listing several jobs). Skip messages already marked processed.

Links: "JobAgent - Fetch Message Bodies" returns `links` ({text, url}) per message. Match each job to its link by title. Take `posting_id` from the URL when it has one and store the canonical URL as `job_url`:
- Indeed `jk=<id>` -> `https://ph.indeed.com/viewjob?jk=<id>`
- LinkedIn `/jobs/view/<id>` -> `https://www.linkedin.com/jobs/view/<id>`
- Jobstreet tracking URLs carry no readable ID: store the tracking URL unchanged and leave `posting_id` empty.

For each job found in an alert:
- Skip it if an application with the same `posting_id`, or the same company + normalized position, already exists.
- Evaluate PREPARE / REVIEW / SKIP (see Job evaluation), then `create_application` with `source` (LinkedIn / Indeed / Jobstreet), `job_url`, `posting_id` when known, and `date_found`:
  - PREPARE -> status `FOUND`, `next_action` "PREPARE: build application package" (built when Florian says "prepare APP-…").
  - Alerts usually show only title + company. Missing details are not ambiguity: a relevant title with no senior / staff / lead / principal / architect / manager wording, in a workable location, is status `FOUND` with `next_action` "Check posting".
  - REVIEW -> status `REVIEW`, `needs_review` 1, only for real conflicts (a stated experience requirement above 3 years, a core technology not in the profile, an unclear employer). Put the conflict in `notes`.
  - SKIP -> status `CLOSED`, the reason in `notes` (kept so the same posting is not re-evaluated).
- Log one `add_activity` (event_type `JOB_FOUND`) per job with the alert's `email_message_id`, then `mark_message_processed` once per alert email.

Job alerts are not application events: never set `date_applied` or `APPLIED` from an alert.

## Discord posting

Never hand-format job lists or paste URLs into Discord. Write the database first, then post with the formatter, which reads the rows and handles layout, grouping, short links and message splitting:

```
python C:\Users\monte\JobAgent\tools\discord_post.py <channel> "<heading>" <APP-ID> [<APP-ID> ...] [--summary "<one line>"]
```

- Heading style: `<emoji> <What> · <Mon D, H:MM AM/PM>`, e.g. `🆕 New jobs · Sep 18, 6:00 PM`.
- `--summary`: one line of counts, e.g. `**8 new** · 3 prepare · 2 check · 1 review · 2 skipped`.
- The subtext under each job comes from the row: `next_action` for active stages, `notes` for review / check / skipped. Keep those fields to one clear sentence, because that is what Florian reads.
- Add `--dry-run` to preview without sending. With no IDs it posts only the heading and summary.

Channel routing:

| Channel | Post here |
|---|---|
| `job-inbox` | every job-alert scan: summary counts + all new jobs (the only place new jobs are posted) |
| `ready-to-apply` | only finished application packages and cover letters (things Florian can submit now); never new-job lists |
| `job-review` | anything with `needs_review` 1 |
| `applications` | APPLIED confirmations, REJECTED, WITHDRAWN, posting-expired notices |
| `interviews` | RECRUITER_SCREEN, ASSESSMENT, INTERVIEW, FINAL_INTERVIEW (set `interview_date` / `next_action` first) |
| `alerts` | OFFER, recruiter questions, document requests, deadlines within 48h: things Florian must act on |
| `job-tracker` | reserved for the nightly tracker report (automatic) |

Plain status sentences (no job list), e.g. errors: `hermes send -t discord:<channel> -f <file>` with a short `## ` heading and bullet lines.

## Resumes

Florian applies with one standard resume: `profile\Florian_Monte_Resume.pdf`. Never create per-job or tailored resumes, and never edit the resume files by hand. Tailoring happens in the application brief (which skills to highlight) and the cover letter. The standard resume is rebuilt only when Florian's verified facts change (see the jobagent-ops skill).

## Discord chat

Florian chats with Hermes in `#hermes` (every message) and by DM; in the job channels only when @mentioned. This is interactive mode.

- Scope: JobAgent work only. Read and write only inside `C:\Users\monte\JobAgent`; decline anything else ("that's a Desktop task").
- Replies are short and plain. Any list of jobs goes through the formatter into `#hermes` (`discord_post.py hermes "<heading>" <IDs>`), including when asked by DM; then reply with one line such as "Posted 12 jobs in #hermes."
- Replying to a job post (e.g. "@JobApplication close this" as a Discord reply): act on the APP-IDs in the replied-to message.
- Commands, as examples:
  - "close APP-0034" -> `update_application` status CLOSED, note "closed by Florian".
  - "I applied to APP-0147" -> APPLIED, `date_applied` today.
  - "what's due?" / "show review" / "status of Acme" -> query, then formatter.
  - "check my email now" -> `hermes cron run 2f875a8e957d`.
  - "draft a reply to <company>" -> draft in `output\drafts\`, never send.
  - "cover letter APP-…" / "make the letter for APP-… shorter" -> confirm, then run in the background like "prepare", with the prompt "Cover letter for <APP-ID>: follow the job-hunt skill's 'Cover letters' section in automation mode. Feedback: <Florian's words or none>." and `--name letter-<APP-ID>`. Reply "Started; the letter will appear in #ready-to-apply."
- Confirm first (ask "yes?") before changing more than 3 applications at once, and before "prepare". A single explicit command runs immediately.
- "prepare APP-…" runs in the background so the chat stays free. After Florian confirms, run:
  `hermes cron create "1m" "Prepare <APP-ID>: follow the job-hunt skill's 'Application package' section in automation mode." --name prepare-<APP-ID> --repeat 1 --skill job-hunt --deliver local --failure-deliver discord:alerts --workdir C:\Users\monte\JobAgent --model gpt-5.6-luna --provider openai-codex --reasoning-effort xhigh`
  and reply "Started; the package will appear in #ready-to-apply."

## Application package (on request)

Run only when Florian asks, e.g. "prepare APP-2026-0148" (Discord or Desktop). Never automatically.

1. `get_application`; it must be FOUND or REVIEW.
2. Posting: read `job_url` with the web tools and save the full posting text to `applications\<APP-ID>\posting.txt`. If it can't be read (login wall, expired), ask Florian to paste it; in automation mode, set `needs_review` and stop. Optionally save text from the company's own website to `company.txt`.
3. Brief: write `applications\<APP-ID>\brief.json`:
   `{"fit": "1-2 sentences on why you fit, citing your actual projects", "highlight": ["skills to lead with"], "gaps": ["requirements Florian doesn't meet yet, and how to prepare"], "check": ["things to verify before submitting"]}`
   `highlight` may only contain skills from `profile\standard-resume.json` (the formatter rejects others). Keep each list to 2-5 short items, one sentence each. The brief is read by Florian: write it in second person ("you", "your"), never "Florian" or he/his/she/her.
4. Cover letter: always, per Cover letters.
5. `answers.md` only when the posting lists application questions (see Application answers); mark user-required ones `NEEDS FLORIAN`.
6. `update_application`: `application_folder`, status `READY_TO_APPLY`, `next_action` "Review the brief and cover letter, then submit with the standard resume".
7. Post one message with everything attached:
   `python C:\Users\monte\JobAgent\tools\discord_post.py ready-to-apply "📦 Ready to apply · <Mon D, H:MM AM/PM>" <APP-ID> --package applications\<APP-ID>\brief.json --letter <letter .md> --attach <letter .pdf> <letter .docx> C:\Users\monte\JobAgent\profile\Florian_Monte_Resume.pdf`

## Application answers

Use `answer-bank.yaml` and verified career facts.
Tailor routine answers.
Require human input for salary, start date, relocation, shift availability, work authorization, legal declarations, or contractual questions.

## Cover letters

When: as part of every "prepare", or when Florian says "cover letter APP-…" or asks for a revision.

Requires `applications\<APP-ID>\posting.txt`. If it's missing, offer to run "prepare" first.

Content rules (enforced by the validator):
- Claims only what Florian's standard resume shows: facts, skills and project stacks in `profile\standard-resume.json`. Never facts the resume leaves out, never anything outside `career-profile.yaml`.
- 250-320 words, 3-4 short paragraphs: why this role at this company; 2-3 proof points from the selected projects/experience; fit with their stack or duties; a short close. Direct and specific. No clichés ("I am writing to express…", "passionate", "team player", "fast-paced environment").
- Company details only from `posting.txt` or `company.txt` (text you fetched from the company's own website and saved there), quoted exactly in `company_claims`.
- A required skill Florian lacks: at most one sentence, as related experience plus readiness to learn. Never imply Florian has it.
- Greeting: the recruiter's name if the posting gives one, else "Dear Hiring Team,".

How:
1. Write a draft JSON (format in the docstring of `tools\cover_letter\make_cover_letter.py`) with `claims` mapping every concrete claim to exact facts, and `company_claims` with exact quotes.
2. `python C:\Users\monte\JobAgent\tools\cover_letter\make_cover_letter.py <draft.json> applications\<APP-ID> --check-only`
3. On `errors`, revise and re-check, at most 3 attempts. Still failing: save nothing, set `needs_review` 1 with the blocking errors in `notes`, and post the ID to `job-review`.
4. On success, run it without `--check-only`. It writes `Florian_Monte_Cover_Letter_<Company>.md/.docx/.pdf` plus `_claims.json` and prints their paths (revisions get `_v2`, `_v3` automatically; nothing is overwritten).
5. Inside "prepare", the package post (Application package step 7) carries the letter. For a standalone letter or a revision, post it alone: `discord_post.py ready-to-apply "✉️ Cover letter · <Mon D, H:MM AM/PM>" <APP-ID> --letter <md> --attach <pdf> <docx>`.

Revisions ("make the letter for APP-0164 shorter"): same steps with the feedback applied; the tool saves the next version and it is posted again.

## Email handling

Classify messages into one of these, with the status each proposes:

| classification           | proposed_status          |
|--------------------------|--------------------------|
| APPLICATION_CONFIRMATION | APPLIED                  |
| RECRUITER_SCREEN         | RECRUITER_SCREEN         |
| ASSESSMENT               | ASSESSMENT               |
| INTERVIEW_INVITE         | INTERVIEW                |
| FINAL_INTERVIEW          | FINAL_INTERVIEW          |
| OFFER                    | OFFER                    |
| REJECTION                | REJECTED                 |
| CLOSED                   | CLOSED                   |
| POSTING_EXPIRED          | null (no status change)  |
| RECRUITER_QUESTION       | null (no status change)  |
| OTHER                    | null (no status change)  |

`POSTING_EXPIRED` means the job board closed the posting (e.g. Jobstreet "the job has closed / has expired and is no longer taking applications"). It is not a rejection: the employer may still be reviewing. Log it as activity and keep the status. If the application is `APPLIED` with no later employer contact, set `follow_up_date` to 30 days after the email and `next_action` to "Posting expired; close if still no response". `CLOSED` is only for an employer explicitly saying the role is filled or cancelled.

Classify by message content, not by Gmail label; labels are often wrong (e.g. confirmations under Job Alerts, newsletters under Interviews & Offers).

Before processing a Gmail message, check `message_processed`; skip it if already handled. Log it with `add_activity` including `email_message_id` and `email_thread_id`. One message can concern several applications (e.g. Jobstreet "new activity in jobs you applied for" digests): log one activity per application, then call `mark_message_processed` once, after all of them are logged.

High-confidence status updates may be applied with `update_application`.
Ambiguous classification or application matching: set `needs_review: true` and `proposed_status: null`, and never change the application's status. If a matching row exists, set its `needs_review` to 1.

Submission: never assume `READY_TO_APPLY` means submitted. Move to `APPLIED` only on a clear application-confirmation email or when Florian confirms it was submitted.

Draft recruiter replies when useful, but never send them.

## Follow-ups

Use context-aware follow-up timing:
- APPLIED with a direct contact (a recruiter or employer emailed Florian, or Florian applied by email): reminder 7 days after the last contact if silent.
- APPLIED through a job board with no contact (one-click Jobstreet / Indeed / LinkedIn): no follow-up date; there is nobody to follow up with. After 30 days without contact it appears in `job_db.py list_stale` and the nightly tracker as a candidate to close. When Florian says "close APP-…", set status `CLOSED` with a note.
- Active recruiter conversation: do not generate generic follow-up.
- ASSESSMENT: prioritize stated deadline.
- INTERVIEW: follow explicit recruiter timeline where available.
- OFFER / REJECTED / WITHDRAWN / CLOSED: no generic follow-up.

Explicit employer timelines override defaults.

Store the chosen date in `follow_up_date` (YYYY-MM-DD). Follow-up is not a status.

## Historical backfill

Covers the six months before the run date given in the request. If no run date is provided, do not guess; see Missing required information.

Sources:
- Gmail label: Job Search/Application Updates
- Gmail label: Job Search/Interviews & Offers
- Sent Mail likely application messages

Identity:
- one application per company + normalized job title;
- store platform posting ID when known;
- IDs are allocated only when a record is committed (see Application IDs).

Run as a dry run first: produce preview records only. Do not create rows in `applications` or `activity_log`, and do not mark messages processed, until Florian approves the preview.
Ambiguous records are flagged `needs_review: true` in the preview.

## Model routing (reference only)

Model selection is configured in Hermes/n8n, not by this skill. Intended routing:

- Routine/mechanical tasks: OpenCode Free first, Nous free fallback.
- Important or ambiguous reasoning (application briefs, ambiguous application matching, recruiter-email reasoning, application answers, cover letters, interview preparation): GPT-5.6 Luna through Codex subscription.

## Response modes

### Automation mode

When the request explicitly identifies the caller as n8n or includes `automation_mode: true`, respond with exactly one raw JSON object matching the output contract below:
- no prose
- no markdown
- no code fences

### Interactive mode

When Florian is communicating directly through Hermes Desktop or Discord, respond normally and conversationally unless structured JSON is explicitly requested.

Never assume automation mode merely because this skill is active.

## Missing required information

In interactive mode:
- ask Florian for the missing information.

In automation mode:
- do not ask a conversational question;
- set `needs_review: true`;
- set `confidence: "LOW"`;
- set `proposed_status: null`;
- explain the missing requirement in `reason`;
- put the required human action in `next_action`.

## Idempotency

Automation may retry.

- Never create duplicate application folders for the same `application_id`.
- If the application folder already exists, inspect it before writing.
- Never overwrite submitted artifacts.
- The same Gmail message must never produce two activity events: `add_activity` with `email_message_id` enforces this through `processed_messages`.
- Before `create_application`, check for an existing application (company + normalized position) so retries don't create duplicates.

## Output contract for n8n

{
  "application_id": null,
  "company": "",
  "job_title": "",
  "classification": "",
  "proposed_status": null,
  "confidence": "HIGH|MEDIUM|LOW",
  "needs_review": false,
  "reason": "",
  "draft_reply": null,
  "next_action": null,
  "artifacts": {
    "brief": null,
    "answers": null,
    "cover_letter": null,
    "posting": null
  }
}

- `classification`: an email class from the table above, or PREPARE / REVIEW / SKIP for job evaluation.
- `proposed_status`: one of the Statuses, or null.
- `confidence` is never HIGH when `needs_review` is true.
- `artifacts`: paths relative to `C:\Users\monte\JobAgent`, or null for files not created.

Example (preparation succeeded):

{
  "application_id": "APP-2026-0042",
  "company": "ABC Corp",
  "job_title": "Junior Full Stack Developer",
  "classification": "PREPARE",
  "proposed_status": "READY_TO_APPLY",
  "confidence": "HIGH",
  "needs_review": false,
  "reason": "Role is an early-career position and core requirements align with verified profile facts.",
  "draft_reply": null,
  "next_action": "Review the brief and cover letter, then submit with the standard resume.",
  "artifacts": {
    "brief": "applications\\APP-2026-0042\\brief.json",
    "answers": null,
    "cover_letter": "applications\\APP-2026-0042\\Florian_Monte_Cover_Letter_ABC.pdf",
    "posting": "applications\\APP-2026-0042\\posting.txt"
  }
}

Never perform an irreversible external action unless explicitly instructed by the user.
