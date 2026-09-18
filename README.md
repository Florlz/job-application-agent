# Job Application Agent

A local-first job search assistant. It reads job alerts and application emails from Gmail, keeps a tracker of every application in SQLite, writes fact-checked cover letters, and reports everything in a private Discord server. I review and submit every application myself; the agent never sends an email or submits a form.

Built on [Hermes Agent](https://hermes-agent.nousresearch.com) (scheduling, reasoning, Discord chat) and [n8n](https://n8n.io) (Gmail access), running on one Windows PC.

## What it does

- **Finds jobs.** Twice a day it reads LinkedIn, Indeed and Jobstreet alert emails, skips duplicates, and sorts each job into prepare, check posting, review, or skip against my verified profile.
- **Tracks applications.** Every 15 minutes it checks for confirmations, rejections, interview invites and recruiter replies, and updates the tracker. A cheap script checks for new mail first, so the model only runs when there is something to process.
- **Prepares applications on request.** "prepare APP-2026-0164" in Discord produces an application brief (why I fit, skills to highlight, gaps, things to check) and a tailored cover letter, posted with the files attached.
- **Keeps me honest.** A validator rejects any cover letter that cites a fact, number or technology that is not on my resume. Company details must be quoted from the posting or the company's own site.
- **Reports in Discord.** New jobs, packages, interviews, action items and a nightly tracker summary each go to their own channel, as structured cards.
- **Chat.** I can ask it things in a Discord channel: "what's due?", "close APP-0034", "I applied to APP-0147".

## How it fits together

```
Gmail (filtered labels)
  │  Gmail API (OAuth)
  ▼
n8n in Docker ── webhook workflows: fetch metadata, fetch bodies + links
  │  MCP / localhost webhooks
  ▼
Hermes cron jobs ── reasoning (LLM), rules in skills
  │  tools/job_db.py (only writer)        tools/discord_post.py
  ▼                                       ▼
SQLite job tracker                     Discord (webhooks + bot)
```

| Job | Schedule | Model |
|---|---|---|
| Job alert scan | 9:00 and 18:00 | yes |
| Application email processor | every 15 min, model runs only when new mail exists | yes |
| Tracker report | 21:00 | no, plain script |

Design choices:
- **One writer.** Only `tools/job_db.py` writes the database. n8n only fetches mail.
- **Rules as data, tools as code.** The agent's judgment lives in two skills (`hermes/skills/job-hunt`, `docs/OPERATIONS.md`); anything that must be exact (IDs, deduplication, formatting, validation, PDFs) is a tested script.
- **Idempotent email handling.** Each Gmail message is processed once; a digest email can update several applications.
- **Human in the loop.** Drafts only. Applications and emails are always sent by me.

## Repository layout

| Path | Contents |
|---|---|
| `tools/job_db.py` | SQLite helper CLI: IDs, applications, activity log, processed messages, follow-ups, backfill import |
| `tools/discord_post.py` | Discord cards: job lists grouped by stage, application packages, cover letters with attachments |
| `tools/tracker_report.py` | Nightly tracker card (no LLM) |
| `tools/app_email_monitor.py` | Cheap check that decides whether the email processor needs the model |
| `tools/cover_letter/` | Cover letter validator and builder (DOCX + PDF) |
| `tools/resume/` | Builds the one-page standard resume from the profile |
| `hermes/skills/job-hunt/` | The agent's rules for job work |
| `hermes/cron/` | Instructions each scheduled job follows |
| `hermes/scripts/` | Launchers the Hermes scheduler runs |
| `n8n/` | Docker Compose and the Gmail workflows |
| `docs/OPERATIONS.md` | Maintenance manual: every job, workflow, channel and setting, plus troubleshooting |
| `profile/*.example.*`, `secrets-discord.example.json` | Example config with a fictional person |

Not in this repository, on purpose: my job database, emails, applications, cover letters, resume, profile, and webhook secrets.

## Running it yourself

You need Windows with Microsoft Word (for PDFs), Python 3 with PyYAML, Node.js, Docker, and Hermes Agent.

1. Copy `profile/career-profile.example.yaml` to `career-profile.yaml` and `standard-resume.example.json` to `standard-resume.json`, then fill in your own facts.
2. `cd tools && npm install` (installs `docx`).
3. `python tools/job_db.py init` creates the database.
4. `docker compose -f n8n/docker-compose.yml up -d`, connect a Gmail credential, and import the workflows from `n8n/workflows/`.
5. Install the `job-hunt` skill in Hermes, create the cron jobs described in `docs/OPERATIONS.md`, and point them at `hermes/cron/*.md`.
6. Create Discord webhooks and put them in `secrets-discord.json` (see the example).

## Tests

```
python tools/test_job_db.py
python tools/test_discord_post.py
python tools/test_app_email_monitor.py
python tools/cover_letter/test_cover_letter.py   # needs Word and a profile
```
