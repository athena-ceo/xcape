// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Spinner } from '../components/Spinner'
import { useT } from '../i18n'
import { placeName } from '../i18n/places'
import { api } from '../services/api'

type Goal = 'invest' | 'income'

// "I have €X — where could that take me?" — the inverse of the per-country drill-down. Ranks
// destinations whose investment / passive-income visa threshold the entered amount clears,
// over the pre-computed pathway cache (see `./xcape.sh evaluate-visas`).
export function VisaFinder() {
  const { t, lang } = useT()
  const vf = t.visaFinder as Record<string, string>
  const v = t.drilldown.visa as Record<string, string>
  const [goal, setGoal] = useState<Goal>('invest')
  const [amount, setAmount] = useState<string>('')
  const [currency, setCurrency] = useState<string>('EUR')
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [results, setResults] = useState<any[]>([])

  useEffect(() => {
    api.getProfile().then((p: any) => { if (p?.currency) setCurrency(p.currency) }).catch(() => {})
  }, [])

  function money(x: any): string | null {
    if (x == null) return null
    try {
      return new Intl.NumberFormat(lang, { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(x))
    } catch {
      return `${Number(x).toLocaleString(lang)} ${currency}`
    }
  }

  async function run() {
    const amt = Number(amount)
    if (!amt || loading) return
    setLoading(true)
    try {
      const r = await api.visaFinder(amt, goal, lang)
      if (r?.currency) setCurrency(r.currency)
      setResults(r?.results ?? [])
      setSearched(true)
    } finally {
      setLoading(false)
    }
  }

  function stayText(days: any): string | null {
    if (days == null) return null
    return days <= 0 ? v.stayNone : v.stayDays.replace('{n}', String(days))
  }

  const goalBtn = (g: Goal, label: string) => (
    <button type="button" onClick={() => setGoal(g)}
      className={`rounded-md px-3 py-1.5 text-sm border ${goal === g
        ? 'bg-turquoise-600 text-turquoise-50 border-turquoise-600'
        : 'border-turquoise-200 text-turquoise-700 hover:bg-turquoise-50'}`}>
      {label}
    </button>
  )

  const tier = (d: number) => (d >= 70 ? 'text-emerald-700' : d >= 45 ? 'text-turquoise-700' : 'text-amber-700')
  const term = (label: string, val: string | null) =>
    val && <span>{label}: <b className="text-turquoise-900">{val}</b></span>

  return (
    <main className="max-w-3xl mx-auto px-5 py-8">
      <h1 className="text-2xl font-medium text-turquoise-900 mb-1">{vf.title}</h1>
      <p className="text-sm text-turquoise-800/60 mb-5">{vf.subtitle}</p>

      <div className="rounded-lg border border-turquoise-100 bg-turquoise-50/40 p-4 mb-6">
        <p className="text-xs text-turquoise-800/60 mb-1">{vf.goalLabel}</p>
        <div className="flex flex-wrap gap-2 mb-3">
          {goalBtn('invest', vf.goalInvest)}
          {goalBtn('income', vf.goalIncome)}
        </div>
        <label className="block text-xs text-turquoise-800/60 mb-1">
          {goal === 'invest' ? vf.amountInvest : vf.amountIncome}
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <input type="number" min={0} value={amount} autoFocus
            onChange={(e) => setAmount(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && run()}
            className="w-44 border border-turquoise-100 rounded-md px-3 py-1.5 text-sm" />
          <span className="text-sm text-turquoise-800/60">{currency}</span>
          <button onClick={run} disabled={!Number(amount) || loading}
            className="bg-turquoise-600 text-turquoise-50 rounded-md px-3 py-1.5 text-sm disabled:opacity-50 inline-flex items-center gap-2">
            {loading && <Spinner className="border-turquoise-100 border-t-white" />}
            {loading ? vf.searching : vf.search}
          </button>
        </div>
        <p className="text-xs text-turquoise-800/40 mt-2">{vf.amountHint.replace('{currency}', currency)}</p>
      </div>

      {searched && (
        results.length === 0 ? (
          <p className="text-sm text-turquoise-800/50 italic">{vf.none}</p>
        ) : (
          <>
            <p className="text-sm text-turquoise-800/70 mb-3">
              {vf.resultsCount.replace('{n}', String(results.length))}
            </p>
            <div className="space-y-3">
              {results.map((r: any) => (
                <Link key={`${r.place_id}-${r.category}`} to={`/drilldown/${r.place_id}`}
                  className="block bg-white border border-turquoise-100 rounded-lg p-4 hover:border-turquoise-300 transition-colors">
                  <div className="flex items-center gap-2 mb-1">
                    <p className="text-sm font-medium text-turquoise-900">{placeName(r, lang)}</p>
                    {r.program_name && <span className="text-xs text-turquoise-800/50">· {r.program_name}</span>}
                    {r.difficulty != null && (
                      <span className={`ml-auto text-sm font-medium ${tier(r.difficulty)}`}>{r.difficulty}/100</span>
                    )}
                  </div>
                  {(lang === 'fr' ? r.summary_fr : r.summary_en) && (
                    <p className="text-sm text-turquoise-800/80">{lang === 'fr' ? r.summary_fr : r.summary_en}</p>
                  )}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-turquoise-800/70">
                    {term(vf.from, money(goal === 'invest' ? r.investment : r.income))}
                    {term(v.pr, r.pr_years == null ? null : `${r.pr_years} ${v.years}`)}
                    {term(v.citizenship, r.citizenship_years == null ? null : `${r.citizenship_years} ${v.years}`)}
                    {term(v.stay, stayText(r.min_stay_days))}
                  </div>
                  <p className="text-xs text-turquoise-600 mt-2">{vf.viewCountry}</p>
                </Link>
              ))}
            </div>
            <p className="text-xs text-turquoise-800/40 mt-4">{vf.disclaimer}</p>
          </>
        )
      )}
    </main>
  )
}
