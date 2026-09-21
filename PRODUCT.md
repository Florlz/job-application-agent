# JobAgent onboarding

## Platform and stack
Windows terminal; Python and Textual. Microsoft Word supplies PDF conversion.

## Users and purpose
New users setting up their own local job-search assistant. Success means a verified
Gmail → n8n → Hermes → Discord flow and an explicitly offered automation activation.

## Confirmed experience
One guided, resumable command. Keyboard-first full-screen wizard with boxed panels,
a step sidebar, Back/Next, retry, and Save and exit. Import PDF/DOCX or pasted resume
text, confirm facts, collect job preferences, and guide account setup in the browser.
Reuse existing connections and preserve settings. Show model and schedules before
activation. Sample packages stay outside the real application tracker.

## Boundaries
Drafts only; never submit applications or send email. Database writes use job_db.py.
Account connections, external verification posts, and automation activation require
explicit actions inside onboarding. Secrets must not appear in progress or logs.
