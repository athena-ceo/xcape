// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { VoiceInput } from '../components/VoiceInput'
import { useT } from '../i18n'
import { api } from '../services/api'

const HOUSEHOLDS = ['single', 'couple', 'family'] as const
type Household = (typeof HOUSEHOLDS)[number]

// Scaffold: a single baseline question. The full progressive flow (reasons, budget,
// climate, language, buy vs rent, weights) is a build-phase task — see plan §6.
export function Onboarding() {
  const { t } = useT()
  const navigate = useNavigate()
  const [household, setHousehold] = useState<Household | null>(null)
  const [busy, setBusy] = useState(false)

  async function next() {
    if (!household) return
    setBusy(true)
    try {
      await api.updateProfile({ household_type: household })
      const search = await api.createSearch(t.shortlist.title)
      await api.buildShortlist(search.id)
      navigate(`/shortlist/${search.id}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="max-w-xl mx-auto px-5 py-12">
      <div className="bg-turquoise-50 rounded-xl p-5">
        <p className="text-sm text-turquoise-600 mb-1">
          {t.onboarding.step} 3 {t.onboarding.of} 6
        </p>
        <div className="h-1.5 bg-turquoise-100 rounded-full mb-6">
          <div className="h-full w-1/2 bg-turquoise-400 rounded-full" />
        </div>

        <div className="bg-white rounded-xl p-6 border border-turquoise-100">
          <h1 className="text-xl font-medium text-turquoise-900 mb-4">{t.onboarding.household}</h1>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
            {HOUSEHOLDS.map((h) => (
              <button
                key={h}
                onClick={() => setHousehold(h)}
                className={`rounded-lg border p-4 text-sm ${
                  household === h
                    ? 'border-turquoise-400 bg-turquoise-50 text-turquoise-600'
                    : 'border-turquoise-100'
                }`}
              >
                {t.onboarding[h]}
              </button>
            ))}
          </div>

          <div className="border border-turquoise-100 rounded-md px-3 py-2 mb-5">
            <VoiceInput onTranscript={() => {}} label={t.onboarding.voiceHint} />
          </div>

          <button
            disabled={!household || busy}
            onClick={next}
            className="w-full bg-turquoise-600 text-turquoise-50 rounded-md py-2.5 disabled:opacity-50"
          >
            {busy ? t.common.loading : t.onboarding.continue}
          </button>
        </div>
      </div>
    </main>
  )
}
