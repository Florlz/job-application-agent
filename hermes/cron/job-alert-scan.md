# Job alert scan

Scheduled run (9:00 and 18:00 Asia/Manila). Use the job-hunt skill. This is an unattended run: do not ask questions; report anything missing or failing instead.

1. Fetch: call the n8n workflow "JobAgent - Backfill Fetch" through MCP with body
   `{"queries": ["label:\"Job Search/Job Alerts\" newer_than:2d"]}`.
2. Filter:
   - Drop messages already processed (`job_db.py message_processed <id>`).
   - Discovery only. Leave application-event emails (Jobstreet "successfully submitted", "job has closed", application updates) untouched and unprocessed; they are handled by a separate job.
3. Read jobs: fetch every new alert with "JobAgent - Fetch Message Bodies" (`max_chars` 8000, at most 20 IDs per call). Use `body_text` for the jobs and `links` for each job's URL; every stored job needs a `job_url` unless its email has no link for it.
4. Apply the skill's "Job alert discovery" rules: dedupe against the database (posting ID first), evaluate against `profile\career-profile.yaml` (title-only alerts without senior wording are FOUND "Check posting", not REVIEW), write through `tools\job_db.py` only, and mark each alert email processed after all its jobs are logged. Keep each row's `notes` to one clear sentence.
5. Post with `tools\discord_post.py` (see the skill's "Discord posting"), skipping any post with no jobs:
   - `job-inbox`: heading `🆕 Job alerts · <Mon D, H:MM AM/PM>`, `--summary "**N new** · A prepare · B check · C review · D skipped · E already known"`, all new job IDs.
     If there were no new alert emails, post the heading with `--summary "Nothing new."` and no IDs.
   - `job-review`: heading `⚠️ Needs review · <Mon D, H:MM AM/PM>`, the new REVIEW job IDs.
   - Never post new jobs to `ready-to-apply`; that channel is only for finished application packages.
6. Final reply: one line, `done: N new` or the error. It is not posted anywhere; failures are reported to #alerts automatically.

Never apply to jobs, send emails, or change statuses of existing applications in this run.
