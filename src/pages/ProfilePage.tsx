// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Chip } from '../components/Chip'
import { CommunitySelect } from '../components/CommunitySelect'
import { CountryMultiSelect } from '../components/CountryMultiSelect'
import { LanguageMultiSelect } from '../components/LanguageMultiSelect'
import { VoiceField } from '../components/VoiceField'
import {
  CLIMATE_KEYS, HOUSEHOLDS,
  PRIORITY_KEYS, PRIORITY_WEIGHT, REASON_KEYS, toggle,
} from '../data/profileOptions'
import { useT } from '../i18n'
import { api } from '../services/api'
import { useCriteria, type Persona } from '../services/criteria'
import { useAuth } from '../store/auth'

interface Form {
  first_name: string
  last_name: string
  current_country: string
  citizenships: string[]
  household_type: string | null
  intends_children: boolean | null
  reasons_leaving: string[]
  minority_groups: string[]
  budget_monthly: number | null
  tenure: 'rent' | 'buy' | null
  climate_pref: string | null
  known_languages: string[]
  willing_to_learn: boolean | null
  priorities: string[]
  priorities_text: string
  persona: string | null
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-white rounded-xl p-5 border border-turquoise-100">
      <h2 className="text-base font-medium text-turquoise-900 mb-3">{title}</h2>
      {children}
    </section>
  )
}

export function ProfilePage() {
  const { t, lang } = useT()
  const reg = useCriteria()
  const navigate = useNavigate()
  const refreshAuth = useAuth((s) => s.refresh)
  const [f, setF] = useState<Form | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)

  // Load the current truth from the server.
  useEffect(() => {
    Promise.all([api.me(), api.getProfile() as Promise<any>]).then(([me, p]) => {
      setF({
        first_name: me.first_name ?? '',
        last_name: me.last_name ?? '',
        current_country: me.current_country ?? '',
        citizenships: me.citizenships ?? [],
        household_type: p?.household_type ?? null,
        intends_children: p?.intends_children ?? null,
        reasons_leaving: p?.reasons_leaving ?? [],
        minority_groups: p?.minority_groups ?? [],
        budget_monthly: p?.budget_monthly ?? null,
        tenure: p?.tenure ?? null,
        climate_pref: p?.climate_pref ?? null,
        known_languages: p?.language_skills?.known ?? [],
        willing_to_learn: p?.language_skills?.willing_to_learn ?? null,
        priorities: Object.keys(p?.criteria_weights ?? {}),
        priorities_text: p?.priorities_text ?? '',
        persona: p?.persona ?? null,
      })
    })
  }, [])

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setSaved(false)
    setF((cur) => (cur ? { ...cur, [key]: value } : cur))
  }

  const personaList: Persona[] = reg?.personas ?? []
  // Initial weights from the chosen persona, with explicitly-picked priorities lifted.
  function weightsFor(form: Form): Record<string, number> {
    const pw = personaList.find((p) => p.key === form.persona)?.weights ?? {}
    const cw: Record<string, number> = { ...pw }
    for (const k of form.priorities) cw[k] = Math.max(pw[k] ?? 0, PRIORITY_WEIGHT)
    return cw
  }

  async function save() {
    if (!f) return
    setBusy(true)
    try {
      await api.updateMe({
        first_name: f.first_name || undefined,
        last_name: f.last_name || undefined,
        current_country: f.current_country.trim() || undefined,
        citizenships: f.citizenships,
      })
      await api.updateProfile({
        household_type: f.household_type,
        intends_children: f.intends_children,
        reasons_leaving: f.reasons_leaving,
        minority_groups: f.minority_groups,
        budget_monthly: f.budget_monthly,
        tenure: f.tenure,
        climate_pref: f.climate_pref,
        language_skills: { known: f.known_languages, willing_to_learn: !!f.willing_to_learn },
        criteria_weights: weightsFor(f),
        persona: f.persona ?? undefined,
        priorities_text: f.priorities_text.trim(),
      })
      await refreshAuth() // re-read identity from the server
      setSaved(true)
    } finally {
      setBusy(false)
    }
  }

  if (!f) return <p className="p-8 text-center">{t.common.loading}</p>

  return (
    <main className="max-w-2xl mx-auto px-5 py-8">
      <Link to="/search" className="text-turquoise-600 text-sm">← {t.nav.search}</Link>
      <h1 className="text-2xl font-medium text-turquoise-900 mb-1 mt-3">{t.profile.title}</h1>
      <p className="text-turquoise-800/70 mb-6">{t.profile.intro}</p>

      <div className="space-y-4">
        <Section title={`${t.auth.firstName} / ${t.auth.lastName}`}>
          <div className="flex flex-wrap gap-3">
            <input value={f.first_name} onChange={(e) => set('first_name', e.target.value)}
              placeholder={t.auth.firstName}
              className="flex-1 border border-turquoise-100 rounded-md px-3 py-2" />
            <input value={f.last_name} onChange={(e) => set('last_name', e.target.value)}
              placeholder={t.auth.lastName}
              className="flex-1 border border-turquoise-100 rounded-md px-3 py-2" />
          </div>
        </Section>

        <Section title={t.onboarding.currentCountry.q}>
          <VoiceField value={f.current_country} onChange={(v) => set('current_country', v)} placeholder="France" />
        </Section>

        <Section title={t.onboarding.citizenship.q}>
          <p className="text-sm text-turquoise-800/60 mb-3">{t.onboarding.citizenship.hint}</p>
          <CountryMultiSelect
            value={f.citizenships}
            onChange={(v) => set('citizenships', v)}
            addLabel={t.onboarding.citizenship.add}
          />
        </Section>

        <Section title={t.onboarding.household.q}>
          <div className="grid sm:grid-cols-3 gap-3">
            {HOUSEHOLDS.map((h) => (
              <Chip key={h} active={f.household_type === h} onClick={() => set('household_type', h)}>
                {t.onboarding.household[h]}
              </Chip>
            ))}
          </div>
          {f.household_type === 'couple' && (
            <div className="mt-4">
              <p className="text-sm font-medium text-turquoise-900 mb-2">{t.onboarding.household.intendsQ}</p>
              <div className="grid grid-cols-2 gap-3">
                <Chip active={f.intends_children === true} onClick={() => set('intends_children', true)}>
                  {t.onboarding.household.intendsYes}
                </Chip>
                <Chip active={f.intends_children === false} onClick={() => set('intends_children', false)}>
                  {t.onboarding.household.intendsNo}
                </Chip>
              </div>
            </div>
          )}
        </Section>

        <Section title={t.onboarding.reasons.q}>
          <div className="grid sm:grid-cols-2 gap-3">
            {REASON_KEYS.map((r) => (
              <Chip key={r} active={f.reasons_leaving.includes(r)}
                onClick={() => set('reasons_leaving', toggle(f.reasons_leaving, r))}>
                {t.onboarding.reasons[r]}
              </Chip>
            ))}
          </div>
        </Section>

        {personaList.length > 0 && (
          <Section title={t.onboarding.persona.q}>
            <p className="text-sm text-turquoise-800/60 mb-3">{t.onboarding.persona.change}</p>
            <select value={f.persona ?? ''} onChange={(e) => set('persona', e.target.value || null)}
              className="w-full border border-turquoise-100 rounded-md px-3 py-2 text-sm">
              <option value="">—</option>
              {personaList.map((p) => (
                <option key={p.key} value={p.key}>{(lang === 'fr' ? p.label_fr : p.label_en) || p.label_en}</option>
              ))}
            </select>
            <p className="text-xs text-turquoise-800/50 mt-2">{t.profile.personaNote}</p>
          </Section>
        )}

        <Section title={t.onboarding.communities.q}>
          <p className="text-sm text-turquoise-800/60 mb-3">{t.onboarding.communities.hint}</p>
          <CommunitySelect
            value={f.minority_groups}
            onChange={(v) => set('minority_groups', v)}
          />
        </Section>

        <Section title={t.onboarding.budget.q}>
          <div className="flex items-center gap-2">
            <input type="number" min={0} step={100} value={f.budget_monthly ?? ''}
              onChange={(e) => set('budget_monthly', e.target.value ? Number(e.target.value) : null)}
              className="w-40 border border-turquoise-100 rounded-md px-3 py-2" placeholder="2000" />
            <span className="text-turquoise-800/70">{t.onboarding.budget.suffix}</span>
          </div>
        </Section>

        <Section title={t.onboarding.tenure.q}>
          <div className="grid sm:grid-cols-3 gap-3">
            {([['rent', 'rent'], ['buy', 'buy'], ['either', null]] as const).map(([label, val]) => (
              <Chip key={label} active={f.tenure === val} onClick={() => set('tenure', val)}>
                {t.onboarding.tenure[label]}
              </Chip>
            ))}
          </div>
        </Section>

        <Section title={t.onboarding.climate.q}>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {CLIMATE_KEYS.map((c) => (
              <Chip key={c} active={f.climate_pref === c} onClick={() => set('climate_pref', c)}>
                {t.onboarding.climate[c]}
              </Chip>
            ))}
          </div>
        </Section>

        <Section title={t.onboarding.language.knownQ}>
          <div className="mb-4">
            <LanguageMultiSelect
              value={f.known_languages}
              onChange={(v) => set('known_languages', v)}
              addLabel={t.onboarding.language.knownQ}
            />
          </div>
          <div className="grid gap-3">
            <Chip active={f.willing_to_learn === true} onClick={() => set('willing_to_learn', true)}>
              {t.onboarding.language.willing}
            </Chip>
            <Chip active={f.willing_to_learn === false} onClick={() => set('willing_to_learn', false)}>
              {t.onboarding.language.notWilling}
            </Chip>
          </div>
        </Section>

        <Section title={t.onboarding.priorities.q}>
          <p className="text-sm text-turquoise-800/60 mb-3">{t.onboarding.priorities.hint}</p>
          <div className="grid sm:grid-cols-2 gap-3">
            {PRIORITY_KEYS.map((k) => (
              <Chip key={k} active={f.priorities.includes(k)}
                onClick={() => set('priorities', toggle(f.priorities, k))}>
                {t.criteria[k]}
              </Chip>
            ))}
          </div>
          <p className="text-sm font-medium text-turquoise-900 mt-4 mb-1">{t.onboarding.priorities.moreQ}</p>
          <p className="text-sm text-turquoise-800/60 mb-2">{t.onboarding.priorities.moreHint}</p>
          <VoiceField
            value={f.priorities_text}
            onChange={(v) => set('priorities_text', v)}
            placeholder={t.onboarding.priorities.morePlaceholder}
          />
        </Section>
      </div>

      <div className="flex flex-wrap items-center gap-3 mt-6">
        <button onClick={save} disabled={busy}
          className="bg-turquoise-600 text-turquoise-50 rounded-lg px-6 py-2.5 disabled:opacity-50">
          {busy ? t.profile.saving : t.profile.save}
        </button>
        <button onClick={async () => { await save(); navigate('/search') }} disabled={busy}
          className="border border-turquoise-200 text-turquoise-700 rounded-lg px-5 py-2.5 disabled:opacity-50">
          {t.profile.saveAndView}
        </button>
        {saved && (
          <span className="text-turquoise-600 text-sm flex items-center gap-2">
            {t.profile.saved}
            <Link to="/search" className="underline">{t.nav.search}</Link>
          </span>
        )}
      </div>
    </main>
  )
}
