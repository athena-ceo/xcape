// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useState } from 'react'

import { useT } from '../i18n'

const CRITERIA = [
  'cost_of_living', 'climate', 'language_ease', 'healthcare', 'education', 'safety',
  'political_stability', 'tax', 'visa', 'expat_community', 'nature', 'internet',
] as const
const CLIMATES = ['cold', 'temperate', 'mild', 'warm', 'tropical'] as const

const LEVELS: Record<string, number> = { ignore: 0, low: 0.5, normal: 1, high: 2.5 }

function levelOf(weight: number | undefined): string {
  if (weight === undefined) return 'default'
  if (weight >= 2) return 'high'
  if (weight >= 0.8) return 'normal'
  if (weight > 0) return 'low'
  return 'ignore'
}

interface Props {
  weights: Record<string, number>
  filters: Record<string, any>
  busy: boolean
  onApply: (weights: Record<string, number>, filters: Record<string, any>) => void
}

// Revealed affordance: per-criterion importance plus the key hard filters (language,
// climate, visa). "Apply" rebuilds the shortlist with these settings.
export function CriteriaSettings({ weights, filters, busy, onApply }: Props) {
  const { t } = useT()
  const [levels, setLevels] = useState<Record<string, string>>(
    Object.fromEntries(CRITERIA.map((k) => [k, levelOf(weights[k])])),
  )
  const [f, setF] = useState<Record<string, any>>({ ...filters })

  function apply() {
    const w: Record<string, number> = {}
    for (const k of CRITERIA) {
      if (levels[k] !== 'default') w[k] = LEVELS[levels[k]]
    }
    // Drop empty filters.
    const cleaned: Record<string, any> = {}
    for (const [k, v] of Object.entries(f)) {
      if (v) cleaned[k] = v
    }
    onApply(w, cleaned)
  }

  return (
    <div className="bg-white border border-turquoise-100 rounded-lg p-4 mb-4">
      <p className="text-sm text-turquoise-800/60 mb-3">{t.comparison.settingsHint}</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-turquoise-800/60">
            <th className="py-1">{t.comparison.criterion}</th>
            <th className="py-1">{t.comparison.importance}</th>
            <th className="py-1">{t.comparison.filter}</th>
          </tr>
        </thead>
        <tbody>
          {CRITERIA.map((k) => (
            <tr key={k} className="border-t border-turquoise-50">
              <td className="py-1.5 pr-2">{t.criteria[k]}</td>
              <td className="py-1.5 pr-2">
                <select value={levels[k]} onChange={(e) => setLevels({ ...levels, [k]: e.target.value })}
                  className="border border-turquoise-100 rounded-md px-2 py-1">
                  <option value="default">{t.comparison.impDefault}</option>
                  <option value="ignore">{t.comparison.impIgnore}</option>
                  <option value="low">{t.comparison.impLow}</option>
                  <option value="normal">{t.comparison.impNormal}</option>
                  <option value="high">{t.comparison.impHigh}</option>
                </select>
              </td>
              <td className="py-1.5">
                {k === 'language_ease' && (
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={!!f.language_ease}
                      onChange={(e) => setF({ ...f, language_ease: e.target.checked })}
                      className="accent-turquoise-600" />
                    {t.comparison.filterLanguageOnly}
                  </label>
                )}
                {k === 'visa' && (
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={!!f.visa}
                      onChange={(e) => setF({ ...f, visa: e.target.checked })}
                      className="accent-turquoise-600" />
                    {t.comparison.filterVisaOnly}
                  </label>
                )}
                {k === 'climate' && (
                  <select value={f.climate ?? ''} onChange={(e) => setF({ ...f, climate: e.target.value })}
                    className="border border-turquoise-100 rounded-md px-2 py-1">
                    <option value="">{t.comparison.filterAny}</option>
                    {CLIMATES.map((c) => <option key={c} value={c}>{t.onboarding.climate[c]}</option>)}
                  </select>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={apply} disabled={busy}
        className="mt-3 bg-turquoise-600 text-turquoise-50 rounded-md px-4 py-2 text-sm disabled:opacity-50">
        {t.comparison.apply}
      </button>
    </div>
  )
}
