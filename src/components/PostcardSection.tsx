// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useRef, useState } from 'react'

import { useT } from '../i18n'
import { api } from '../services/api'
import { Spinner } from './Spinner'

interface Props {
  placeId: number
  searchId: number | null
  countryName: string
  photoUrl?: string | null
}

// "Postcard from your future" (red hat) + "Two years in" pre-mortem (black hat) on a country
// page: an imagined ordinary day there for THIS household, and a candid look at what could go
// wrong — always labelled as imagined. Instant from cache; written once per country and
// language (one AI call), re-written when the profile it was based on changes.
export function PostcardSection({ placeId, searchId, countryName, photoUrl }: Props) {
  const { t, lang } = useT()
  const [card, setCard] = useState<any | null>(null)
  const [writing, setWriting] = useState(false)
  const [failed, setFailed] = useState(false)
  const genRef = useRef(false)

  async function write(force = false) {
    if (genRef.current) return
    genRef.current = true
    setWriting(true)
    setFailed(false)
    try {
      const res = await api.generatePostcard(placeId, lang, searchId ?? undefined, force)
      if (res.unavailable) setFailed(true)
      else setCard(res)
    } catch {
      setFailed(true)
    } finally {
      genRef.current = false
      setWriting(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    setCard(null)
    api.getPostcard(placeId, lang, searchId ?? undefined)
      .then((res) => {
        if (cancelled || res.home) return
        if (res.postcard) setCard(res)  // a stale one stays visible while it is re-written
        if (res.pending) void write()
      })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [placeId, lang, searchId]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section aria-labelledby="postcard-title" className="mb-6 rounded-xl border border-amber-200 bg-amber-50/40 overflow-hidden">
      {photoUrl && (
        <img src={photoUrl} alt="" className="w-full h-40 sm:h-48 object-cover"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
      )}
      <div className="p-4 sm:p-5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2">
          <h2 id="postcard-title" className="text-lg font-medium text-turquoise-900">{t.postcard.title}</h2>
          <span className="text-xs text-amber-900/70">{t.postcard.imagined}</span>
        </div>

        {card?.postcard ? (
          <>
            {card.setting && (
              <p className="text-xs uppercase tracking-wide text-amber-900/70 mb-1">
                {card.setting} · {countryName}
              </p>
            )}
            <p className="font-serif text-[17px] leading-relaxed text-turquoise-900 whitespace-pre-line">{card.postcard}</p>

            {card.premortem?.length > 0 && (
              <div className="mt-5 pt-4 border-t border-amber-200/70">
                <h3 className="text-sm font-medium text-turquoise-900">{t.postcard.premortemTitle}</h3>
                <p className="text-xs text-turquoise-800/60 mb-2">{t.postcard.premortemHint}</p>
                <ul className="space-y-2">
                  {card.premortem.map((r: any, i: number) => (
                    <li key={i} className="text-sm">
                      <span className="font-medium text-turquoise-900">{r.title}.</span>{' '}
                      <span className="text-turquoise-800/80">{r.text}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        ) : failed ? (
          <p className="text-sm text-turquoise-800/70">{t.postcard.failed}</p>
        ) : (
          <p className="text-sm text-turquoise-800/60 flex items-center gap-2"><Spinner /> {t.postcard.writing}</p>
        )}

        <div className="mt-4 flex items-center gap-3">
          {(card?.postcard || failed) && (
            <button onClick={() => write(true)} disabled={writing}
              className="min-h-11 text-sm text-turquoise-700 underline decoration-dotted underline-offset-4 disabled:opacity-50 inline-flex items-center gap-2">
              {writing && <Spinner />}{failed && !card ? t.postcard.retry : t.postcard.another}
            </button>
          )}
          {writing && card?.postcard && <span className="text-xs text-turquoise-800/60">{t.postcard.rewriting}</span>}
        </div>
      </div>
    </section>
  )
}
