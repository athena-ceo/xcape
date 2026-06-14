// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { Fragment, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { CriteriaSettings } from '../components/CriteriaSettings'
import { Markdown } from '../components/Markdown'
import { Spinner } from '../components/Spinner'
import { Waiting } from '../components/Waiting'
import { VoiceButton } from '../components/VoiceButton'
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
  const [evaluating, setEvaluating] = useState(false)
  const evaluatingRef = useRef(false)
  const [places, setPlaces] = useState<Record<number, any>>({})
  // Category expand/collapse, persisted across refreshes; collapsed by default.
  const [openCats, setOpenCats] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem('xcape_open_cats') || '{}') } catch { return {} }
  })
  function toggleCat(key: string, open: boolean) {
    setOpenCats((o) => {
      const next = { ...o, [key]: !open }
      try { localStorage.setItem('xcape_open_cats', JSON.stringify(next)) } catch { /* ignore */ }
      return next
    })
  }

  const [chat, setChat] = useState('')
  const [messages, setMessages] = useState<any[]>([])
  const [chatBusy, setChatBusy] = useState(false)

  const [newCountry, setNewCountry] = useState('')
  const [researching, setResearching] = useState(false)
  const [customCrit, setCustomCrit] = useState<{ key: string; label: string }[]>([])
  const [newCustom, setNewCustom] = useState('')
  const [newCustomDesc, setNewCustomDesc] = useState('')
  const [addingCustom, setAddingCustom] = useState(false)

  const [questions, setQuestions] = useState<any[]>([])
  const [narrowing, setNarrowing] = useState(false)
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [filters, setFilters] = useState<Record<string, any>>({})
  const [showSettings, setShowSettings] = useState(false)
  const [showTune, setShowTune] = useState(false)
  const [tuneTags, setTuneTags] = useState<string[]>([])
  const [tuneText, setTuneText] = useState('')
  const [tuning, setTuning] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [applying, setApplying] = useState(false)

  const [baseline, setBaseline] = useState<any>(null)
  const [explain, setExplain] = useState<{ candidate: any; data: any } | null>(null)
  const [why, setWhy] = useState<{ placeId: number; name: string; key: string; value: any; text: string; score?: number | null } | null>(null)
  const chatScrollRef = useRef<HTMLDivElement | null>(null)
  const lastReplyRef = useRef<HTMLDivElement | null>(null)

  // When a new assistant reply arrives, scroll so the TOP of that reply is at the top of
  // the chat box (the user reads from the start of the answer). While waiting, or after a
  // user turn, fall back to pinning to the bottom so the spinner / new message is visible.
  useEffect(() => {
    const el = chatScrollRef.current
    if (!el) return
    const last = messages[messages.length - 1]
    if (!chatBusy && last?.role === 'assistant' && lastReplyRef.current) {
      el.scrollTop = lastReplyRef.current.offsetTop - el.offsetTop
    } else {
      el.scrollTop = el.scrollHeight
    }
  }, [messages, chatBusy])

  // Split a candidate list into the board (selected) and the suggestion pool, and kick off
  // progressive evaluation if any cells are still pending.
  function applyCandidates(cands: any[]) {
    setCandidates(cands.filter((c) => c.selected))
    setSuggestions(cands.filter((c) => !c.selected))
    if (cands.some((c) => (c.pending || []).length)) void drainPending()
  }

  // Re-read candidates from the server (the source of truth).
  async function reloadCandidates() {
    applyCandidates(await api.listCandidates(sid))
  }

  // Fill not-yet-evaluated (country × criterion) cells a few at a time, re-rendering after
  // each batch (candidates AND the baseline column), until nothing is pending. Guarded so
  // only one drain runs at a time.
  async function drainPending() {
    if (evaluatingRef.current) return
    evaluatingRef.current = true
    setEvaluating(true)
    try {
      for (let i = 0; i < 200; i++) {
        const cands = await api.evaluatePending(sid, 2)
        setCandidates(cands.filter((c) => c.selected))
        setSuggestions(cands.filter((c) => !c.selected))
        const b: any = await api.getBaseline(sid).catch(() => null)
        if (b) setBaseline(b)
        const anyPending = cands.some((c) => (c.pending || []).length) || !!(b?.pending?.length)
        if (!anyPending) break
      }
    } finally {
      evaluatingRef.current = false
      setEvaluating(false)
    }
  }

  async function reload() {
    const [pls, hist, profile, custom] = await Promise.all([
      api.listPlaces('country'), api.getChat(sid), api.getProfile() as Promise<any>,
      api.listCustomCriteria(sid).catch(() => []),
    ])
    setPlaces(Object.fromEntries(pls.map((p) => [p.id, p])))
    setMessages(hist)
    setWeights(profile?.criteria_weights ?? {})
    setFilters(profile?.filters ?? {})
    setCustomCrit(custom.map((c: any) => ({ key: c.key, label: c.label })))
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
    return labelOf(reg, key, lang, customCrit)
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

  async function send(message: string) {
    if (!message.trim() || chatBusy) return
    setChat('')
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: 'user', content: message }])
    setChatBusy(true)
    try {
      const res = await api.sendChat(sid, message)
      // The assistant may have used tools to change the board — re-read everything so the
      // table, weights and filters reflect it (also syncs the chat history).
      if (res.changed) await reload()
      else setMessages(await api.getChat(sid))
    } finally {
      setChatBusy(false)
    }
  }

  // Hybrid criterion selection: chosen tags + free text → AI sets weights / adds criteria.
  async function tune() {
    if (tuning) return
    setTuning(true)
    try {
      await api.suggestCriteria(sid, tuneTags, tuneText.trim())
      setShowTune(false)
      setTuneText('')
      await reload()  // picks up new weights, custom criteria and re-ranked candidates
    } finally {
      setTuning(false)
    }
  }

  async function downloadReport() {
    if (downloading) return
    setDownloading(true)
    try {
      await api.downloadReport(sid)
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
      await reload() // picks up the new column, labels and re-scored candidates
    } finally {
      setAddingCustom(false)
    }
  }

  // "×" removes a country from the comparison board by unselecting it — it stays in the
  // shortlist for reselection.
  async function removeCountry(candidateId: number) {
    await api.setSelected(sid, candidateId, false)
    await reloadCandidates()
  }

  // One-click add a suggested (ranked but unselected) country to the board.
  async function addSuggestion(candidateId: number) {
    if (candidates.length >= 5) return
    await api.setSelected(sid, candidateId, true)
    await reloadCandidates()
  }

  async function narrow() {
    setNarrowing(true)
    try {
      const res = await api.discriminate(sid)
      setQuestions(res.questions ?? [])
    } finally {
      setNarrowing(false)
    }
  }

  // Picking an answer sets that criterion's importance weight, which re-scores and
  // re-ranks the candidates server-side.
  async function applyWeight(criterion: string, weight: number) {
    if (applying) return
    setApplying(true)
    const next = { ...weights, [criterion]: weight }
    setWeights(next)
    try {
      await api.updateProfile({ criteria_weights: next }) // triggers rescore
      await reloadCandidates() // scores in the table update
    } finally {
      setApplying(false)
    }
  }

  async function showExplanation(candidate: any) {
    const data = await api.scoreExplanation(sid, candidate.id)
    setExplain({ candidate, data })
  }

  // Apply criteria settings: persist weights + filters, then rebuild the shortlist so
  // filters (e.g. language) change which countries qualify.
  async function applySettings(w: Record<string, number>, f: Record<string, any>) {
    setApplying(true)
    try {
      await api.updateProfile({ criteria_weights: w, filters: f })
      await api.buildShortlist(sid)
      setShowSettings(false)
      await reload()
    } finally {
      setApplying(false)
    }
  }

  // Criteria grouped for the table: registry categories + a synthetic group for the
  // search's custom criteria. Each group = {key, label, leaves[]}.
  const TIER_VALUE: Record<string, number> = { good: 1, ok: 0.6, bad: 0.3 }
  const groups = [
    ...categories(reg).map((c) => ({
      key: c.key, label: labelOf(reg, c.key, lang), leaves: c.leaves,
    })),
    ...(customCrit.length
      ? [{ key: '__custom', label: t.comparison.customGroup, leaves: customCrit.map((c) => c.key) }]
      : []),
  ]
  const weightOf = (key: string) => weights[key] ?? 0
  // Collapsed by default; the user's choice persists (see openCats / toggleCat).
  const isOpen = (g: { key: string; leaves: string[] }) => openCats[g.key] ?? false
  // Roll-up colour tier for a category column = weighted average of its leaves' tiers.
  function rollupTier(cand: any, leaves: string[]): string | undefined {
    let num = 0, den = 0
    for (const k of leaves) {
      const tier = cand.quality?.[k]
      if (!tier) continue
      const w = weightOf(k) || 0.5
      num += TIER_VALUE[tier] * w; den += w
    }
    if (!den) return undefined
    const v = num / den
    return v >= 0.7 ? 'good' : v >= 0.45 ? 'ok' : 'bad'
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

  // One leaf criterion row (used inside each open category group).
  function leafRow(key: string) {
    return (
      <tr key={key} className="border-t border-turquoise-50">
        <td className="p-3 pl-8 text-turquoise-800/70">{critLabel(key)}</td>
        {baseline && (() => {
          const bpending = (baseline.pending || []).includes(key)
          const bcol = { place_id: baseline.id, reasons: baseline.reasons, quality: baseline.quality }
          return (
            <td className={`p-0 text-center ${qualityClass(baseline.quality?.[key]) || 'bg-turquoise-50'}`}>
              <button onClick={() => openWhy(bcol, key)} className="block w-full p-3 hover:underline cursor-pointer">
                {bpending
                  ? <span className="inline-flex justify-center text-turquoise-800/40"><Spinner /></span>
                  : cellValue(key, baseline.attributes, baseline.quality?.[key])}
              </button>
            </td>
          )
        })()}
        {candidates.map((c) => {
          const pending = (c.pending || []).includes(key)
          return (
            <td key={c.id} className={`p-0 text-center ${pending ? '' : qualityClass(c.quality?.[key])}`}>
              <button onClick={() => openWhy(c, key)} className="block w-full p-3 hover:underline cursor-pointer">
                {pending
                  ? <span className="inline-flex justify-center text-turquoise-800/40"><Spinner /></span>
                  : cellValue(key, places[c.place_id]?.attributes, c.quality?.[key])}
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
          <button onClick={() => setShowTune((s) => !s)}
            className="border border-turquoise-100 rounded-md px-3 py-1.5">
            {t.comparison.tune}
          </button>
          <button onClick={() => setShowSettings((s) => !s)}
            className="border border-turquoise-100 rounded-md px-3 py-1.5">
            {t.comparison.settings}
          </button>
          <button onClick={downloadReport} disabled={downloading || !candidates.length}
            className="border border-turquoise-100 rounded-md px-3 py-1.5 disabled:opacity-50 inline-flex items-center gap-2">
            {downloading && <Spinner />}
            {t.comparison.downloadReport}
          </button>
          <button onClick={narrow} disabled={narrowing}
            className="border border-turquoise-100 rounded-md px-3 py-1.5 disabled:opacity-50 inline-flex items-center gap-2">
            {narrowing && <Spinner />}
            {narrowing ? t.comparison.narrowing : t.comparison.narrow}
          </button>
        </div>
      </div>

      {showTune && (
        <div className="bg-white border border-turquoise-100 rounded-lg p-4 mb-4">
          <p className="text-sm text-turquoise-800/70 mb-2">{t.comparison.tuneHint}</p>
          <div className="flex flex-wrap gap-1.5 mb-3">
            {Object.entries(reg?.tags ?? {}).map(([key, tag]) => {
              const on = tuneTags.includes(key)
              return (
                <button key={key} type="button"
                  onClick={() => setTuneTags((ts) => on ? ts.filter((x) => x !== key) : [...ts, key])}
                  className={`text-xs rounded-full border px-2.5 py-1 ${
                    on ? 'border-turquoise-400 bg-turquoise-50 text-turquoise-700'
                       : 'border-turquoise-100 hover:bg-turquoise-50'}`}>
                  {lang === 'fr' ? (tag as any).label_fr : (tag as any).label_en}
                </button>
              )
            })}
          </div>
          <textarea value={tuneText} onChange={(e) => setTuneText(e.target.value)}
            placeholder={t.comparison.tunePrompt} rows={2}
            className="w-full border border-turquoise-100 rounded-md px-3 py-2 text-sm mb-3" />
          <button onClick={tune} disabled={tuning || (!tuneTags.length && !tuneText.trim())}
            className="bg-turquoise-600 text-turquoise-50 rounded-md px-4 py-2 text-sm disabled:opacity-50 inline-flex items-center gap-2">
            {tuning && <Spinner className="border-turquoise-100 border-t-white" />}
            {tuning ? t.comparison.customAdding : t.comparison.tuneApply}
          </button>
        </div>
      )}

      {showSettings && (
        <CriteriaSettings weights={weights} filters={filters} busy={applying} onApply={applySettings} />
      )}

      {/* Colour legend */}
      <div className="flex items-center gap-4 text-xs text-turquoise-800/70 mb-2">
        <span>{t.comparison.legend}:</span>
        <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-800">{t.comparison.legendGood}</span>
        <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-900">{t.comparison.legendWeak}</span>
        <span className="px-2 py-0.5 rounded bg-red-50 text-red-800">{t.comparison.legendNogo}</span>
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
                  {placeName(baseline, lang)}
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
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => {
              const open = isOpen(g)
              return (
                <Fragment key={g.key}>
                  <tr className="border-t border-turquoise-200 bg-turquoise-50/70 cursor-pointer select-none"
                    onClick={() => toggleCat(g.key, open)}>
                    <td className="p-2.5 font-medium text-turquoise-900">
                      <span className="inline-block w-4 text-turquoise-600">{open ? '▾' : '▸'}</span>{g.label}
                    </td>
                    {baseline && (
                      <td className={`p-2.5 text-center text-xs ${qualityClass(rollupTier(baseline, g.leaves)) || 'bg-turquoise-50'}`}>
                        {tierWord(rollupTier(baseline, g.leaves))}
                      </td>
                    )}
                    {candidates.map((c) => (
                      <td key={c.id} className={`p-2.5 text-center text-xs ${qualityClass(rollupTier(c, g.leaves))}`}>
                        {tierWord(rollupTier(c, g.leaves))}
                      </td>
                    ))}
                  </tr>
                  {open && g.leaves.map((key) => leafRow(key))}
                </Fragment>
              )
            })}
            <tr className="border-t border-turquoise-200 bg-turquoise-50">
              <td className="p-3 font-medium">{t.comparison.matchScore}</td>
              {baseline && <td className="p-3 text-center bg-turquoise-100/60 text-turquoise-800/40">—</td>}
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
        {/* User-defined criterion: a short column name + an optional longer description
            that guides the AI, which then scores each country on it. */}
        <div className="flex items-center gap-2">
          <input value={newCustom} onChange={(e) => setNewCustom(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addCustom()}
            placeholder={t.comparison.customNamePrompt}
            className="w-40 border border-turquoise-100 rounded-md px-3 py-1.5 text-sm" />
          <input value={newCustomDesc} onChange={(e) => setNewCustomDesc(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addCustom()}
            placeholder={t.comparison.customDescPrompt}
            className="w-64 border border-turquoise-100 rounded-md px-3 py-1.5 text-sm" />
          <button onClick={addCustom} disabled={!newCustom.trim() || addingCustom}
            className="border border-turquoise-100 rounded-md px-3 py-1.5 text-sm disabled:opacity-50 inline-flex items-center gap-2">
            {addingCustom && <Spinner />}
            {addingCustom ? t.comparison.customAdding : `+ ${t.comparison.customCriterion}`}
          </button>
        </div>
      </div>

      {/* Discriminator questions — clicking an answer re-weights and re-ranks. */}
      {questions.length > 0 && (
        <div className="bg-white border border-turquoise-100 rounded-lg p-4 mb-4">
          <p className="text-sm text-turquoise-800/60 mb-3">{t.comparison.narrowHint}</p>
          <div className="space-y-4">
            {questions.map((q, i) => (
              <div key={i}>
                <p className="text-sm font-medium">
                  {(t.criteria as Record<string, string>)[q.criterion] ?? q.criterion} — {q.question}
                </p>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {(q.options ?? []).map((o: any, j: number) => {
                    const active = weights[q.criterion] === o.weight
                    return (
                      <button key={j} onClick={() => applyWeight(q.criterion, o.weight)}
                        disabled={applying}
                        className={`text-xs rounded-full px-2.5 py-1 border transition disabled:opacity-50 ${
                          active ? 'border-turquoise-400 bg-turquoise-50 text-turquoise-700'
                                 : 'border-turquoise-100 hover:bg-turquoise-50'}`}>
                        {o.label}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Chat */}
      <div className="bg-turquoise-50 border border-turquoise-100 rounded-lg p-3">
        <p className="text-sm font-medium text-turquoise-600 mb-2">{t.comparison.askAssistant}</p>
        <div ref={chatScrollRef} className="space-y-2 mb-3 max-h-72 overflow-y-auto">
          {messages.length === 0 && (
            <p className="text-sm text-turquoise-800/50">{t.comparison.chatEmpty}</p>
          )}
          {messages.map((m, i) => (
            <div key={m.id}
              ref={i === messages.length - 1 && m.role === 'assistant' ? lastReplyRef : undefined}
              className={`text-sm rounded-lg px-3 py-2 ${
                m.role === 'user' ? 'bg-turquoise-600 text-turquoise-50 ml-8'
                                  : 'bg-white border border-turquoise-100 mr-8'}`}>
              {m.role === 'user' ? m.content : <Markdown>{m.content}</Markdown>}
            </div>
          ))}
          {chatBusy && (
            <p className="text-sm text-turquoise-800/50 flex items-center gap-2">
              <Spinner /> {t.comparison.thinking}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 bg-white rounded-md px-3 py-2">
          <input value={chat} onChange={(e) => setChat(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send(chat)}
            placeholder={t.comparison.placeholder}
            className="flex-1 outline-none text-sm" />
          <VoiceButton onTranscript={(text) => setChat((c) => (c.trim() ? `${c.trim()} ${text}` : text))} />
          <button onClick={() => send(chat)} disabled={chatBusy} className="text-turquoise-600 disabled:opacity-40">→</button>
        </div>
      </div>

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
                      {(t.criteria as Record<string, string>)[r.key] ?? r.key}
                      {r.prioritized && (
                        <span className="ml-1 text-xs text-turquoise-600">({t.comparison.explainPrioritized})</span>
                      )}
                    </td>
                    <td className="py-1.5 text-right">{r.quality}%</td>
                    <td className="py-1.5 text-right">×{r.weight}</td>
                    <td className="py-1.5 text-right font-medium text-turquoise-700">{r.contribution} pts</td>
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
