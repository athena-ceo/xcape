// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { useT } from '../i18n'
import { placeName } from '../i18n/places'
import { api } from '../services/api'
import { useHearts } from '../services/hearts'
import { HeartButton } from './HeartButton'

interface Props {
  searchId: number
  // Changes whenever the board changes, so the standings are re-read.
  boardKey: string
  critLabel: (key: string) => string
  onWhy: (placeId: number) => void
}

// "Your heart says X, the numbers say Y" (emotional roadmap, item 5): each hearted country
// with where the numbers put it against the user's #5. The heart never changes a score —
// this puts the two side by side, so the gap is visible and can be acted on.
export function HeartsPanel({ searchId, boardKey, critLabel, onWhy }: Props) {
  const { t, lang } = useT()
  const { hearts } = useHearts()
  const [rows, setRows] = useState<any[] | null>(null)
  const heartKey = hearts.map((h) => h.place_id).join(',')

  useEffect(() => {
    if (!heartKey) { setRows([]); return }
    let cancelled = false
    api.heartsVsNumbers(searchId).then((r) => { if (!cancelled) setRows(r) }).catch(() => {})
    return () => { cancelled = true }
  }, [searchId, heartKey, boardKey])

  const fill = (s: string, v: Record<string, string | number>) =>
    Object.entries(v).reduce((acc, [k, x]) => acc.split(`{${k}}`).join(String(x)), s)

  function standing(r: any): string {
    switch (r.status) {
      case 'on_board': return t.hearts.agree
      case 'home': return t.hearts.home
      case 'removed': return t.hearts.removed
      case 'pending': return t.hearts.pending
      case 'excluded':
        return fill(t.hearts.excluded, { filters: r.violations.map((v: any) => critLabel(v.key)).join(', ') })
      default: {
        const base = fill(t.hearts.below, {
          rank: r.rank ?? '?', score: Math.round(r.score),
          ref: r.reference ? placeName(r.reference, lang) : '', refScore: Math.round(r.reference?.score ?? 0),
        })
        return r.gaps?.length
          ? `${base} ${fill(t.hearts.losesOn, { list: r.gaps.map((g: any) => critLabel(g.key)).join(', ') })}`
          : base
      }
    }
  }

  return (
    <section aria-labelledby="hearts-title" className="mb-5">
      <h2 id="hearts-title" className="text-sm font-medium text-turquoise-900 mb-1.5">{t.hearts.title}</h2>
      {hearts.length === 0 ? (
        <p className="text-xs text-turquoise-800/60">{t.hearts.empty}</p>
      ) : (
        <ul className="space-y-1.5">
          {hearts.map((h) => {
            const r = rows?.find((x) => x.place_id === h.place_id)
            const why = r && !['on_board', 'home'].includes(r.status)
            return (
              <li key={h.place_id} className="flex items-start gap-2 rounded-lg border border-rose-100 bg-rose-50/50 px-2 py-1.5">
                <HeartButton size="sm" place={{ id: h.place_id, name: h.name, iso_code: h.iso_code }} />
                <div className="flex-1 min-w-0 text-sm py-0.5">
                  <Link to={`/drilldown/${h.place_id}?search=${searchId}`} className="font-medium text-turquoise-900 hover:underline">
                    {placeName(h, lang)}
                  </Link>
                  {r && <span className="text-turquoise-800/70">: {standing(r)}</span>}
                </div>
                {why && (
                  <button onClick={() => onWhy(h.place_id)}
                    className="shrink-0 text-xs text-turquoise-700 underline decoration-dotted underline-offset-2 px-1.5 py-1">
                    {t.whyNot.explore}
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
