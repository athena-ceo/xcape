// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { Fragment, useState } from 'react'

import { useT } from '../i18n'
import { categories, labelOf, nodeOf, useCriteria } from '../services/criteria'

const CLIMATES = ['cold', 'temperate', 'mild', 'warm', 'tropical'] as const
const PRESETS: { key: string; w: number }[] = [
  { key: 'impIgnore', w: 0 }, { key: 'impLow', w: 0.5 }, { key: 'impNormal', w: 1 }, { key: 'impHigh', w: 2.5 },
]

interface Props {
  weights: Record<string, number>
  filters: Record<string, any>
  busy: boolean
  onApply: (weights: Record<string, number>, filters: Record<string, any>) => void
}

// Criteria control: per-criterion numeric importance (with quick presets), grouped by
// category, plus the hard filters. Reads the catalog from the registry.
export function CriteriaSettings({ weights, filters, busy, onApply }: Props) {
  const { t, lang } = useT()
  const reg = useCriteria()
  const [w, setW] = useState<Record<string, number>>({ ...weights })
  const [f, setF] = useState<Record<string, any>>({ ...filters })
  const climateSel: string[] = Array.isArray(f.climate) ? f.climate : (f.climate ? [f.climate] : [])

  function weightFor(key: string): number {
    return w[key] ?? nodeOf(reg, key)?.default_weight ?? 0
  }
  function setWeight(key: string, val: number) {
    setW({ ...w, [key]: Math.max(0, Math.min(5, val)) })
  }
  function toggleClimate(c: string) {
    const next = climateSel.includes(c) ? climateSel.filter((x) => x !== c) : [...climateSel, c]
    setF({ ...f, climate: next })
  }
  function apply() {
    const cleaned: Record<string, any> = {}
    for (const [k, v] of Object.entries(f)) {
      if (Array.isArray(v) ? v.length : v) cleaned[k] = v
    }
    onApply(w, cleaned)
  }

  function filterCell(key: string) {
    if (key === 'language_ease') return (
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={!!f.language_ease} className="accent-turquoise-600"
          onChange={(e) => setF({ ...f, language_ease: e.target.checked })} />
        {t.comparison.filterLanguageOnly}
      </label>
    )
    if (key === 'visa') return (
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={!!f.visa} className="accent-turquoise-600"
          onChange={(e) => setF({ ...f, visa: e.target.checked })} />
        {t.comparison.filterVisaOnly}
      </label>
    )
    if (key === 'inclusion') return (
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={!!f.inclusion} className="accent-turquoise-600"
          onChange={(e) => setF({ ...f, inclusion: e.target.checked })} />
        {t.comparison.filterWelcomingOnly}
      </label>
    )
    if (key === 'climate') return (
      <div className="flex flex-wrap gap-1.5">
        {CLIMATES.map((c) => (
          <button key={c} type="button" onClick={() => toggleClimate(c)}
            className={`text-xs rounded-full border px-2 py-0.5 ${
              climateSel.includes(c) ? 'border-turquoise-400 bg-turquoise-50 text-turquoise-700'
                                     : 'border-turquoise-100'}`}>
            {t.onboarding.climate[c]}
          </button>
        ))}
      </div>
    )
    return null
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
          {categories(reg).map((cat) => (
            <Fragment key={cat.key}>
              <tr className="border-t border-turquoise-100 bg-turquoise-50/60">
                <td colSpan={3} className="py-1.5 font-medium text-turquoise-900">{labelOf(reg, cat.key, lang)}</td>
              </tr>
              {cat.leaves.map((key) => (
                <tr key={key} className="border-t border-turquoise-50">
                  <td className="py-1.5 pr-2 pl-3">{labelOf(reg, key, lang)}</td>
                  <td className="py-1.5 pr-2">
                    <div className="flex items-center gap-2">
                      <input type="number" min={0} max={5} step={0.5} value={weightFor(key)}
                        onChange={(e) => setWeight(key, Number(e.target.value))}
                        className="w-16 border border-turquoise-100 rounded-md px-2 py-1" />
                      <div className="flex gap-1">
                        {PRESETS.map((p) => (
                          <button key={p.key} type="button" onClick={() => setWeight(key, p.w)}
                            className="text-xs rounded border border-turquoise-100 px-1.5 py-0.5 hover:bg-turquoise-50">
                            {(t.comparison as Record<string, string>)[p.key]}
                          </button>
                        ))}
                      </div>
                    </div>
                  </td>
                  <td className="py-1.5">{filterCell(key)}</td>
                </tr>
              ))}
            </Fragment>
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
