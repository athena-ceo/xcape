<!-- Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved. -->
<!-- Proprietary and confidential — unauthorized copying or distribution is prohibited. -->

# xCape — iOS App Store Packaging (Backlog Plan)

**Status:** Backlog candidate (not scheduled). Drafted 2026-06-26.

**Goal:** Ship the existing web app to the **Apple App Store** with **minimum code changes**,
as a **consumer subscription** product. Keep the project **Android-ready** (Play submission a
small follow-up), but plan/submit iOS first.

---

## Decisions (confirmed 2026-06-26)

- **Approach:** Wrap the existing build with **Capacitor** (native WebView shell), web assets
  **bundled into the binary**; API still hits the production backend.
- **Monetization:** **Apple In-App Purchase** (StoreKit) for a consumer subscription — via
  **RevenueCat** + a Capacitor plugin, with backend entitlement mapping. This is the largest
  added scope.
- **Platforms:** iOS now; keep the Capacitor project so `cap add android` + Play is a small
  follow-up.

---

## Why Capacitor (not React Native / not remote-URL wrapper)

- **Minimum code changes:** Capacitor loads the existing `dist/` (Vite + React 18 SPA) unchanged
  and exposes native plugins (share, filesystem, push, mic, IAP). React Native/Expo would be a
  rewrite — rejected.
- **Bundled assets, not a remote URL:** pointing Capacitor's `server.url` at the hosted site is
  the fast path but Apple routinely rejects it under Guideline 4.2 ("just a website"). Bundle the
  build; call the remote API over HTTPS.
- **One codebase → both stores:** the same project yields Android via `cap add android`.

### Current stack (grounding)

- Vite + React 18 SPA, `react-router-dom` (client-side routing), `zustand`, `fetch` client.
- Auth: JWT in `localStorage('xcape_token')` (`src/store/auth.ts`, `src/services/api.ts`).
- API base: `VITE_API_URL` env (`src/services/api.ts:4`), default `http://localhost:8030`.
- No PWA/service worker. `apple-touch-icon.png` already present.
- Browser features that matter in a WebView:
  - **Voice capture** — `getUserMedia` + `MediaRecorder` (`src/components/VoiceButton.tsx`);
    code already handles iOS `MediaRecorder` quirks. Needs mic permission in Info.plist.
  - **PDF report download** — blob + `URL.createObjectURL` + `<a download>`
    (`src/services/api.ts:136-150`, used by `ComparisonPlayground.tsx`). **The `download`
    attribute does nothing in iOS WKWebView** — this is the one feature that genuinely breaks and
    must be re-routed through a native share/save.

---

## Engineering changes (small)

1. **Add Capacitor** — `@capacitor/core`, `@capacitor/cli`, `@capacitor/ios`;
   `cap init` (`webDir: dist`); `cap add ios`. Adds `capacitor.config.ts` + an `ios/` Xcode
   project. Build stays `vite build` then `cap sync`.
2. **Point mobile build at prod** — `VITE_API_URL=https://apps.athenadecisions.com` (backend);
   add the app origin (`capacitor://localhost` / `https://localhost`) to backend CORS allowlist.
3. **Native PDF export** (the one real breakage) — when `Capacitor.isNativePlatform()`, write the
   report blob via `@capacitor/filesystem` and present `@capacitor/share` (native share sheet)
   instead of `<a download>`. Isolated change in `api.ts` / `ComparisonPlayground.tsx`.
4. **Microphone** — `NSMicrophoneUsageDescription` in Info.plist; allow `getUserMedia` in the
   WebView config. (WKWebView supports it iOS 14.3+.)
5. **Safe-area + chrome** — `env(safe-area-inset-*)` padding so the header clears the notch;
   `@capacitor/status-bar` + `@capacitor/splash-screen`; generate app-icon set.
6. **External links** open in the system browser via `@capacitor/browser` (don't navigate the
   app WebView away).
7. **(Polish) token storage** — move `xcape_token` to `@capacitor/preferences`/Keychain.
   localStorage persists in WKWebView, so this is optional, not a blocker.

---

## In-App Purchase (the heavy part)

**Stack:** `@revenuecat/purchases-capacitor` (wraps StoreKit) + RevenueCat dashboard.

- **App Store Connect:** define the subscription group + products (e.g. monthly / annual);
  fill metadata, pricing, and a review-test account.
- **Client:** a paywall screen; `Purchases.configure(apiKey, appUserId=<xCape user id>)`;
  purchase + **"Restore purchases"** (Apple-required); gate premium features on the active
  entitlement.
- **Backend entitlement mapping:** add a subscription status/tier field to the user; consume a
  **RevenueCat webhook** (or verify via RevenueCat REST API) to mark entitlement
  active/expired server-side, so the backend — not just the client — is the source of truth
  (consistent with "server is source of truth"). Existing email/password auth stays; map the
  RevenueCat app-user-id to the xCape user.
- **Anti-steering:** keep purchasing inside IAP; do not link to external web payment from the
  iOS app.
- **Existing web subscribers:** decide cross-platform entitlement (a user who paid on the web
  should be premium in the app) — backend entitlement check covers this; the app reads server
  state in addition to RevenueCat.

---

## App Store review checklist

- **3.1.1 IAP** — covered by the IAP work above (digital subscription consumed in-app ⇒ must use
  StoreKit).
- **5.1.1(v) Account deletion** — required in-app. Deletion already exists
  (`backend/.../tests/test_account_delete.py`); ensure it's reachable from a settings screen.
- **4.2 Minimum functionality** — bundled assets + native mic + native share + push notifications
  give enough native surface to avoid a "just a website" rejection.
- **4.8 Sign in with Apple** — required only if third-party/social login is offered. Email/password
  today ⇒ not required; consider adding it to lift iOS conversion.
- **Privacy** — privacy-policy URL; App Privacy "nutrition labels" (email, usage; disclose content
  sent to OpenAI); `ITSAppUsesNonExemptEncryption=false`; ATT only if tracking across apps (not
  currently).
- **Logistics** — Apple Developer Program ($99/yr); a Mac + Xcode to build/sign/submit; TestFlight
  for beta.

---

## Suggested sequencing (each independently demoable)

- **A. Wrapper boots** — add Capacitor, bundle the build, run on a simulator/device against prod
  API; fix safe-area + status bar. (small)
- **B. Native fixes** — PDF share + microphone permission verified on a real device. (small)
- **C. IAP** — RevenueCat client paywall + restore; backend entitlement webhook + gating.
  (medium, the bulk of the work)
- **D. Compliance + submit** — account-deletion screen reachable, privacy labels, icons/splash,
  privacy policy, TestFlight, submit. (medium, mostly non-code)
- **E. (Later) Android** — `cap add android`, Play billing nuances, Play submission. (follow-up)

**Start with A** — it's mechanical and proves the whole app runs natively before investing in IAP.

---

## Risks to watch

- **iOS WKWebView PDF/download** — must be re-routed natively (item 3); easy to miss until tested
  on a device.
- **IAP review friction** — most first-submission rejections are IAP metadata / restore-purchases
  / entitlement issues; budget a review round-trip.
- **Cross-platform entitlement** — web-paid vs app-paid users must resolve to one server-side
  truth, or users get double-charged / wrongly gated.
- **Mic permission UX** — first voice use must request permission gracefully; denied state already
  partly handled in `VoiceButton.tsx`.
- **Layout on device** — re-check notch/safe-area and the comparison board (`table-fixed` wrapping
  added 2026-06-26) on real screen sizes.

---

## Key file references

- API client / base URL / PDF download: `src/services/api.ts`
- Auth token store: `src/store/auth.ts`
- PDF export trigger: `src/pages/ComparisonPlayground.tsx`
- Voice capture: `src/components/VoiceButton.tsx`, `src/components/VoiceField.tsx`
- Build config: `vite.config.ts`, `package.json`, `index.html`
- (New) `capacitor.config.ts`, `ios/` Xcode project
- Backend CORS + (new) subscription entitlement: `backend/app/` (config + user model + a
  RevenueCat webhook endpoint)
