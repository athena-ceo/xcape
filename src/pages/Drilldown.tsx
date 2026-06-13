// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { useT } from '../i18n'
import { api } from '../services/api'

// Drill-down on a candidate: built-in summary + AI/web-discovered media (maps, links,
// photos), cached per place. The first visit may take a moment while media is fetched.
export function Drilldown() {
  const { t, lang } = useT()
  const { placeId } = useParams()
  const navigate = useNavigate()
  const [place, setPlace] = useState<any>(null)
  const [media, setMedia] = useState<any[]>([])
  const [loadingMedia, setLoadingMedia] = useState(true)

  useEffect(() => {
    const id = Number(placeId)
    api.getPlace(id).then(setPlace)
    api.getMedia(id).then(setMedia).finally(() => setLoadingMedia(false))
  }, [placeId])

  const summary = place && (lang === 'fr' ? place.summary_fr : place.summary_en)

  return (
    <main className="max-w-2xl mx-auto px-5 py-8">
      <button onClick={() => navigate(-1)} className="text-turquoise-600 text-sm mb-4">
        ← {t.drilldown.back}
      </button>

      <h1 className="text-2xl font-medium text-turquoise-900 mb-2">{place?.name ?? ''}</h1>
      {summary && (
        <p className="text-turquoise-800/80 mb-6">{summary}</p>
      )}

      <h2 className="text-lg font-medium text-turquoise-900 mb-3">{t.drilldown.links}</h2>
      {loadingMedia && <p className="text-turquoise-800/60">{t.drilldown.loading}</p>}
      {!loadingMedia && media.length === 0 && (
        <p className="text-turquoise-800/60">{t.drilldown.noMedia}</p>
      )}
      <ul className="space-y-2">
        {media.map((m) => (
          <li key={m.id} className="bg-white border border-turquoise-100 rounded-lg px-4 py-3">
            <a href={m.url} target="_blank" rel="noreferrer"
              className="text-turquoise-600 hover:underline break-words">
              {m.caption || m.url}
            </a>
            {m.source && <p className="text-xs text-turquoise-800/50 mt-1 break-words">{m.source}</p>}
          </li>
        ))}
      </ul>
    </main>
  )
}
