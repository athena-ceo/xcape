// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useT } from '../i18n'
import { placeName } from '../i18n/places'
import { api } from '../services/api'
import { labelOf, useCriteria } from '../services/criteria'

type Row = {
  place_id: number; name: string; iso_code: string | null; score: number
  reasons: string[]; violations: string[]; pending: string[]; on_board: boolean
}

// Full ranked list of every country for the search — a read-only exploration surface reached
// from the comparison board ("Explore all countries"). Doubles as the mobile-friendly results
// view (a list, not a wide matrix). Read-only over the existing scoring: no eval calls.
export function ExplorePage() {
  const { searchId } = useParams()
  const sid = Number(searchId)
  const { t, lang } = useT()
  const reg = useCriteria()

  const [rows, setRows] = useState<Row[] | null>(null)
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<'score' | 'name'>('score')
  const [showExcluded, setShowExcluded] = useState(false)
  const [adding, setAdding] = useState<Set<number>>(new Set())
  const [added, setAdded] = useState<Set<number>>(new Set())
  type Spark = { place_id: number; name: string; iso_code: string | null; score: number; standout_key: string; standout_value: number }
  const [sparks, setSparks] = useState<Spark[] | null>(null)
  // The search's custom criteria — needed to localize custom keys (e.g. community safety) in
  // violation reasons; labelOf falls back to the raw key without them.
  const [customs, setCustoms] = useState<{ key: string; label: string }[]>([])

  useEffect(() => { api.explore(sid).then(setRows).catch(() => setRows([])) }, [sid])
  useEffect(() => { api.listCustomCriteria(sid).then(setCustoms).catch(() => {}) }, [sid])
  function shuffleSparks() { setSparks(null); api.wildcards(sid).then(setSparks).catch(() => setSparks([])) }
  useEffect(() => { shuffleSparks() }, [sid])  // eslint-disable-line react-hooks/exhaustive-deps

  // Localise a criterion key, incl. service component sub-keys (healthcare:access).
  function critLabel(key: string): string {
    const [base, comp] = key.split(':')
    const label = labelOf(reg, base, lang, customs)  // customs → resolves custom-criterion labels
    return comp ? `${label} · ${(t.trend as Record<string, string>)[comp] ?? comp}` : label
  }

  const visible = useMemo(() => {
    if (!rows) return []
    const needle = q.trim().toLowerCase()
    let list = rows.filter((r) => !needle || placeName(r, lang).toLowerCase().includes(needle))
    if (!showExcluded) list = list.filter((r) => r.violations.length === 0)
    list = [...list].sort((a, b) =>
      sort === 'name' ? placeName(a, lang).localeCompare(placeName(b, lang)) : b.score - a.score)
    return list
  }, [rows, q, sort, showExcluded, lang])

  async function add(r: Row) {
    if (adding.has(r.place_id) || added.has(r.place_id) || r.on_board) return
    setAdding((s) => new Set(s).add(r.place_id))
    try {
      await api.addCandidate(sid, { place_id: r.place_id })
      setAdded((s) => new Set(s).add(r.place_id))
    } finally {
      setAdding((s) => { const n = new Set(s); n.delete(r.place_id); return n })
    }
  }

  const excludedCount = rows ? rows.filter((r) => r.violations.length > 0).length : 0
  const scoreTier = (s: number) => (s >= 70 ? 'text-emerald-700' : s >= 50 ? 'text-turquoise-700' : 'text-amber-700')

  return (
    <main className="max-w-3xl mx-auto px-5 py-8">
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <h1 className="text-xl font-medium text-turquoise-900">{t.explore.title}</h1>
        <Link to={`/compare/${sid}`} className="text-sm text-turquoise-600 hover:underline">
          ← {t.explore.backToBoard}
        </Link>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4 text-sm">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.explore.searchPlaceholder}
          className="flex-1 min-w-[10rem] border border-turquoise-100 rounded-md px-3 py-1.5" />
        <select value={sort} onChange={(e) => setSort(e.target.value as 'score' | 'name')}
          className="border border-turquoise-100 rounded-md px-2 py-1.5">
          <option value="score">{t.explore.sortByScore}</option>
          <option value="name">{t.explore.sortByName}</option>
        </select>
        {excludedCount > 0 && (
          <label className="flex items-center gap-1.5 text-turquoise-800/70">
            <input type="checkbox" checked={showExcluded} className="accent-turquoise-600"
              onChange={(e) => setShowExcluded(e.target.checked)} />
            {t.explore.showExcluded} ({excludedCount})
          </label>
        )}
      </div>

      {/* Sparks: off-board dark horses to provoke ideas — clearly NOT recommendations. */}
      {sparks && sparks.length > 0 && (
        <div className="mb-5 rounded-lg border border-amber-200 bg-amber-50/50 p-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-medium text-amber-900">✨ {t.explore.sparksTitle}</span>
            <span className="text-xs text-amber-800/70">{t.explore.sparksHint}</span>
            <button onClick={shuffleSparks} className="ml-auto text-xs text-amber-800 hover:underline">↻ {t.explore.shuffle}</button>
          </div>
          <div className="grid sm:grid-cols-3 gap-2">
            {sparks.map((s) => (
              <Link key={s.place_id} to={`/drilldown/${s.place_id}?search=${sid}`}
                className="block rounded-md border border-amber-100 bg-white px-3 py-2 hover:border-amber-300">
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-turquoise-900">{placeName(s, lang)}</span>
                  <span className="text-xs text-turquoise-800/50 tabular-nums">{s.score}%</span>
                </div>
                <div className="text-xs text-amber-800/80">
                  {t.explore.strongOn} {critLabel(s.standout_key)} ({s.standout_value})
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {rows === null ? (
        <p className="text-sm text-turquoise-800/50">{t.explore.loading}</p>
      ) : (
        <>
          <p className="text-xs text-turquoise-800/50 mb-2">{visible.length} / {rows.length}</p>
          <ul className="divide-y divide-turquoise-50 border border-turquoise-100 rounded-lg overflow-hidden">
            {visible.map((r) => {
              const excluded = r.violations.length > 0
              const onBoard = r.on_board || added.has(r.place_id)
              return (
                <li key={r.place_id} className={`flex items-center gap-3 px-3 py-2.5 ${excluded ? 'bg-amber-50/40' : 'bg-white'}`}>
                  <span className={`w-10 text-right font-medium tabular-nums ${scoreTier(r.score)}`}>{r.score}%</span>
                  <div className="flex-1 min-w-0">
                    <Link to={`/drilldown/${r.place_id}?search=${sid}`}
                      className="text-turquoise-900 hover:underline">{placeName(r, lang)}</Link>
                    {excluded && (
                      <span className="ml-2 text-xs text-amber-700">
                        ⚠ {t.comparison.flagBadge}: {r.violations.map(critLabel).join(', ')}
                      </span>
                    )}
                    {!excluded && r.reasons.length > 0 && (
                      <span className="ml-2 text-xs text-turquoise-800/50">{r.reasons.join(' · ')}</span>
                    )}
                  </div>
                  {onBoard ? (
                    <span className="text-xs text-turquoise-600/70 shrink-0">{t.explore.onBoard}</span>
                  ) : (
                    <button onClick={() => add(r)} disabled={adding.has(r.place_id)}
                      className="text-xs border border-turquoise-100 rounded-md px-2.5 py-1 text-turquoise-700 hover:bg-turquoise-50 disabled:opacity-50 shrink-0">
                      {t.explore.addToBoard}
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        </>
      )}
    </main>
  )
}
