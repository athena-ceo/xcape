// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useT } from '../i18n'
import { api } from '../services/api'

export function Shortlist() {
  const { t } = useT()
  const { searchId } = useParams()
  const [candidates, setCandidates] = useState<any[]>([])
  const [places, setPlaces] = useState<Record<number, any>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const [cands, pls] = await Promise.all([
        api.listCandidates(Number(searchId)),
        api.listPlaces('country'),
      ])
      setCandidates(cands)
      setPlaces(Object.fromEntries(pls.map((p) => [p.id, p])))
      setLoading(false)
    }
    load()
  }, [searchId])

  if (loading) return <p className="p-8 text-center">{t.common.loading}</p>

  return (
    <main className="max-w-2xl mx-auto px-5 py-10">
      <h1 className="text-2xl font-medium text-turquoise-900 mb-1">{t.shortlist.title}</h1>
      <p className="text-turquoise-800/70 mb-6">{t.shortlist.subtitle}</p>

      <ul className="space-y-2 mb-6">
        {candidates.map((c) => {
          const place = places[c.place_id]
          return (
            <li
              key={c.id}
              className="bg-white border border-turquoise-100 rounded-lg px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <span className="font-medium">{place?.name ?? c.place_id}</span>
                <Link to={`/drilldown/${c.place_id}`}
                  className="text-xs text-turquoise-600 hover:underline">{t.comparison.drilldown}</Link>
                <span className="ml-auto text-turquoise-600 font-medium">
                  {t.shortlist.matchScore} {Math.round(c.match_score)}%
                </span>
              </div>
              {Array.isArray(c.match_reasons) && c.match_reasons.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
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
        {t.shortlist.refine}
      </Link>
    </main>
  )
}
