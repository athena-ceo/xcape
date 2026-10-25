// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useMemo, useState } from 'react'

import { useT } from '../i18n'
import { placeName } from '../i18n/places'
import { api } from '../services/api'
import { addCountryToBoard, type BoardMember } from '../services/board'
import { Spinner } from './Spinner'

type Country = { id: number; name: string; iso_code?: string | null }

interface Props {
  searchId: number
  // The country to explain; null opens the sheet on a country picker first.
  placeId: number | null
  // Countries the picker offers (the user's home is filtered out by the caller).
  countries: Country[]
  // The current board, for the "replace the weakest" prompt when it's full.
  board: BoardMember[]
  // Localized criterion label (handles custom criteria and sub-components).
  critLabel: (key: string) => string
  onClose: () => void
  // The board changed (country added, filter relaxed) — the host re-reads it.
  onChanged: () => void
}

// "Why isn't X in my top 5?" — rank, blocking filters with values, and where the country loses
// points against the user's #5, straight from the board's own scores (GET /why/{place}).
// A bottom sheet on phones, a centred card on larger screens (mockup C).
export function WhyNotSheet({ searchId, placeId, countries, board, critLabel, onClose, onChanged }: Props) {
  const { t, lang } = useT()
  const [pid, setPid] = useState<number | null>(placeId)
  const [q, setQ] = useState('')
  const [data, setData] = useState<any | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setData(null)
    if (pid != null) api.whyNot(searchId, pid).then(setData).catch(() => setData({ error: true }))
  }, [searchId, pid])

  const matches = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return []
    return countries
      .filter((c) => placeName(c, lang).toLowerCase().includes(needle))
      .sort((a, b) => placeName(a, lang).localeCompare(placeName(b, lang), lang))
      .slice(0, 8)
  }, [q, countries, lang])

  const name = data ? placeName(data, lang) : ''
  const refName = data?.reference ? placeName(data.reference, lang) : ''
  const fill = (s: string, extra: Record<string, string | number> = {}) =>
    Object.entries({ country: name, ref: refName, ...extra })
      .reduce((acc, [k, v]) => acc.split(`{${k}}`).join(String(v)), s)

  function minLabel(v: any): string {
    if (v === 'good' || (typeof v === 'number' && v >= 0.7)) return t.comparison.minGood
    if (v === 'ok' || (typeof v === 'number' && v > 0)) return t.comparison.minOk
    return t.whyNot.yourFilter
  }

  async function addAnyway() {
    if (busy || !data) return
    setBusy(true)
    try {
      const res = await addCountryToBoard(
        searchId, { place_id: data.place_id, label: name }, board, t.explore.replaceConfirm)
      if (res === 'added') { onChanged(); onClose() }
    } finally { setBusy(false) }
  }

  async function relax(v: any) {
    if (busy) return
    setBusy(true)
    try {
      if (v.relax === 'custom_min') {
        await api.updateCustomCriterion(searchId, v.key, { min: null })
      } else {
        const profile: any = await api.getProfile()
        const filters = { ...(profile?.filters ?? {}) }
        delete filters[v.key]
        await api.updateProfile({ filters })
      }
      await api.repopulate(searchId)  // filters are exclusionary → re-rank the pool
      onChanged()
      setData(await api.whyNot(searchId, data.place_id))  // show the new standing
    } finally { setBusy(false) }
  }

  const head = !data || data.error ? '' : {
    home: fill(t.whyNot.titleHome),
    on_board: fill(t.whyNot.titleOnBoard),
    removed: fill(t.whyNot.titleRemoved),
  }[data.status as string] ?? fill(t.whyNot.title)

  return (
    <div onClick={onClose} className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center sm:p-4 z-50">
      <section onClick={(e) => e.stopPropagation()} aria-labelledby="why-not-title"
        className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-xl max-h-[88vh] overflow-y-auto p-5">
        <div className="flex items-start gap-3 mb-3">
          <h2 id="why-not-title" className="text-lg font-medium text-turquoise-900 flex-1">
            {pid == null ? t.whyNot.pickTitle : head}
          </h2>
          <button onClick={onClose} aria-label={t.comparison.close}
            className="w-11 h-11 -mt-2 -mr-2 flex items-center justify-center text-turquoise-800/50 hover:text-turquoise-900 text-xl">×</button>
        </div>

        {pid == null ? (
          <div className="relative">
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
              placeholder={t.comparison.addCountryPrompt} aria-label={t.whyNot.pickTitle}
              className="w-full border border-turquoise-100 rounded-md px-3 py-2 text-sm" />
            {matches.length > 0 && (
              <div className="mt-1 border border-turquoise-100 rounded-md divide-y divide-turquoise-50">
                {matches.map((c) => (
                  <button key={c.id} onClick={() => setPid(c.id)}
                    className="block w-full text-left px-3 py-2.5 text-sm hover:bg-turquoise-50">
                    {placeName(c, lang)}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : !data ? (
          <p className="text-sm text-turquoise-800/60 flex items-center gap-2"><Spinner /> {t.common.loading}</p>
        ) : data.error ? (
          <p className="text-sm text-red-700">{t.admin.actionFailed}</p>
        ) : data.status === 'home' ? (
          <p className="text-sm text-turquoise-800/80">{fill(t.whyNot.home)}</p>
        ) : (
          <div className="space-y-4">
            {data.violations.length > 0 && (
              <div role="note" className="rounded-lg px-3 py-2.5 bg-red-50 text-red-900">
                <p className="text-sm font-medium">{t.whyNot.excludedHead}</p>
                <ul className="mt-1 space-y-1 text-sm">
                  {data.violations.map((v: any) => (
                    <li key={v.key}>
                      {fill(v.value != null ? t.whyNot.violation : t.whyNot.violationNoValue,
                        { criterion: critLabel(v.key), min: minLabel(v.min), value: v.value ?? '' })}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.status === 'removed' && <p className="text-sm text-turquoise-800/80">{fill(t.whyNot.removed)}</p>}
            {data.pending.length > 0 && (
              <p className="text-sm text-turquoise-800/70">
                {fill(t.whyNot.pending, { list: data.pending.map(critLabel).join(', ') })}
              </p>
            )}

            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg bg-turquoise-50/70 px-3 py-2">
                <p className="text-xs text-turquoise-800/70">{name}{data.rank ? ` · #${data.rank}/${data.total}` : ''}</p>
                <p className="text-2xl font-semibold text-turquoise-900">{Math.round(data.score)}%</p>
              </div>
              {data.reference && (
                <div className="rounded-lg bg-turquoise-50/70 px-3 py-2">
                  <p className="text-xs text-turquoise-800/70">{fill(t.whyNot.refLabel)}</p>
                  <p className="text-2xl font-semibold text-turquoise-900">{Math.round(data.reference.score)}%</p>
                </div>
              )}
            </div>

            {data.gaps.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-turquoise-900 mb-2">{fill(t.whyNot.gapsTitle)}</h3>
                <ul className="space-y-2">
                  {data.gaps.map((g: any) => (
                    <li key={g.key}>
                      <div className="flex justify-between gap-3 text-sm">
                        <span className="text-turquoise-900">{critLabel(g.key)}</span>
                        <span className="text-red-700 tabular-nums shrink-0">−{g.points} {t.whyNot.pts}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <div className="h-2 flex-1 rounded bg-turquoise-50 overflow-hidden" aria-hidden="true">
                          <div className="h-2 rounded bg-amber-500" style={{ width: `${g.quality}%` }} />
                        </div>
                        <span className="text-xs text-turquoise-800/60 tabular-nums w-24 text-right">
                          {g.quality} {t.whyNot.vs} {g.ref_quality}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.strengths.length > 0 && (
              <p className="text-sm text-turquoise-800/70">
                {fill(t.whyNot.strengths, { list: data.strengths.map((s: any) => critLabel(s.key)).join(', ') })}
              </p>
            )}

            {data.status !== 'on_board' && (
              <div className="flex flex-col gap-2 pt-1">
                <button onClick={addAnyway} disabled={busy}
                  className="min-h-11 rounded-full bg-turquoise-600 text-turquoise-50 px-4 text-sm font-medium disabled:opacity-50">
                  {fill(data.violations.length ? t.whyNot.addAnyway : t.whyNot.add)}
                </button>
                {data.violations.map((v: any) => (
                  <button key={v.key} onClick={() => relax(v)} disabled={busy}
                    className="min-h-11 rounded-full border border-turquoise-600 text-turquoise-700 px-4 text-sm font-medium disabled:opacity-50">
                    {fill(t.whyNot.relax, { criterion: critLabel(v.key) })}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
