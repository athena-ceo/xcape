// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

// In-progress onboarding state, saved to localStorage so a user who leaves mid-wizard resumes
// where they left off (same browser). Written as the user advances; cleared when onboarding
// finishes, on "New request" (start over), and on logout (so the next user doesn't inherit it).
const KEY = 'xcape_onboarding_draft'

export interface OnboardingDraft {
  index: number          // current step
  a: unknown             // the Answers object (typed in Onboarding.tsx)
  persona: string | null // selected persona key (drives the dynamic step list)
}

export function loadDraft(): OnboardingDraft | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const d = JSON.parse(raw)
    return d && typeof d === 'object' && d.a ? (d as OnboardingDraft) : null
  } catch {
    return null
  }
}

export function saveDraft(d: OnboardingDraft): void {
  try { localStorage.setItem(KEY, JSON.stringify(d)) } catch { /* quota / private mode — ignore */ }
}

export function clearDraft(): void {
  try { localStorage.removeItem(KEY) } catch { /* ignore */ }
}
