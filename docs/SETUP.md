# Guided Windows setup

JobAgent is set up with a full-screen terminal wizard. It walks you through nine
steps, saves as you go, and never connects an account or turns on automation
until you tick that step's confirmation box.

## Before you start

- Windows with Microsoft Word, and Python 3.11 or newer.
- Your resume as a PDF or DOCX (or its text, ready to paste).
- Logins for Discord and Gmail, and a Hermes model you have already set up.
- About 30–45 minutes. You can stop at any step and pick up later.

The wizard checks for Node.js, npm, Docker and Hermes itself and links to their
installers, so you don't need them installed before you begin.

## Start the wizard

Open a terminal (Windows Terminal is best) in the JobAgent folder. Install the app
once into a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .
```

Then start the wizard:

```powershell
.venv\Scripts\jobagent setup
```

Run the same command to reopen it later, for example after installing something it
asked for. It picks up where you left off.

Keep the JobAgent folder where it is: the app is installed from it, so moving or
deleting the folder breaks the command.

## Using the wizard

```
 jobagent setup
┌ Steps ──────────┐┌──────────────────────────────────────────────┐
│ 01  Welcome     ││ 2 / 9  Computer                              │
│  >  Computer    ││                                              │
│ 03  Model       ││ Instructions, fields and buttons for this    │
│ ...             ││ step. Scrolls if it doesn't fit.             │
│                 ││                                              │
│ Tab  next item  │├──────────────────────────────────────────────┤
│ ...             ││ Status line: results and errors              │
└─────────────────┘└──────────────────────────────────────────────┘
                                   Back   Continue   Save & exit
```

- **Step list (left):** `>` marks the step you're on and `OK` marks steps whose
  checks have passed. Use the arrow keys and Enter to jump to a step.
- **Status line (bottom of the panel):** shows what the last action did.
  Problems start with `Error:` in amber and say what to fix.
- **Buttons:** the highlighted one on each step is the main action. A button
  ending in `↗` opens a web page in your browser.
- **Confirmation boxes:** anything that uses your model, reads your email, posts
  to Discord or schedules jobs has a checkbox. Read it, tick it with Space, then
  press the button below it.
- **Continue** only moves on once the step's check has passed. If it refuses,
  the status line says what's still missing.

| Key | Action |
|---|---|
| Tab / Shift+Tab | Next / previous field or button |
| Enter | Press the selected button |
| Space | Tick or untick a checkbox |
| Arrow keys | Choose a step in the step list |
| Alt+Right / Alt+Left | Next / previous step |
| Escape | Previous step |
| Ctrl+S | Save progress |
| Ctrl+Q | Save and exit |

Terminal size: 120×38 or larger is most comfortable. The wizard works down to
80×24; below 88 columns it hides the step list to make room, and the step name
stays at the top of the panel. Maximize the window if text feels cramped.

## Walkthrough

1. **Welcome:** an overview and the location of your workspace. Nothing to check.
2. **Computer:** detect Windows, Python, Node, npm, Docker, Hermes and Word. Start Docker
   Desktop before checking. Missing prerequisites have official installation links.
   Install project dependencies to install `docx` and initialize SQLite through
   `tools/job_db.py`. Existing tracker data is retained.
3. **Model:** show the configured Hermes model, review it, then verify it with a
   small request. If necessary, open Hermes setup from the wizard and authenticate
   there. Setup never stores provider keys. Resume extraction and sample generation
   use this model with tool access disabled and may incur provider charges.
4. **Resume:** enter a PDF/DOCX path or paste text. Scanned PDFs need pasted text.
   Extraction uses your model; review the editable YAML and confirm its facts.
   Original imports become `profile/Standard_Resume.pdf` or `.docx`. Pasted text
   uses the existing resume builder during verification. Facts go in
   `career-profile.yaml`, with selected facts in `standard-resume.json`.
5. **Preferences:** enter roles, seniority, locations, work arrangements and hard
   exclusions. Saving writes `profile/job-preferences.json`; generated job rules
   consult it before evaluating roles.
6. **Discord:** create or choose a private server. Add `hermes`, `job-inbox`,
   `ready-to-apply`, `job-review`, `applications`, `interviews`, `alerts`, and
   `job-tracker`. For each channel, create a webhook in Edit Channel → Integrations
   and paste its URL. Blank fields reuse existing values. The check reads webhook
   metadata; the sample post happens later. Use Hermes gateway setup to configure
   your bot, user allowlist, and server access. Enable Message Content Intent in
   the Discord Developer Portal and invite the bot with its required permissions.
7. **Gmail:** start/check n8n, then open localhost:5678. Create your n8n owner account
   and Gmail OAuth2 credential using the linked n8n guide. Import the two JSON
   workflows from `n8n/workflows/`, select your credential in their Gmail nodes,
   and publish both. Reuse existing workflows instead of importing duplicates.
   Keep the service bound to localhost; its webhooks return email content.
   Create the three `Job Search/...` labels shown in the wizard and Gmail filters
   for your job-board messages. Enter a narrow search for a harmless test email,
   choose Find test messages, and select one of the returned messages.
   Verification reads that message through both workflows.
8. **Verify:** explicitly authorize rechecking connections, model calls, Word
   conversion and a SAMPLE package post to `ready-to-apply`. Sample artifacts
   live under `output/setup/sample`, outside the real tracker. Verify your bot
   replies in Discord and check the chat confirmation box. Use `hermes gateway`
   in another terminal, or your existing Hermes background gateway, to run it.
9. **Automation:** review the model, timezone and schedules, then enable or finish
   without automation. Defaults are scans at 09:00/18:00, email checks every
   15 minutes and a report at 21:00. Setup installs personalized instructions and
   launcher scripts in Hermes, creates missing jobs paused, then enables them
   once all three exist. The selected model is pinned on the two reasoning jobs.
   Keep both Docker and the Hermes gateway running afterward.

## Resume and recovery

`output/setup/state.json` retains fields and the current step. It contains resume
text, so treat it as private. The repository allowlist excludes it from Git.
Credential inputs are deliberately not retained there: unfinished webhook inputs
must be pasted again. Browser credentials stay in the services that own them.

Each action reports failure without dumping command output or credentials. Retry
after correcting the indicated input/service. A timed-out Discord post may already
have arrived; check the channel before retrying. Retrying full verification may
create another versioned letter and post another clearly labeled sample.

Save and exit waits for an active operation to finish rather than interrupting a
file write. After an abrupt process termination, rerun setup: completed files are
reused or reported as conflicts, and existing scheduled jobs are inspected before
creating any more. Corrupt saved state is reported and never silently replaced.

Existing profile files, resume selections, webhook connections, skills and launcher
scripts are not silently replaced. A conflict asks you to review the file or use
a dedicated Hermes profile. Schedule/model conflicts likewise require review in
Hermes. Setup does not change the timezone of other Hermes jobs: the selected
timezone must match the active Hermes profile's configured timezone (or its local
timezone fallback). Review any timezone change and restart the gateway yourself.

The three source copies of the personal job-hunt skill are not edited by setup.
It renders a private personalized copy in `output/setup/runtime` and installs that
copy in the new user's Hermes profile. Scheduled instructions use the local
`tools/n8n_fetch.py` adapter, so they do not require a separately configured MCP
server to reach the two n8n workflows.

## Developer checks

```powershell
.venv\Scripts\python tools/test_setup.py
.venv\Scripts\python tools/test_n8n_fetch.py
.venv\Scripts\python tools/test_job_db.py
.venv\Scripts\python tools/cover_letter/test_cover_letter.py
```

The setup suite uses temporary workspaces and fake account services. It exercises
preservation, secret exclusion, workflow response validation, repeated activation,
and Textual keyboard navigation. It captures 120×38 and 80×24 terminal layouts as
SVG in `output/setup-preview`. Real OAuth, Discord delivery, Hermes model requests,
and gateway behavior are verified by the new user inside the wizard; offline tests
do not establish that those live connections work.
