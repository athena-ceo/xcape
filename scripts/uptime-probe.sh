#!/usr/bin/env bash
# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.
#
# Is xCape answering?
#
# Ported from golden-path's scripts/uptime-probe.sh. A cron job on the server asks the
# health endpoint every minute and says so in Slack when the answer stops coming.
#
# It alerts on *transitions*, not on every run — one message when xCape goes down and one
# when it comes back. A probe that re-reports the same outage every minute gets muted. It
# also waits for FAILURES_BEFORE_DOWN consecutive failures, so a deploy or a restore
# (`./xcape.sh restore-backup` stops the backend to swap databases) pages nobody.
#
# Honest limitation: this runs ON the server, so it cannot tell you the machine itself is
# gone. It catches the common case — the app is down, the box is not.
#
# Install: `./xcape.sh uptime-cron prod --install`. Cron runs this file from the checkout,
# so a deploy's `git pull` updates it (golden-path's copy in ~/bin has to be re-copied).
#
# Config:
#   SLACK_WEBHOOK_URL  read from /etc/xcape/environment (ENV_FILE) when not already set, so
#                      the secret is never in the repo or visible in `crontab -l`. No webhook
#                      = the probe still runs and keeps state, it just tells nobody.
#   DRY_RUN=1          print the Slack message instead of posting it (for testing).

set -uo pipefail

# Each address watched on its own: the backend answering on localhost says nothing about the
# public nginx block or its certificate.
HEALTH_URLS="${HEALTH_URLS:-http://localhost:8030/health https://apps.athenadecisions.com/xcape/health}"
# Not /tmp (golden-path's default): that is wiped on reboot and shared by every user. Not
# /data/backups/xcape either: that folder belongs to the dumps and the offsite upload job.
STATE_DIR="${STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/xcape}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-15}"
# Consecutive failed checks before xCape is called down. At one run per minute this is
# roughly the grace period a deploy gets.
FAILURES_BEFORE_DOWN="${FAILURES_BEFORE_DOWN:-3}"
ENV_FILE="${ENV_FILE:-/etc/xcape/environment}"
DRY_RUN="${DRY_RUN:-0}"

# Read only the one key — never source the file — and drop optional surrounding quotes.
if [[ -z "${SLACK_WEBHOOK_URL:-}" && -r "$ENV_FILE" ]]; then
    SLACK_WEBHOOK_URL="$(grep -E '^SLACK_WEBHOOK_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- | sed -E "s/^[\"']//; s/[\"']\$//")"
fi

mkdir -p "$STATE_DIR" || { echo "uptime-probe: cannot create $STATE_DIR" >&2; exit 2; }

notify() {
    local text="$1"
    if [[ "$DRY_RUN" == "1" ]]; then
        echo "[dry-run] would post to Slack: $text"
        return 0
    fi
    [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && return 0
    # --max-time so a wedged Slack cannot wedge the probe; failure is ignored, because the
    # probe's job is to watch the app, not to guarantee delivery.
    curl -fsS --max-time 10 -X POST -H 'Content-type: application/json' \
        --data "{\"text\": $(printf '%s' "$text" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}" \
        "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true
}

# State is "<verdict> <consecutive-failures>"; the second field is what lets a one-minute
# blip be told apart from an outage across runs.
probe() {
    local HEALTH_URL="$1"
    local STATE_FILE
    STATE_FILE="$STATE_DIR/xcape-uptime-$(printf '%s' "$HEALTH_URL" | tr -c 'A-Za-z0-9' '_').state"
    local previous="up" fails=0 response status_code body observed current
    if [[ -r "$STATE_FILE" ]]; then
        read -r previous fails < "$STATE_FILE" 2>/dev/null || true
        [[ -z "${previous:-}" ]] && previous="up"
        [[ "$fails" =~ ^[0-9]+$ ]] || fails=0
    fi

    # NB: no -f (golden-path learned this): with --fail curl prints the real status AND exits
    # non-zero, so a fallback concatenates onto it ("502000"). Without it curl prints the
    # true code, or "000" when the connection never happened. The code goes on its own last
    # line after the body.
    response="$(curl -sS -w '\n%{http_code}' --max-time "$TIMEOUT_SECONDS" "$HEALTH_URL" 2>/dev/null || true)"
    status_code="${response##*$'\n'}"
    body="${response%$'\n'*}"
    [[ "$status_code" =~ ^[0-9]{3}$ ]] || status_code="000"

    # A 200 alone is not enough: nginx sends unknown /xcape/ paths to the frontend, which
    # answers every path with index.html and a 200. Only the backend says "status": "ok".
    if [[ "$status_code" == "200" && "$body" =~ \"status\":[[:space:]]*\"ok\" ]]; then
        observed="up"
    else
        observed="down"
        [[ "$status_code" == "200" ]] && status_code="200 without status ok"
    fi

    # Deliberately NOT a pause file that deploys touch: a crashed deploy would leave the
    # probe permanently mute. Consecutive failures degrade safely; a flag does not.
    if [[ "$observed" == "down" ]]; then
        fails=$(( fails + 1 ))
    else
        fails=0
    fi

    if (( fails >= FAILURES_BEFORE_DOWN )); then
        current="down"
    elif [[ "$observed" == "up" ]]; then
        current="up"
    else
        # Failing, but not yet confirmed: hold the previous verdict and stay quiet.
        current="$previous"
    fi

    if [[ "$current" != "$previous" ]]; then
        if [[ "$current" == "down" ]]; then
            notify ":red_circle: *xCape is not answering* — health check returned \`${status_code}\` at $(date -u '+%Y-%m-%d %H:%M UTC'). URL: ${HEALTH_URL}"
        else
            notify ":large_green_circle: *xCape is answering again* — health check back to 200 at $(date -u '+%Y-%m-%d %H:%M UTC'). URL: ${HEALTH_URL}"
        fi
    fi

    [[ "$DRY_RUN" == "1" ]] && echo "[dry-run] $HEALTH_URL observed=$observed code=$status_code fails=$fails verdict=$current"
    printf '%s %s' "$current" "$fails" > "$STATE_FILE"
    [[ "$current" == "up" ]]
}

# Exit non-zero while any address is down, so cron mail (if configured) carries it and a
# human running the script by hand sees the failure in `$?`.
all_up=0
for url in $HEALTH_URLS; do
    probe "$url" || all_up=1
done
exit "$all_up"
