// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useT } from '../i18n'

export type Reflection = {
  reflection: string; hopes: string[]; worries: string[]; persona: string | null; unavailable?: boolean
}

// "Here's what we heard": the AI's reflection of the user's story, with the hopes and worries
// it found. Shared by onboarding and the profile page.
export function StoryReflection({ reflection }: { reflection: Reflection }) {
  const { t } = useT()
  return (
    <div role="status" className="mt-4 rounded-lg border border-amber-200 bg-amber-50/50 p-4">
      <p className="text-xs uppercase tracking-wide text-amber-900/70 mb-1">{t.onboarding.story.heard}</p>
      <p className="font-serif text-[17px] leading-relaxed text-turquoise-900">{reflection.reflection}</p>
      {(reflection.hopes.length > 0 || reflection.worries.length > 0) && (
        <div className="mt-3 grid sm:grid-cols-2 gap-3 text-sm">
          {reflection.hopes.length > 0 && (
            <div>
              <p className="text-xs font-medium text-emerald-800 mb-1">{t.onboarding.story.hopes}</p>
              <ul className="space-y-0.5">{reflection.hopes.map((h) => <li key={h}>· {h}</li>)}</ul>
            </div>
          )}
          {reflection.worries.length > 0 && (
            <div>
              <p className="text-xs font-medium text-amber-900 mb-1">{t.onboarding.story.worries}</p>
              <ul className="space-y-0.5">{reflection.worries.map((w) => <li key={w}>· {w}</li>)}</ul>
            </div>
          )}
        </div>
      )}
      <p className="mt-3 text-xs text-turquoise-800/60">{t.onboarding.story.notRight}</p>
    </div>
  )
}
