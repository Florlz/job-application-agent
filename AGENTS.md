# JobAgent workspace

This folder is Florian's job-search system. Before doing anything here, load two skills:

- `jobagent-ops`: how the system is built and how to change, test and troubleshoot it (cron jobs, n8n workflows, Discord channels, database, tools).
- `job-hunt`: how to do the job work itself (evaluating jobs, "prepare", cover letters, email handling, posting to Discord).

Ground rules:
- Write the database only through `tools\job_db.py`.
- Never submit applications or send email; drafts only.
- Never print the contents of `secrets-discord.json`.
- Run the matching test in `tools\` after changing a tool, and keep the three copies of the job-hunt skill in sync.
- Ask Florian before deleting data, changing schedules or models, or touching Gmail/OAuth.

Layout:
- `data\` job-hunt.db and snapshots
- `profile\` verified facts, standard resume, answer bank
- `applications\APP-…\` posting, brief, cover letters
- `tools\` scripts and their tests
- `hermes\cron\` instructions read by the scheduled jobs
- `hermes\skills\` backup copies of the skills
- `n8n\` docker-compose and workflow exports
- `output\` backfill previews, drafts, set-aside files
