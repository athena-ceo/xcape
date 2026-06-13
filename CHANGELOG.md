<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# Changelog

## [Unreleased]

### 2026-06-13 — Project scaffold

- Architecture & plan document (`docs/xcape-architecture-and-plan.md`).
- Backend: FastAPI app, SQLAlchemy models (user, profile, search, place, candidate,
  media, chat, ai_log), Pydantic schemas, JWT auth (bcrypt), API v1 routers
  (auth, profile, search, candidates, places, chat, voice, admin), services
  (ai_client, shortlist, chat, place_research), Alembic setup + initial migration,
  bundled place seed data (12 countries + regions), pytest suite (6 passing).
- Frontend: Vite + React + TS + Tailwind, bilingual FR/EN i18n (default FR), turquoise
  theme, auth store, API client, pages (Home, Login, Register, Onboarding, Shortlist,
  Comparison playground, Admin), VoiceInput component.
- Ops: `xcape.sh`, dev + server Docker compose, external nginx example, env template.
  Ports 8030 (backend) / 3030 (frontend).
