// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { Fragment, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ChatPanel } from '../components/ChatPanel'
import { CriteriaSettings } from '../components/CriteriaSettings'
import { Spinner } from '../components/Spinner'
import { Waiting } from '../components/Waiting'
import { useT } from '../i18n'
import { attrValue, languageCell, placeName } from '../i18n/places'
import { api } from '../services/api'
import { categories, labelOf, useCriteria, valueLabel } from '../services/criteria'

export function ComparisonPlayground() {
  const { t, lang } = useT()
  const reg = useCriteria()  // the criteria registry (tree, labels, value labels) — single catalog
  const { searchId } = useParams()
  const sid = Number(searchId)
  const [candidates, setCandidates] = useState<any[]>([])
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [excluded, setExcluded] = useState<any[]>([])
  const [evaluating, setEvaluating] = useState(false)
  const evaluatingRef = useRef(false)
  const [places, setPlaces] = useState<Record<number, any>>({})
  // Category expand/collapse, persisted across refreshes; collapsed by default.
  // Categories start collapsed on every load; toggling is in-session only.
  const [openCats, setOpenCats] = useState<Record<string, boolean>>({})
  function toggleCat(key: string, open: boolean) {
    setOpenCats((o) => ({ ...o, [key]: !open }))
  }

  const [newCountry, setNewCountry] = useState('')
  const [researching, setResearching] = useState(false)
  const [customCrit, setCustomCrit] = useState<{ key: string; label: string; weight?: number; min?: number; category?: string }[]>([])
  const [newCustom, setNewCustom] = useState('')
  const [newCustomDesc, setNewCustomDesc] = useState('')
  const [addingCustom, setAddingCustom] = useState(false)
  const [showCustomForm, setShowCustomForm] = useState(false)
  const [editKey, setEditKey] = useState<string | null>(null)  // criterion whose weight/filter popover is open

  const [weights, setWeights] = useState<Record<string, number>>({})
  const [filters, setFilters] = useState<Record<string, any>>({})
  const [showSettings, setShowSettings] = useState(false)
  const [settingsDirty, setSettingsDirty] = useState(false)
  // Bumped after a successful Apply to remount the settings panel from the freshly-saved
  // props, so its "dirty" baseline resets cleanly (re-enabling the toolbar) regardless of
  // how the server echoes the values back.
  const [settingsKey, setSettingsKey] = useState(0)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [advice, setAdvice] = useState<{ qualified: number; board_size: number; suggestions: { key: string; admits: number; best_score: number; best_country: string | null }[] } | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [showZero, setShowZero] = useState(false)  // reveal weight-0 (unimportant) criteria
  const [sortMode, setSortMode] = useState<'category' | 'importance'>('category')

  const [baseline, setBaseline] = useState<any>(null)
  const [explain, setExplain] = useState<{ candidate: any; data: any } | null>(null)
  const [why, setWhy] = useState<{ placeId: number; name: string; key: string; value: any; text: string; score?: number | null } | null>(null)
  // Split a candidate list into the board (selected), the suggestion pool (ranked, not on the
  // board) and the user-excluded bar (override "out"), then kick off progressive evaluation if
  // any cells are still pending.
  function applyCandidates(cands: any[]) {
    setCandidates(cands.filter((c) => c.selected && c.override !== 'out'))
    setSuggestions(cands.filter((c) => !c.selected && c.override !== 'out'))
    setExcluded(cands.filter((c) => c.override === 'out'))
    if (cands.some((c) => (c.pending || []).length)) void drainPending()
  }

  // Re-read candidates from the server (the source of truth).
  async function reloadCandidates() {
    applyCandidates(await api.listCandidates(sid))
    // Refresh the filter diagnostics (how many qualify, what to relax) alongside the board.
    api.filterAdvice(sid).then(setAdvice).catch(() => {})
  }

  // Fill not-yet-evaluated (country × criterion) cells a few at a time, re-rendering after
  // each batch (candidates AND the baseline column), until nothing is pending. Guarded so
  // only one drain runs at a time.
  async function drainPending() {
    if (evaluatingRef.current) return
    evaluatingRef.current = true
    setEvaluating(true)
    try {
      let prevPending = Infinity
      for (let i = 0; i < 200; i++) {
        const cands = await api.evaluatePending(sid, 2)
        setCandidates(cands.filter((c) => c.selected && c.override !== 'out'))
        setSuggestions(cands.filter((c) => !c.selected && c.override !== 'out'))
        setExcluded(cands.filter((c) => c.override === 'out'))
        const b: any = await api.getBaseline(sid).catch(() => null)
        if (b) setBaseline(b)
        const pendingCount = cands.reduce((n, c) => n + (c.pending?.length || 0), 0)
          + (b?.pending?.length || 0)
        if (pendingCount === 0) break
        // No-progress guard: if a round clears nothing (a cell that can't be evaluated — AI
        // failure, unresolvable criterion), stop instead of spinning for 200 slow rounds with
        // the spinner stuck on. Those cells get retried on the next user action.
        if (pendingCount >= prevPending) break
        prevPending = pendingCount
      }
      // Once the late objective/custom evals have landed, re-apply hard filters so the
      // board re-flags / tops up against now-known values (the iteration). Non-destructive.
      if (Object.keys(filters).length) {
        await api.repopulate(sid)
        await reloadCandidates()
      }
    } finally {
      evaluatingRef.current = false
      setEvaluating(false)
    }
  }

  async function reload() {
    const [pls, profile, custom] = await Promise.all([
      api.listPlaces('country'), api.getProfile() as Promise<any>,
      api.listCustomCriteria(sid).catch(() => []),
    ])
    setPlaces(Object.fromEntries(pls.map((p) => [p.id, p])))
    setWeights(profile?.criteria_weights ?? {})
    setFilters(profile?.filters ?? {})
    setCustomCrit(custom.map((c: any) => ({ key: c.key, label: c.label, weight: c.weight, min: c.min, category: c.category })))
    await reloadCandidates()
  }

  async function loadBaseline() {
    // May research the current country on first call (cache-first thereafter).
    const b: any = await api.getBaseline(sid)
    setBaseline(b)
    if (b) await reloadCandidates() // deltas need the baseline; re-read from server
    if (b?.pending?.length) void drainPending() // fill the baseline column too
  }

  useEffect(() => { reload(); loadBaseline() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  // Colour a cell by how good the criterion is for this user: green good, amber weak,
  // red no-go. Light tints that complement the turquoise palette.
  // Build the localized justification sentence from the backend reason code + tokens.
  function reasonText(key: string, r: any): string {
    if (!r?.code) return ''
    // AI evaluations carry a ready-made sentence in BOTH languages; pick the current UI one.
    if (r.code === 'custom') return (lang === 'fr' ? r.text_fr : r.text_en) || r.text_en || r.text_fr || ''
    if (r.code === 'custom_pending') return t.comparison.customPending
    const tpl = (t.reasons as Record<string, string>)[r.code] ?? ''
    const v = r.v != null ? attrValue(t, r.v) : ''
    const langName = (l: string) => (t.langNames as Record<string, string>)[l] ?? l
    const groupName = (g: string) => (t.groups as Record<string, string>)[g] ?? g
    return tpl
      .replace('{v}', v)
      .replace('{lang}', r.lang ? langName(r.lang) : '')
      .replace('{langs}', Array.isArray(r.langs) ? r.langs.map(langName).join(', ') : '')
      .replace('{group}', r.group ? groupName(r.group) : '')
      .replace('{label}', critLabel(key))
  }

  function openWhy(c: any, key: string) {
    setWhy({
      placeId: c.place_id,
      name: placeName(places[c.place_id], lang),
      key,
      value: cellValue(key, places[c.place_id]?.attributes, c.quality?.[key]),
      text: reasonText(key, c.reasons?.[key]),
      score: c.reasons?.[key]?.score,
    })
  }

  function qualityClass(tier?: string) {
    if (tier === 'good') return 'bg-emerald-50 text-emerald-800'
    if (tier === 'ok') return 'bg-amber-50 text-amber-900'
    if (tier === 'bad') return 'bg-red-50 text-red-800'
    return ''
  }

  // Visa is shown relative to the user (citizenship), so the label matches the colour —
  // "Difficile" for a US passport into the EU, not the country's generic "Facile".
  function visaCell(tier: string | undefined, attrs: any) {
    const byTier: Record<string, string> = { good: 'easy', ok: 'medium', bad: 'hard' }
    return attrValue(t, byTier[tier ?? ''] ?? attrs?.visa)
  }

  // Label for any criterion — resolved from the registry, falling back to a custom name.
  function critLabel(key: string) {
    // Service component sub-keys (e.g. "healthcare:access") → "Healthcare · Access", localized.
    const [base, comp] = key.split(':')
    const label = labelOf(reg, base, lang, customCrit)
    if (comp) return `${label} · ${(t.trend as Record<string, string>)[comp] ?? comp}`
    return label
  }

  // Generic quality word from a tier — used when an objective criterion has an AI score but
  // no coarse seed bucket to name (the ~190 seed-sparse countries).
  function tierWord(tier?: string) {
    if (tier === 'good') return t.comparison.legendGood
    if (tier === 'ok') return t.comparison.legendWeak
    if (tier === 'bad') return t.comparison.legendNogo
    return '—'
  }

  function cellValue(key: string, attrs: any, tier?: string) {
    if (key === 'language_ease') return languageCell(t, attrs)
    if (key === 'visa') return visaCell(tier, attrs)
    // Criteria with registry value labels (inclusion, proximity…) show their tier word.
    const vl = valueLabel(reg, key, tier, lang)
    if (vl) return vl
    const raw = attrs?.[key]
    return raw ? attrValue(t, raw) : tierWord(tier)
  }


  async function downloadReport() {
    if (downloading) return
    setDownloading(true)
    try {
      await api.downloadReport(sid, lang)
    } finally {
      setDownloading(false)
    }
  }

  // Add a known country straight from the picker (no AI research needed).
  async function addPlace(place: any) {
    if (candidates.length >= 5 || researching) return
    setResearching(true)
    try {
      await api.addCandidate(sid, { place_id: place.id })
      setNewCountry('')
      await reload()
    } finally {
      setResearching(false)
    }
  }

  // Fallback: a name not in our list → research it via AI.
  async function addCountry() {
    if (!newCountry.trim() || researching || candidates.length >= 5) return
    setResearching(true)
    try {
      await api.addCandidate(sid, { place_name: newCountry.trim() })
      setNewCountry('')
      await reload()
    } finally {
      setResearching(false)
    }
  }

  // Add a user-defined criterion: a short name for the column + an optional longer
  // description that guides the AI. The AI rates every country, then it joins the board.
  async function addCustom() {
    const label = newCustom.trim()
    if (!label || addingCustom) return
    setAddingCustom(true)
    try {
      await api.addCustomCriterion(sid, label, newCustomDesc.trim() || undefined)
      setNewCustom('')
      setNewCustomDesc('')
      setShowCustomForm(false)
      await reload() // picks up the new column, labels and re-scored candidates
    } finally {
      setAddingCustom(false)
    }
  }

  // "×" explicitly excludes a country: it leaves the board and won't be re-added by score or
  // filters (it lands in the "excluded" bar). This is a user override — it survives repopulate.
  async function removeCountry(candidateId: number) {
    await api.excludeCandidate(sid, candidateId)
    await reloadCandidates()
  }

  // Restore an excluded country to the neutral ranked pool (back into "suggestions"); the user
  // then re-adds it to the board if they want it.
  async function restoreCountry(candidateId: number) {
    await api.restoreCandidate(sid, candidateId)
    await reloadCandidates()
  }

  // One-click add a suggested (ranked but unselected) country to the board.
  async function addSuggestion(candidateId: number) {
    if (candidates.length >= 5) return
    await api.setSelected(sid, candidateId, true)
    await reloadCandidates()
  }

  // Changing a criterion's importance re-ranks the WHOLE country pool, so a higher weight
  // can surface countries that now rank into the board (not just re-score the current five).
  // Custom-criterion edits already repopulate server-side; built-ins need an explicit
  // repopulate after the profile update (which on its own only re-scores the existing board).
  async function applyWeight(criterion: string, weight: number) {
    if (applying) return
    setApplying(true)
    try {
      if (customCrit.some((c) => c.key === criterion)) {
        // Custom-criterion weight lives on the per-search definition, not the profile.
        setCustomCrit((cc) => cc.map((c) => (c.key === criterion ? { ...c, weight } : c)))
        await api.updateCustomCriterion(sid, criterion, { weight })  // repopulates server-side
      } else {
        const next = { ...weights, [criterion]: weight }
        setWeights(next)
        await api.updateProfile({ criteria_weights: next })
        await api.repopulate(sid)  // re-rank the full pool, not just re-score the current board
      }
      await reloadCandidates() // board (countries + scores) updates
    } finally {
      setApplying(false)
    }
  }

  // Inline hard-filter on a built-in criterion straight from the table (tier '' | 'ok' | 'good').
  // Custom criteria use their per-search `min` instead (edited in Criteria settings).
  async function applyFilter(criterion: string, tier: string) {
    if (applying) return
    setApplying(true)
    try {
      const next = { ...filters }
      if (tier) next[criterion] = tier; else delete next[criterion]
      setFilters(next)
      await api.updateProfile({ filters: next })
      await api.repopulate(sid)  // filters are exclusionary → re-rank the pool
      await reloadCandidates()
    } finally {
      setApplying(false)
    }
  }

  // Set a filter to an arbitrary value (a tier word, a list of climates, or a boolean) — used by
  // the per-criterion popover for the bespoke filters (climate list, inclusion toggle).
  async function applyFilterValue(criterion: string, value: any) {
    if (applying) return
    setApplying(true)
    try {
      const empty = value === '' || value == null || value === false ||
        (Array.isArray(value) && value.length === 0)
      const next = { ...filters }
      if (empty) delete next[criterion]; else next[criterion] = value
      setFilters(next)
      await api.updateProfile({ filters: next })
      await api.repopulate(sid)
      await reloadCandidates()
    } finally {
      setApplying(false)
    }
  }

  // Inline filter for a CUSTOM criterion = its per-search min threshold.
  async function applyCustomMin(criterion: string, tier: string) {
    if (applying) return
    setApplying(true)
    try {
      const min = tier === 'good' ? 0.7 : tier === 'ok' ? 0.45 : null
      setCustomCrit((cc) => cc.map((c) => (c.key === criterion ? { ...c, min: min ?? undefined } : c)))
      await api.updateCustomCriterion(sid, criterion, { min })  // repopulates server-side
      await reloadCandidates()
    } finally {
      setApplying(false)
    }
  }

  async function showExplanation(candidate: any) {
    const data = await api.scoreExplanation(sid, candidate.id)
    setExplain({ candidate, data })
  }

  // Apply criteria settings: persist weights + filters (+ custom-criterion weight/threshold),
  // then repopulate so filters change which countries qualify — keeping the selected board
  // and topping it up (flagging any that don't meet the filters).
  async function applySettings(payload: import('../components/CriteriaSettings').SettingsPayload) {
    setApplying(true)
    setApplyError(null)
    try {
      await api.updateProfile({ criteria_weights: payload.weights, filters: payload.filters })
      // Custom-criterion weight/threshold live per-search; push any that changed. A failure
      // on one custom criterion (e.g. a stale key) must NOT abort the whole apply — the
      // built-in weights/filters above are already saved and the board must still refresh.
      for (const c of payload.customCriteria) {
        const prev = customCrit.find((x) => x.key === c.key)
        if (!prev || prev.weight !== c.weight || prev.min !== c.min) {
          try {
            await api.updateCustomCriterion(sid, c.key, { weight: c.weight, min: c.min ?? null })
          } catch (e) {
            console.error('custom-criterion update failed', c.key, e)
          }
        }
      }
      await api.repopulate(sid)
      await reload()
      // Reset the panel's draft baseline to the now-saved values (clears dirty, re-enables
      // the toolbar) and keep it open so the user can see the changes took effect.
      setSettingsDirty(false)
      setSettingsKey((k) => k + 1)
    } catch (e) {
      // Surface the failure instead of silently leaving a stale board.
      console.error('Apply settings failed', e)
      setApplyError(t.comparison.applyFailed)
    } finally {
      setApplying(false)
    }
  }

  // Explicit "repopulate the list with the current criteria" — reliable, persists, and
  // respects all active filters (top-up with flagged extras when a filter is strict).
  async function repopulate() {
    if (applying) return
    setApplying(true)
    try {
      await api.repopulate(sid)
      await reload()
    } finally {
      setApplying(false)
    }
  }

  // Criteria grouped for the table: registry categories + a synthetic group for the
  // search's custom criteria. Each group = {key, label, leaves[]}.
  const TIER_VALUE: Record<string, number> = { good: 1, ok: 0.6, bad: 0.3 }
  // Custom criteria with a `category` are filed under that built-in category; the rest go to
  // the catch-all "Your criteria" group.
  const customByCat: Record<string, string[]> = {}
  const customUngrouped: string[] = []
  for (const c of customCrit) {
    if (c.category) (customByCat[c.category] ??= []).push(c.key)
    else customUngrouped.push(c.key)
  }
  const groups = [
    ...categories(reg).map((c) => ({
      key: c.key, label: labelOf(reg, c.key, lang),
      leaves: [...c.leaves, ...(customByCat[c.key] ?? [])],
    })),
    ...(customUngrouped.length
      ? [{ key: '__custom', label: t.comparison.customGroup, leaves: customUngrouped }]
      : []),
  ]
  // Custom-criterion weights live on the per-search definition; built-ins on the profile.
  const customWeights = Object.fromEntries(customCrit.map((c) => [c.key, c.weight ?? 1]))
  const weightOf = (key: string) => (key in customWeights ? customWeights[key] : (weights[key] ?? 0))
  // "Sort by importance" floats the heaviest-weighted categories (and leaves within them) up;
  // default keeps the registry/category order.
  const groupWeight = (g: { leaves: string[] }) => g.leaves.reduce((s, k) => s + Math.max(0, weightOf(k)), 0)
  const orderedGroups = sortMode === 'importance'
    ? [...groups].sort((a, b) => groupWeight(b) - groupWeight(a))
    : groups
  // Weight-0 criteria are ignored entirely (score AND filter — see filter_status), so they're
  // simply hidden behind "other criteria"; a dormant filter never produces a violation flag.
  const visibleLeaf = (key: string) => weightOf(key) > 0
  // Expanded by default (showing the non-zero-weight criteria); the user's choice persists.
  const isOpen = (g: { key: string; leaves: string[] }) => openCats[g.key] ?? true
  // Roll-up colour tier for a category column = weighted average of its WEIGHTED leaves'
  // tiers. Weight-0 criteria are excluded (they don't affect the score), so the roll-up is
  // identical whether or not "other criteria" are shown.
  function rollupTier(cand: any, leaves: string[]): string | undefined {
    let num = 0, den = 0
    for (const k of leaves) {
      const w = weightOf(k)
      if (w <= 0) continue
      const tier = cand.quality?.[k]
      if (!tier) continue
      num += TIER_VALUE[tier] * w; den += w
    }
    if (!den) return undefined
    const v = num / den
    return v >= 0.7 ? 'good' : v >= 0.45 ? 'ok' : 'bad'
  }
  // Which of a category's leaves this candidate fails a hard filter on (to flag in the roll-up).
  function catViolations(cand: any, leaves: string[]): string[] {
    const v: string[] = cand.filter_violations ?? []
    return leaves.filter((k) => v.includes(k))
  }

  // Known countries matching the picker text (localized name substring), excluding ones
  // already on the board. Resolves French names → the canonical place.
  const onBoard = new Set(candidates.map((c) => c.place_id))
  const q = newCountry.trim().toLowerCase()
  const countryMatches = q
    ? Object.values(places)
        .filter((p: any) => !onBoard.has(p.id) && placeName(p, lang).toLowerCase().includes(q))
        .sort((a: any, b: any) => placeName(a, lang).localeCompare(placeName(b, lang), lang))
        .slice(0, 8)
    : []

  // A compact −/value/+ weight stepper (capped 0–5, half-steps), reused by each criterion row.
  const WEIGHT_MAX = 5
  function weightControl(key: string) {
    const w = weightOf(key)
    const set = (v: number) => applyWeight(key, Math.max(0, Math.min(WEIGHT_MAX, Math.round(v * 2) / 2)))
    return (
      <span className="inline-flex items-center rounded border border-turquoise-100 text-xs shrink-0"
        title={t.comparison.importance}>
        <button type="button" aria-label="−" disabled={w <= 0} onClick={() => set(w - 0.5)}
          className="px-1.5 py-0.5 text-turquoise-600 disabled:opacity-30 hover:bg-turquoise-50">−</button>
        <span className="w-6 text-center tabular-nums text-turquoise-800/70">{w}</span>
        <button type="button" aria-label="+" disabled={w >= WEIGHT_MAX} onClick={() => set(w + 0.5)}
          className="px-1.5 py-0.5 text-turquoise-600 disabled:opacity-30 hover:bg-turquoise-50">+</button>
      </span>
    )
  }

  // The current ≥OK/≥Good tier of a criterion's filter (custom criteria use their per-search min).
  const CLIMATES = ['cold', 'temperate', 'mild', 'warm', 'tropical'] as const
  function filterTierOf(key: string): string {
    const cust = customCrit.find((c) => c.key === key)
    if (cust) return cust.min != null && cust.min >= 0.7 ? 'good' : cust.min != null && cust.min > 0 ? 'ok' : ''
    const v = (filters as Record<string, any>)[key]
    return v === 'good' || v === 'ok' ? v : ''
  }
  // Whether a criterion currently has an active filter (drives the chip's "filtered" styling).
  function isFiltered(key: string): boolean {
    const cust = customCrit.find((c) => c.key === key)
    if (cust) return cust.min != null && cust.min > 0
    const v = (filters as Record<string, any>)[key]
    return Array.isArray(v) ? v.length > 0 : (v != null && v !== '' && v !== false)
  }
  // Threshold (Any / ≥OK / ≥Good) select, the common filter control.
  function thresholdSelect(key: string) {
    const tier = filterTierOf(key)
    const isCustom = customCrit.some((c) => c.key === key)
    return (
      <select value={tier} disabled={applying}
        onChange={(e) => (isCustom ? applyCustomMin(key, e.target.value) : applyFilter(key, e.target.value))}
        className="w-full text-sm rounded border border-turquoise-200 px-2 py-1">
        <option value="">{t.comparison.minAny}</option>
        <option value="ok">{t.comparison.minOk}</option>
        <option value="good">{t.comparison.minGood}</option>
      </select>
    )
  }
  // The right filter control for a criterion (bespoke for climate/inclusion, threshold otherwise),
  // shown inside the per-criterion popover so every criterion is filterable without cluttering the row.
  function filterEditor(key: string) {
    if (key === 'climate') {
      const sel: string[] = Array.isArray(filters.climate) ? filters.climate
        : (filters.climate ? [filters.climate] : [])
      return (
        <div className="flex flex-wrap gap-1.5">
          {CLIMATES.map((c) => {
            const on = sel.includes(c)
            return (
              <button key={c} type="button" disabled={applying}
                onClick={() => applyFilterValue('climate', on ? sel.filter((x) => x !== c) : [...sel, c])}
                className={`text-xs rounded-full border px-2 py-0.5 ${on
                  ? 'border-turquoise-400 bg-turquoise-50 text-turquoise-700' : 'border-turquoise-100 text-turquoise-800/60'}`}>
                {(t.onboarding.climate as Record<string, string>)[c]}
              </button>
            )
          })}
        </div>
      )
    }
    if (key === 'inclusion') {
      return (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="accent-turquoise-600" disabled={applying}
            checked={!!filters.inclusion} onChange={(e) => applyFilterValue('inclusion', e.target.checked)} />
          {t.comparison.filterWelcomingOnly}
        </label>
      )
    }
    return thresholdSelect(key)
  }

  // Compact per-criterion control chip: shows the weight (and a filter dot when set) and opens a
  // popover to change weight + filter — keeps each row to one line.
  function controlChip(key: string) {
    const w = weightOf(key)
    const filtered = isFiltered(key)
    return (
      <button onClick={() => setEditKey(key)} disabled={applying}
        title={t.comparison.editControls}
        className={`ml-auto shrink-0 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs hover:bg-turquoise-50 ${
          filtered ? 'border-turquoise-400 bg-turquoise-50 text-turquoise-700' : 'border-turquoise-100 text-turquoise-800/60'}`}>
        <span aria-hidden>⚙</span>
        <span className="tabular-nums">{w}</span>
        {filtered && <span className="text-turquoise-500" title={t.comparison.filter} aria-hidden>●</span>}
      </button>
    )
  }

  // One leaf criterion row (used inside each open category group). Weight + filter live in a
  // compact popover opened from the chip, so the row stays a single clean line.
  function leafRow(key: string) {
    return (
      <tr key={key} className="border-t border-turquoise-50">
        <td className="p-3 pl-8 text-turquoise-800/70">
          <div className="flex items-center gap-2">
            <span>{critLabel(key)}</span>
            {controlChip(key)}
          </div>
        </td>
        {baseline && (() => {
          const bpending = (baseline.pending || []).includes(key)
          const bcol = { place_id: baseline.id, reasons: baseline.reasons, quality: baseline.quality }
          return (
            <td className={`p-0 text-center ${qualityClass(baseline.quality?.[key]) || 'bg-turquoise-50'}`}>
              <button onClick={() => openWhy(bcol, key)} className="block w-full p-3 cursor-pointer underline decoration-dotted decoration-turquoise-300 underline-offset-4 hover:decoration-turquoise-600">
                {bpending
                  ? <span className="inline-flex justify-center text-turquoise-800/40"><Spinner /></span>
                  : cellValue(key, baseline.attributes, baseline.quality?.[key])}
              </button>
            </td>
          )
        })()}
        {candidates.map((c) => {
          const pending = (c.pending || []).includes(key)
          const viol = (c.filter_violations || []).includes(key)
          return (
            <td key={c.id}
              className={`p-0 text-center ${pending ? '' : (viol ? 'bg-amber-100 text-amber-900' : qualityClass(c.quality?.[key]))}`}
              title={viol ? `${t.comparison.flagTitle}: ${critLabel(key)}` : undefined}>
              <button onClick={() => openWhy(c, key)} className="block w-full p-3 cursor-pointer underline decoration-dotted decoration-turquoise-300 underline-offset-4 hover:decoration-turquoise-600">
                {pending
                  ? <span className="inline-flex justify-center text-turquoise-800/40"><Spinner /></span>
                  : <>{viol && '⚠ '}{cellValue(key, places[c.place_id]?.attributes, c.quality?.[key])}</>}
              </button>
            </td>
          )
        })}
      </tr>
    )
  }

  return (
    <main className="max-w-4xl mx-auto px-5 py-8">
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <h1 className="text-xl font-medium text-turquoise-900">{t.comparison.title}</h1>
        <div className="ml-auto flex flex-wrap gap-2 text-sm">
          {/* While Criteria settings has unsaved edits, the other actions are disabled so they
              can't discard the in-progress changes (Apply or Cancel in the panel first). */}
          <button onClick={() => setShowSettings((s) => !s)} disabled={settingsDirty}
            title={settingsDirty ? t.comparison.unsavedChanges : undefined}
            className="border border-turquoise-100 rounded-md px-3 py-1.5 disabled:opacity-40">
            {t.comparison.settings}
          </button>
          <button onClick={repopulate} disabled={applying || settingsDirty}
            title={settingsDirty ? t.comparison.unsavedChanges : t.comparison.repopulateHint}
            className="border border-turquoise-100 rounded-md px-3 py-1.5 disabled:opacity-40 inline-flex items-center gap-2">
            {applying && <Spinner />}
            {t.comparison.repopulate}
          </button>
          <button onClick={downloadReport} disabled={downloading || !candidates.length || settingsDirty}
            className="border border-turquoise-100 rounded-md px-3 py-1.5 disabled:opacity-40 inline-flex items-center gap-2">
            {downloading && <Spinner />}
            {t.comparison.downloadReport}
          </button>
        </div>
      </div>

      {applyError && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {applyError}
        </div>
      )}
      {advice && advice.qualified < advice.board_size && (() => {
        const s = advice.suggestions[0]
        const lead = advice.qualified === 0
          ? t.comparison.filterNoneMatch
          : t.comparison.filterFewMatch.replace('{n}', String(advice.qualified))
        const hint = s
          ? t.comparison.filterRelaxHint
              .replace('{filter}', critLabel(s.key))
              .replace('{n}', String(s.admits))
              .replace('{country}', s.best_country ?? '')
              .replace('{score}', String(Math.round(s.best_score)))
          : ''
        return (
          <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-900 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-medium">{lead}</span>
            {hint && <span>{hint}</span>}
            <button onClick={() => setShowSettings(true)}
              className="ml-auto underline underline-offset-2 hover:no-underline">
              {t.comparison.adjustFilters}
            </button>
          </div>
        )
      })()}
      {showSettings && (
        <CriteriaSettings key={settingsKey} weights={weights} filters={filters} customCriteria={customCrit}
          busy={applying} onApply={applySettings}
          onCancel={() => { setSettingsDirty(false); setShowSettings(false) }}
          onDirtyChange={setSettingsDirty} />
      )}

      {/* Colour legend + criteria sort */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-turquoise-800/70 mb-2">
        <span>{t.comparison.legend}:</span>
        <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-800">{t.comparison.legendGood}</span>
        <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-900">{t.comparison.legendWeak}</span>
        <span className="px-2 py-0.5 rounded bg-red-50 text-red-800">{t.comparison.legendNogo}</span>
        <label className="ml-auto flex items-center gap-1.5">
          {t.comparison.sortLabel}:
          <select value={sortMode} onChange={(e) => setSortMode(e.target.value as 'category' | 'importance')}
            className="border border-turquoise-100 rounded px-1.5 py-0.5">
            <option value="category">{t.comparison.sortCategory}</option>
            <option value="importance">{t.comparison.sortImportance}</option>
          </select>
        </label>
      </div>

      {/* Interaction hint */}
      <p className="flex items-center gap-1.5 text-xs text-turquoise-800/60 mb-2">
        <span aria-hidden>👆</span>{t.comparison.tableHint}
      </p>

      {/* Comparison table */}
      <div className="overflow-x-auto bg-white border border-turquoise-100 rounded-lg mb-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-turquoise-50 text-left">
              <th className="p-3 font-medium">{t.comparison.criterion}</th>
              {baseline && (
                <th className="p-3 font-medium text-center bg-turquoise-100/60 whitespace-nowrap" title={t.comparison.current}>
                  <Link to={`/drilldown/${baseline.id}?search=${sid}`} className="text-turquoise-700 hover:underline">
                    {placeName(baseline, lang)}
                  </Link>
                </th>
              )}
              {candidates.map((c) => (
                <th key={c.id} className="p-3 font-medium text-center whitespace-nowrap">
                  <Link to={`/drilldown/${c.place_id}?search=${sid}`} className="text-turquoise-600 hover:underline">
                    {placeName(places[c.place_id], lang)}
                  </Link>
                  <button onClick={() => removeCountry(c.id)}
                    title={t.comparison.remove}
                    className="ml-2 text-turquoise-800/40 hover:text-red-600">×</button>
                  {(c.override === 'in' || !!c.filter_violations?.length) && (
                    <div className="mt-1 flex flex-wrap justify-center gap-1">
                      {c.override === 'in' && (
                        <span className="inline-block text-[10px] font-normal rounded-full bg-turquoise-100 text-turquoise-700 px-2 py-0.5"
                          title={t.comparison.pinnedTitle}>
                          📌 {t.comparison.pinnedBadge}
                        </span>
                      )}
                      {!!c.filter_violations?.length && (
                        <span className="inline-block text-[10px] font-normal rounded-full bg-amber-100 text-amber-800 px-2 py-0.5"
                          title={`${t.comparison.flagTitle}: ${c.filter_violations.map(critLabel).join(', ')}`}>
                          ⚠ {t.comparison.flagBadge}
                        </span>
                      )}
                    </div>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {orderedGroups.map((g) => {
              // Hide weight-0 (unimportant) criteria unless the user reveals them; a category
              // with nothing important is hidden entirely. Filtered leaves stay visible so a
              // category flag always has a visible culprit row.
              let vis = showZero ? g.leaves : g.leaves.filter(visibleLeaf)
              if (sortMode === 'importance') vis = [...vis].sort((a, b) => weightOf(b) - weightOf(a))
              if (!vis.length) return null
              const open = isOpen(g)
              return (
                <Fragment key={g.key}>
                  <tr className="border-t border-turquoise-200 bg-turquoise-50/70 cursor-pointer select-none hover:bg-turquoise-100/70"
                    onClick={() => toggleCat(g.key, open)}>
                    <td className="p-2.5 font-medium text-turquoise-900">
                      <span className="inline-flex items-center gap-2">
                        <span className="inline-grid place-items-center w-5 h-5 rounded border border-turquoise-300 text-turquoise-600 text-xs">
                          {open ? '▾' : '▸'}
                        </span>
                        {g.label}
                        {!open && (
                          <span className="text-xs font-normal text-turquoise-600/70">
                            {vis.length} · {t.comparison.expandHint}
                          </span>
                        )}
                      </span>
                    </td>
                    {baseline && (
                      <td className={`p-0 text-center text-xs ${qualityClass(rollupTier(baseline, g.leaves)) || 'bg-turquoise-50'}`}>
                        <Link to={`/drilldown/${baseline.id}?search=${sid}`} onClick={(e) => e.stopPropagation()}
                          className="block p-2.5 hover:underline">
                          {tierWord(rollupTier(baseline, g.leaves))}
                        </Link>
                      </td>
                    )}
                    {candidates.map((c) => {
                      const viol = catViolations(c, g.leaves)
                      return (
                        <td key={c.id} className={`p-0 text-center text-xs ${viol.length ? 'bg-amber-100 text-amber-900' : qualityClass(rollupTier(c, g.leaves))}`}
                          title={viol.length ? `${t.comparison.flagTitle}: ${viol.map(critLabel).join(', ')}` : undefined}>
                          <Link to={`/drilldown/${c.place_id}?search=${sid}`} onClick={(e) => e.stopPropagation()}
                            className="block p-2.5 hover:underline">
                            {viol.length ? `⚠ ${tierWord(rollupTier(c, g.leaves))}` : tierWord(rollupTier(c, g.leaves))}
                          </Link>
                        </td>
                      )
                    })}
                  </tr>
                  {open && vis.map((key) => leafRow(key))}
                </Fragment>
              )
            })}
            {(() => {
              const hidden = groups.reduce((n, g) => n + g.leaves.filter((k) => !visibleLeaf(k)).length, 0)
              if (!hidden) return null
              const cols = 1 + (baseline ? 1 : 0) + candidates.length
              return (
                <tr className="border-t border-turquoise-100">
                  <td colSpan={cols} className="p-2 text-center">
                    <button onClick={() => {
                        const next = !showZero
                        setShowZero(next)
                        // Reveal the rows: weight-0 criteria live inside category groups, so
                        // expand the groups that contain them — otherwise nothing visibly
                        // changes (a real point of confusion in user testing).
                        if (next) {
                          setOpenCats((o) => {
                            const m = { ...o }
                            for (const g of groups) {
                              if (g.leaves.some((k) => !visibleLeaf(k))) m[g.key] = true
                            }
                            return m
                          })
                        }
                      }}
                      className="text-xs text-turquoise-600 hover:underline">
                      {showZero ? t.comparison.hideUnimportant : `${t.comparison.showUnimportant} (${hidden})`}
                    </button>
                  </td>
                </tr>
              )
            })()}
            <tr className="border-t border-turquoise-200 bg-turquoise-50">
              <td className="p-3 font-medium">{t.comparison.matchScore}</td>
              {baseline && (
                <td className="p-3 text-center bg-turquoise-100/60 font-medium text-turquoise-700">
                  {baseline.match_score != null ? `${Math.round(baseline.match_score)}%` : '—'}
                </td>
              )}
              {candidates.map((c) => (
                <td key={c.id} className="p-3 text-center font-medium text-turquoise-600">
                  {c.match_score != null ? (
                    <button onClick={() => showExplanation(c)} className="underline decoration-dotted hover:text-turquoise-800"
                      title={t.comparison.explainTitle}>
                      {Math.round(c.match_score)}%
                    </button>
                  ) : '—'}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {/* Excluded countries — explicitly removed by the user; one click restores them to the pool. */}
      {excluded.length > 0 && (
        <div className="mb-4 rounded-md border border-turquoise-100 bg-turquoise-50/40 px-3 py-2">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 mb-1.5">
            <span className="text-xs font-medium text-turquoise-800/80">
              {t.comparison.excludedTitle} ({excluded.length})
            </span>
            <span className="text-[11px] text-turquoise-800/50">{t.comparison.excludedHint}</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {excluded.map((c) => (
              <button key={c.id} onClick={() => restoreCountry(c.id)}
                title={t.comparison.restore}
                className="text-xs rounded-full border border-turquoise-100 bg-white px-2.5 py-1 text-turquoise-800/70 hover:bg-turquoise-50 inline-flex items-center gap-1.5">
                <span className="line-through decoration-turquoise-800/30">{placeName(places[c.place_id], lang)}</span>
                <span className="text-turquoise-600">↺</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {evaluating && <div className="mb-4"><Waiting /></div>}

      {/* Suggested matches — the ranked pool not yet on the board; one click adds them. */}
      {suggestions.length > 0 && candidates.length < 5 && (
        <div className="mb-4">
          <p className="text-xs text-turquoise-800/60 mb-1.5">{t.comparison.suggested}</p>
          <div className="flex flex-wrap gap-1.5">
            {suggestions.slice(0, 12).map((c) => (
              <button key={c.id} onClick={() => addSuggestion(c.id)}
                className="text-xs rounded-full border border-turquoise-100 px-2.5 py-1 hover:bg-turquoise-50 inline-flex items-center gap-1.5">
                <span>{placeName(places[c.place_id], lang)}</span>
                {c.match_score != null && (
                  <span className="text-turquoise-600/70">{Math.round(c.match_score)}%</span>
                )}
                <span className="text-turquoise-600">+</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Add country / add criterion */}
      <div className="flex flex-wrap gap-3 mb-5">
        {candidates.length >= 5 ? (
          <p className="text-sm text-turquoise-800/60 self-center">{t.comparison.boardFull}</p>
        ) : (
        <div className="flex items-center gap-2">
          <div className="relative w-56">
            <input value={newCountry} onChange={(e) => setNewCountry(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') (countryMatches[0] ? addPlace(countryMatches[0]) : addCountry()) }}
              placeholder={t.comparison.addCountryPrompt}
              className="w-full border border-turquoise-100 rounded-md px-3 py-1.5 text-sm" />
            {newCountry.trim() && countryMatches.length > 0 && (
              <div className="absolute z-10 mt-1 w-full bg-white border border-turquoise-100 rounded-md shadow-lg max-h-56 overflow-y-auto">
                {countryMatches.map((p) => (
                  <button key={p.id} onClick={() => addPlace(p)}
                    className="block w-full text-left px-3 py-1.5 text-sm hover:bg-turquoise-50">
                    {placeName(p, lang)}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button onClick={() => (countryMatches[0] ? addPlace(countryMatches[0]) : addCountry())}
            disabled={researching || !newCountry.trim()}
            className="bg-turquoise-600 text-turquoise-50 rounded-md px-3 py-1.5 text-sm disabled:opacity-50 inline-flex items-center gap-2">
            {researching && <Spinner className="border-turquoise-100 border-t-white" />}
            {researching ? t.comparison.researching : `+ ${t.comparison.addCountry}`}
          </button>
        </div>
        )}
        {/* User-defined criterion: revealed on demand so the board stays uncluttered and the
            purpose is explicit (a short name + an optional description guiding the AI). */}
        {!showCustomForm && (
          <button onClick={() => setShowCustomForm(true)}
            className="self-center border border-dashed border-turquoise-300 text-turquoise-700 rounded-md px-3 py-1.5 text-sm hover:bg-turquoise-50">
            + {t.comparison.addCustomCta}
          </button>
        )}
      </div>

      {/* Add-your-own-criterion form (revealed by the button above) */}
      {showCustomForm && (
        <div className="mb-5 rounded-lg border border-turquoise-100 bg-turquoise-50/40 p-3">
          <p className="text-sm font-medium text-turquoise-900 mb-0.5">{t.comparison.addCustomTitle}</p>
          <p className="text-xs text-turquoise-800/60 mb-2">{t.comparison.addCustomHelp}</p>
          <div className="flex flex-wrap items-center gap-2">
            <input value={newCustom} onChange={(e) => setNewCustom(e.target.value)} autoFocus
              onKeyDown={(e) => e.key === 'Enter' && addCustom()}
              placeholder={t.comparison.customNamePrompt}
              className="w-40 border border-turquoise-100 rounded-md px-3 py-1.5 text-sm" />
            <input value={newCustomDesc} onChange={(e) => setNewCustomDesc(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addCustom()}
              placeholder={t.comparison.customDescPrompt}
              className="flex-1 min-w-[16rem] border border-turquoise-100 rounded-md px-3 py-1.5 text-sm" />
            <button onClick={addCustom} disabled={!newCustom.trim() || addingCustom}
              className="bg-turquoise-600 text-turquoise-50 rounded-md px-3 py-1.5 text-sm disabled:opacity-50 inline-flex items-center gap-2">
              {addingCustom && <Spinner className="border-turquoise-100 border-t-white" />}
              {addingCustom ? t.comparison.customAdding : `+ ${t.comparison.customCriterion}`}
            </button>
            <button onClick={() => { setShowCustomForm(false); setNewCustom(''); setNewCustomDesc('') }}
              className="text-sm text-turquoise-800/50 hover:text-turquoise-900 px-2">{t.comparison.close}</button>
          </div>
        </div>
      )}

      {/* Quiet entry to the full ranked list (progressive disclosure — keeps the board minimal). */}
      <div className="mb-5">
        <Link to={`/explore/${sid}`} className="text-sm text-turquoise-600 hover:underline">
          {t.explore.exploreAll} →
        </Link>
      </div>

      {/* Chat — shared conversation with the drill-down page (same searchId). */}
      <ChatPanel searchId={sid} onChanged={reload} />

      {/* Criterion justification popover (tap a cell) */}
      {why && (
        <div onClick={() => setWhy(null)}
          className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center p-4 z-50">
          <div onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-xl max-w-sm w-full p-5">
            <div className="flex items-start gap-3 mb-1">
              <p className="font-medium text-turquoise-900">
                {why.name} — {critLabel(why.key)}
              </p>
              <button onClick={() => setWhy(null)} className="ml-auto text-turquoise-800/50 hover:text-turquoise-900"
                aria-label={t.comparison.close}>×</button>
            </div>
            <p className="text-sm font-medium text-turquoise-700 mb-1">
              {why.value}{why.score != null ? ` · ${t.comparison.scoreLabel} ${why.score}/100` : ''}
            </p>
            <p className="text-sm text-turquoise-800/80 mb-4">{why.text || '—'}</p>
            <Link to={`/drilldown/${why.placeId}?search=${sid}#criterion-${why.key}`}
              className="text-sm text-turquoise-600 hover:underline">
              {t.reasons.details} →
            </Link>
          </div>
        </div>
      )}

      {/* Per-criterion weight + filter popover (opened from a row's ⚙ chip) */}
      {editKey && (
        <div onClick={() => setEditKey(null)}
          className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center p-4 z-50">
          <div onClick={(e) => e.stopPropagation()} className="bg-white rounded-xl max-w-xs w-full p-5">
            <div className="flex items-start gap-3 mb-3">
              <p className="font-medium text-turquoise-900">{critLabel(editKey)}</p>
              <button onClick={() => setEditKey(null)}
                className="ml-auto text-turquoise-800/50 hover:text-turquoise-900" aria-label={t.comparison.close}>×</button>
            </div>
            <div className="mb-4">
              <p className="text-xs text-turquoise-800/60 mb-1">{t.comparison.importance}</p>
              {weightControl(editKey)}
              {weightOf(editKey) === 0 && (
                <p className="text-xs text-amber-700 mt-1">{t.comparison.filterIgnoredZero}</p>
              )}
            </div>
            <div>
              <p className="text-xs text-turquoise-800/60 mb-1">{t.comparison.filter}</p>
              {filterEditor(editKey)}
            </div>
          </div>
        </div>
      )}

      {/* Score explanation modal */}
      {explain && (
        <div onClick={() => setExplain(null)}
          className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-xl max-w-lg w-full max-h-[85vh] overflow-y-auto p-5">
            <div className="flex items-start gap-3 mb-1">
              <h2 className="text-lg font-medium text-turquoise-900">
                {placeName(places[explain.candidate.place_id], lang)} — {t.comparison.explainTitle}
              </h2>
              <button onClick={() => setExplain(null)}
                className="ml-auto text-turquoise-800/50 hover:text-turquoise-900" aria-label={t.comparison.close}>×</button>
            </div>
            <p className="text-sm text-turquoise-800/60 mb-4">{t.comparison.explainIntro}</p>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-turquoise-800/60 border-b border-turquoise-100">
                  <th className="py-1.5">{t.comparison.explainCriterion}</th>
                  <th className="py-1.5 text-right">{t.comparison.explainQuality}</th>
                  <th className="py-1.5 text-right">{t.comparison.explainWeight}</th>
                  <th className="py-1.5 text-right">{t.comparison.explainContribution}</th>
                </tr>
              </thead>
              <tbody>
                {(explain.data.rows ?? []).map((r: any) => (
                  <tr key={r.key} className="border-b border-turquoise-50">
                    <td className="py-1.5">
                      {critLabel(r.key)}
                      {r.prioritized && (
                        <span className="ml-1 text-xs text-turquoise-600">({t.comparison.explainPrioritized})</span>
                      )}
                    </td>
                    <td className="py-1.5 text-right">{r.quality}%</td>
                    <td className="py-1.5 text-right">×{r.weight}</td>
                    <td className="py-1.5 text-right font-medium text-turquoise-700">+{r.contribution}%</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-turquoise-200">
                  <td className="py-2 font-medium" colSpan={3}>{t.comparison.explainTotal}</td>
                  <td className="py-2 text-right font-medium text-turquoise-700">{Math.round(explain.data.score)}%</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
    </main>
  )
}
