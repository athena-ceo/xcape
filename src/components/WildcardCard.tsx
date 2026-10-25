// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { useT } from '../i18n'
import { placeName } from '../i18n/places'
import { api } from '../services/api'

interface Props {
  searchId: number
  critLabel: (key: string) => string
  onWhy: (placeId: number) => void
}

// "Something different" (green hat, emotional roadmap item 8): one country off the board that
// excels on something the user cares about — a provocation, clearly not a recommendation.
// Backed by the same wildcard logic as Explore's sparks; "show another" reshuffles.
export function WildcardCard({ searchId, critLabel, onWhy }: Props) {
  const { t, lang } = useT()
  const [items, setItems] = useState<any[]>([])
  const [i, setI] = useState(0)

  function load() {
    api.wildcards(searchId).then((w) => { setItems(w); setI(0) }).catch(() => setItems([]))
  }
  useEffect(load, [searchId]) // eslint-disable-line react-hooks/exhaustive-deps

  const w = items[i]
  if (!w) return null
  return (
    <section aria-labelledby="wildcard-title" className="mb-5 rounded-lg border border-violet-200 bg-violet-50/50 px-3 py-2.5">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h2 id="wildcard-title" className="text-sm font-medium text-violet-900">{t.wildcard.title}</h2>
        <span className="text-xs text-violet-900/70">{t.wildcard.hint}</span>
      </div>
      <p className="mt-1 text-sm text-turquoise-900">
        <Link to={`/drilldown/${w.place_id}?search=${searchId}`} className="font-medium hover:underline">
          {placeName(w, lang)}
        </Link>
        <span className="text-turquoise-800/70"> · {t.explore.strongOn} {critLabel(w.standout_key)} ({w.standout_value}) · {w.score}%</span>
      </p>
      <div className="mt-1 flex gap-4">
        <button onClick={() => onWhy(w.place_id)} className="min-h-9 text-xs text-violet-800 underline decoration-dotted underline-offset-2">
          {t.wildcard.compare}
        </button>
        <button onClick={() => (i + 1 < items.length ? setI(i + 1) : load())}
          className="min-h-9 text-xs text-violet-800 underline decoration-dotted underline-offset-2">
          {t.wildcard.another}
        </button>
      </div>
    </section>
  )
}
