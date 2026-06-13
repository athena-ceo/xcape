<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape

Help people find a new place to live — country, region, city — based on their own
criteria, using a built-in place database plus AI and web search.

- Requirements: [`docs/xcape-requirements-high-level.md`](docs/xcape-requirements-high-level.md)
- Architecture & plan: [`docs/xcape-architecture-and-plan.md`](docs/xcape-architecture-and-plan.md)

## Stack

- Backend: Python FastAPI + SQLAlchemy + Alembic, Postgres
- Frontend: TypeScript + React + Vite + Tailwind (bilingual FR/EN, default FR)
- AI: OpenAI Responses API (`gpt-5`), web search, cache-first
- Docker compose; ports **8030** (backend) / **3030** (frontend) — distinct from golden-path

## Quick start (dev)

```bash
cp env.example .env          # add OPENAI_API_KEY if you want AI features
./xcape.sh start dev         # builds + starts db, backend, frontend
./xcape.sh migrate dev       # apply schema
./xcape.sh seed dev          # load the bundled place database
```

- Frontend: http://localhost:3030
- Backend API + docs: http://localhost:8030/docs

## Production deploy (apps.athenadecisions.com)

Served path-based at `https://apps.athenadecisions.com/xcape` (containers: frontend 3030,
backend 8030 — no collision with golden-path's 3020/8020).

1. One-time: paste the location blocks from [`nginx/xcape-apps-location.conf`](nginx/xcape-apps-location.conf)
   into the `apps.athenadecisions.com` server block in
   `/etc/nginx/sites-available/apps.athenadecisions.com`, then `sudo nginx -t && sudo systemctl reload nginx`.
2. Create a prod `.env` (see `env.example`) with `SECRET_KEY`, `POSTGRES_PASSWORD`,
   `OPENAI_API_KEY`, and `ENVIRONMENT=production`.
3. Deploy:

```bash
./xcape.sh deploy prod    # pre-deploy backup, git pull, build, up, migrate, seed, health check
```

To move to a dedicated subdomain later (`xcape.athenadecisions.com`), use
[`nginx/xcape.conf.example`](nginx/xcape.conf.example) and set `XCAPE_BASE_PATH=/` +
`PUBLIC_URL=https://xcape.athenadecisions.com` in the prod `.env` before deploying.

## Backend tests

```bash
./xcape.sh test dev
# or locally: cd backend && python -m pytest tests -q
```

## CI

Every push and PR to `main` runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml):
backend pytest, frontend type-check + build, and an end-to-end Docker smoke test. Run
the smoke test locally against a running stack with `./xcape.sh smoke dev` (it also
gates `deploy prod`).

## Status

Scaffold complete and verified: auth, profile, instant seed-driven shortlist, and the
core screens render. AI layer (discriminator questions, on-demand research, media, chat,
voice), the full onboarding flow, and the admin dashboard are the next build phases —
see plan §8.
