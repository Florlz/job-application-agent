# Application email processor

Runs every 15 minutes, but the model only wakes when the monitor lists new unprocessed emails (lines `message_id | date | from | subject` above). Use the job-hunt skill. Unattended run: do not ask questions.

1. Read: fetch the listed IDs with "JobAgent - Fetch Message Bodies" through MCP (`max_chars` 4000, at most 20 IDs per call). Skip any ID that `job_db.py message_processed` now reports as done.
2. Classify each email by content with the skill's email table (plus POSTING_EXPIRED). Newsletters, promos, hiring-day ads, connection invites and job alerts are OTHER.
3. Match each non-OTHER email to an application: posting ID, then company + normalized position, then thread (`email_thread_id` in activity_log). A Jobstreet "new activity in jobs you applied for" digest can concern several applications.
4. Update the database through `tools\job_db.py` only (source `email`):
   - APPLICATION_CONFIRMATION with no matching row: `create_application` with status APPLIED, `date_applied` = email date, `source`, `job_url`/`posting_id` if the email links the posting. With a matching FOUND / READY_TO_APPLY row: set APPLIED and `date_applied`.
   - Status changes per the table, HIGH confidence only; set `last_contact` = email date. For RECRUITER_SCREEN / ASSESSMENT / INTERVIEW / FINAL_INTERVIEW also set `interview_date` (YYYY-MM-DD HH:MM when given) and a one-sentence `next_action` (what to do, by when).
   - Follow-ups: when an employer or recruiter writes directly (not a job-board notification), set `recruiter` / `recruiter_email` and `follow_up_date` = 7 days after the email unless the email gives a timeline; follow the timeline if it does. POSTING_EXPIRED follows the skill (log only; 30-day follow-up if no later contact). Platform confirmations get no follow-up date.
   - Ambiguous classification or no confident match: never change a status; set `needs_review` 1 on the matched row, or create nothing and report it.
   - Recruiter questions and anything needing a reply: draft the reply (never send) to `C:\Users\monte\JobAgent\output\drafts\<APP-ID>-<YYYYMMDD>.md` and put "Reply drafted: output\drafts\…" in `next_action`.
   - `add_activity` for every application an email concerns, then `mark_message_processed` once per email (OTHER emails too, with no activity).
5. Post with `tools\discord_post.py` (skip empty posts; heading time is now):
   - `applications`: `📨 Application updates · <Mon D, H:MM AM/PM>`, IDs that became APPLIED / REJECTED / WITHDRAWN or got a POSTING_EXPIRED note.
   - `interviews`: `🗓️ Interviews & assessments · <…>`, IDs now in RECRUITER_SCREEN / ASSESSMENT / INTERVIEW / FINAL_INTERVIEW.
   - `alerts`: `🔔 Action needed · <…>`, OFFER, drafted replies, document requests, deadlines within 48 hours.
   - `job-review`: `⚠️ Needs review · <…>`, IDs you flagged `needs_review`.
   Unmatched emails you could not attach to any application: one `hermes send -t discord:job-review -f <file>` message, heading `## ⚠️ Unmatched emails`, one bullet each with date, sender and subject.
6. Final reply: one line, `done: N emails (A updated, B new, C other, D review)` or the error. It is not posted anywhere; failures are reported to #alerts automatically.

Never send emails, apply to jobs, or change a status on anything below HIGH confidence.
