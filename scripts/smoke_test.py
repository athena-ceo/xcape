#!/usr/bin/env python3
# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""End-to-end smoke test against a running xCape backend.

Exercises the key non-AI flows so each push (and each deploy) is validated:
health, registration (names + current-country default), profile, instant shortlist,
current-country baseline + comparison deltas, and graceful chat without an API key.

Usage: SMOKE_BASE_URL=http://localhost:8030 python3 scripts/smoke_test.py
Exits non-zero if any check fails.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("SMOKE_BASE_URL", "http://localhost:8030").rstrip("/")
API = f"{BASE}/api/v1"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def call(method: str, path: str, token: str | None = None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None


def wait_for_health(retries: int = 40) -> bool:
    for _ in range(retries):
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def main() -> int:
    check("health endpoint responds", wait_for_health())

    email = f"smoke-{int(time.time())}@example.com"
    st, reg = call("POST", "/auth/register", body={
        "email": email, "password": "password123", "locale": "fr",
        "first_name": "CI", "last_name": "Bot",
    })
    check("register returns 201", st == 201, f"status={st}")
    token = reg.get("access_token") if isinstance(reg, dict) else None
    check("register returns a token", bool(token))
    if not token:
        return _finish()

    st, me = call("GET", "/auth/me", token)
    check("me carries names + default current country",
          isinstance(me, dict) and me.get("first_name") == "CI" and me.get("current_country") == "France",
          str(me))

    st, _ = call("PUT", "/profile", token, {
        "household_type": "couple", "reasons_leaving": ["politics", "cost"], "climate_pref": "warm",
    })
    check("profile update returns 200", st == 200, f"status={st}")

    st, search = call("POST", "/searches", token, {"title": "CI"})
    check("create search returns 201", st == 201, f"status={st}")
    sid = search.get("id") if isinstance(search, dict) else None
    if not sid:
        return _finish()

    st, cands = call("POST", f"/searches/{sid}/shortlist", token)
    check("shortlist returns 200", st == 200, f"status={st}")
    n = len(cands) if isinstance(cands, list) else 0
    check("shortlist is non-empty", n > 0, f"n={n}")
    if isinstance(cands, list) and cands:
        scores = [c["match_score"] for c in cands]
        check("shortlist sorted by score desc", scores == sorted(scores, reverse=True))

    st, base = call("GET", f"/searches/{sid}/baseline", token)
    check("baseline resolves to France",
          isinstance(base, dict) and base.get("name") == "France",
          str(base.get("name") if isinstance(base, dict) else base))

    st, cands2 = call("GET", f"/searches/{sid}/candidates", token)
    check("candidates carry vs_current deltas",
          isinstance(cands2, list) and any(c.get("vs_current") for c in cands2))

    # No OpenAI key in CI: the chat endpoint must still return 200 with a graceful reply.
    st, msg = call("POST", f"/searches/{sid}/chat", token, {"message": "Test?"})
    check("chat degrades gracefully (200)",
          st == 200 and isinstance(msg, dict) and bool(msg.get("reply")), f"status={st}")

    return _finish()


def _finish() -> int:
    if failures:
        print(f"\n{len(failures)} smoke check(s) FAILED: {failures}")
        return 1
    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
