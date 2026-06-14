// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { CriteriaSettings } from '../components/CriteriaSettings'
import { Markdown } from '../components/Markdown'
import { Spinner } from '../components/Spinner'
import { VoiceButton } from '../components/VoiceButton'
import { VoiceField } from '../components/VoiceField'
import { useT } from '../i18n'
import { attrValue, languageCell, placeName } from '../i18n/places'
import { api } from '../services/api'

const DEFAULT_ROWS = ['cost_of_living', 'climate', 'language_ease', 'healthcare', 'political_stability']
const ALL_CRITERIA = [
  'cost_of_living', 'climate', 'language_ease', 'healthcare', 'safety',
  'political_stability', 'tax', 'visa', 'expat_community', 'nature', 'internet',
] as const

type CritKey = (typeof ALL_CRITERIA)[number]

export function ComparisonPlayground() {
  const { t, lang } = useT()
  const { searchId } = useParams()
  const sid = Number(searchId)
  const [candidates, setCandidates] = useState<any[]>([])
  const [places, setPlaces] = useState<Record<number, any>>({})
  const [rows, setRows] = useState<string[]>(DEFAULT_ROWS)

  const [chat, setChat] = useState('')
  const [messages, setMessages] = useState<any[]>([])
  const [chatBusy, setChatBusy] = useState(false)

  const [newCountry, setNewCountry] = useState('')
  const [researching, setResearching] = useState(false)
  const [newCriterion, setNewCriterion] = useState<CritKey | ''>('')

  const [questions, setQuestions] = useState<any[]>([])
  const [narrowing, setNarrowing] = useState(false)
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [filters, setFilters] = useState<Record<string, any>>({})
  const [showSettings, setShowSettings] = useState(false)
  const [applying, setApplying] = useState(false)

  const [baseline, setBaseline] = useState<any>(null)
  const [explain, setExplain] = useState<{ candidate: any; data: any } | null>(null)

  // Re-read candidates from the server (the source of truth) and keep only the ones
  // the user selected for the comparison board.
  async function reloadCandidates() {
    const cands = await api.listCandidates(sid)
    setCandidates(cands.filter((c) => c.selected))
  }

  async function reload() {
    const [pls, hist, profile] = await Promise.all([
      api.listPlaces('country'), api.getChat(sid), api.getProfile() as Promise<any>,
    ])
    setPlaces(Object.fromEntries(pls.map((p) => [p.id, p])))
    setMessages(hist)
    setWeights(profile?.criteria_weights ?? {})
    setFilters(profile?.filters ?? {})
    await reloadCandidates()
  }

  async function loadBaseline() {
    // May research the current country on first call (cache-first thereafter).
    const b = await api.getBaseline(sid)
    setBaseline(b)
    if (b) await reloadCandidates() // deltas need the baseline; re-read from server
  }

  useEffect(() => { reload(); loadBaseline() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  // Colour a cell by how good the criterion is for this user: green good, amber weak,
  // red no-go. Light tints that complement the turquoise palette.
  function qualityClass(tier?: string) {
    if (tier === 'good') return 'bg-emerald-50 text-emerald-800'
    if (tier === 'ok') return 'bg-amber-50 text-amber-900'
    if (tier === 'bad') return 'bg-red-50 text-red-800'
    return ''
  }

  async function send(message: string) {
    if (!message.trim() || chatBusy) return
    setChat('')
    const aid = `a-${Date.now()}`
    setMessages((m) => [
      ...m,
      { id: `u-${Date.now()}`, role: 'user', content: message },
      { id: aid, role: 'assistant', content: '' },
    ])
    setChatBusy(true)
    try {
      await api.streamChat(sid, message, (delta) =>
        setMessages((m) => m.map((x) => (x.id === aid ? { ...x, content: x.content + delta } : x))),
      )
    } catch {
      // Fall back to a single non-streamed reply, then re-read history.
      await api.sendChat(sid, message).catch(() => {})
      setMessages(await api.getChat(sid))
    } finally {
      setChatBusy(false)
    }
  }

  async function addCountry() {
    if (!newCountry.trim() || researching) return
    setResearching(true)
    try {
      await api.addCandidate(sid, { place_name: newCountry.trim() })
      setNewCountry('')
      await reload()
    } finally {
      setResearching(false)
    }
  }

  async function addCriterion() {
    if (!newCriterion) return
    const key = newCriterion
    setNewCriterion('')
    if (!rows.includes(key)) setRows((r) => [...r, key])
    await api.addCriterion(sid, key)
    await reloadCandidates() // re-read from server rather than trusting the response
  }

  // "×" removes a country from the comparison board by unselecting it — it stays in the
  // shortlist for reselection.
  async function removeCountry(candidateId: number) {
    await api.setSelected(sid, candidateId, false)
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
  // re-ranks the candidates server-side. Make sure the criterion appears as a row too.
  async function applyWeight(criterion: string, weight: number) {
    if (applying) return
    setApplying(true)
    const next = { ...weights, [criterion]: weight }
    setWeights(next)
    if (!rows.includes(criterion)) setRows((r) => [...r, criterion])
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

  const availableCriteria = ALL_CRITERIA.filter((k) => !rows.includes(k))

  return (
    <main className="max-w-4xl mx-auto px-5 py-8">
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <h1 className="text-xl font-medium text-turquoise-900">{t.comparison.title}</h1>
        <div className="ml-auto flex flex-wrap gap-2 text-sm">
          <button onClick={() => setShowSettings((s) => !s)}
            className="border border-turquoise-100 rounded-md px-3 py-1.5">
            {t.comparison.settings}
          </button>
          <button onClick={narrow} disabled={narrowing}
            className="border border-turquoise-100 rounded-md px-3 py-1.5 disabled:opacity-50 inline-flex items-center gap-2">
            {narrowing && <Spinner />}
            {narrowing ? t.comparison.narrowing : t.comparison.narrow}
          </button>
        </div>
      </div>

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
                  <Link to={`/drilldown/${c.place_id}`} className="text-turquoise-600 hover:underline">
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
            {rows.map((key) => (
              <tr key={key} className="border-t border-turquoise-100">
                <td className="p-3 text-turquoise-800/70">{t.criteria[key as CritKey] ?? key}</td>
                {baseline && (
                  <td className="p-3 text-center bg-turquoise-50">
                    {key === 'language_ease'
                      ? languageCell(t, baseline.attributes)
                      : attrValue(t, baseline.attributes?.[key])}
                  </td>
                )}
                {candidates.map((c) => (
                  // Value and colour both read from the live place attributes (the same
                  // source the backend scores from) so they never disagree.
                  <td key={c.id} className={`p-3 text-center ${qualityClass(c.quality?.[key])}`}>
                    {key === 'language_ease'
                      ? languageCell(t, places[c.place_id]?.attributes)
                      : attrValue(t, places[c.place_id]?.attributes?.[key])}
                  </td>
                ))}
              </tr>
            ))}
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

      {/* Add country / add criterion */}
      <div className="flex flex-wrap gap-3 mb-5">
        <div className="flex items-center gap-2">
          <div className="w-56">
            <VoiceField value={newCountry} onChange={setNewCountry} onEnter={addCountry}
              placeholder={t.comparison.addCountryPrompt}
              className="w-full border border-turquoise-100 rounded-md pl-3 pr-10 py-1.5 text-sm" />
          </div>
          <button onClick={addCountry} disabled={researching}
            className="bg-turquoise-600 text-turquoise-50 rounded-md px-3 py-1.5 text-sm disabled:opacity-50 inline-flex items-center gap-2">
            {researching && <Spinner className="border-turquoise-100 border-t-white" />}
            {researching ? t.comparison.researching : `+ ${t.comparison.addCountry}`}
          </button>
        </div>
        {availableCriteria.length > 0 && (
          <div className="flex items-center gap-2">
            <select value={newCriterion} onChange={(e) => setNewCriterion(e.target.value as CritKey)}
              className="border border-turquoise-100 rounded-md px-2 py-1.5 text-sm">
              <option value="">{t.comparison.addCriterion}…</option>
              {availableCriteria.map((k) => <option key={k} value={k}>{t.criteria[k]}</option>)}
            </select>
            <button onClick={addCriterion} disabled={!newCriterion}
              className="border border-turquoise-100 rounded-md px-3 py-1.5 text-sm disabled:opacity-50">
              +
            </button>
          </div>
        )}
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
        <div className="space-y-2 mb-3 max-h-72 overflow-y-auto">
          {messages.length === 0 && (
            <p className="text-sm text-turquoise-800/50">{t.comparison.chatEmpty}</p>
          )}
          {messages.map((m) => (
            <div key={m.id}
              className={`text-sm rounded-lg px-3 py-2 ${
                m.role === 'user' ? 'bg-turquoise-600 text-turquoise-50 ml-8'
                                  : 'bg-white border border-turquoise-100 mr-8'}`}>
              {m.role === 'user' ? m.content : <Markdown>{m.content}</Markdown>}
            </div>
          ))}
          {chatBusy && !messages[messages.length - 1]?.content && (
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
