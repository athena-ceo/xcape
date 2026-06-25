// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Chip } from '../components/Chip'
import { CommunitySelect } from '../components/CommunitySelect'
import { CountryMultiSelect } from '../components/CountryMultiSelect'
import { LanguageMultiSelect } from '../components/LanguageMultiSelect'
import { Spinner } from '../components/Spinner'
import { VoiceField } from '../components/VoiceField'
import {
  CLIMATE_KEYS, HERITAGE_KEYS, HOUSEHOLDS, LOCALE_LANGUAGE, toggle,
} from '../data/profileOptions'
import { useT } from '../i18n'
import { api } from '../services/api'
import { labelOf, useCriteria, type Persona } from '../services/criteria'
import { clearDraft, loadDraft, saveDraft } from '../services/onboardingDraft'
import { useAuth } from '../store/auth'

type StepId =
  | 'currentCountry'
  | 'citizenship'
  | 'household'
  | 'persona'
  | 'communities'
  | 'budget'
  | 'climate'
  | 'language'

// The user picks a persona directly (no guessing); it then gates which optional follow-up
// steps are shown (persona.ask). 'language' is universal and shown last.
const BASE_STEPS: StepId[] = ['currentCountry', 'citizenship', 'household', 'persona']
const GATED_STEPS: StepId[] = ['communities', 'budget', 'climate']

interface Answers {
  current_country: string
  citizenships: string[]
  ancestry_countries: string[]
  heritages: string[]
  household_type: string | null
  intends_children: boolean | null
  reasons_leaving: string[]
  minority_groups: string[]
  budget_monthly: number | null
  annual_income: number | null
  investable_amount: number | null
  tenure: 'rent' | 'buy' | null
  climate_pref: string | null
  known_languages: string[]
  willing_to_learn: boolean | null
  priorities: string[]
  priorities_text: string
}

const EMPTY: Answers = {
  current_country: '',
  citizenships: [],
  ancestry_countries: [],
  heritages: [],
  household_type: null,
  intends_children: null,
  reasons_leaving: [],
  minority_groups: [],
  budget_monthly: null,
  annual_income: null,
  investable_amount: null,
  tenure: null,
  climate_pref: null,
  known_languages: [],
  willing_to_learn: null,
  priorities: [],
  priorities_text: '',
}

export function Onboarding() {
  const { t, lang } = useT()
  const reg = useCriteria()
  const navigate = useNavigate()
  const refreshAuth = useAuth((s) => s.refresh)
  const [index, setIndex] = useState(0)
  const [a, setA] = useState<Answers>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [persona, setPersona] = useState<Persona | null>(null)
  const [savedPersonaKey, setSavedPersonaKey] = useState<string | null>(null)
  // Gate draft-saving until hydration (draft restore OR server pre-fill) has settled, so the
  // initial empty state never clobbers a saved draft.
  const hydratedRef = useRef(false)

  // On mount: resume an in-progress draft if one exists; otherwise pre-fill from the saved
  // profile (so "New request" lets a returning user tweak and re-run rather than re-enter
  // everything). Runs ONCE — an async locale change can't overwrite answers mid-selection.
  useEffect(() => {
    const draft = loadDraft()
    if (draft) {
      if (draft.a) setA({ ...EMPTY, ...(draft.a as Partial<Answers>) })  // tolerate older draft shapes
      if (typeof draft.index === 'number') setIndex(Math.max(0, draft.index))
      if (draft.persona) setSavedPersonaKey(draft.persona)
      hydratedRef.current = true
      return
    }
    Promise.all([
      api.me().then((me) => {
        setA((cur) => ({
          ...cur,
          current_country: me.current_country ?? cur.current_country,
          citizenships: me.citizenships ?? cur.citizenships,
          ancestry_countries: me.ancestry_countries ?? cur.ancestry_countries,
          heritages: me.heritages ?? cur.heritages,
        }))
      }).catch(() => {}),
      api.getProfile().then((p: any) => {
        const known: string[] | undefined = p?.language_skills?.known
        setSavedPersonaKey(p?.persona ?? null)  // pre-select the returning user's previous profile
        setA((cur) => ({
          ...cur,
          household_type: p?.household_type ?? cur.household_type,
          intends_children: p?.intends_children ?? cur.intends_children,
          reasons_leaving: p?.reasons_leaving ?? cur.reasons_leaving,
          minority_groups: p?.minority_groups ?? cur.minority_groups,
          budget_monthly: p?.budget_monthly ?? cur.budget_monthly,
        annual_income: p?.annual_income ?? cur.annual_income,
        investable_amount: p?.investable_amount ?? cur.investable_amount,
          tenure: p?.tenure ?? cur.tenure,
          climate_pref: p?.climate_pref ?? cur.climate_pref,
          priorities: Object.keys(p?.criteria_weights ?? {}),
          priorities_text: p?.priorities_text ?? cur.priorities_text,
          known_languages: known?.length ? known : [LOCALE_LANGUAGE[lang] ?? 'English'],
          willing_to_learn: p?.language_skills?.willing_to_learn ?? cur.willing_to_learn,
        }))
      }).catch(() => {}),
    ]).finally(() => { hydratedRef.current = true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Persist the in-progress draft (step + answers + persona) on every change, once hydrated.
  useEffect(() => {
    if (!hydratedRef.current) return
    saveDraft({ index, a, persona: persona?.key ?? null })
  }, [index, a, persona])

  // Steps are dynamic: until a persona is chosen the wizard ends at the picker; once chosen,
  // the persona's `ask` gates which optional follow-ups appear (then language, last).
  const STEPS = useMemo<StepId[]>(() => {
    if (!persona) return BASE_STEPS
    const ask = persona.ask ?? GATED_STEPS
    return [...BASE_STEPS, ...GATED_STEPS.filter((g) => ask.includes(g)), 'language']
  }, [persona])
  // While a resumed persona is still loading, the step list is shorter than the saved index, so
  // clamp the VIEW (never the stored index) — once the persona resolves, stepIdx === index again.
  const stepIdx = Math.min(index, Math.max(0, STEPS.length - 1))
  const step = STEPS[stepIdx]
  const isLast = stepIdx === STEPS.length - 1

  // Once the registry has loaded, pre-select the returning user's saved persona in the picker.
  useEffect(() => {
    if (savedPersonaKey && !persona) {
      const found = (reg?.personas ?? []).find((p) => p.key === savedPersonaKey)
      if (found) setPersona(found)
    }
  }, [savedPersonaKey, reg]) // eslint-disable-line react-hooks/exhaustive-deps

  // Each step is "answered enough" to advance; most are optional.
  const canAdvance =
    step === 'household' ? !!a.household_type
    : step === 'currentCountry' ? !!a.current_country.trim()
    : step === 'persona' ? !!persona
    : true

  const personaList: Persona[] = reg?.personas ?? []
  function personaLabel(p: Persona | null): string {
    return p ? ((lang === 'fr' ? p.label_fr : p.label_en) || p.label_en) : ''
  }
  function personaBlurb(p: Persona | null): string {
    return p ? ((lang === 'fr' ? p.blurb_fr : p.blurb_en) || p.blurb_en || '') : ''
  }
  // The criteria a persona will focus on (its highest weights), for the confirm screen.
  function focusCriteria(p: Persona | null): string[] {
    const w = p?.weights ?? {}
    return Object.keys(w).sort((x, y) => (w[y] ?? 0) - (w[x] ?? 0)).slice(0, 5)
  }

  async function finish() {
    setBusy(true)
    try {
      await api.updateMe({ current_country: a.current_country.trim(), citizenships: a.citizenships, ancestry_countries: a.ancestry_countries, heritages: a.heritages })
      // Re-read identity from the server so the cached store reflects the new truth.
      await refreshAuth()
      await api.updateProfile({
        household_type: a.household_type,
        intends_children: a.intends_children,
        reasons_leaving: a.reasons_leaving,
        budget_monthly: a.budget_monthly,
        annual_income: a.annual_income,
        investable_amount: a.investable_amount,
        tenure: a.tenure,
        climate_pref: a.climate_pref,
        language_skills: { known: a.known_languages, willing_to_learn: !!a.willing_to_learn },
        criteria_weights: weightsFromPersona(),
        filters: filtersFromPersona(),
        minority_groups: a.minority_groups,
        persona: persona?.key,
        priorities_text: a.priorities_text.trim(),
      })
      const search = await api.createSearch(t.shortlist.title)
      await api.buildShortlist(search.id)
      // Add the persona's specific criteria (e.g. per-community tolerance, asset-tax, pension visa).
      await api.applyPersona(search.id).catch(() => {})
      // Free-text priorities → let the AI pick & weight extra criteria from them, so the
      // user's own words shape the comparison (best-effort; never blocks the flow).
      if (a.priorities_text.trim()) {
        await api.suggestCriteria(search.id, [], a.priorities_text.trim()).catch(() => {})
      }
      // Onboarding is done — drop the resume draft so a future visit starts clean.
      hydratedRef.current = false
      clearDraft()
      // Straight to the comparison table (pre-filled with the top matches) — the old
      // checklist step added friction without value.
      navigate(`/compare/${search.id}`)
    } finally {
      setBusy(false)
    }
  }

  // Initial weights = the chosen persona's default profile (the user fine-tunes on the board).
  function weightsFromPersona(): Record<string, number> {
    return { ...(persona?.weights ?? {}) }
  }
  // The persona's critical criteria default to an "exclude-bad" filter so countries rated
  // À éviter on them drop off automatically (the user can loosen via the relax banner). This
  // also REPLACES any stale filters from a previous search/onboarding.
  function filtersFromPersona(): Record<string, string> {
    const f: Record<string, string> = {}
    for (const k of persona?.filters ?? []) f[k] = 'ok'
    return f
  }

  function onNext() {
    if (isLast) finish()
    else setIndex(stepIdx + 1)
  }

  return (
    <main className="max-w-xl mx-auto px-5 py-12">
      <p className="text-center text-turquoise-800/70 mb-6">{t.onboarding.intro}</p>
      <div className="bg-turquoise-50 rounded-xl p-5">
        <p className="text-sm text-turquoise-600 mb-1">
          {t.onboarding.stepLabel} {stepIdx + 1} {t.onboarding.of} {STEPS.length}
        </p>
        <div className="h-1.5 bg-turquoise-100 rounded-full mb-6">
          <div
            className="h-full bg-turquoise-400 rounded-full transition-all"
            style={{ width: `${((stepIdx + 1) / STEPS.length) * 100}%` }}
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

          {step === 'citizenship' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-1">{t.onboarding.citizenship.q}</h1>
              <p className="text-sm text-turquoise-800/60 mb-4">{t.onboarding.citizenship.hint}</p>
              <CountryMultiSelect
                value={a.citizenships}
                onChange={(v) => setA({ ...a, citizenships: v })}
                addLabel={t.onboarding.citizenship.add}
              />
              <p className="text-sm font-medium text-turquoise-900 mt-5 mb-1">{t.onboarding.ancestry.q}</p>
              <p className="text-sm text-turquoise-800/60 mb-2">{t.onboarding.ancestry.hint}</p>
              <CountryMultiSelect
                value={a.ancestry_countries}
                onChange={(v) => setA({ ...a, ancestry_countries: v })}
                addLabel={t.onboarding.ancestry.add}
              />
              <p className="text-sm font-medium text-turquoise-900 mt-5 mb-1">{t.onboarding.heritage.q}</p>
              <p className="text-sm text-turquoise-800/60 mb-2">{t.onboarding.heritage.hint}</p>
              <div className="flex flex-wrap gap-2">
                {HERITAGE_KEYS.map((h) => (
                  <Chip key={h} active={a.heritages.includes(h)}
                    onClick={() => setA({ ...a, heritages: toggle(a.heritages, h) })}>
                    {(t.onboarding.heritage.options as Record<string, string>)[h]}
                  </Chip>
                ))}
              </div>
            </>
          )}

          {step === 'household' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-4">{t.onboarding.household.q}</h1>
              <div className="grid sm:grid-cols-3 gap-3">
                {HOUSEHOLDS.map((h) => (
                  <Chip key={h} active={a.household_type === h}
                    onClick={() => setA({ ...a, household_type: h })}>
                    {t.onboarding.household[h]}
                  </Chip>
                ))}
              </div>
              {a.household_type === 'couple' && (
                <div className="mt-5">
                  <p className="text-sm font-medium text-turquoise-900 mb-2">{t.onboarding.household.intendsQ}</p>
                  <div className="grid grid-cols-2 gap-3">
                    <Chip active={a.intends_children === true}
                      onClick={() => setA({ ...a, intends_children: true })}>
                      {t.onboarding.household.intendsYes}
                    </Chip>
                    <Chip active={a.intends_children === false}
                      onClick={() => setA({ ...a, intends_children: false })}>
                      {t.onboarding.household.intendsNo}
                    </Chip>
                  </div>
                </div>
              )}
            </>
          )}


          {step === 'communities' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-1">{t.onboarding.communities.q}</h1>
              <p className="text-sm text-turquoise-800/60 mb-4">{t.onboarding.communities.hint}</p>
              <CommunitySelect
                value={a.minority_groups}
                onChange={(v) => setA({ ...a, minority_groups: v })}
              />
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

              <p className="text-sm font-medium text-turquoise-900 mt-5 mb-1">{t.onboarding.means.q}</p>
              <p className="text-sm text-turquoise-800/60 mb-3">{t.onboarding.means.hint}</p>
              <div className="grid sm:grid-cols-2 gap-3">
                <label className="text-sm">
                  <span className="block text-xs text-turquoise-800/60 mb-1">{t.onboarding.means.income}</span>
                  <input type="number" min={0} step={1000} value={a.annual_income ?? ''}
                    onChange={(e) => setA({ ...a, annual_income: e.target.value ? Number(e.target.value) : null })}
                    className="w-full border border-turquoise-100 rounded-md px-3 py-2" placeholder="40000" />
                </label>
                <label className="text-sm">
                  <span className="block text-xs text-turquoise-800/60 mb-1">{t.onboarding.means.investable}</span>
                  <input type="number" min={0} step={10000} value={a.investable_amount ?? ''}
                    onChange={(e) => setA({ ...a, investable_amount: e.target.value ? Number(e.target.value) : null })}
                    className="w-full border border-turquoise-100 rounded-md px-3 py-2" placeholder="250000" />
                </label>
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
              <h1 className="text-xl font-medium text-turquoise-900 mb-1">{t.onboarding.language.knownQ}</h1>
              <p className="text-sm text-turquoise-800/60 mb-4">{t.onboarding.language.knownHint}</p>
              <div className="mb-6">
                <LanguageMultiSelect
                  value={a.known_languages}
                  onChange={(v) => setA({ ...a, known_languages: v })}
                  addLabel={t.onboarding.language.knownQ}
                />
              </div>

              <p className="text-sm font-medium text-turquoise-900 mb-1">{t.onboarding.language.q}</p>
              <p className="text-sm text-turquoise-800/60 mb-3">{t.onboarding.language.hint}</p>
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

          {step === 'persona' && (
            <>
              <h1 className="text-xl font-medium text-turquoise-900 mb-1">{t.onboarding.persona.q}</h1>
              <p className="text-sm text-turquoise-800/60 mb-4">{t.onboarding.persona.hint}</p>
              {/* Pick a profile directly — no guessing. The selected one shows its focus criteria. */}
              <div className="space-y-2 mb-5">
                {personaList.length === 0 ? (
                  // The registry (which supplies the profiles) is still loading or retrying after a
                  // hiccup — show feedback instead of a blank gap. `reg == null` covers both states
                  // since useCriteria keeps retrying until it resolves.
                  reg == null ? (
                    <p className="text-sm text-turquoise-800/60 flex items-center gap-2 py-2">
                      <Spinner /> {t.onboarding.persona.loading}
                    </p>
                  ) : (
                    <p className="text-sm text-turquoise-800/60 py-2">{t.onboarding.persona.unavailable}</p>
                  )
                ) : personaList.map((p) => {
                  const on = persona?.key === p.key
                  return (
                    <button key={p.key} type="button" onClick={() => setPersona(p)}
                      className={`block w-full text-left rounded-lg border p-3 ${
                        on ? 'border-turquoise-400 bg-turquoise-50' : 'border-turquoise-100 hover:bg-turquoise-50'}`}>
                      <span className="font-medium text-turquoise-900">{personaLabel(p)}</span>
                      {personaBlurb(p) && (
                        <span className="block text-sm text-turquoise-800/70 mt-0.5">{personaBlurb(p)}</span>
                      )}
                      {on && focusCriteria(p).length > 0 && (
                        <span className="block text-xs text-turquoise-800/60 mt-1.5">
                          {t.onboarding.persona.focus} {focusCriteria(p).map((k) => labelOf(reg, k, lang)).join(', ')}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
              {/* Optional free-text to help clinch the shortlist. */}
              <p className="text-sm font-medium text-turquoise-900 mb-1">{t.onboarding.priorities.moreQ}</p>
              <p className="text-sm text-turquoise-800/60 mb-2">{t.onboarding.priorities.moreHint}</p>
              <VoiceField
                value={a.priorities_text}
                onChange={(v) => setA({ ...a, priorities_text: v })}
                placeholder={t.onboarding.priorities.morePlaceholder}
              />
            </>
          )}

          <div className="mt-6 flex items-center gap-3">
            {stepIdx > 0 && (
              <button onClick={() => setIndex(stepIdx - 1)}
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
