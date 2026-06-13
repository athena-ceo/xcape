# xCape — Claude Code Project Instructions

<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

## What this is

xCape helps people find a new place to live (country / region / city) based on their
own criteria. FastAPI + Postgres backend, React + TypeScript + Tailwind frontend, all
in Docker compose. AI via the OpenAI Responses API (`gpt-5`) for web search and tools.
See `docs/xcape-requirements-high-level.md` and `docs/xcape-architecture-and-plan.md`.

## Proprietary software and copyright

This repository is **proprietary** to **Athena Decisions Systems SAS**. When creating or
substantially editing a project-owned source file, add the copyright notice near the top:

- Python / shell / YAML / Dockerfile: `# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.` + `# Proprietary and confidential — unauthorized copying or distribution is prohibited.`
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
| Backup DB | `./xcape.sh backup-db dev` |
| Reset DB (dev only) | `./xcape.sh reset-db dev` |

**Local dev URLs:** Frontend http://localhost:3030 · Backend http://localhost:8030 (docs at `/docs`).

**Production safety:** NEVER run `reset-db prod` or `clean prod`. xCape uses ports
**8030 (backend) / 3030 (frontend)** — distinct from golden-path's 8020/3020. Postgres is
not host-published in production.

## Conventions (same as golden-path)

- **Plan before executing** non-trivial changes; wait for confirmation.
- **No time estimates** — use scope signals (small/medium/large, low-risk, etc.).
- **No automatic commits or pushes** — only when the user explicitly says commit/push, and
  only after they confirm they validated locally.
- **Localize every user-visible string** in both `src/i18n/fr.ts` and `src/i18n/en.ts` via
  `useT()`. Default locale is French. Never hardcode UI strings; never use `lang === 'fr' ? …` ternaries.
- **Changelog discipline** — single canonical `CHANGELOG.md` at repo root.
- **Backend checklist** — ORM change ⇒ Alembic migration (idempotent) + constraint test;
  every new route has an auth dependency; no skipped tests (pass/fail only).
- **Phrase user-facing product questions in UX terms**, with one RECOMMENDED option.
