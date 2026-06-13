// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useT } from '../i18n'
import { placeName } from '../i18n/places'
import { api } from '../services/api'

const MAX_COMPARE = 5

export function Shortlist() {
  const { t, lang } = useT()
  const { searchId } = useParams()
  const sid = Number(searchId)
  const [candidates, setCandidates] = useState<any[]>([])
  const [places, setPlaces] = useState<Record<number, any>>({})
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<number | null>(null)

  // Always read the current truth from the server.
  async function load() {
    const [cands, pls] = await Promise.all([
      api.listCandidates(sid),
      api.listPlaces('country'),
    ])
    setCandidates(cands)
    setPlaces(Object.fromEntries(pls.map((p) => [p.id, p])))
    setLoading(false)
  }

  useEffect(() => { load() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  const selectedCount = candidates.filter((c) => c.selected).length

  async function toggle(c: any) {
    // Server enforces the max; we just disable the box. Re-read after the write.
    if (!c.selected && selectedCount >= MAX_COMPARE) return
    setSavingId(c.id)
    try {
      await api.setSelected(sid, c.id, !c.selected)
      await load()
    } finally {
      setSavingId(null)
    }
  }

  if (loading) return <p className="p-8 text-center">{t.common.loading}</p>

  return (
    <main className="max-w-2xl mx-auto px-5 py-10">
      <h1 className="text-2xl font-medium text-turquoise-900 mb-1">{t.shortlist.title}</h1>
      <p className="text-turquoise-800/70 mb-2">{t.shortlist.subtitle}</p>
      <p className="text-sm text-turquoise-600 mb-5">
        {t.shortlist.selectHint} — {selectedCount}/{MAX_COMPARE} {t.shortlist.selectedLabel}
      </p>

      <ul className="space-y-2 mb-6">
        {candidates.map((c) => {
          const place = places[c.place_id]
          const atMax = !c.selected && selectedCount >= MAX_COMPARE
          return (
            <li key={c.id}
              className={`bg-white border rounded-lg px-4 py-3 ${
                c.selected ? 'border-turquoise-400' : 'border-turquoise-100'}`}>
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={!!c.selected}
                  disabled={atMax || savingId === c.id}
                  onChange={() => toggle(c)}
                  aria-label={placeName(place, lang)}
                  className="w-4 h-4 accent-turquoise-600"
                />
                <span className="font-medium">{placeName(place, lang)}</span>
                <Link to={`/drilldown/${c.place_id}`}
                  className="text-xs text-turquoise-600 hover:underline">{t.comparison.drilldown}</Link>
                <span className="ml-auto text-turquoise-600 font-medium">
                  {t.shortlist.matchScore} {Math.round(c.match_score)}%
                </span>
              </div>
              {Array.isArray(c.match_reasons) && c.match_reasons.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 pl-7">
                  {c.match_reasons.map((r: string) => (
                    <span key={r}
                      className="text-xs bg-turquoise-50 text-turquoise-600 rounded-full px-2.5 py-0.5">
                      {r}
                    </span>
                  ))}
                </div>
              )}
            </li>
          )
        })}
      </ul>

      <Link
        to={`/compare/${searchId}`}
        className="inline-block bg-turquoise-600 text-turquoise-50 rounded-lg px-5 py-2.5"
      >
        {t.shortlist.compare}
      </Link>
    </main>
  )
}
