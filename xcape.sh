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
  stop|restart|rebuild|migrate|makemigration|seed|reseed|rescore|adopt-dev-volumes|restore-backup|backup-cron|uptime-cron|dedupe-places|make-admin|reset-password|purge-test-users|backup-db|reset-db)
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

# One-time move for dev checkouts that predate the xcape-dev project name: their data lives in
# `xcape_*` volumes (and maybe containers) of project `xcape`. Never on the server, where
# `xcape` IS prod.
if [[ "$ENV" == "dev" && "$DEFAULT_ENV" == "dev" && "$CMD" != "adopt-dev-volumes" ]] \
   && docker volume inspect xcape_postgres_dev_data >/dev/null 2>&1 \
   && ! docker volume inspect xcape-dev_postgres_dev_data >/dev/null 2>&1; then
  echo "Note: your dev data is still in the old 'xcape_*' volumes. Move it once with:" >&2
  echo "        ./xcape.sh adopt-dev-volumes dev" >&2
fi

# psql / pg_dump use the credentials the db container itself was started with, so they work
# in every environment without matching defaults here.
db_sh() { $COMPOSE exec -T db sh -c "$1"; }

container() { $COMPOSE ps -q "$1"; }

# --- Backups -----------------------------------------------------------------------------
# Prod dumps live OUTSIDE the checkout, in /data/backups/xcape: the host's nightly offsite job
# (golden-path scripts/server-upload-dedibackup.sh, 03:00) uploads the newest db_*.sql.gz of
# every folder under /data/backups. Dev keeps ./backups (git-ignored). BACKUP_ROOT overrides.
if [[ -z "${BACKUP_ROOT:-}" ]]; then
  if [[ "$ENV" == "prod" ]]; then BACKUP_ROOT="/data/backups/xcape"; else BACKUP_ROOT="backups"; fi
fi
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"  # local retention…
BACKUP_KEEP_MIN="${BACKUP_KEEP_MIN:-7}"     # …but always keep at least this many newest dumps

latest_backup() { ls -1t "$BACKUP_ROOT"/db_"$ENV"_*.sql.gz 2>/dev/null | head -n1 || true; }

# A dump is usable only if it is complete: pg_dump writes this trailer as its very last line.
backup_is_complete() { gunzip -c "$1" 2>/dev/null | tail -n 5 | grep -q "PostgreSQL database dump complete"; }

# Dump the database to $BACKUP_ROOT/db_<env>_<stamp>.sql.gz and print its path on stdout.
# Fails (non-zero) — leaving no usable file behind — if pg_dump fails, the dump is incomplete,
# or it is less than half the size of the previous one: the signature of an empty/wrong
# database being dumped (golden-path's prod incident went unnoticed for days because a
# collapsed dump still passed a naive "not empty" check). Callers use `backup_db || abort`,
# which disables `set -e` in here, so every step checks explicitly.
backup_db() {
  if ! mkdir -p "$BACKUP_ROOT" 2>/dev/null || [[ ! -w "$BACKUP_ROOT" ]]; then
    echo "Cannot write to $BACKUP_ROOT. On the server, create it once:" >&2
    echo "  sudo mkdir -p $BACKUP_ROOT && sudo chown $(id -un):$(id -gn) $BACKUP_ROOT" >&2
    return 1
  fi
  local prev dest part bytes prevbytes
  prev="$(latest_backup)"
  dest="$BACKUP_ROOT/db_${ENV}_$(date +%Y%m%d_%H%M%S).sql.gz"
  part="$dest.partial"
  if ! db_sh 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip -c > "$part"; then
    rm -f "$part"; echo "pg_dump FAILED — no backup written." >&2; return 1
  fi
  if ! backup_is_complete "$part"; then
    rm -f "$part"; echo "Dump is INCOMPLETE (no end-of-dump marker) — removed it." >&2; return 1
  fi
  bytes="$(wc -c < "$part" | tr -d ' ')"
  if [[ -n "$prev" ]]; then
    prevbytes="$(wc -c < "$prev" | tr -d ' ')"
    if [[ "$prevbytes" -gt 0 && $(( bytes * 2 )) -lt "$prevbytes" ]]; then
      mv "$part" "$dest.suspect"
      echo "" >&2
      echo "!!! BACKUP SIZE-COLLAPSE ALARM !!!" >&2
      echo "    The new dump is ${bytes} bytes — less than HALF of the previous one" >&2
      echo "    ($(basename "$prev"), ${prevbytes} bytes). Kept aside as $dest.suspect." >&2
      echo "    This is the signature of an empty/wrong database (e.g. compose mounted a stray" >&2
      echo "    ./data instead of XCAPE_DATA_ROOT). Investigate before deploying or restoring." >&2
      return 1
    fi
  fi
  mv "$part" "$dest"
  echo "Backup: $dest ($(du -h "$dest" | cut -f1))" >&2
  # Retention: drop dumps older than BACKUP_KEEP_DAYS, never touching the newest KEEP_MIN.
  ls -1t "$BACKUP_ROOT"/db_"$ENV"_*.sql.gz 2>/dev/null | tail -n +$(( BACKUP_KEEP_MIN + 1 )) \
    | while read -r old; do
        if [[ -n "$(find "$old" -mtime +"$BACKUP_KEEP_DAYS" 2>/dev/null)" ]]; then
          rm -f "$old" && echo "  pruned $(basename "$old")" >&2
        fi
      done
  echo "$dest"
}

# psql inside the db container with the container's own credentials. Read-only unless
# PSQL_WRITE=1: the session runs with default_transaction_read_only, so the DATABASE refuses
# any write — no SQL pattern-matching to outwit. Extra args go to psql.
psql_db() {
  local ro="-c default_transaction_read_only=on"
  [[ "${PSQL_WRITE:-0}" == "1" ]] && ro=""
  $COMPOSE exec -T -e PGOPTIONS="$ro" db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"' sh "$@"
}

# The database name as the container sees it (for restore/rehearsal).
# (These helpers take no input: </dev/null stops `compose exec` from swallowing the caller's
# stdin — e.g. the answer piped to a later confirmation prompt.)
db_name() { db_sh 'printf %s "$POSTGRES_DB"' </dev/null; }
# SQL on the maintenance database (CREATE/DROP/RENAME DATABASE can't run inside the target).
admin_sql() { db_sh "PGOPTIONS='-c client_min_messages=warning' psql -v ON_ERROR_STOP=1 -qAt -U \"\$POSTGRES_USER\" -d postgres -c \"$1\"" </dev/null; }

# Load a .sql.gz dump into database $2 (which must exist and be empty).
load_dump() {
  gunzip -c "$1" | $COMPOSE exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$1" >/dev/null' sh "$2"
}

# Row counts of the main tables in database $1 — a quick "does this look like our data" check.
db_counts() {
  db_sh "psql -qAt -U \"\$POSTGRES_USER\" -d $1 -c \"select 'users=' || (select count(*) from users) || '  searches=' || (select count(*) from searches) || '  places=' || (select count(*) from places) || '  evals=' || (select count(*) from place_custom_evals)\"" </dev/null
}

wait_healthy() {  # wait_healthy <seconds>
  local deadline=$(( SECONDS + $1 ))
  while (( SECONDS < deadline )); do
    curl -fsS "http://localhost:${BACKEND_PORT:-8030}/health" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
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
  psql)
    # ./xcape.sh psql <env> "<SQL>"          read-only (the database refuses writes)
    # ./xcape.sh psql <env> - < query.sql    same, SQL from stdin
    # ./xcape.sh psql <env> --write "<SQL>"  writes allowed (prod: typed confirmation)
    PSQL_WRITE=0; SQL=""
    for a in "$@"; do case "$a" in --write) PSQL_WRITE=1 ;; *) SQL="$a" ;; esac; done
    [[ -n "$SQL" ]] || { echo "usage: ./xcape.sh psql <env> [--write] \"<SQL>\" | -"; exit 1; }
    if [[ "$PSQL_WRITE" == 1 && "$ENV" == "prod" ]]; then
      read -r -p "WRITE on PRODUCTION. Type 'psql-write-production' to run: " ans </dev/tty
      [[ "$ans" == "psql-write-production" ]] || { echo "Aborted."; exit 1; }
    fi
    export PSQL_WRITE
    if [[ "$SQL" == "-" ]]; then psql_db; else psql_db -c "$SQL"; fi ;;
  dbshell)
    # Interactive psql; read-only unless --write (prod: typed confirmation).
    RO="-c default_transaction_read_only=on"
    if [[ "${1:-}" == "--write" ]]; then
      if [[ "$ENV" == "prod" ]]; then
        read -r -p "WRITE on PRODUCTION. Type 'psql-write-production' to open a writable shell: " ans
        [[ "$ans" == "psql-write-production" ]] || { echo "Aborted."; exit 1; }
      fi
      RO=""
    fi
    $COMPOSE exec -e PGOPTIONS="$RO" db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' ;;
  backup-db)
    backup_db ;;
  list-backups)
    echo "Backups in $BACKUP_ROOT (newest first; kept ${BACKUP_KEEP_DAYS} days, at least the ${BACKUP_KEEP_MIN} newest):"
    found=0
    while read -r f; do
      [[ -n "$f" ]] || continue
      found=1
      ok="ok"; backup_is_complete "$f" || ok="INCOMPLETE"
      printf "  %6s  %s  %s\n" "$(du -h "$f" | cut -f1)" "$(basename "$f")" "$ok"
    done < <(ls -1t "$BACKUP_ROOT"/db_"$ENV"_*.sql.gz 2>/dev/null || true)
    [[ "$found" == 1 ]] || echo "  (none)" ;;
  restore-backup)
    # ./xcape.sh restore-backup <env> <file.sql.gz>|--latest [--rehearse-into <scratch_db>]
    #   --rehearse-into: load into a throwaway database, compare row counts with live, drop it.
    #   Without it: safety dump → load into <db>_restoring while the site keeps running →
    #   brief backend stop → rename live to <db>_pre_restore_<stamp> and the restored one to
    #   <db> → restart. The previous database is KEPT, so a restore can be undone.
    FILE=""; REHEARSE=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --latest) FILE="$(latest_backup)" ;;
        --rehearse-into) REHEARSE="${2:-}"; shift ;;
        *) FILE="$1" ;;
      esac
      shift
    done
    if [[ -z "$FILE" || ! -f "$FILE" ]]; then
      echo "usage: ./xcape.sh restore-backup <env> <file.sql.gz>|--latest [--rehearse-into <scratch_db>]"; exit 1
    fi
    backup_is_complete "$FILE" || { echo "$FILE is not a complete dump (no end-of-dump marker) — refusing."; exit 1; }
    LIVE="$(db_name)"
    if [[ -n "$REHEARSE" ]]; then
      if [[ ! "$REHEARSE" =~ ^[a-z_][a-z0-9_]{0,40}$ || "$REHEARSE" == "$LIVE" || "$REHEARSE" == "postgres" ]]; then
        echo "Invalid scratch database name '$REHEARSE' (lowercase letters, digits, _; not the live one)."; exit 1
      fi
      echo "--> Rehearsal: loading $(basename "$FILE") into '$REHEARSE' (the live database is not touched)"
      admin_sql "DROP DATABASE IF EXISTS $REHEARSE" >/dev/null && admin_sql "CREATE DATABASE $REHEARSE" >/dev/null
      if load_dump "$FILE" "$REHEARSE"; then
        echo "    restored: $(db_counts "$REHEARSE")"
        echo "    live:     $(db_counts "$LIVE")"
        admin_sql "DROP DATABASE $REHEARSE" >/dev/null
        echo "==> Rehearsal OK — this dump restores cleanly (scratch database dropped)."
      else
        admin_sql "DROP DATABASE IF EXISTS $REHEARSE" >/dev/null
        echo "REHEARSAL FAILED — this dump does not restore cleanly."; exit 1
      fi
      exit 0
    fi
    echo "About to REPLACE the $ENV database '$LIVE' with $(basename "$FILE")."
    echo "The current database is kept under another name, so this can be undone."
    if [[ "$ENV" == "prod" ]]; then
      read -r -p "Type 'restore-production' to continue: " ans
      [[ "$ans" == "restore-production" ]] || { echo "Aborted."; exit 1; }
    else
      read -r -p "Proceed on $ENV? [y/N] " ans
      [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "Aborted."; exit 0; }
    fi
    echo "--> Safety dump of the current database"
    backup_db >/dev/null || { echo "ABORTING: could not take a safety dump first."; exit 1; }
    STAMP="$(date +%Y%m%d_%H%M%S)"; TMP="${LIVE}_restoring"; OLD="${LIVE}_pre_restore_${STAMP}"
    echo "--> Loading the dump into '$TMP' (the site keeps running on the current database)"
    admin_sql "DROP DATABASE IF EXISTS $TMP" >/dev/null && admin_sql "CREATE DATABASE $TMP" >/dev/null
    if ! load_dump "$FILE" "$TMP"; then
      admin_sql "DROP DATABASE IF EXISTS $TMP" >/dev/null; echo "LOAD FAILED — nothing was changed."; exit 1
    fi
    echo "    loaded: $(db_counts "$TMP")"
    echo "--> Swapping databases (backend briefly stopped)"
    $COMPOSE stop "$BACKEND_SVC"
    admin_sql "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('$LIVE', '$TMP') AND pid <> pg_backend_pid()" >/dev/null
    if ! { admin_sql "ALTER DATABASE $LIVE RENAME TO $OLD" >/dev/null && admin_sql "ALTER DATABASE $TMP RENAME TO $LIVE" >/dev/null; }; then
      echo "RENAME FAILED — check the databases by hand (./xcape.sh dbshell $ENV, then \\l)."
      $COMPOSE start "$BACKEND_SVC"; exit 1
    fi
    $COMPOSE start "$BACKEND_SVC"
    wait_healthy 120 || echo "WARNING: backend not healthy yet — check ./xcape.sh logs $ENV --service backend"
    echo "==> Restored: $(db_counts "$LIVE")"
    echo "    The previous database is kept as '$OLD'. Once you're satisfied:"
    echo "    ./xcape.sh psql $ENV --write \"DROP DATABASE $OLD\"" ;;
  backup-cron)
    # Show the nightly backup crontab line for this checkout; --install adds it (idempotent).
    # 02:15 — after golden-path's 02:00 dump, before the 03:00 offsite upload.
    LINE="15 2 * * * cd $(pwd) && ./xcape.sh backup-db $ENV >> $BACKUP_ROOT/backup.log 2>&1 # xcape-backup-$ENV"
    if crontab -l 2>/dev/null | grep -q "# xcape-backup-$ENV\$"; then
      echo "Installed:"; crontab -l | grep "# xcape-backup-$ENV\$"
    elif [[ "${1:-}" == "--install" ]]; then
      mkdir -p "$BACKUP_ROOT" 2>/dev/null && [[ -w "$BACKUP_ROOT" ]] \
        || { echo "Create $BACKUP_ROOT first: sudo mkdir -p $BACKUP_ROOT && sudo chown $(id -un):$(id -gn) $BACKUP_ROOT"; exit 1; }
      (crontab -l 2>/dev/null || true; echo "$LINE") | crontab -
      echo "Installed: $LINE"
    else
      echo "Not installed. It would add:"; echo "  $LINE"
      echo "Install with: ./xcape.sh backup-cron $ENV --install"
    fi ;;
  uptime-cron)
    # Show the every-minute uptime probe crontab line; --install adds it (idempotent). Cron
    # runs scripts/uptime-probe.sh from this checkout, so deploys keep it current. Slack is
    # told only on down/up transitions; the webhook comes from /etc/xcape/environment.
    PROBE="$(pwd)/scripts/uptime-probe.sh"
    if [[ "$ENV" == "prod" ]]; then
      LINE="* * * * * $PROBE # xcape-uptime-$ENV"
    else
      LINE="* * * * * HEALTH_URLS=http://localhost:${BACKEND_PORT:-8030}/health $PROBE # xcape-uptime-$ENV"
    fi
    if crontab -l 2>/dev/null | grep -q "# xcape-uptime-$ENV\$"; then
      echo "Installed:"; crontab -l | grep "# xcape-uptime-$ENV\$"
    elif [[ "${1:-}" == "--install" ]]; then
      [[ -x "$PROBE" ]] || { echo "$PROBE is missing or not executable."; exit 1; }
      (crontab -l 2>/dev/null || true; echo "$LINE") | crontab -
      echo "Installed: $LINE"
    else
      echo "Not installed. It would add:"; echo "  $LINE"
      echo "Install with: ./xcape.sh uptime-cron $ENV --install"
    fi
    if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
      echo "Note: no SLACK_WEBHOOK_URL in /etc/xcape/environment — the probe runs but tells nobody."
    fi ;;
  schema-check)
    # Do the migrations match the ORM models? (Tests use create_all, so they can't tell.)
    $COMPOSE exec -T "$BACKEND_SVC" alembic check ;;
  typecheck)
    [[ "$ENV" == "dev" ]] || { echo "typecheck runs in the dev frontend container: ./xcape.sh typecheck dev"; exit 1; }
    $COMPOSE exec -T frontend-dev npx tsc -b --pretty false && echo "Types OK" ;;
  prune-images)
    # Reclaim disk on the shared host: dangling images + build cache older than a week.
    # Never touches running containers, volumes or tagged images.
    docker system df
    docker image prune -f
    docker builder prune -f --filter until=168h
    docker system df ;;
  deploy)
    if [[ "$ENV" != "prod" ]]; then echo "deploy is production-only. Use: ./xcape.sh deploy prod"; exit 1; fi
    echo "==> Deploying xCape to production"
    echo "--> Pre-deploy DB backup"
    if [[ -n "$(container db 2>/dev/null || true)" ]]; then
      # Real DB running: a failed, incomplete or collapsed dump means we'd be deploying over a
      # likely-empty or wrong-mounted database. Abort loudly rather than press on.
      backup_db >/dev/null \
        || { echo "ABORTING DEPLOY: pre-deploy backup failed — investigate (XCAPE_DATA_ROOT, $BACKUP_ROOT) before retrying."; exit 1; }
    else
      echo "    (no running DB to back up — first deploy?)"
    fi
    if ! git diff --quiet HEAD 2>/dev/null; then
      echo "--> Stashing local changes"; git stash push -m "auto-stash before deploy $(date +%F-%T)" || true
    fi
    echo "--> Pulling latest code"
    git pull origin main || { echo "git pull failed"; exit 1; }
    echo "--> Building images (the site stays up meanwhile)"
    $COMPOSE build backend frontend || { echo "BUILD FAILED — the running site is untouched."; exit 1; }
    # Migrate with the NEW code in a one-off container BEFORE swapping, so the new backend never
    # starts against the old schema, and a failed migration leaves the old site serving.
    echo "--> Applying migrations (new code, before the swap)"
    $COMPOSE run --rm -T "$BACKEND_SVC" alembic upgrade head \
      || { echo "MIGRATIONS FAILED — the running site is untouched (old code still serving). Fix, then redeploy."; exit 1; }
    echo "--> Swapping to the new containers"
    $COMPOSE up -d
    echo "--> Waiting for backend to come up"
    wait_healthy 180 || { echo "BACKEND DID NOT BECOME HEALTHY within 180s — check: ./xcape.sh logs prod --service backend"; exit 1; }
    echo "--> Seeding place database (insert-only: bootstrap + new countries, no overwrite)"
    $COMPOSE exec -T "$BACKEND_SVC" python -m app.db.seed
    echo "--> Health check"
    curl -fsS "http://localhost:${BACKEND_PORT:-8030}/health" && echo "" || { echo "BACKEND UNHEALTHY"; exit 1; }
    echo "--> Smoke tests"
    SMOKE_BASE_URL="http://localhost:${BACKEND_PORT:-8030}" python3 scripts/smoke_test.py \
      || { echo "SMOKE TESTS FAILED — investigate before sending traffic"; exit 1; }
    echo "==> Deploy complete." ;;
  adopt-dev-volumes)
    # One-time: copy the dev volumes created under the old compose project name (`xcape_*`)
    # into volumes owned by `xcape-dev`, then start dev. Read-only on the old volumes, which are
    # kept (delete them yourself once happy). Dev machines only.
    if [[ "$ENV" != "dev" || "$DEFAULT_ENV" != "dev" ]]; then
      echo "adopt-dev-volumes is for dev machines only — never on the server."; exit 1
    fi
    docker compose -p xcape -f docker-compose.dev.yml down 2>/dev/null || true  # legacy containers
    $COMPOSE down
    $COMPOSE up --no-start  # creates the project-owned (empty) volumes
    for v in postgres_dev_data frontend_dev_node_modules backend_dev_xcvenv; do
      if docker volume inspect "xcape_$v" >/dev/null 2>&1; then
        echo "--> copying xcape_$v -> xcape-dev_$v"
        # postgres:15-alpine is already pulled for the db service — no extra image download.
        docker run --rm --entrypoint sh -v "xcape_$v:/from:ro" -v "xcape-dev_$v:/to" postgres:15-alpine \
          -c 'find /to -mindepth 1 -delete && cp -a /from/. /to/'
      fi
    done
    $COMPOSE up -d
    echo "Done. The old volumes are kept; remove them once you're happy:"
    echo "  docker volume rm xcape_postgres_dev_data xcape_frontend_dev_node_modules xcape_backend_dev_xcvenv" ;;
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
  psql <env> [--write] "<SQL>" | -   run SQL (read-only unless --write; prod writes need a typed phrase)
  dbshell <env> [--write]  interactive psql (read-only unless --write)
  schema-check            do the Alembic migrations match the ORM models?
  typecheck dev           TypeScript check in the dev frontend container
  test                    run backend pytest
  smoke                   run end-to-end smoke tests against the running stack
  shell                   open a backend shell
  backup-db <env>         gzip'd, verified pg_dump → /data/backups/xcape (prod) or ./backups (dev),
                          size-collapse alarm, retention (BACKUP_KEEP_DAYS=14, BACKUP_KEEP_MIN=7)
  list-backups <env>      the dumps, newest first, with an integrity check
  restore-backup <env> <file>|--latest [--rehearse-into <scratch_db>]
                          rehearse into a throwaway DB, or restore (safety dump first; the
                          previous database is kept under another name)
  backup-cron <env> [--install]  show / install the nightly 02:15 backup
  uptime-cron <env> [--install]  show / install the every-minute uptime probe (Slack on down/up)
  prune-images            reclaim disk: dangling images + week-old build cache
  deploy prod             backup, pull, build, migrate (before the swap), swap, seed, health, smoke
  reset-db                (dev only) wipe DB volume
  adopt-dev-volumes dev   (once, dev only) move data from pre-rename \`xcape_*\` volumes to \`xcape-dev\`

Dev URLs: frontend http://localhost:${FRONTEND_PORT:-3030}  backend http://localhost:${BACKEND_PORT:-8030}/docs
EOF
    ;;
esac
