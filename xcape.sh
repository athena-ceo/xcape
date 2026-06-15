#!/usr/bin/env bash
# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
#
# xCape dev-ops wrapper. Usage: ./xcape.sh <command> [dev|prod] [options]

set -euo pipefail
cd "$(dirname "$0")"

CMD="${1:-help}"
ENV="${2:-dev}"
shift || true
shift || true

if [[ "$ENV" == "prod" ]]; then
  COMPOSE="docker compose -f docker-compose.server.yml"
  BACKEND_SVC="backend"
else
  COMPOSE="docker compose -f docker-compose.dev.yml"
  BACKEND_SVC="backend"
fi

# Load .env if present so compose variable substitution matches the script's view.
[[ -f .env ]] && set -a && . ./.env && set +a || true

container() { $COMPOSE ps -q "$1"; }

case "$CMD" in
  start)    $COMPOSE up -d "$@" ;;
  stop)     $COMPOSE down "$@" ;;
  restart)  $COMPOSE down && $COMPOSE up -d "$@" ;;
  rebuild)  $COMPOSE build "$@" && $COMPOSE up -d ;;
  status)   $COMPOSE ps "$@" ;;
  logs)
    FOLLOW=""; SVC=""
    for a in "$@"; do
      [[ "$a" == "--follow" || "$a" == "-f" ]] && FOLLOW="-f"
      [[ "$a" == --service=* ]] && SVC="${a#--service=}"
    done
    $COMPOSE logs $FOLLOW $SVC ;;
  health)
    PORT="${BACKEND_PORT:-8030}"
    curl -fsS "http://localhost:${PORT}/health" && echo "" || { echo "backend unhealthy"; exit 1; } ;;
  migrate)  $COMPOSE exec "$BACKEND_SVC" alembic upgrade head ;;
  makemigration)
    MSG="${1:-change}"
    $COMPOSE exec "$BACKEND_SVC" alembic revision --autogenerate -m "$MSG" ;;
  seed)     $COMPOSE exec "$BACKEND_SVC" python -m app.db.seed ;;
  reseed-criteria)
    # Overwrite the editable criteria registry (criteria tree, personas, communities) from
    # the bundled criteria.json. seed/deploy never touch an existing registry, so this is how
    # registry changes (e.g. new personas) roll out. WARNING: replaces any admin UI edits.
    echo "This OVERWRITES the $ENV criteria registry (tree, personas, communities) from"
    echo "the bundled criteria.json, replacing any admin edits made in the UI."
    read -r -p "Proceed on $ENV? [y/N] " ans
    [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "Aborted."; exit 0; }
    $COMPOSE exec -T "$BACKEND_SVC" python -m app.db.reseed_criteria ;;
  backfill-social)
    $COMPOSE exec "$BACKEND_SVC" python -m app.db.backfill_social ;;
  evaluate-all)
    $COMPOSE exec "$BACKEND_SVC" python -m app.db.evaluate_all "$@" ;;
  export-evals)
    $COMPOSE exec "$BACKEND_SVC" python -m app.db.export_evals ;;
  make-admin)
    EMAIL="${1:-}"
    [[ -z "$EMAIL" ]] && { echo "usage: ./xcape.sh make-admin <dev|prod> <email>"; exit 1; }
    $COMPOSE exec -T db psql -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-xcape_dev}" \
      -c "update users set is_admin = true where lower(email) = lower('${EMAIL}');"
    echo "Granted admin to ${EMAIL}. They can now open /admin (link appears in the header after re-login)." ;;
  reset-password)
    EMAIL="${1:-}"; NEWPW="${2:-}"
    [[ -z "$EMAIL" || -z "$NEWPW" ]] && { echo "usage: ./xcape.sh reset-password <dev|prod> <email> <newpassword>"; exit 1; }
    $COMPOSE exec -T "$BACKEND_SVC" python -m app.db.set_password "$EMAIL" "$NEWPW" ;;
  purge-test-users)
    if [[ "$ENV" == "prod" ]]; then echo "Refusing to purge on prod."; exit 1; fi
    $COMPOSE exec -T db psql -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-xcape_dev}" \
      -c "delete from users where email ilike '%@example.com' or email ilike '%@xcape.test';"
    echo "Purged test users (@example.com / @xcape.test) and their data." ;;
  test)     $COMPOSE exec "$BACKEND_SVC" python -m pytest /app/tests -q ;;
  smoke)    SMOKE_BASE_URL="http://localhost:${BACKEND_PORT:-8030}" python3 scripts/smoke_test.py ;;
  shell)    $COMPOSE exec "$BACKEND_SVC" bash ;;
  backup-db)
    mkdir -p backups
    TS="backup-$(date +%Y%m%d-%H%M%S).sql"
    $COMPOSE exec -T db pg_dump -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-xcape_dev}" > "backups/${TS}"
    echo "Wrote backups/${TS}" ;;
  deploy)
    if [[ "$ENV" != "prod" ]]; then echo "deploy is production-only. Use: ./xcape.sh deploy prod"; exit 1; fi
    echo "==> Deploying xCape to production"
    echo "--> Pre-deploy DB backup"
    mkdir -p backups
    $COMPOSE exec -T db pg_dump -U "${POSTGRES_USER:-xcape}" "${POSTGRES_DB:-xcape_prod}" \
      > "backups/predeploy-$(date +%Y%m%d-%H%M%S).sql" 2>/dev/null \
      || echo "    (no running DB to back up — first deploy?)"
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
    for i in $(seq 1 60); do
      curl -fsS "http://localhost:${BACKEND_PORT:-8030}/health" >/dev/null 2>&1 && break; sleep 2
    done
    echo "--> Applying migrations"
    $COMPOSE exec -T "$BACKEND_SVC" alembic upgrade head
    echo "--> Seeding place database (idempotent)"
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

  start | stop | restart | rebuild | status
  logs [--follow] [--service=NAME]
  health
  migrate                 apply Alembic migrations
  makemigration "msg"     autogenerate a migration
  seed                    load the bundled place database (+ cached evals; idempotent)
  reseed-criteria <env>   overwrite the criteria registry (tree, personas, communities) from
                          criteria.json — rolls out registry changes; replaces admin UI edits
  backfill-social         AI-fill social criteria (tolerance, gender, culture, food) on seeded countries
  evaluate-all [--force] [--stale-days N] [--limit N]
                          AI-evaluate every objective criterion for every country (cross-user cache)
  make-admin <env> <email>  grant admin rights to a user
  reset-password <env> <email> <pw>  set a user's password
  purge-test-users <env>    (dev) delete @example.com / @xcape.test test users
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
