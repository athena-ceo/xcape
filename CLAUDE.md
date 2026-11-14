# xCape — Claude Code Project Instructions

<!-- Copyright (c) 2025–2026 Athena Decision Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

## What this is

xCape helps people find a new place to live (country / region / city) based on their
own criteria. FastAPI + Postgres backend, React + TypeScript + Tailwind frontend, all
in Docker compose. AI via the OpenAI Responses API (`gpt-5`) for web search and tools.
See `docs/xcape-requirements-high-level.md` and `docs/xcape-architecture-and-plan.md`.

## Proprietary software and copyright

This repository is **proprietary** to **Athena Decision Systems SAS**. When creating or
substantially editing a project-owned source file, add the copyright notice near the top:

- Python / shell / YAML / Dockerfile: `# Copyright (c) 2025–2026 Athena Decision Systems SAS. All rights reserved.` + `# Proprietary and confidential — unauthorized copying or distribution is prohibited.`
- TypeScript / JavaScript: `// Copyright …` (same text)
- CSS: `/* Copyright … */`  ·  HTML / Markdown: `<!-- Copyright … -->`

Do **not** add headers to `node_modules`, lockfiles, or vendored trees.

## Dev ops — use `./xcape.sh`

```bash
./xcape.sh <command> [environment] [options]
```

| Goal | Command |
|------|---------|
| Start stack | `./xcape.sh start dev` |
| Stop stack | `./xcape.sh stop dev` |
| Restart | `./xcape.sh restart dev` |
| Rebuild images | `./xcape.sh rebuild dev` |
| Status | `./xcape.sh status dev` |
| Logs | `./xcape.sh logs dev --follow` |
| Migrations | `./xcape.sh migrate dev` |
| Seed place DB | `./xcape.sh seed dev` |
| Read-only SQL (prod-safe) | `./xcape.sh psql prod "SELECT …"` (or `- < query.sql`) |
| Backup DB | `./xcape.sh backup-db dev` · `list-backups` |
| Restore rehearsal | `./xcape.sh restore-backup dev --latest --rehearse-into scratch` |
| Reset DB (dev only) | `./xcape.sh reset-db dev` |

**Local dev URLs:** Frontend http://localhost:3030 · Backend http://localhost:8030 (docs at `/docs`).

**Production safety:** NEVER run `reset-db prod` or `clean prod`. xCape uses ports
**8030 (backend) / 3030 (frontend)** — distinct from golden-path's 8020/3020. Postgres is
not host-published in production.

## Conventions

Harley's general way of working — plan before executing, the commit and push rules,
working on `main`, changelog discipline, no time estimates, no skipped tests, questions
phrased in UX terms — is in [`.claude/rules/general.md`](.claude/rules/general.md). That
file is a **generated copy** shared by every Athena project: never edit it here. Change
`general.md` in the `working-rules` repository, then run
`python3 ../working-rules/sync.py .`; `scripts/lint-working-rules.py` (CI) fails if the
copy was edited in place.

Specific to xCape:

- **Localized strings** live in `src/i18n/fr.ts` and `src/i18n/en.ts`, read via `useT()`.
  Default locale is French.
- **Backend checklist** — ORM change ⇒ Alembic migration (idempotent) + constraint test;
  every new route has an auth dependency.
- **The server is the source of truth.** No application data (profile, searches, candidates,
  places, chat) is kept in a browser store: each view fetches it and fetches again after a
  change. The only lasting client value is the sign-in token; the cached identity is re-read
  on load, and `isAdmin` only shows or hides controls — the server enforces every privilege.
- **AI-derived data about a country fills itself in on first view**, then is cached for
  everyone. Never a bulk run across all countries as a required step: most are never
  visited. A new AI-backed attribute goes into the existing generator and its `/generate`
  path, not a new script. The one exception is the visa finder, which ranks every country:
  computed once on dev and shipped in the seed (`criteria_evals_seed.json`).
- **Models:** research and scoring use `settings.openai_model`; chat and per-criterion
  evaluations use the smaller `settings.openai_chat_model`, with web search off in chat.
  Every call is logged in `AIQueryLog`.
- **Editing inside a JSON column needs a copy and a flag.** `custom_criteria`,
  `criteria_weights`, `filters` and `place.attributes` are plain JSON columns: an in-place
  edit is not seen, no UPDATE is sent and the change is silently lost. Deep-copy the value
  (`[dict(c) for c in col]`), assign it, and call `flag_modified(obj, "col")`.
