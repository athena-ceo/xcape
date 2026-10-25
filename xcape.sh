#!/usr/bin/env bash
# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
#
# xCape dev-ops wrapper. Usage: ./xcape.sh <command> [dev|prod] [options]

set -euo pipefail
cd "$(dirname "$0")"

CMD="${1:-help}"
shift || true

# --- Environment selection -------------------------------------------------------------
# The default follows the machine: prod on the server, dev everywhere else. golden-path
# learned this the hard way — with a dev default on the server, `./xcape.sh stop` ran the dev
# compose file under the SAME project name as prod and took prod down.
if [[ "$(hostname 2>/dev/null)" == "apps.athenadecisions.com" ]]; then
  DEFAULT_ENV="prod"
else
  DEFAULT_ENV="dev"
fi
EXPLICIT_ENV=false
case "${1:-}" in
  dev) ENV="dev"; EXPLICIT_ENV=true; shift ;;
  prod|server) ENV="prod"; EXPLICIT_ENV=true; shift ;;
  ""|-*) ENV="$DEFAULT_ENV" ;;  # no env given (flags such as --follow are not an env)
  *)
    if [[ "$CMD" != "help" ]]; then
      echo "Unknown environment '$1' — use dev or prod: ./xcape.sh $CMD <dev|prod> ..." >&2
      exit 1
    fi
    ENV="$DEFAULT_ENV" ;;
esac

# Commands that change or remove data/services must name the environment, so nobody hits
# prod by omission on the server.
case "$CMD" in
  stop|restart|rebuild|migrate|makemigration|seed|reseed|rescore|dedupe-places|make-admin|reset-password|purge-test-users|backup-db|reset-db)
    if [[ "$EXPLICIT_ENV" != true ]]; then
      echo "$CMD needs an explicit environment: ./xcape.sh $CMD <dev|prod> ..." >&2
      echo "(on this machine the default would be '$DEFAULT_ENV')" >&2
      exit 1
    fi ;;
esac

# Distinct compose project per environment: dev and prod share service names (db, backend),
# so under one project name a dev `down` removes the prod containers. Prod keeps the project
# name it has always run under (`xcape`); dev is `xcape-dev` (its volumes keep their names —
# see docker-compose.dev.yml).
if [[ "$ENV" == "prod" ]]; then
  COMPOSE="docker compose -p xcape -f docker-compose.server.yml"
else
  COMPOSE="docker compose -p xcape-dev -f docker-compose.dev.yml"
fi
BACKEND_SVC="backend"

# Load the checkout-local .env FIRST, then the system env file (outside any git checkout), so
# the system file wins: on the server, /etc/xcape/environment carries XCAPE_DATA_ROOT — the
# absolute, persistent data root the prod compose binds Postgres into (see
# docs/xcape-prod-data-migration.md). A stray value in a checkout's .env must not override it,
# or a second clone could bring the stack up against an empty ./data and silently
# re-initialize an empty database.
[[ -f .env ]] && set -a && . ./.env && set +a || true
[[ -f /etc/xcape/environment ]] && set -a && . /etc/xcape/environment && set +a || true

# One-time move for dev checkouts that predate the xcape-dev project name: their containers
# still belong to project `xcape`. Never on the server, where `xcape` IS prod.
if [[ "$ENV" == "dev" && "$DEFAULT_ENV" == "dev" ]] \
   && [[ -n "$(docker ps -aq --filter label=com.docker.compose.project=xcape --filter name=frontend-dev 2>/dev/null)" ]]; then
  echo "Note: your dev containers still run under the old compose project 'xcape'." >&2
  echo "      Move them once (data volumes are kept):" >&2
  echo "        docker compose -p xcape -f docker-compose.dev.yml down && ./xcape.sh start dev" >&2
fi

# psql / pg_dump use the credentials the db container itself was started with, so they work
# in every environment without matching defaults here.
db_sh() { $COMPOSE exec -T db sh -c "$1"; }

container() { $COMPOSE ps -q "$1"; }

# Dump a Postgres backup, then raise a loud alarm (and a non-zero status) if the new dump is
# less than half the size of the previous one — the signature of an accidental empty-DB dump
# (e.g. compose mounted the wrong/empty data dir). golden-path's prod incident went unnoticed
# for days precisely because a collapsed dump still passed a naive "not empty" check.
#   $1 = destination .sql path   (writes to the file, returns non-zero on a size collapse)
backup_db_to() {
  local dest="$1" prev new
  # Previous NON-EMPTY dump: a 0-byte file from a failed run must not disarm the alarm below.
  prev="$(find backups -maxdepth 1 -name '*.sql' -size +0 ! -path "$dest" -print 2>/dev/null \
          | xargs ls -1t 2>/dev/null | head -n1 || true)"
  # Callers use `backup_db_to ... || abort`, which disables `set -e` in here — check explicitly.
  if ! db_sh 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$dest"; then
    rm -f "$dest"
    echo "pg_dump FAILED — no backup written." >&2
    return 1
  fi
  new="$(wc -c < "$dest" | tr -d ' ')"
  echo "Wrote ${dest} (${new} bytes)"
  if [[ "$new" -eq 0 ]]; then
    rm -f "$dest"
    echo "pg_dump produced an EMPTY dump — removed it." >&2
    return 1
  fi
  if [[ -n "$prev" && -f "$prev" ]]; then
    local prevsize; prevsize="$(wc -c < "$prev" | tr -d ' ')"
    if [[ "$prevsize" -gt 0 && $(( new * 2 )) -lt "$prevsize" ]]; then
      echo "" >&2
      echo "!!! BACKUP SIZE-COLLAPSE ALARM !!!" >&2
      echo "    New dump ${dest} is ${new} bytes — less than HALF of the previous" >&2
      echo "    dump ${prev} (${prevsize} bytes)." >&2
      echo "    This is the signature of an empty/wrong database being dumped (e.g. compose" >&2
      echo "    mounted a stray ./data instead of XCAPE_DATA_ROOT). Do NOT trust this dump." >&2
      echo "    Investigate before deploying or rotating backups." >&2
      return 1
    fi
  fi
}

case "$CMD" in
  start)    $COMPOSE up -d "$@" ;;
  stop)     $COMPOSE down "$@" ;;
  restart)  $COMPOSE down && $COMPOSE up -d "$@" ;;
  rebuild)  $COMPOSE build "$@" && $COMPOSE up -d ;;
  status)   $COMPOSE ps "$@" ;;
  logs)
    # ./xcape.sh logs [env] [--follow] [--service NAME] [--tail N] [--since 1h]
    LOG_ARGS=(--tail 200); SVC=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --follow|-f) LOG_ARGS+=(-f) ;;
        --service=*) SVC="${1#--service=}" ;;
        --service) SVC="${2:-}"; shift ;;
        --tail=*) LOG_ARGS[1]="${1#--tail=}" ;;
        --tail) LOG_ARGS[1]="${2:-200}"; shift ;;
        --since=*) LOG_ARGS+=(--since "${1#--since=}") ;;
        --since) LOG_ARGS+=(--since "${2:-}"); shift ;;
        *) echo "unknown logs option: $1" >&2; exit 1 ;;
      esac
      shift
    done
    $COMPOSE logs "${LOG_ARGS[@]}" $SVC ;;
  health)
    PORT="${BACKEND_PORT:-8030}"
    curl -fsS "http://localhost:${PORT}/health" && echo "" || { echo "backend unhealthy"; exit 1; } ;;
  migrate)  $COMPOSE exec "$BACKEND_SVC" alembic upgrade head ;;
  makemigration)
    MSG="${1:-change}"
    $COMPOSE exec "$BACKEND_SVC" alembic revision --autogenerate -m "$MSG" ;;
  seed)     $COMPOSE exec "$BACKEND_SVC" python -m app.db.seed ;;
  generate)
    # ONE command to generate all shared AI-derived country data (attributes, criterion evals,
    # finder visa pathways, cost breakdowns), cache-first/resumable/Ctrl-C-safe. Most of this
    # also self-heals on demand when a country is opened, so this is a WARM-UP / finder-prep.
    #   --only attributes,criteria,visas,cost   --force   --limit N   --check   --export
    $COMPOSE exec "$BACKEND_SVC" python -m app.db.generate "$@" ;;
  reseed)
    # Load the committed seed into the DB, OVERWRITING existing rows (places + attributes + evals;
    # --criteria also rolls the registry). seed/deploy are insert-only, so use this to push the
    # data from `generate --export`. User searches/profiles/custom criteria are untouched.
    echo "This OVERWRITES the $ENV country data (places + attributes + cached evals) from the"
    echo "committed seed. User searches/profiles and custom-criterion evals are untouched."
    read -r -p "Proceed on $ENV? [y/N] " ans
    [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "Aborted."; exit 0; }
    $COMPOSE exec -T "$BACKEND_SVC" python -m app.db.reseed "$@" ;;
  rescore)
    # Re-score every saved board after a scoring change (no AI). --repopulate also re-picks each
    # board's top 5 like "Refresh list" (pinned countries stay, removed ones never return).
    # --dry-run prints the before/after boards and writes nothing.
    $COMPOSE exec -T "$BACKEND_SVC" python -m app.db.rescore "$@" ;;
  dedupe-places)
    # Merge duplicate country rows that share an ISO code (e.g. "Espagne" + "Spain"). Keeps the
    # canonical row, moves any board entries onto it, deletes the rest. Pass --dry-run to preview.
    $COMPOSE exec "$BACKEND_SVC" python -m app.db.dedupe_places "$@" ;;
  make-admin)
    EMAIL="${1:-}"
    [[ -z "$EMAIL" ]] && { echo "usage: ./xcape.sh make-admin <dev|prod> <email>"; exit 1; }
    # The email is passed as a psql variable (:'email' quotes it), never spliced into the SQL.
    echo "update users set is_admin = true where lower(email) = lower(:'email');" \
      | $COMPOSE exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB" -v email="$1"' sh "$EMAIL"
    echo "Granted admin to ${EMAIL} (UPDATE 0 above = no such user). They can now open /admin (link appears in the header after re-login)." ;;
  reset-password)
    EMAIL="${1:-}"; NEWPW="${2:-}"
    [[ -z "$EMAIL" ]] && { echo "usage: ./xcape.sh reset-password <dev|prod> <email>   (prompts for the password)"; exit 1; }
    if [[ -z "$NEWPW" ]]; then
      # Prompted, so the password doesn't land in shell history.
      read -r -s -p "New password for ${EMAIL}: " NEWPW; echo
      [[ -z "$NEWPW" ]] && { echo "Aborted (empty password)."; exit 1; }
    fi
    $COMPOSE exec -T "$BACKEND_SVC" python -m app.db.set_password "$EMAIL" "$NEWPW" ;;
  purge-test-users)
    # Scoped to test domains only (@example.com / @xcape.test) — never touches real users — so
    # it's safe on prod too, behind a confirmation. Cascades to their searches/candidates/chat.
    echo "Permanently DELETE test-domain users (@example.com / @xcape.test) and their data on $ENV?"
    read -r -p "Proceed on $ENV? [y/N] " ans
    [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "Aborted."; exit 0; }
    echo "delete from users where email ilike '%@example.com' or email ilike '%@xcape.test';" \
      | db_sh 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'
    echo "Purged test users (@example.com / @xcape.test) and their data." ;;
  test)     $COMPOSE exec "$BACKEND_SVC" python -m pytest /app/tests -q ;;
  smoke)    SMOKE_BASE_URL="http://localhost:${BACKEND_PORT:-8030}" python3 scripts/smoke_test.py ;;
  shell)    $COMPOSE exec "$BACKEND_SVC" bash ;;
  backup-db)
    mkdir -p backups
    TS="backup-$(date +%Y%m%d-%H%M%S).sql"
    backup_db_to "backups/${TS}" ;;
  deploy)
    if [[ "$ENV" != "prod" ]]; then echo "deploy is production-only. Use: ./xcape.sh deploy prod"; exit 1; fi
    echo "==> Deploying xCape to production"
    echo "--> Pre-deploy DB backup"
    mkdir -p backups
    if [[ -n "$(container db 2>/dev/null || true)" ]]; then
      # Real DB running: a size-collapse here means we'd be deploying over a likely-empty or
      # wrong-mounted database. Abort loudly rather than rotate a bad backup and press on.
      backup_db_to "backups/predeploy-$(date +%Y%m%d-%H%M%S).sql" \
        || { echo "ABORTING DEPLOY: pre-deploy backup collapsed — investigate the data mount (XCAPE_DATA_ROOT) before retrying."; exit 1; }
    else
      echo "    (no running DB to back up — first deploy?)"
    fi
    if ! git diff --quiet HEAD 2>/dev/null; then
      echo "--> Stashing local changes"; git stash push -m "auto-stash before deploy $(date +%F-%T)" || true
    fi
    echo "--> Pulling latest code"
    git pull origin main || { echo "git pull failed"; exit 1; }
    echo "--> Building images"
    $COMPOSE build backend frontend
    echo "--> Starting services"
    $COMPOSE up -d
    echo "--> Waiting for backend to come up"
    UP=false
    for i in $(seq 1 90); do
      curl -fsS "http://localhost:${BACKEND_PORT:-8030}/health" >/dev/null 2>&1 && { UP=true; break; }
      sleep 2
    done
    # Don't run migrations against a backend that never came up — stop and say so.
    [[ "$UP" == true ]] || { echo "BACKEND DID NOT BECOME HEALTHY within 180s — check: ./xcape.sh logs prod --service backend"; exit 1; }
    echo "--> Applying migrations"
    $COMPOSE exec -T "$BACKEND_SVC" alembic upgrade head
    echo "--> Seeding place database (insert-only: bootstrap + new countries, no overwrite)"
    $COMPOSE exec -T "$BACKEND_SVC" python -m app.db.seed
    echo "--> Health check"
    curl -fsS "http://localhost:${BACKEND_PORT:-8030}/health" && echo "" || { echo "BACKEND UNHEALTHY"; exit 1; }
    echo "--> Smoke tests"
    SMOKE_BASE_URL="http://localhost:${BACKEND_PORT:-8030}" python3 scripts/smoke_test.py \
      || { echo "SMOKE TESTS FAILED — investigate before sending traffic"; exit 1; }
    echo "==> Deploy complete." ;;
  reset-db)
    if [[ "$ENV" == "prod" ]]; then echo "Refusing to reset-db on prod."; exit 1; fi
    $COMPOSE down -v && $COMPOSE up -d db
    echo "Dev DB volume wiped. Run: ./xcape.sh migrate dev && ./xcape.sh seed dev" ;;
  help|*)
    cat <<EOF
xCape ops — ./xcape.sh <command> [dev|prod] [options]

  The environment defaults to prod on apps.athenadecisions.com and dev elsewhere; commands
  that change services or data (stop, restart, rebuild, migrate, seed, reseed, make-admin,
  reset-password, purge-test-users, backup-db, reset-db, …) require it explicitly.

  start | stop | restart | rebuild | status
  logs [--follow] [--service NAME] [--tail N] [--since 1h]
  health
  migrate                 apply Alembic migrations
  makemigration "msg"     autogenerate a migration
  seed                    bootstrap the place database (+ cached attributes/evals; INSERT-ONLY)
  generate [--only attributes,criteria,visas,cost] [--force] [--limit N] [--check] [--export]
                          ONE command for all shared AI-derived country data — cache-first,
                          resumable, Ctrl-C-safe. Most of it self-heals on demand when a country
                          is opened, so this is a warm-up / finder-prep. --check reports pending
                          work (no AI calls); --export snapshots the caches to the git seed.
  reseed <env> [--criteria]  load the committed seed into the DB, overwriting existing rows
                          (places + attributes + evals); --criteria also rolls the registry
  rescore <env> [--repopulate] [--dry-run]  re-score saved boards after a scoring change
  dedupe-places [--dry-run]  merge duplicate country rows sharing an ISO code (e.g. Espagne + Spain)
  make-admin <env> <email>  grant admin rights to a user
  reset-password <env> <email>  set a user's password (prompted, kept out of shell history)
  purge-test-users <env>    delete @example.com / @xcape.test test users (confirm; prod-safe)
  test                    run backend pytest
  smoke                   run end-to-end smoke tests against the running stack
  shell                   open a backend shell
  backup-db               pg_dump to ./backups
  deploy prod             pull, build, restart, migrate, seed, health-check
  reset-db                (dev only) wipe DB volume

Dev URLs: frontend http://localhost:${FRONTEND_PORT:-3030}  backend http://localhost:${BACKEND_PORT:-8030}/docs
EOF
    ;;
esac
