<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape prod data root migration (silent-data-loss fix)

## Why

Until this change, `docker-compose.server.yml` bound Postgres to a **relative** path:

```yaml
- ./data/postgres:/var/lib/postgresql/data
```

A relative bind resolves against **the current working directory of whoever runs
`docker compose`**. If the stack is ever brought up from a different directory — a second
clone, a stale path, a future systemd unit, a cron job — Docker mounts a *different, empty*
directory and Postgres **initializes a brand-new empty database with no error**. That is
silent data loss. The sibling project golden-path was bitten by exactly this twice (its prod
DB appeared to "lose" all 99 users, fell back to a 5-user demo seed on reboot, then
"recovered" when started from the right directory again).

## What changed (already in the repo)

- **`docker-compose.server.yml`** now binds an **absolute**, env-driven path with a fail-loud
  guard:

  ```yaml
  - ${XCAPE_DATA_ROOT:?XCAPE_DATA_ROOT must be set in /etc/xcape/environment — refusing to start against a relative ./data path}/postgres:/var/lib/postgresql/data
  ```

  If `XCAPE_DATA_ROOT` is unset, `docker compose` **errors out and refuses to start** instead
  of silently falling back to a stray `./data`.

- **`xcape.sh`** now sources **`/etc/xcape/environment`** (a system file outside any git
  checkout) before the checkout-local `.env`, so `XCAPE_DATA_ROOT` reaches compose for every
  command (`start`, `deploy`, `backup-db`, …).

- **`xcape.sh` backups** (`backup-db` and the pre-deploy backup) now raise a loud
  **size-collapse alarm** and return non-zero if a new dump is less than half the previous
  one — the signature of an accidental empty-DB dump. The pre-deploy path **aborts the
  deploy** on a collapse (when a DB container is running) rather than rotating a bad backup.

> Dev is unaffected: `docker-compose.dev.yml` uses a named Docker volume
> (`postgres_dev_data`), not a host bind, so it has never had this failure mode.

## One-time server migration (run by hand on `apps`)

The live data currently sits **inside the checkout** at `~/projects/xcape/data/postgres`.
Move it to a persistent location outside any git tree and point `XCAPE_DATA_ROOT` at it.

```bash
cd ~/projects/xcape

# 1. Stop the stack (release the Postgres data dir).
./xcape.sh stop prod

# 2. Move the existing data OUT of the checkout to a stable, non-git location.
sudo mkdir -p /data/xcape
sudo mv ~/projects/xcape/data/postgres /data/xcape/postgres
#    (verify it moved; the old ./data/postgres should now be gone)
ls -la /data/xcape/postgres | head

# 3. Point XCAPE_DATA_ROOT at it in the system env file (outside any checkout).
sudo mkdir -p /etc/xcape
echo 'XCAPE_DATA_ROOT=/data/xcape' | sudo tee -a /etc/xcape/environment
#    Make sure /etc/xcape/environment is root-owned and not world-readable if it
#    later holds secrets:  sudo chmod 600 /etc/xcape/environment

# 4. Sanity-check compose resolution BEFORE starting:
#    - unset must error loudly; set must resolve to /data/xcape/postgres.
env -u XCAPE_DATA_ROOT docker compose -f docker-compose.server.yml config >/dev/null \
  && echo "UNEXPECTED: should have errored" || echo "OK: errors loudly when unset"
XCAPE_DATA_ROOT=/data/xcape docker compose -f docker-compose.server.yml config \
  | grep -A2 'source:.*postgres'

# 5. Start the stack (xcape.sh now sources /etc/xcape/environment automatically).
./xcape.sh start prod

# 6. VERIFY the data survived — row counts should match pre-migration, NOT a fresh seed.
./xcape.sh status prod
docker compose -f docker-compose.server.yml exec -T db \
  psql -U "${POSTGRES_USER:-xcape}" "${POSTGRES_DB:-xcape_prod}" \
  -c "select count(*) as users from users;" \
  -c "select count(*) as places from places;"

# 7. VERIFY a fresh backup is full-size (no size-collapse alarm).
./xcape.sh backup-db prod
ls -la backups/ | tail -3
```

### Rollback

If row counts come back wrong (e.g. an empty/seed-sized DB), **stop immediately** and do not
let an empty dump rotate over good backups:

```bash
./xcape.sh stop prod
# Move the data back to where it was and investigate before restarting:
sudo mv /data/xcape/postgres ~/projects/xcape/data/postgres
```

The original data is only *moved*, never deleted, so the pre-migration state is fully
recoverable until you're satisfied the counts are right.

## Notes

- **No systemd unit** is added: xcape is started manually via `xcape.sh`, and Docker's
  `restart: unless-stopped` policy reuses the already-resolved absolute mount across reboots.
  If a unit is ever introduced, its `WorkingDirectory` must be the real checkout and it must
  inherit `XCAPE_DATA_ROOT` (e.g. `EnvironmentFile=/etc/xcape/environment`).
- Uploads (`backend/uploads/`) are **not** bind-mounted in the server compose today, so they
  are ephemeral inside the backend container. That is a separate, pre-existing concern; if
  persistent uploads are ever needed, give them the same `${XCAPE_DATA_ROOT:?…}/uploads`
  treatment.
