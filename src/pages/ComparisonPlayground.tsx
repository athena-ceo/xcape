// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { VoiceButton } from '../components/VoiceButton'
import { VoiceField } from '../components/VoiceField'
import { useT } from '../i18n'
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

  const [baseline, setBaseline] = useState<any>(null)

  async function reload() {
    const [cands, pls, hist] = await Promise.all([
      api.listCandidates(sid),
      api.listPlaces('country'),
      api.getChat(sid),
    ])
    setCandidates(cands.slice(0, 8))
    setPlaces(Object.fromEntries(pls.map((p) => [p.id, p])))
    setMessages(hist)
  }

  async function loadBaseline() {
    // May research the current country on first call (cache-first thereafter).
    const b = await api.getBaseline(sid)
    setBaseline(b)
    if (b) setCandidates((await api.listCandidates(sid)).slice(0, 8)) // refresh deltas
  }

  useEffect(() => { reload(); loadBaseline() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  function indicator(delta?: string) {
    if (delta === 'better') return <span title={t.comparison.better} className="text-green-600">↑</span>
    if (delta === 'worse') return <span title={t.comparison.worse} className="text-red-600">↓</span>
    if (delta === 'same') return <span title={t.comparison.same} className="text-turquoise-800/30">=</span>
    return null
  }

  async function send(message: string) {
    if (!message.trim() || chatBusy) return
    setChat('')
    setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: 'user', content: message }])
    setChatBusy(true)
    try {
      await api.sendChat(sid, message)
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
    const updated = await api.addCriterion(sid, key)
    setCandidates((cur) => cur.map((c) => updated.find((u) => u.id === c.id) ?? c))
  }

  async function removeCountry(candidateId: number) {
    await api.removeCandidate(sid, candidateId)
    setCandidates((c) => c.filter((x) => x.id !== candidateId))
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

  const availableCriteria = ALL_CRITERIA.filter((k) => !rows.includes(k))

  return (
    <main className="max-w-4xl mx-auto px-5 py-8">
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <h1 className="text-xl font-medium text-turquoise-900">{t.comparison.title}</h1>
        <div className="ml-auto flex flex-wrap gap-2 text-sm">
          <button onClick={narrow} disabled={narrowing}
            className="border border-turquoise-100 rounded-md px-3 py-1.5 disabled:opacity-50">
            {narrowing ? t.comparison.narrowing : t.comparison.narrow}
          </button>
        </div>
      </div>

      {/* Comparison table */}
      <div className="overflow-x-auto bg-white border border-turquoise-100 rounded-lg mb-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-turquoise-50 text-left">
              <th className="p-3 font-medium">{t.comparison.criterion}</th>
              {baseline && (
                <th className="p-3 font-medium bg-turquoise-100/60 whitespace-nowrap" title={t.comparison.current}>
                  {baseline.name}
                </th>
              )}
              {candidates.map((c) => (
                <th key={c.id} className="p-3 font-medium whitespace-nowrap">
                  <Link to={`/drilldown/${c.place_id}`} className="text-turquoise-600 hover:underline">
                    {places[c.place_id]?.name}
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
                    {String(baseline.attributes?.[key] ?? '—')}
                  </td>
                )}
                {candidates.map((c) => (
                  <td key={c.id} className="p-3 text-center">
                    {String(c.per_criterion?.[key] ?? '—')} {indicator(c.vs_current?.[key])}
                  </td>
                ))}
              </tr>
            ))}
            <tr className="border-t border-turquoise-200 bg-turquoise-50">
              <td className="p-3 font-medium">{t.comparison.matchScore}</td>
              {baseline && <td className="p-3 text-center bg-turquoise-100/60 text-turquoise-800/40">—</td>}
              {candidates.map((c) => (
                <td key={c.id} className="p-3 text-center font-medium text-turquoise-600">
                  {c.match_score != null ? `${Math.round(c.match_score)}%` : '—'}
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
            className="bg-turquoise-600 text-turquoise-50 rounded-md px-3 py-1.5 text-sm disabled:opacity-50">
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

      {/* Discriminator questions */}
      {questions.length > 0 && (
        <div className="bg-white border border-turquoise-100 rounded-lg p-4 mb-4">
          <div className="space-y-3">
            {questions.map((q, i) => (
              <div key={i}>
                <p className="text-sm font-medium">{lang === 'fr' ? q.question_fr : q.question_en}</p>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {(q.options ?? []).map((o: string) => (
                    <button key={o} onClick={() => setChat(`${lang === 'fr' ? q.question_fr : q.question_en} ${o}`)}
                      className="text-xs border border-turquoise-100 rounded-full px-2.5 py-0.5 hover:bg-turquoise-50">
                      {o}
                    </button>
                  ))}
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
              {m.content}
            </div>
          ))}
          {chatBusy && <p className="text-sm text-turquoise-800/50">{t.comparison.thinking}</p>}
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
    </main>
  )
}
