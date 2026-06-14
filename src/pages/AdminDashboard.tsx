// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useMemo, useState } from 'react'

import { useT } from '../i18n'
import { api } from '../services/api'

type Tab = 'users' | 'searches' | 'places' | 'ailog'

export function AdminDashboard() {
  const { t, lang } = useT()
  const [tab, setTab] = useState<Tab>('users')
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 }>({ key: '', dir: 1 })

  useEffect(() => {
    setLoading(true)
    setQuery('')
    setSort({ key: '', dir: 1 })
    const fetcher = {
      users: api.getAdminUsers, searches: api.getAdminSearches,
      places: api.getAdminPlaces, ailog: api.getAdminAiLog,
    }[tab]
    fetcher().then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }, [tab])

  async function resetPassword(u: any) {
    const pw = window.prompt(`${t.admin.resetPrompt} ${u.email}`)
    if (pw === null) return
    if (pw.length < 8) return window.alert(t.admin.resetTooShort)
    await api.adminResetPassword(u.id, pw)
    window.alert(t.admin.resetDone)
  }

  async function resetUser(u: any) {
    if (!window.confirm(`${t.admin.resetDataConfirm} ${u.email}`)) return
    await api.adminResetUser(u.id)
    window.alert(t.admin.resetDataDone)
  }

  function toggleSort(key: string) {
    setSort((s) => (s.key === key ? { key, dir: (s.dir === 1 ? -1 : 1) as 1 | -1 } : { key, dir: 1 }))
  }

  // Column definitions per tab: [key, label, render?].
  const columns: [string, string, ((r: any) => any)?][] = useMemo(() => ({
    users: [
      ['name', t.admin.colName, (r: any) => [r.first_name, r.last_name].filter(Boolean).join(' ') || '—'],
      ['email', t.admin.colEmail],
      ['is_admin', t.admin.colAdmin, (r: any) => (r.is_admin ? t.admin.yes : '')],
    ],
    searches: [
      ['user_email', t.admin.colEmail], ['title', t.admin.colTitle],
      ['candidates', t.admin.colCandidates], ['selected', t.admin.colSelected],
      ['updated_at', t.admin.colUpdated, (r: any) => fmt(r.updated_at, lang)],
    ],
    places: [
      ['name', t.admin.colName], ['kind', t.admin.colKind], ['iso_code', 'ISO'],
      ['source', t.admin.colSource],
      ['enriched', t.admin.colEnriched, (r: any) => (r.enriched ? t.admin.yes : '')],
      ['freshness_at', t.admin.colFreshness, (r: any) => fmt(r.freshness_at, lang)],
    ],
    ailog: [
      ['kind', t.admin.colKind], ['model', t.admin.colModel],
      ['tokens', t.admin.colTokens, (r: any) => `${r.tokens_in ?? 0}/${r.tokens_out ?? 0}`],
      ['latency_ms', t.admin.colLatency, (r: any) => (r.latency_ms ? `${Math.round(r.latency_ms / 1000)}s` : '')],
      ['created_at', t.admin.colWhen, (r: any) => fmt(r.created_at, lang)],
    ],
  }[tab] as any), [tab, t, lang])

  const view = useMemo(() => {
    let v = rows
    if (query.trim()) {
      const q = query.toLowerCase()
      v = v.filter((r) => JSON.stringify(r).toLowerCase().includes(q))
    }
    if (sort.key) {
      v = [...v].sort((a, b) => {
        const av = a[sort.key], bv = b[sort.key]
        return (av > bv ? 1 : av < bv ? -1 : 0) * sort.dir
      })
    }
    return v
  }, [rows, query, sort])

  const tabs: [Tab, string][] = [
    ['users', t.admin.usersTitle], ['searches', t.admin.searchesTitle],
    ['places', t.admin.placesTitle], ['ailog', t.admin.aiLogTitle],
  ]

  return (
    <main className="max-w-5xl mx-auto px-5 py-10">
      <h1 className="text-2xl font-medium text-turquoise-900 mb-4">{t.admin.title}</h1>

      <div className="flex flex-wrap gap-2 mb-4">
        {tabs.map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)}
            className={`rounded-md px-3 py-1.5 text-sm border ${
              tab === key ? 'bg-turquoise-600 text-turquoise-50 border-turquoise-600'
                          : 'border-turquoise-100 text-turquoise-700'}`}>
            {label}
          </button>
        ))}
      </div>

      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t.admin.search}
        className="w-full sm:w-72 border border-turquoise-100 rounded-md px-3 py-2 text-sm mb-3" />

      {loading ? (
        <p className="text-turquoise-800/60">{t.common.loading}</p>
      ) : view.length === 0 ? (
        <p className="text-turquoise-800/60">{t.admin.none}</p>
      ) : (
        <div className="overflow-x-auto bg-white border border-turquoise-100 rounded-lg">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-turquoise-50 text-left">
                {columns.map(([key, label]) => (
                  <th key={key} onClick={() => toggleSort(key)}
                    className="p-3 font-medium cursor-pointer select-none whitespace-nowrap">
                    {label}{sort.key === key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                  </th>
                ))}
                {tab === 'users' && <th className="p-3" />}
              </tr>
            </thead>
            <tbody>
              {view.map((r, i) => (
                <tr key={r.id ?? i} className="border-t border-turquoise-100">
                  {columns.map(([key, , render]) => (
                    <td key={key} className="p-3">{render ? render(r) : String(r[key] ?? '')}</td>
                  ))}
                  {tab === 'users' && (
                    <td className="p-3 text-right whitespace-nowrap">
                      <button onClick={() => resetPassword(r)} className="text-turquoise-600 hover:underline">
                        {t.admin.resetPassword}
                      </button>
                      <button onClick={() => resetUser(r)} className="ml-3 text-red-600 hover:underline">
                        {t.admin.resetData}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-turquoise-800/50 mt-2">{view.length}</p>
    </main>
  )
}

function fmt(iso: string | null | undefined, lang: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString(lang, { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return String(iso)
  }
}
