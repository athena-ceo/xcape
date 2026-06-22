// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { Fragment, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { useT } from '../i18n'
import { categories, labelOf, nodeOf, useCriteria } from '../services/criteria'

const CLIMATES = ['cold', 'temperate', 'mild', 'warm', 'tropical'] as const
// Service criteria expose quality vs newcomer-access sub-scores you can filter on separately.
const SERVICE_KEYS = ['healthcare', 'education']
const SERVICE_COMPONENTS = ['quality', 'access'] as const
const PRESETS: { key: string; w: number }[] = [
  { key: 'impIgnore', w: 0 }, { key: 'impLow', w: 0.5 }, { key: 'impNormal', w: 1 }, { key: 'impHigh', w: 2.5 },
]
export interface CustomCrit { key: string; label: string; weight?: number; min?: number; category?: string }
export interface SettingsPayload {
  weights: Record<string, number>
  filters: Record<string, any>
  customCriteria: CustomCrit[]
}

interface Props {
  weights: Record<string, number>
  filters: Record<string, any>
  customCriteria?: CustomCrit[]
  busy: boolean
  onApply: (payload: SettingsPayload) => void
  onCancel: () => void
  onDirtyChange?: (dirty: boolean) => void
}

// Criteria control: per-criterion numeric importance (with quick presets), grouped by
// category, plus the hard filters (a generic Any / At least OK / Only good threshold on
// every criterion, and bespoke controls for language/visa/inclusion/climate). Custom
// criteria appear in their own group with the same importance + threshold controls. Reads
// the catalog from the registry.
export function CriteriaSettings({ weights, filters, customCriteria = [], busy, onApply, onCancel, onDirtyChange }: Props) {
  const { t, lang } = useT()
  const reg = useCriteria()
  const [w, setW] = useState<Record<string, number>>({ ...weights })
  const [f, setF] = useState<Record<string, any>>({ ...filters })
  const [cc, setCc] = useState<CustomCrit[]>(customCriteria.map((c) => ({ ...c })))

  // "Dirty" = the panel has edits not yet applied. We compare the local draft to the saved
  // props (filters cleaned the same way apply() does).
  const cleanF = (x: Record<string, any>) => {
    const o: Record<string, any> = {}
    for (const [k, v] of Object.entries(x)) if (Array.isArray(v) ? v.length : v) o[k] = v
    return o
  }
  const dirty = JSON.stringify({ w, f: cleanF(f), cc })
    !== JSON.stringify({ w: weights, f: cleanF(filters), cc: customCriteria.map((c) => ({ ...c })) })
  const dirtyRef = useRef(dirty)
  dirtyRef.current = dirty
  useEffect(() => { onDirtyChange?.(dirty) }, [dirty, onDirtyChange])
  // Safety net: whatever path unmounts the panel, report "clean" so the toolbar never
  // stays disabled.
  useEffect(() => () => onDirtyChange?.(false), [])  // eslint-disable-line react-hooks/exhaustive-deps

  // Resync from saved state ONLY when there are no unsaved edits — so an external change
  // (or a stray re-render) can never wipe edits in progress.
  useEffect(() => { if (!dirtyRef.current) setW({ ...weights }) }, [weights])
  useEffect(() => { if (!dirtyRef.current) setF({ ...filters }) }, [filters])
  useEffect(() => { if (!dirtyRef.current) setCc(customCriteria.map((c) => ({ ...c }))) }, [customCriteria])

  function cancel() {
    setW({ ...weights }); setF({ ...filters }); setCc(customCriteria.map((c) => ({ ...c })))
    onCancel()
  }

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
  // A filter is "set" when its value is truthy / a non-empty list.
  function filterActive(key: string): boolean {
    const v = f[key]
    if (Array.isArray(v) ? v.length > 0 : !!v) return true
    return SERVICE_KEYS.includes(key) && SERVICE_COMPONENTS.some((c) => !!f[`${key}:${c}`])
  }
  // Service criteria can be filtered on the whole thing or just one component (e.g. require
  // healthcare ACCESS ≥ good regardless of quality). Stored as filters[`${key}:${component}`].
  function serviceComp(base: string): string {
    return SERVICE_COMPONENTS.find((c) => f[`${base}:${c}`]) ?? ''
  }
  function serviceTier(base: string): string {
    const comp = serviceComp(base)
    const v = f[comp ? `${base}:${comp}` : base]
    return v === 'good' || v === 'ok' ? v : ''
  }
  function setService(base: string, comp: string, tier: string) {
    const next = { ...f }
    delete next[base]
    for (const c of SERVICE_COMPONENTS) delete next[`${base}:${c}`]
    if (tier) next[comp ? `${base}:${comp}` : base] = tier
    setF(next)
  }
  // Generic threshold: '' (any) | 'ok' | 'good', stored as a tier word in filters[key].
  function genericThreshold(key: string): string {
    const v = f[key]
    return v === 'good' || v === 'ok' ? v : ''
  }
  function setGenericThreshold(key: string, v: string) {
    const next = { ...f }
    if (v) next[key] = v
    else delete next[key]
    setF(next)
  }
  function setCustom(key: string, patch: Partial<CustomCrit>) {
    setCc((list) => list.map((c) => (c.key === key ? { ...c, ...patch } : c)))
  }
  // min number <-> tier word for the custom threshold select.
  function customTier(min?: number): string {
    return min != null && min >= 0.7 ? 'good' : min != null && min > 0 ? 'ok' : ''
  }
  function setCustomTier(key: string, v: string) {
    setCustom(key, { min: v === 'good' ? 0.7 : v === 'ok' ? 0.45 : undefined })
  }

  function apply() {
    const cleaned: Record<string, any> = {}
    for (const [k, v] of Object.entries(f)) {
      if (Array.isArray(v) ? v.length : v) cleaned[k] = v
    }
    onApply({ weights: w, filters: cleaned, customCriteria: cc })
  }

  function thresholdSelect(value: string, onChange: (v: string) => void) {
    return (
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="border border-turquoise-100 rounded px-2 py-1 text-sm">
        <option value="">{t.comparison.minAny}</option>
        <option value="ok">{t.comparison.minOk}</option>
        <option value="good">{t.comparison.minGood}</option>
      </select>
    )
  }

  function filterCell(key: string) {
    // visa & language_ease use the same generic ≥ OK / ≥ Good threshold as the board (their
    // computed value supports it), so they fall through to the generic control below.
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
    if (SERVICE_KEYS.includes(key)) return (
      <div className="flex flex-wrap items-center gap-1.5">
        <select value={serviceComp(key)} onChange={(e) => setService(key, e.target.value, serviceTier(key))}
          className="border border-turquoise-100 rounded px-2 py-1 text-sm">
          <option value="">{t.comparison.componentOverall}</option>
          <option value="quality">{(t.trend as Record<string, string>).quality}</option>
          <option value="access">{(t.trend as Record<string, string>).access}</option>
        </select>
        {thresholdSelect(serviceTier(key), (v) => setService(key, serviceComp(key), v))}
      </div>
    )
    // Every other criterion: a generic minimum threshold.
    return thresholdSelect(genericThreshold(key), (v) => setGenericThreshold(key, v))
  }

  // Wrap a filter control, dimming it and noting that a weight-0 criterion's filter is dormant
  // (the criterion is ignored entirely — score and filter — so it can't constrain results).
  function filterWithNote(control: ReactNode, ignored: boolean) {
    return (
      <div className={ignored ? 'opacity-60' : ''}>
        {control}
        {ignored && <div className="text-xs text-amber-700 mt-0.5">{t.comparison.filterIgnoredZero}</div>}
      </div>
    )
  }

  function weightInput(value: number, onChange: (v: number) => void) {
    return (
      <div className="flex items-center gap-2">
        <input type="number" min={0} max={5} step={0.5} value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-16 border border-turquoise-100 rounded-md px-2 py-1" />
        <div className="flex gap-1">
          {PRESETS.map((p) => (
            <button key={p.key} type="button" onClick={() => onChange(p.w)}
              className="text-xs rounded border border-turquoise-100 px-1.5 py-0.5 hover:bg-turquoise-50">
              {(t.comparison as Record<string, string>)[p.key]}
            </button>
          ))}
        </div>
      </div>
    )
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
                  <td className="py-1.5 pr-2">{weightInput(weightFor(key), (v) => setWeight(key, v))}</td>
                  <td className="py-1.5">{filterWithNote(filterCell(key), weightFor(key) <= 0 && filterActive(key))}</td>
                </tr>
              ))}
            </Fragment>
          ))}
          {cc.length > 0 && (
            <Fragment>
              <tr className="border-t border-turquoise-100 bg-turquoise-50/60">
                <td colSpan={3} className="py-1.5 font-medium text-turquoise-900">{t.comparison.customGroup}</td>
              </tr>
              {cc.map((c) => (
                <tr key={c.key} className="border-t border-turquoise-50">
                  <td className="py-1.5 pr-2 pl-3">{c.label}</td>
                  <td className="py-1.5 pr-2">
                    {weightInput(c.weight ?? 1, (v) => setCustom(c.key, { weight: Math.max(0, Math.min(5, v)) }))}
                  </td>
                  <td className="py-1.5">{filterWithNote(thresholdSelect(customTier(c.min), (v) => setCustomTier(c.key, v)), (c.weight ?? 1) <= 0 && c.min != null)}</td>
                </tr>
              ))}
            </Fragment>
          )}
        </tbody>
      </table>
      <div className="mt-3 flex items-center gap-2">
        <button onClick={apply} disabled={busy || !dirty}
          className="bg-turquoise-600 text-turquoise-50 rounded-md px-4 py-2 text-sm disabled:opacity-50">
          {t.comparison.apply}
        </button>
        <button onClick={cancel} disabled={busy}
          className="border border-turquoise-100 text-turquoise-700 rounded-md px-4 py-2 text-sm disabled:opacity-50">
          {dirty ? t.common.cancel : t.common.close}
        </button>
        {dirty && <span className="text-xs text-turquoise-800/60">{t.comparison.unsavedChanges}</span>}
      </div>
    </div>
  )
}
