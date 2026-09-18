
# JobAgent operations

> Sanitized copy of the `jobagent-ops` Hermes skill: Discord channel IDs and usernames are replaced
> with placeholders. The live skill in the Hermes profile has the real values.


This is the maintenance manual for the job-search automation. The job-hunt skill says how to do the job work; this skill says how the machinery works and how to change it safely. Load both when changing anything.

## System map

```
Gmail (labels: Job Search/Application Updates, Job Search/Interviews & Offers, Job Search/Job Alerts)
  -> n8n in Docker (localhost:5678 only): fetches mail, never writes the database
  -> Hermes cron jobs (this profile): reason, write SQLite through tools\job_db.py, post to Discord
  -> Discord server "Job Applications": Florian reads and chats
Florian applies by hand with the standard resume. Nothing is ever sent or submitted automatically.
```

Workspace: `C:\Users\monte\JobAgent`. Hermes home: `C:\Users\monte\AppData\Local\hermes`.

## Scheduled jobs (hermes cron)

| ID | Name | Schedule | What it does | Model |
|---|---|---|---|---|
| `5a90ef02036e` | job-alert-scan | `0 9,18 * * *` | Reads Job Alerts emails, adds new jobs, posts to #job-inbox and #job-review. Instructions: `hermes\cron\job-alert-scan.md` | gpt-5.6-luna, xhigh (pinned) |
| `2f875a8e957d` | app-email-processor | `*/15 * * * *` with monitor script `app_email_monitor.py` | Handles confirmations, rejections, interviews, recruiter mail. The model only runs when the monitor output changes. Instructions: `hermes\cron\app-email-processor.md` | gpt-5.6-luna, xhigh (pinned) |
| `7cf54d188c98` | job-tracker-report | `0 21 * * *`, no agent | Runs `tools\tracker_report.py`, which posts the nightly #job-tracker card itself | none |

- Both agent jobs deliver `local` (their own posts go through the formatter) and send failures to #alerts (`discord:<channel-id>`).
- The prompt of each agent job is one line: "Read <instructions file> and follow it exactly." To change behavior, edit the `.md` file; the next run uses it. No need to recreate the job.
- "prepare APP-…" and "cover letter APP-…" run as one-time jobs (`--repeat 1`, name `prepare-<APP-ID>` / `letter-<APP-ID>`). Delete them with `hermes cron remove <id>` after they complete.
- A paused job cannot be run manually (`hermes cron run` refuses). For a test, create a one-time copy (`"1m"`, `--repeat 1`) instead of resuming the real one.
- `hermes cron list` hides paused and finished jobs; use `hermes cron list --all`. `hermes cron runs <id>` shows run history. `hermes cron list` does not show pinned models; read `cron\jobs.json` (fields `model`, `provider`, `reasoning_effort`) or the gateway log line "using per-job reasoning_effort".
- Scripts for cron must live in `<hermes home>\scripts\`. Ours are launchers that run the real files in `JobAgent\tools`: `job_tracker_report.py`, `app_email_monitor.py`.

## n8n workflows (Docker container `jobagent-n8n`, compose file `JobAgent\n8n\docker-compose.yml`)

| ID | Name | Trigger | Purpose |
|---|---|---|---|
| `TnPHCUdySQDQIYAg` | JobAgent - Backfill Fetch | Webhook `POST /webhook/jobagent-backfill-fetch` | Gmail metadata for a list of queries. Body `{"queries": [...], "after"?, "before"?}`. Runs queries one at a time with a 15 s pause (Gmail quota). |
| `O7KjbAJv8zDAi1vz` | JobAgent - Fetch Message Bodies | Webhook `POST /webhook/jobagent-fetch-bodies` | Body text and links for up to 20 message IDs. Body `{"message_ids": [...], "max_chars"?: 1500..8000}` |
| `JobAgentGmailTst` | JobAgent - Gmail Fetch Test | Manual | Original read-only test; unused |

- Hermes reaches n8n through the `n8n-mcp` MCP server (Desktop and cron only; Discord chat has MCP turned off). MCP can only execute published workflows with a webhook, form, schedule or chat trigger.
- The port is bound to `127.0.0.1:5678`, so only this PC can reach n8n. Keep it that way; the webhooks return Florian's email.
- Gmail credential "Gmail account" uses a Google Cloud OAuth app. While that app is in Testing mode, Google expires the login every 7 days and all fetching silently stops. Fix: Google Auth Platform -> Audience -> Publish app, then reconnect the credential in n8n.
- Gmail search: `before:` is exclusive (use tomorrow's date to include today). Use Simplify = true for listing; full bodies only through Fetch Message Bodies, or Gmail's per-minute quota trips.

## Database

`JobAgent\data\job-hunt.db` (SQLite). Only `tools\job_db.py` writes it; the job-hunt skill lists its commands. Tables: `applications`, `activity_log`, `processed_messages`, `app_sequence`. A CHECK constraint allows only the 12 statuses; a unique index stops the same email being logged twice for one application.

Snapshots: `job-hunt.pre-backfill.db` (empty), `job-hunt.post-backfill.db` (123 imported), `job-hunt.pre-app-processor.db`. Before any risky change, snapshot with Python's `sqlite3` `backup()` (safe while in use), not a file copy.

## Tools (`JobAgent\tools`)

| File | Purpose | Test |
|---|---|---|
| `job_db.py` | Database helper CLI (JSON output) | `python test_job_db.py` |
| `discord_post.py` | Posts job cards, cover letters and application packages to Discord | `python test_discord_post.py` |
| `tracker_report.py` | Nightly #job-tracker card (read-only) | run with `--dry-run` |
| `app_email_monitor.py` | Cheap check for new application emails (read-only) | run directly |
| `cover_letter\make_cover_letter.py` | Validates a cover letter draft and builds MD/DOCX/PDF | `python test_cover_letter.py` (needs Word) |
| `cover_letter\build_cover_letter.js` | DOCX layout (letterhead colors: `INK`, `ACCENT` at the top) | via the test |
| `resume\build_resume.py` + `build_resume.js` | Builds the standard resume from the profile (one page enforced) | run it; it exits 1 if not one page |

Run the matching test after every change. Node packages (`docx`) are in `tools\node_modules`. PDFs are made by Microsoft Word through COM, so cover letters only build on this PC.

Removed on purpose: per-job tailored resumes and the Indeed MCP (Indeed's OAuth only accepts clients it has approved; Hermes gets `invalid_client`). Florian applies with one standard resume, `profile\Florian_Monte_Resume.pdf`; `profile\standard-resume.json` lists what is on it, and cover letters may only claim those facts.

Rebuilding the standard resume (only after Florian approves a change to the facts or layout):
1. Edit the facts in `profile\career-profile.yaml` (and `standard-resume.json` if bullets are added, removed or reordered; each bullet must match a verified fact exactly).
2. `python tools\resume\build_resume.py` builds a preview in `output\resume-preview\` and fails unless it is exactly one page. Layout knobs are `LAYOUT` at the top of `build_resume.py`; colors and fonts are in `build_resume.js`.
3. Show Florian the preview (e.g. post both files to #hermes). After approval, copy the preview files over `profile\Florian_Monte_Resume.pdf` and `.docx`. Florian prefers replacing the old version to keeping it.
4. Run `tools\cover_letter\test_cover_letter.py`; cover letters check claims against `standard-resume.json`.

## Discord

Server "Job Applications". Bot user `<bot-user>`; webhook posts appear as "JobAgent".

| Channel | ID | Receives |
|---|---|---|
| #hermes | <channel-id> | Chat with Hermes (no @mention needed) |
| #alerts | <channel-id> | Offers, recruiter questions, deadlines, cron failures |
| #interviews | <channel-id> | Screens, assessments, interviews |
| #job-review | <channel-id> | Anything with needs_review |
| #job-inbox | <channel-id> | Every new job from the scans (the only place new jobs go) |
| #ready-to-apply | <channel-id> | Finished application packages and cover letters only |
| #applications | <channel-id> | Confirmations, rejections, withdrawals, closed postings |
| #job-tracker | <channel-id> | Nightly report |

- Webhook URLs are secrets in `JobAgent\secrets-discord.json` (keys = channel names). Never print or paste them.
- Channel names are referenced by `hermes send -t discord:<name>` (text fallback, unmatched emails). Renaming a channel breaks those; switch them to IDs first.
- Gateway settings in `config.yaml` (set with `hermes config set`; the CLI warns "not a recognized key" for some valid keys, ignore it):
  - `discord.free_response_channels: <channel-id>`, `discord.require_mention: true`
  - `discord.allow_from` / `discord.group_allow_from: [<your-discord-username>]` (only Florian)
  - `platform_toolsets.discord: [terminal, file, web, skills, memory, session_search, clarify, todo, discord]` (no MCP, no cron, no browser)
  - `platforms.discord.channel_overrides.<channel-id>.system_prompt` (loads job-hunt)
  - `display.platforms.discord.tool_progress: false` (no terminal blocks in chat)
  - `model.default: gpt-5.6-luna`, `agent.reasoning_effort: xhigh`
- After gateway config changes: `hermes gateway restart` (check nothing is mid-run first with `hermes cron runs <id>`), then confirm "discord connected" in `logs\gateway.log`.

## Profile files (`JobAgent\profile`)

`career-profile.yaml` (verified facts; the only source of truth about Florian), `standard-resume.json`, `Florian_Monte_Resume.pdf`/`.docx` (built by `tools\resume\build_resume.py`), `answer-bank.yaml`, `resume-template.docx` (the first layout, superseded). Setup script: `Downloads\JobAgent-Starter\JobAgent-Starter\setup.ps1` never overwrites profile files.

This skill has a backup at `JobAgent\hermes\skills\jobagent-ops\SKILL.md`; copy it there after edits.

The job-hunt skill exists in three copies; edit the live one and copy it to the other two:
- live: `<hermes home>\skills\productivity\job-hunt\SKILL.md`
- copies: `JobAgent\hermes\skills\job-hunt\SKILL.md`, `Downloads\JobAgent-Starter\JobAgent-Starter\hermes\skills\job-hunt\SKILL.md`

## How to change things safely

1. Snapshot the database if the change touches data.
2. Change the smallest thing: an instructions `.md`, a skill section, or one tool.
3. Run the tool's test. For cron behavior, create a one-time test job rather than resuming or editing the live schedule blindly.
4. Check the result in the database (read-only query) and in Discord.
5. Sync the skill copies.
6. Tell Florian what changed and what will look different.

Confirm with Florian before: deleting jobs, rows or files; changing schedules or models; anything that posts outside the job channels; anything touching Gmail, OAuth or secrets.

## Troubleshooting

| Symptom | Check |
|---|---|
| No posts at all | `hermes gateway status`; `hermes cron status` ("Ticker heartbeat" should be seconds old); Docker running (`docker ps`) |
| Scan or processor fetches nothing | n8n up (`curl http://localhost:5678/healthz`), Gmail credential expired (Testing mode, see above), workflows still published |
| Error posts in #alerts | `hermes cron runs <id>`, then `logs\gateway.log` and `logs\agent.log` |
| Emails processed twice / never | `processed_messages` table; the monitor prints unprocessed IDs (`python tools\app_email_monitor.py`) |
| Discord bot silent in chat | `logs\gateway.log` for "discord connected"; allowlist `discord.allow_from`; channel ID in `free_response_channels` |
| Cover letter fails validation | Read its `errors`; it rejects numbers, technologies and facts not on the standard resume, and lengths outside 250-320 words |
| Token use too high | Lower effort: `hermes cron edit <id> --reasoning-effort medium` |

Shell notes on this PC: Git Bash rewrites `/tmp/...` paths passed to `docker exec`; prefix with `MSYS_NO_PATHCONV=1`. PowerShell 5.1 re-encodes files it rewrites; edit files with the file tool, not `Get-Content | Set-Content`. Python heredocs in Git Bash can lose backslashes; write scripts to a file first.

## Open items

- Publish the Gmail OAuth app (Testing mode expires logins every 7 days).
- Optional: OpenCode Zen key (`hermes auth add opencode-zen --type api-key`) if a second provider is wanted.
- A few backfill rows were never imported (missing company or position).
- Florian wants more Indeed coverage via Indeed saved-search email alerts (no API access).
