// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { VoiceField } from '../components/VoiceField'
import { useT } from '../i18n'
import { api } from '../services/api'

type StepId =
  | 'currentCountry'
  | 'household'
  | 'reasons'
  | 'budget'
  | 'tenure'
  | 'climate'
  | 'language'
  | 'priorities'

const STEPS: StepId[] = [
  'currentCountry', 'household', 'reasons', 'budget', 'tenure', 'climate', 'language', 'priorities',
]

const REASON_KEYS = [
  'politics', 'economy', 'safety', 'climate', 'cost', 'healthcare', 'lifestyle', 'career',
] as const
const CLIMATE_KEYS = ['cold', 'temperate', 'mild', 'warm', 'tropical'] as const
const PRIORITY_KEYS = [
  'cost_of_living', 'healthcare', 'safety', 'political_stability',
  'climate', 'language_ease', 'tax', 'visa', 'nature',
] as const

interface Answers {
  current_country: string
  household_type: string | null
  reasons_leaving: string[]
  budget_monthly: number | null
  tenure: 'rent' | 'buy' | null
  climate_pref: string | null
  willing_to_learn: boolean | null
  priorities: string[]
}

const EMPTY: Answers = {
  current_country: '',
  household_type: null,
  reasons_leaving: [],
  budget_monthly: null,
  tenure: null,
  climate_pref: null,
  willing_to_learn: null,
  priorities: [],
}

function Chip({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg border px-4 py-2.5 text-sm text-left transition ${
        active ? 'border-turquoise-400 bg-turquoise-50 text-turquoise-600'
               : 'border-turquoise-100 hover:border-turquoise-200'
      }`}
    >
      {children}
    </button>
  )
}

export function Onboarding() {
  const { t } = useT()
  const navigate = useNavigate()
  const [index, setIndex] = useState(0)
  const [a, setA] = useState<Answers>(EMPTY)
  const [busy, setBusy] = useState(false)

  // Pre-fill the current country with the value detected at registration.
  useEffect(() => {
    api.me().then((me) => {
      if (me.current_country) setA((cur) => ({ ...cur, current_country: me.current_country! }))
    })
  }, [])

  const step = STEPS[index]
  const isLast = index === STEPS.length - 1

  function toggle<T extends string>(list: T[], value: T, max = Infinity): T[] {
    if (list.includes(value)) return list.filter((v) => v !== value)
    if (list.length >= max) return list
    return [...list, value]
  }

  // Each step is "answered enough" to advance; most are optional.
  const canAdvance =
    step === 'household' ? !!a.household_type
    : step === 'currentCountry' ? !!a.current_country.trim()
    : true

  async function finish() {
    setBusy(true)
    try {
      await api.updateMe({ current_country: a.current_country.trim() })
      await api.updateProfile({
        household_type: a.household_type,
        reasons_leaving: a.reasons_leaving,
        budget_monthly: a.budget_monthly,
        tenure: a.tenure,
        climate_pref: a.climate_pref,
        language_skills: { willing_to_learn: !!a.willing_to_learn },
        criteria_weights: Object.fromEntries(a.priorities.map((k) => [k, 2.0])),
      })
      const search = await api.createSearch(t.shortlist.title)
      await api.buildShortlist(search.id)
      navigate(`/shortlist/${search.id}`)
    } finally {
      setBusy(false)
    }
  }

  function onNext() {
    if (isLast) finish()
    else setIndex((i) => i + 1)
  }

  return (
    <main className="max-w-xl mx-auto px-5 py-12">
      <p className="text-center text-turquoise-800/70 mb-6">{t.onboarding.intro}</p>
      <div className="bg-turquoise-50 rounded-xl p-5">
        <p className="text-sm text-turquoise-600 mb-1">
          {t.onboarding.stepLabel} {index + 1} {t.onboarding.of} {STEPS.length}
        </p>
        <div className="h-1.5 bg-turquoise-100 rounded-full mb-6">
          <div
            className="h-full bg-turquoise-400 rounded-full transition-all"
            style={{ width: `${((index + 1) / STEPS.length) * 100}%` }}
          />
        </div>

        <div className="bg-white rounded-xl p-6 border border-turquoise-100">
          {step === 'currentCountry' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-1">{t.onboarding.currentCountry.q}</h1>
              <p className="text-sm text-turquoise-800/60 mb-4">{t.onboarding.currentCountry.hint}</p>
              <VoiceField
                value={a.current_country}
                onChange={(v) => setA({ ...a, current_country: v })}
                placeholder="France"
              />
            </>
          )}

          {step === 'household' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-4">{t.onboarding.household.q}</h1>
              <div className="grid sm:grid-cols-3 gap-3">
                {(['single', 'couple', 'family'] as const).map((h) => (
                  <Chip key={h} active={a.household_type === h}
                    onClick={() => setA({ ...a, household_type: h })}>
                    {t.onboarding.household[h]}
                  </Chip>
                ))}
              </div>
            </>
          )}

          {step === 'reasons' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-1">{t.onboarding.reasons.q}</h1>
              <p className="text-sm text-turquoise-800/60 mb-4">{t.onboarding.reasons.hint}</p>
              <div className="grid sm:grid-cols-2 gap-3">
                {REASON_KEYS.map((r) => (
                  <Chip key={r} active={a.reasons_leaving.includes(r)}
                    onClick={() => setA({ ...a, reasons_leaving: toggle(a.reasons_leaving, r) })}>
                    {t.onboarding.reasons[r]}
                  </Chip>
                ))}
              </div>
            </>
          )}

          {step === 'budget' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-1">{t.onboarding.budget.q}</h1>
              <p className="text-sm text-turquoise-800/60 mb-4">{t.onboarding.budget.hint}</p>
              <div className="flex items-center gap-2">
                <input
                  type="number" min={0} step={100}
                  value={a.budget_monthly ?? ''}
                  onChange={(e) => setA({ ...a, budget_monthly: e.target.value ? Number(e.target.value) : null })}
                  className="w-40 border border-turquoise-100 rounded-md px-3 py-2"
                  placeholder="2000"
                />
                <span className="text-turquoise-800/70">{t.onboarding.budget.suffix}</span>
              </div>
            </>
          )}

          {step === 'tenure' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-4">{t.onboarding.tenure.q}</h1>
              <div className="grid sm:grid-cols-3 gap-3">
                {([['rent', 'rent'], ['buy', 'buy'], ['either', null]] as const).map(([label, val]) => (
                  <Chip key={label} active={a.tenure === val}
                    onClick={() => setA({ ...a, tenure: val })}>
                    {t.onboarding.tenure[label]}
                  </Chip>
                ))}
              </div>
            </>
          )}

          {step === 'climate' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-4">{t.onboarding.climate.q}</h1>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {CLIMATE_KEYS.map((c) => (
                  <Chip key={c} active={a.climate_pref === c}
                    onClick={() => setA({ ...a, climate_pref: c })}>
                    {t.onboarding.climate[c]}
                  </Chip>
                ))}
              </div>
            </>
          )}

          {step === 'language' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-1">{t.onboarding.language.q}</h1>
              <p className="text-sm text-turquoise-800/60 mb-4">{t.onboarding.language.hint}</p>
              <div className="grid gap-3">
                <Chip active={a.willing_to_learn === true}
                  onClick={() => setA({ ...a, willing_to_learn: true })}>
                  {t.onboarding.language.willing}
                </Chip>
                <Chip active={a.willing_to_learn === false}
                  onClick={() => setA({ ...a, willing_to_learn: false })}>
                  {t.onboarding.language.notWilling}
                </Chip>
              </div>
            </>
          )}

          {step === 'priorities' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-1">{t.onboarding.priorities.q}</h1>
              <p className="text-sm text-turquoise-800/60 mb-4">{t.onboarding.priorities.hint}</p>
              <div className="grid sm:grid-cols-2 gap-3">
                {PRIORITY_KEYS.map((k) => (
                  <Chip key={k} active={a.priorities.includes(k)}
                    onClick={() => setA({ ...a, priorities: toggle(a.priorities, k, 3) })}>
                    {t.criteria[k]}
                  </Chip>
                ))}
              </div>
            </>
          )}

          <div className="mt-6 flex items-center gap-3">
            {index > 0 && (
              <button onClick={() => setIndex((i) => i - 1)}
                className="border border-turquoise-100 rounded-md px-4 py-2.5 text-sm">
                {t.onboarding.back}
              </button>
            )}
            <button
              disabled={!canAdvance || busy}
              onClick={onNext}
              className="flex-1 bg-turquoise-600 text-turquoise-50 rounded-md py-2.5 disabled:opacity-50"
            >
              {busy ? t.common.loading : isLast ? t.onboarding.finish : t.onboarding.continue}
            </button>
          </div>
        </div>
      </div>
    </main>
  )
}
