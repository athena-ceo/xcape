// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { useT } from '../i18n'

// One comparison column, normalised by the host page (home first, then board countries).
export interface BoardColumn {
  kind: 'home' | 'cand'
  id: string
  name: string
  placeId: number
  score: number | null
  quality: Record<string, string>
  reasons: Record<string, any>
  violations: string[]
  pinned: boolean
}

interface Props {
  searchId: number
  columns: BoardColumn[]
  // Visible criteria per category, already filtered (weight > 0 unless revealed) and sorted.
  groups: { key: string; label: string; keys: string[] }[]
  critLabel: (key: string) => string
  // The cell's display (value word, N/A at home, spinner while pending, ⚠ when filtered out).
  cellText: (col: BoardColumn, key: string) => ReactNode
  qualityClass: (tier?: string) => string
  reasonText: (key: string, reason: any) => string
  onWhy: (col: BoardColumn, key: string) => void
  onExplain: (col: BoardColumn) => void
  onRemove: (col: BoardColumn) => void
  onAdd: () => void
  hiddenCount: number
  showZero: boolean
  onToggleZero: () => void
}

const TIER_VALUE: Record<string, number> = { good: 1, ok: 0.6, bad: 0.3 }

// The comparison board on a phone (< sm), where a 7-column matrix doesn't fit:
//  - Cards: one swipeable card per board country, criteria listed vertically, the home value
//    in small text under each one (mockup A).
//  - Compare two: pick any two columns — home included — side by side (mockup B).
// Tablets and desktops keep the table. Cells open the same "why" popover as the table.
export function MobileBoard(p: Props) {
  const { t } = useT()
  const home = p.columns.find((c) => c.kind === 'home') ?? null
  const cands = p.columns.filter((c) => c.kind === 'cand')
  const [mode, setMode] = useState<'cards' | 'compare'>('cards')
  const [idx, setIdx] = useState(0)
  const [a, setA] = useState<string>(cands[0]?.id ?? home?.id ?? '')
  const [b, setB] = useState<string>(home?.id ?? cands[1]?.id ?? '')
  const touchX = useRef<number | null>(null)

  const i = Math.min(idx, Math.max(0, cands.length - 1))
  const cur = cands[i]
  const go = (d: number) => cands.length && setIdx((i + d + cands.length) % cands.length)
  const colA = p.columns.find((c) => c.id === a) ?? cands[0] ?? home
  const colB = p.columns.find((c) => c.id === b) ?? home ?? cands[1]

  const tierChip = (col: BoardColumn, key: string, extra = '') =>
    `inline-flex shrink-0 items-center rounded-lg px-2.5 py-1 text-sm font-medium ${
      p.qualityClass(col.quality?.[key]) || 'bg-slate-50 text-slate-600'} ${extra}`

  const modeBtn = (m: 'cards' | 'compare', label: string) => (
    <button onClick={() => setMode(m)} aria-pressed={mode === m}
      className={`flex-1 min-h-11 rounded-full text-sm font-medium ${
        mode === m ? 'bg-turquoise-600 text-turquoise-50' : 'text-turquoise-700'}`}>
      {label}
    </button>
  )

  const footer = (
    <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
      <button onClick={p.onAdd} className="min-h-11 text-sm text-turquoise-700">+ {t.comparison.addCountry}</button>
      {p.hiddenCount > 0 && (
        <button onClick={p.onToggleZero} className="min-h-11 text-sm text-turquoise-700">
          {p.showZero ? t.comparison.hideUnimportant : `${t.comparison.showUnimportant} (${p.hiddenCount})`}
        </button>
      )}
    </div>
  )

  return (
    <div className="mb-4">
      <div className="flex gap-1 p-1 mb-3 rounded-full bg-turquoise-50 border border-turquoise-100" role="group">
        {modeBtn('cards', t.comparison.mobileCards)}
        {modeBtn('compare', t.comparison.mobileCompare)}
      </div>

      {mode === 'cards' ? (
        cur ? (
          <>
            {/* Country strip: rank, name, score; the selected one is filled. */}
            <nav aria-label={t.comparison.mobileCards} className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1">
              {cands.map((c, n) => (
                <button key={c.id} onClick={() => setIdx(n)} aria-current={n === i}
                  className={`shrink-0 min-h-11 rounded-full px-3.5 text-sm font-medium border ${
                    n === i ? 'bg-turquoise-600 text-turquoise-50 border-turquoise-600'
                            : 'bg-white text-turquoise-900 border-turquoise-100'}`}>
                  <span className="opacity-70 mr-1">#{n + 1}</span>{c.name}
                  {c.score != null && <span className="ml-1.5 font-semibold">{Math.round(c.score)}%</span>}
                </button>
              ))}
            </nav>

            <div onTouchStart={(e) => { touchX.current = e.touches[0].clientX }}
              onTouchEnd={(e) => {
                if (touchX.current == null) return
                const dx = e.changedTouches[0].clientX - touchX.current
                touchX.current = null
                if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1)
              }}
              className="space-y-3">
              <section className="bg-white border border-turquoise-100 rounded-2xl p-4">
                <div className="flex items-start gap-2">
                  <Link to={`/drilldown/${cur.placeId}?search=${p.searchId}`}
                    className="flex-1 text-2xl font-semibold text-turquoise-900 hover:underline">{cur.name}</Link>
                  {cur.score != null && (
                    <button onClick={() => p.onExplain(cur)} title={t.comparison.explainTitle}
                      className="text-2xl font-semibold text-turquoise-600 underline decoration-dotted underline-offset-4">
                      {Math.round(cur.score)}%
                    </button>
                  )}
                  <button onClick={() => p.onRemove(cur)} aria-label={`${t.comparison.remove} ${cur.name}`}
                    className="w-11 h-11 -mr-2 -mt-1.5 flex items-center justify-center text-turquoise-800/40 hover:text-red-600 text-xl">×</button>
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {cur.pinned && (
                    <span className="text-xs rounded-full bg-turquoise-100 text-turquoise-700 px-2 py-0.5">📌 {t.comparison.pinnedBadge}</span>
                  )}
                  {cur.violations.length > 0 && (
                    <span className="text-xs rounded-full bg-amber-100 text-amber-800 px-2 py-0.5">
                      ⚠ {t.comparison.flagBadge}: {cur.violations.map(p.critLabel).join(', ')}
                    </span>
                  )}
                </div>
                {home && <p className="mt-1 text-xs text-turquoise-800/60">{t.comparison.mobileVsHome} {home.name}</p>}
              </section>

              {p.groups.map((g) => (
                <section key={g.key} className="bg-white border border-turquoise-100 rounded-2xl overflow-hidden">
                  <h3 className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-turquoise-700 bg-turquoise-50/70">{g.label}</h3>
                  {g.keys.map((key) => {
                    const detail = p.reasonText(key, cur.reasons?.[key])
                    return (
                      <button key={key} onClick={() => p.onWhy(cur, key)}
                        className="w-full flex items-center gap-3 px-4 py-3 border-t border-turquoise-50 text-left">
                        <span className="flex-1 min-w-0">
                          <span className="block text-[15px] text-turquoise-900">{p.critLabel(key)}</span>
                          {/* line-clamp sets its own display — don't add `block` (it cancels the clamp) */}
                          {detail && <span className="text-xs text-turquoise-800/60 line-clamp-2">{detail}</span>}
                          {home && (
                            <span className="block text-xs text-turquoise-800/50 mt-0.5">
                              {t.comparison.mobileHome}: {p.cellText(home, key)}
                            </span>
                          )}
                        </span>
                        <span className={tierChip(cur, key)}>{p.cellText(cur, key)}</span>
                      </button>
                    )
                  })}
                </section>
              ))}
            </div>

            <div className="flex items-center gap-2 mt-3">
              <button onClick={() => go(-1)} aria-label={t.comparison.mobilePrev}
                className="w-11 h-11 rounded-full border border-turquoise-100 bg-white text-turquoise-700 text-lg">‹</button>
              <span className="flex-1 text-center text-sm text-turquoise-800/60">
                {t.comparison.mobileSwipe} · {i + 1}/{cands.length}
              </span>
              <button onClick={() => go(1)} aria-label={t.comparison.mobileNext}
                className="w-11 h-11 rounded-full border border-turquoise-100 bg-white text-turquoise-700 text-lg">›</button>
            </div>
          </>
        ) : null  /* board still loading (or empty): nothing to swipe yet */
      ) : (
        colA && colB ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              {/* The value is the RESOLVED column: the initial ids are chosen before the board has
                  loaded, so `a`/`b` can be stale until the user picks. */}
              {([[setA, colA], [setB, colB]] as const).map(([set, col], n) => (
                <label key={n} className="flex flex-col gap-1 text-xs text-turquoise-800/70">
                  {n === 0 ? t.comparison.mobileLeft : t.comparison.mobileRight}
                  <select value={col.id} onChange={(e) => set(e.target.value)}
                    className="min-h-11 rounded-xl border border-turquoise-200 bg-white px-2 text-[15px] font-medium text-turquoise-900">
                    {p.columns.map((c) => (
                      <option key={c.id} value={c.id}>{c.kind === 'home' ? `${c.name} (${t.comparison.mobileHome})` : c.name}</option>
                    ))}
                  </select>
                  <button onClick={() => p.onExplain(col)} disabled={col.score == null}
                    className="text-2xl font-semibold text-turquoise-600 text-center underline decoration-dotted underline-offset-4 disabled:no-underline">
                    {col.score != null ? `${Math.round(col.score)}%` : '—'}
                  </button>
                </label>
              ))}
            </div>
            {p.groups.map((g) => (
              <section key={g.key}>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-turquoise-700 mb-1.5">{g.label}</h3>
                <div className="space-y-2">
                  {g.keys.map((key) => {
                    const va = TIER_VALUE[colA.quality?.[key] ?? ''], vb = TIER_VALUE[colB.quality?.[key] ?? '']
                    const better = va != null && vb != null && va !== vb ? (va > vb ? 'a' : 'b') : null
                    const ring = 'ring-2 ring-turquoise-600'
                    return (
                      <div key={key} className="bg-white border border-turquoise-100 rounded-xl p-2.5">
                        <p className="text-sm font-medium text-turquoise-900 mb-1.5">{p.critLabel(key)}</p>
                        <div className="grid grid-cols-2 gap-2">
                          <button onClick={() => p.onWhy(colA, key)}
                            className={`${tierChip(colA, key, better === 'a' ? ring : '')} justify-center min-h-11 w-full`}>
                            {p.cellText(colA, key)}
                          </button>
                          <button onClick={() => p.onWhy(colB, key)}
                            className={`${tierChip(colB, key, better === 'b' ? ring : '')} justify-center min-h-11 w-full`}>
                            {p.cellText(colB, key)}
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>
            ))}
            <p className="text-xs text-turquoise-800/60">{t.comparison.mobileBetterHint}</p>
          </div>
        ) : null
      )}
      {footer}
    </div>
  )
}
