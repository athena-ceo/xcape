// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { Spinner } from '../components/Spinner'
import { useT } from '../i18n'
import { placeName } from '../i18n/places'
import { api } from '../services/api'

// Drill-down on a country: built-in summary, basic facts (population, capital, …), an
// inline map and photos, AI per-criterion detail with sources, and useful links.
// Facts load fast; the AI detail and media stream in with their own loading states.
export function Drilldown() {
  const { t, lang } = useT()
  const { placeId } = useParams()
  const navigate = useNavigate()
  const { hash } = useLocation()
  const id = Number(placeId)

  const [place, setPlace] = useState<any>(null)
  const [facts, setFacts] = useState<any>(null)
  const [detail, setDetail] = useState<any[] | null>(null)
  const [media, setMedia] = useState<any[]>([])
  const [loadingDetail, setLoadingDetail] = useState(true)
  const [loadingMedia, setLoadingMedia] = useState(true)

  useEffect(() => {
    api.getPlace(id).then(setPlace)
    api.getFacts(id).then(setFacts).catch(() => {})
    api.getDetail(id, lang).then((d) => setDetail(d.criteria ?? [])).catch(() => setDetail([]))
      .finally(() => setLoadingDetail(false))
    api.getMedia(id).then(setMedia).catch(() => {}).finally(() => setLoadingMedia(false))
  }, [id, lang])

  // After the criterion detail renders, scroll to the section the user clicked (the URL
  // hash, e.g. #criterion-healthcare), with a brief highlight.
  useEffect(() => {
    if (loadingDetail || !hash) return
    const el = document.getElementById(hash.slice(1))
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      el.classList.add('ring-2', 'ring-turquoise-300')
      setTimeout(() => el.classList.remove('ring-2', 'ring-turquoise-300'), 1800)
    }
  }, [loadingDetail, hash])

  const summary = place && (lang === 'fr' ? place.summary_fr : place.summary_en)
  const photos = media.filter((m) => m.type === 'photo')
  const links = media.filter((m) => m.type !== 'photo')

  // A source may arrive as a plain URL or as a Markdown link "[name](url)". Pull out the
  // URL, drop utm_* tracking params, and label it with the site name (hostname).
  function parseSource(raw: string): { url: string; label: string } | null {
    const match = String(raw).match(/https?:\/\/[^\s)\]]+/)
    if (!match) return null
    try {
      const u = new URL(match[0])
      for (const key of [...u.searchParams.keys()]) {
        if (key.toLowerCase().startsWith('utm_')) u.searchParams.delete(key)
      }
      return { url: u.toString(), label: u.hostname.replace(/^www\./, '') }
    } catch {
      return { url: match[0], label: match[0] }
    }
  }

  // Older cached summaries had URLs / "Sources:" inlined; strip them for display.
  function cleanSummary(s: string): string {
    return s
      .replace(/https?:\/\/\S+/g, '')
      .replace(/\s*\b(Voir|Sources?|See)\b\s*:?/gi, '')
      .replace(/\s*[;,]\s*\./g, '.')
      .replace(/\s{2,}/g, ' ')
      .replace(/\s+([.,;])/g, '$1')
      .trim()
  }

  function fact(label: string, value: any) {
    if (value == null || value === '') return null
    return (
      <div className="bg-turquoise-50 rounded-md px-3 py-2">
        <p className="text-xs text-turquoise-800/60">{label}</p>
        <p className="text-sm font-medium text-turquoise-900">{value}</p>
      </div>
    )
  }

  return (
    <main className="max-w-3xl mx-auto px-5 py-8">
      <button onClick={() => navigate(-1)} className="text-turquoise-600 text-sm mb-4">
        ← {t.drilldown.back}
      </button>

      <div className="flex items-center gap-3 mb-2">
        {facts?.flag && <img src={facts.flag} alt="" className="w-10 h-auto rounded border border-turquoise-100" />}
        <h1 className="text-2xl font-medium text-turquoise-900">{placeName(place, lang)}</h1>
      </div>
      {summary && <p className="text-turquoise-800/80 mb-5">{summary}</p>}

      {/* Basic facts */}
      {facts && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-5">
          {fact(t.drilldown.capital, facts.capital)}
          {fact(t.drilldown.population, facts.population ? Number(facts.population).toLocaleString(lang) : null)}
          {fact(t.drilldown.currency, (facts.currencies ?? []).join(', '))}
          {fact(t.drilldown.region, facts.subregion || facts.region)}
          {fact(t.drilldown.area, facts.area_km2 ? `${Number(facts.area_km2).toLocaleString(lang)} km²` : null)}
        </div>
      )}

      {/* Inline map + lead photo */}
      <div className="grid sm:grid-cols-2 gap-3 mb-6">
        {facts?.osm_bbox && (
          <iframe
            title="map"
            className="w-full h-56 rounded-lg border border-turquoise-100"
            src={`https://www.openstreetmap.org/export/embed.html?bbox=${facts.osm_bbox}&layer=mapnik&marker=${facts.lat},${facts.lng}`}
          />
        )}
        {facts?.image && (
          <img src={facts.image} alt={placeName(place, lang)}
            className="w-full h-56 object-cover rounded-lg border border-turquoise-100" />
        )}
      </div>

      {/* Extra photos discovered via web search (best-effort) */}
      {photos.length > 0 && (
        <div className="grid grid-cols-3 gap-2 mb-6">
          {photos.map((m) => (
            <img key={m.id} src={m.url} alt={m.caption || ''}
              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
              className="w-full h-28 object-cover rounded-md border border-turquoise-100" />
          ))}
        </div>
      )}

      {/* Per-criterion detail with sources */}
      <h2 className="text-lg font-medium text-turquoise-900 mb-3">{t.drilldown.detailTitle}</h2>
      {loadingDetail && (
        <p className="text-turquoise-800/60 mb-4 flex items-center gap-2">
          <Spinner /> {t.drilldown.loadingDetail}
        </p>
      )}
      <div className="space-y-3 mb-6">
        {(detail ?? []).map((d) => (
          <div key={d.key} id={`criterion-${d.key}`}
            className="bg-white border border-turquoise-100 rounded-lg p-4 scroll-mt-4 transition-shadow">
            <p className="text-sm font-medium text-turquoise-900 mb-1">
              {(t.criteria as Record<string, string>)[d.key] ?? d.key}
            </p>
            <p className="text-sm text-turquoise-800/80">{cleanSummary(d.summary)}</p>
            {Array.isArray(d.sources) && d.sources.length > 0 && (
              <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
                <span className="text-xs text-turquoise-800/50">{t.drilldown.sources}:</span>
                {d.sources.map((s: string, i: number) => {
                  const src = parseSource(s)
                  return src && (
                    <a key={i} href={src.url} target="_blank" rel="noreferrer"
                      className="text-xs text-turquoise-600 hover:underline">
                      {src.label}
                    </a>
                  )
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Useful links */}
      <h2 className="text-lg font-medium text-turquoise-900 mb-3">{t.drilldown.links}</h2>
      {loadingMedia && (
        <p className="text-turquoise-800/60 flex items-center gap-2">
          <Spinner /> {t.drilldown.loading}
        </p>
      )}
      {!loadingMedia && links.length === 0 && <p className="text-turquoise-800/60">{t.drilldown.noMedia}</p>}
      <ul className="space-y-2">
        {links.map((m) => (
          <li key={m.id} className="bg-white border border-turquoise-100 rounded-lg px-4 py-3">
            <a href={m.url} target="_blank" rel="noreferrer"
              className="text-turquoise-600 hover:underline break-words">{m.caption || m.url}</a>
          </li>
        ))}
      </ul>
    </main>
  )
}
