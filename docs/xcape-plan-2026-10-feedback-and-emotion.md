<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape — plan from the October 2026 user feedback, and the emotional-appeal roadmap

Agreed with Harley on 2026-10-25. Part A fixes what testers reported. Part B adds the
emotional side a friend found missing: "good at comparing facts, but it doesn't tug at the
heartstrings". Steps run in order and each one ships on its own.

## Part A — feedback fixes

### What testers reported (2026-10-25)

1. The home country (first comparison column) is scored as if the user were a foreigner
   there: visa difficulty, newcomer access to healthcare, and so on.
2. On phones the table and other wide layouts are painful to use.
3. The assistant "returns silently to the prompt".
4. Spain did not reach the top 5 for a user whose criteria fit it, and the app never said
   why. A second user (US citizen, Polish ancestry, Portuguese speaker) never saw Portugal
   or Brazil. Mauritius and Uruguay appeared on almost every board.
5. `xcape.sh` had fallen far behind `golden-path.sh`.

### Step 1 — Assistant reliability + admin Errors tab + `xcape.sh` prod safety ✅ (`ade5c66`)

Root cause of item 3: the model answered in 4–7 s, but the iPhone dropped the request first
(nginx 499, the phone's IP changed mid-session), and the chat panel had no error path.
CHANGELOG 2026-10-25 has the details.

### Step 2 — Fairer visa scoring ✅ (`ade5c66`)

Root causes of item 4:

- The household was judged by its most restrictive passport, which ignored that an EU
  citizen's family shares EU free-movement rights.
- EU countries got a flat "hard" visa score for any non-EU passport.
- Visa ease came from a seed bucket curated for only 29 of 219 countries.
- The retiree profile counted visa ease twice.
- Climate scoring was binary.

Checked against prod data: Portugal 14 → 19 boards, Spain 7 → 10, Mauritius 10 → 4,
Uruguay 10 → 2. After deploying, run `./xcape.sh rescore prod --repopulate --dry-run`, then
the same command without `--dry-run`.

Still open: Brazil is excluded by the retiree default filter "safety at least OK" (it
scores 40/100). That is legitimate, but it must be explained; step 4 covers it.

### Step 3 — Home-country handling ✅

- Immigration criteria in the home column show "N/A — you live here" and are left out of
  the home score: visa, residency by income or investment, expat community, language, and
  visa-programme custom criteria such as "Retirement visa".
- Newcomer-access criteria (healthcare, education) use the resident **quality** sub-score at
  home instead of the "how a newcomer gets access" score.
- The country page for the home country hides the visa-route, golden-visa and
  income-pathway panels and says "you live here".
- Bug fix: the PDF report's home column scored every AI-researched criterion as 0.5 (no
  evals were passed in).

### Step 4 — "Why not X?" + grounded assistant ✅

- `GET /searches/{id}/why/{place_id}` returns:
  - the country's rank among all countries;
  - its score against the user's #5;
  - the filter that excludes it, if any;
  - the criteria where it loses most points against #5.
- Shown as a bottom sheet (mockup C), opened from Explore and from the "add country"
  picker. Actions: add anyway, relax the filter, ask the assistant.
- The same data becomes a read-only assistant tool, so "why not Spain?" is answered from
  the real scores instead of invented reasons.

### Step 5 — Mobile layout ✅

Mockups: <https://claude.ai/artifact/Vz1hy7jgJwBVdEi7RsRpCK>.

- **A. Country cards:** one swipeable card per country, with the home value shown in small
  text under each criterion. This becomes the phone default.
- **B. Head-to-head:** pick any two countries, home included. One tap away from A.
- **Header:** a menu button instead of the wrapping nav.
- **Criteria settings:** stacked rows instead of a table.
- **Score explanation:** a list instead of a table.

### Step 6 — Rest of the `xcape.sh` port from golden-path ✅ (uptime probe: follow-up)

- A read-only `psql <env> "<SELECT>"` command.
- Compressed, rotated backups in `/data/backups/xcape`. The existing nightly offsite job
  already copies that folder.
- A `restore-backup` command with `--rehearse-into`.
- Migrations run in a one-off container before the new backend starts.
- `schema-check` (`alembic check`) and `typecheck`.
- `prune-images`.
- The xcape health URL added to the uptime probe.

## Part B — emotional appeal (after Part A)

The app is strong on the **white hat** (facts). The six thinking hats give a frame for the
rest, and most items reuse machinery that already exists.

| # | Feature | Hat | What it is | Builds on |
|---|---|---|---|---|
| 1 | **Your story** | Red | Onboarding opens with "tell us your situation, hopes and worries" (typed or dictated). The AI turns it into criteria and weights, then **reflects it back** in plain words: "Here's what I heard: sun, the grandchildren within a short flight, calm." The user confirms or edits. | `criteria_select.suggest` (free text → criteria), `VoiceField` |
| 2 | **Hearts** | Red | Heart a country anywhere (board, Explore, country page). A "My hearts" shelf follows the user. A heart is a gentle preference signal, unlike a pin, which forces a country onto the board. | the candidate `override` mechanism; a new per-user hearts table |
| 3 | **Postcard from your future** | Red + Yellow | On each country page, a short personalised "a Tuesday in Valencia" story for this household, clearly labelled as imagined, with a strong photo. | one AI call per (country, user), cached; the media assets |
| 4 | **Pre-mortem** | Black | Beside the postcard: "Two years in, you're unhappy here. Here's why that might be", specific to the profile and grounded in the existing risk and trend data. | the trend metrics and per-criterion evaluations |
| 5 | **Heart vs numbers** | Red ↔ White | When a hearted country ranks low: "Your heart says Spain, the numbers say Cyprus. Here's the gap, and what would close it." | step 4's "why not X?" |
| 6 | **Hopes & fears scorecard** | Red, in the user's words | The user's top 3 hopes and top 3 fears, in their own words, shown as ✓/✗ on every country instead of criteria jargon. | the custom-criteria evaluation (each hope or fear becomes a custom criterion) |
| 7 | **Photo gut-check** | Red | Swipe 15–20 photos of people in everyday places, each tagged excites / worries / meh. This feeds a modest "gut feeling" criterion, and photo themes (coast, mountains, big city) nudge the nature, climate and culture weights. | needs a licensed photo source (Unsplash or Wikimedia, with credits) |
| 8 | **Wildcards, visible** | Green | "A country you didn't consider, strong on what matters most to you." | `shortlist.wildcards` (computed, barely shown) |

**First slice shipped (2026-10-25): 1, 2, 3 and 4.** Hearts are a marker and a shelf, not a score input (keeps every number identical across board, explanations and assistant); their emotional weight comes in item 5. Second slice shipped (2026-10-25): 5 (heart vs numbers panel), 6 (hopes & worries as scored story criteria, first on the board) and 8 ("Something different" card). Remaining: 7 (photo gut-check) once a photo source is chosen; and a way for users who onboarded before the story existed to write one (e.g. from the profile page).

**Recommended first slice:** 1 + 2 + 3/4. They need no image licensing, reuse existing
services, and the postcard fits mobile layout A naturally. Item 7 follows once a photo
source is chosen; items 5, 6 and 8 build on step 4 and on items 1–2.

**Guardrails:**

- Every emotional element is clearly framed (imagined, a gut feeling) and never presented as
  fact.
- Gut signals adjust the ranking modestly; they don't override hard filters.
- Pre-mortems stay candid, not alarmist.
- All copy goes in `fr.ts` and `en.ts`; French is the default.
