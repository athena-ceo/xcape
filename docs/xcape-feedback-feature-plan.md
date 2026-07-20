<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape — Feedback Feature Plan (phased)

> Status: **Phase 1 approved, not yet implemented** (agreed 2026-07-20). This document is the
> hand-off spec so any dev machine can pick the work up.

## Goal

Let users report bugs, wishes and general comments from inside the app, and give admins a
managed backlog of that feedback. Rolled out in two phases.

## Reference implementation — copy from golden-path

The sibling repo **golden-path** already implements this whole feature and the Scaleway
Transactional Email (TEM) transport. Mirror it, adapting to xcape's simpler conventions
(integer PKs + `Base`; `AppConfig` key→JSON for admin settings; `is_admin` rather than a role
enum). Key files to read there:

- `backend/app/models/user_feedback.py` — the audit-style feedback table (snapshots, no FK).
- `backend/app/schemas/feedback.py` — submit DTO + admin list/detail/patch schemas.
- `backend/app/api/v1/endpoints/feedback.py` — submit + admin list/triage endpoints.
- `backend/app/services/feedback_contact.py` — DB-override → env-default recipient resolver.
- `backend/app/services/tem_transport.py` — the Scaleway TEM REST client (Phase 2).

**Note:** xcape has **no email infrastructure of its own** today — only golden-path does.

## Phase 1 — build this first (signed-in users submit, admins triage, NO email)

Any signed-in user submits feedback; admins view and triage it. **No email is sent** — the
entire Scaleway TEM piece is deferred to Phase 2.

### Backend

- **`Feedback` model + Alembic migration `0028`** (idempotent, matching the `0025`/`0027`
  add-column style). Columns:
  - `user_id` — nullable, **no foreign key** so a note stays legible after the user is deleted;
    plus `submitter_email` / `submitter_name` snapshots for the same reason.
  - `category` — one of `bug` | `idea` | `comment` | `other`.
  - `message` — required text (min length 1; cap ~5000 chars to blunt oversize pastes).
  - Context for triage: `page_path` (SPA route), `locale`, `user_agent`.
  - `status` — `new` → `triaged` → `resolved`, default `new`.
  - `admin_note` — nullable.
  - `created_at` / `updated_at`; index on `(status, created_at)` for the newest-first admin list.
- **Routes:**
  - `POST /api/v1/feedback` (`get_current_user`) — persist the row only. No email in Phase 1.
  - `GET /api/v1/admin/feedback` (`require_admin`) — newest-first, filter by `status`.
  - `PATCH /api/v1/admin/feedback/{id}` (`require_admin`) — update `status` and/or `admin_note`.

### Frontend

- **`FeedbackDialog.tsx`** — model on `src/components/HelpDialog.tsx`. Opened from a "Feedback"
  action in `src/components/Header.tsx`, visible to **all signed-in users**. Fields: category
  chips (bug / idea / comment), a message field via `VoiceField` (dictation, like elsewhere in
  the app), submit + success toast. Silently attaches `page_path` (current route) and `locale`.
- **New `feedback` admin tab** in `src/pages/AdminDashboard.tsx` (its tabs are
  users/searches/places/ailog/criteria/personas — add `feedback`). A sortable list (date, user
  email, category, status, message excerpt) with an expand for the full message + captured
  context, plus inline status change and admin-note editing.
- **i18n** — every user-visible string in BOTH `src/i18n/fr.ts` and `src/i18n/en.ts` (default
  locale French; no hardcoded strings).

### Tests + conventions

- Backend: submit persists a row and rejects a blank message; `GET`/`PATCH` admin routes are
  403 for non-admins; status/note PATCH round-trips; a migration/table test.
- Copyright headers on new files; a `CHANGELOG.md` entry. Prod just needs `migrate`.

## Phase 2 — later (email notifications; additive, no Phase 1 rework)

Port golden-path's TEM transport and notify the designated contact after a feedback row is saved.

- **`app/services/mailer.py`** — port `tem_transport.send_tem_email_sync`: httpx `POST` to
  `https://api.scaleway.com/transactional-email/v1alpha1/regions/{region}/emails` with header
  `X-Auth-Token: <Scaleway IAM secret>`, retry/backoff on transient failures. `send_email(...)`
  is a **no-op when disabled/unconfigured**, so dev and tests never send.
- **Config** (`config.py` + `.env.example`): `email_enabled` (default False), `email_from`,
  `email_from_name` (default "xCape"), `scaleway_secret_key`, `scaleway_project_id`,
  `scaleway_region` (`fr-par`), `feedback_contact_email` (default
  **feedback@athenadecisions.com**); accept `SCW_*` env aliases like golden-path.
- **Admin-overridable recipient** in `AppConfig['feedback'] = {"recipient": …}` (xcape's
  key→JSON admin-settings pattern, in place of golden-path's `PlatformSettings`); resolver is
  DB override → env default. Add `GET`/`PUT /api/v1/admin/feedback/recipient`.
- After persisting the feedback row, fire a **best-effort** notification via FastAPI
  `BackgroundTasks`, stamping `notified_at` / `notify_error` on the row for visibility. The DB
  row remains the source of truth — a mail failure must never lose the feedback.
- **Deliberate simplification:** use the lightweight best-effort background send, **not**
  golden-path's durable `EmailOutbox` + async worker. Tradeoff: no automatic retry/queue for a
  failed send (the in-app backlog is unaffected).
- Prod Phase 2 also needs the Scaleway env vars set and a **verified** `EMAIL_FROM` sender.
