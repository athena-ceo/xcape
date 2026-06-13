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
    echo "==> Deploy complete. Reminder: external nginx must include nginx/xcape-apps-location.conf" ;;
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
  seed                    load the bundled place database
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
