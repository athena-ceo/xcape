// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useMemo, useState } from 'react'

import { useT } from '../i18n'
import { api } from '../services/api'
import { AdminCriteria } from './AdminCriteria'
import { AdminPersonas } from './AdminPersonas'
import { AdminPlaces } from './AdminPlaces'

type Tab = 'users' | 'searches' | 'places' | 'ailog' | 'criteria' | 'personas'

export function AdminDashboard() {
  const { t, lang } = useT()
  const [tab, setTab] = useState<Tab>('users')
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 }>({ key: '', dir: 1 })
  const [includeTest, setIncludeTest] = useState(false)  // searches tab: show smoke/test accounts

  useEffect(() => {
    if (tab === 'criteria' || tab === 'places' || tab === 'personas') { setLoading(false); setRows([]); return }
    setLoading(true)
    const fetcher = {
      users: api.getAdminUsers, searches: () => api.getAdminSearches(includeTest),
      places: api.getAdminPlaces, ailog: api.getAdminAiLog,
    }[tab] as () => Promise<any[]>
    fetcher().then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }, [tab, includeTest])

  useEffect(() => { setQuery(''); setSort({ key: '', dir: 1 }) }, [tab])

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

  function reloadUsers() {
    api.getAdminUsers().then(setRows).catch(() => setRows([]))
  }

  async function toggleActive(u: any) {
    const msg = u.is_active ? t.admin.disableConfirm : t.admin.enableConfirm
    if (!window.confirm(`${msg}\n${u.email}`)) return
    try {
      await api.adminSetUserActive(u.id, !u.is_active)
      reloadUsers()
    } catch { window.alert(t.admin.actionFailed) }
  }

  async function removeUser(u: any) {
    const typed = window.prompt(`${t.admin.removeUserConfirm}\n${u.email}`)
    if (typed === null) return
    if (typed.trim().toLowerCase() !== u.email.toLowerCase()) return window.alert(t.admin.removeUserMismatch)
    try {
      await api.adminDeleteUser(u.id)
      window.alert(t.admin.removeUserDone)
      reloadUsers()
    } catch { window.alert(t.admin.actionFailed) }
  }

  // "Add user" inline form.
  const [addOpen, setAddOpen] = useState(false)
  const [nu, setNu] = useState({ email: '', password: '', first_name: '', last_name: '', is_admin: false })
  async function createUser() {
    if (!nu.email || nu.password.length < 8) return window.alert(t.admin.resetTooShort)
    try {
      await api.adminCreateUser(nu)
      setAddOpen(false)
      setNu({ email: '', password: '', first_name: '', last_name: '', is_admin: false })
      reloadUsers()
    } catch (e) { window.alert(e instanceof Error ? e.message : t.admin.actionFailed) }
  }

  // Which AI-log rows are expanded to show full request/result + diagnostics.
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})

  function toggleSort(key: string) {
    setSort((s) => (s.key === key ? { key, dir: (s.dir === 1 ? -1 : 1) as 1 | -1 } : { key, dir: 1 }))
  }

  // Column definitions per tab: [key, label, render?].
  const columns: [string, string, ((r: any) => any)?][] = useMemo(() => ({
    users: [
      ['name', t.admin.colName, (r: any) => [r.first_name, r.last_name].filter(Boolean).join(' ') || '—'],
      ['email', t.admin.colEmail, (r: any) => (
        <span className={r.is_active ? '' : 'text-turquoise-800/40'}>
          {r.email}{!r.is_active && <span className="ml-2 text-[10px] uppercase tracking-wide text-red-600">{t.admin.disabledBadge}</span>}
        </span>
      )],
      ['is_admin', t.admin.colAdmin, (r: any) => (r.is_admin ? t.admin.yes : '')],
      ['last_login_at', t.admin.colLastLogin, (r: any) => fmt(r.last_login_at, lang)],
      ['latest_search', t.admin.colLatestSearch, (r: any) => (
        r.latest_search ? `${r.latest_search} · ${fmt(r.latest_search_at, lang)}` : '—'
      )],
      ['ai_calls', t.admin.colCalls],
      ['tokens_in', t.admin.colTokensUser, (r: any) => `${fmtNum(r.tokens_in)}/${fmtNum(r.tokens_out)}`],
      ['cost_estimate', t.admin.colCost, (r: any) => `$${(r.cost_estimate ?? 0).toFixed(2)}`],
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
    criteria: [],
    personas: [],
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
    ['places', t.admin.placesTitle], ['criteria', t.admin.criteriaTitle],
    ['personas', t.admin.personasTitle], ['ailog', t.admin.aiLogTitle],
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

      {tab !== 'criteria' && tab !== 'places' && tab !== 'personas' && (
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t.admin.search}
            className="w-full sm:w-72 border border-turquoise-100 rounded-md px-3 py-2 text-sm" />
          {tab === 'searches' && (
            <label className="flex items-center gap-1.5 text-sm text-turquoise-800/70">
              <input type="checkbox" checked={includeTest} className="accent-turquoise-600"
                onChange={(e) => setIncludeTest(e.target.checked)} />
              {t.admin.showTestAccounts}
            </label>
          )}
          {tab === 'users' && (
            <button onClick={() => setAddOpen((o) => !o)}
              className="ml-auto rounded-md px-3 py-2 text-sm border border-turquoise-600 text-turquoise-700 hover:bg-turquoise-50">
              + {t.admin.addUser}
            </button>
          )}
        </div>
      )}

      {tab === 'users' && addOpen && (
        <div className="bg-white border border-turquoise-200 rounded-lg p-4 mb-3 flex flex-wrap items-end gap-3">
          <label className="text-xs text-turquoise-800/70">{t.admin.addUserEmail}
            <input value={nu.email} onChange={(e) => setNu({ ...nu, email: e.target.value })} type="email"
              className="block mt-1 w-56 border border-turquoise-200 rounded px-2 py-1 text-sm" /></label>
          <label className="text-xs text-turquoise-800/70">{t.admin.addUserPassword}
            <input value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} type="text"
              className="block mt-1 w-44 border border-turquoise-200 rounded px-2 py-1 text-sm" /></label>
          <label className="text-xs text-turquoise-800/70">{t.admin.addUserFirstName}
            <input value={nu.first_name} onChange={(e) => setNu({ ...nu, first_name: e.target.value })}
              className="block mt-1 w-32 border border-turquoise-200 rounded px-2 py-1 text-sm" /></label>
          <label className="text-xs text-turquoise-800/70">{t.admin.addUserLastName}
            <input value={nu.last_name} onChange={(e) => setNu({ ...nu, last_name: e.target.value })}
              className="block mt-1 w-32 border border-turquoise-200 rounded px-2 py-1 text-sm" /></label>
          <label className="flex items-center gap-1.5 text-sm text-turquoise-800/70 pb-1">
            <input type="checkbox" checked={nu.is_admin} className="accent-turquoise-600"
              onChange={(e) => setNu({ ...nu, is_admin: e.target.checked })} />
            {t.admin.addUserIsAdmin}
          </label>
          <button onClick={createUser}
            className="rounded-md px-3 py-1.5 text-sm bg-turquoise-600 text-turquoise-50">{t.admin.addUserSubmit}</button>
          <button onClick={() => setAddOpen(false)}
            className="rounded-md px-3 py-1.5 text-sm border border-turquoise-100 text-turquoise-700">{t.admin.addUserCancel}</button>
        </div>
      )}

      {tab === 'criteria' ? (
        <AdminCriteria />
      ) : tab === 'personas' ? (
        <AdminPersonas />
      ) : tab === 'places' ? (
        <AdminPlaces />
      ) : loading ? (
        <p className="text-turquoise-800/60">{t.common.loading}</p>
      ) : view.length === 0 ? (
        <p className="text-turquoise-800/60">{t.admin.none}</p>
      ) : tab === 'ailog' ? (
        <div className="bg-white border border-turquoise-100 rounded-lg divide-y divide-turquoise-50">
          {view.map((r: any) => {
            const open = !!expanded[r.id]
            return (
              <div key={r.id} className="p-3 text-sm">
                <button onClick={() => setExpanded((e) => ({ ...e, [r.id]: !open }))}
                  className="w-full text-left">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-turquoise-900">{r.user_email ?? '—'}</span>
                    <span className="px-2 py-0.5 rounded text-xs bg-turquoise-100 text-turquoise-700 font-mono">{r.kind}</span>
                    <span className="text-xs text-turquoise-800/50">{r.model}</span>
                    <span className="ml-auto text-xs text-turquoise-800/50">{fmt(r.created_at, lang)}</span>
                  </div>
                  <p className="mt-1 text-turquoise-800/70 truncate">
                    <span className="text-turquoise-800/40">{t.admin.colRequest}: </span>{r.prompt_summary || '—'}
                  </p>
                  <p className="text-turquoise-800/70 truncate">
                    <span className="text-turquoise-800/40">{t.admin.colResult}: </span>{r.result_summary || '—'}
                  </p>
                  <span className="text-xs text-turquoise-600">
                    {open ? '▾' : '▸'} {t.admin.aiDetails}: {r.tokens_in ?? 0}/{r.tokens_out ?? 0} tok
                    {r.cost_estimate ? ` · $${r.cost_estimate.toFixed(4)}` : ''}
                    {r.latency_ms ? ` · ${Math.round(r.latency_ms / 1000)}s` : ''}
                  </span>
                </button>
                {open && (
                  <div className="mt-2 grid gap-2 text-xs">
                    <div>
                      <p className="text-turquoise-800/40">{t.admin.colRequest}</p>
                      <p className="whitespace-pre-wrap text-turquoise-800/80">{r.prompt_summary || '—'}</p>
                    </div>
                    <div>
                      <p className="text-turquoise-800/40">{t.admin.colResult}</p>
                      <p className="whitespace-pre-wrap text-turquoise-800/80">{r.result_summary || '—'}</p>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
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
                      <button onClick={() => toggleActive(r)} className="ml-3 text-amber-700 hover:underline">
                        {r.is_active ? t.admin.disable : t.admin.enable}
                      </button>
                      <button onClick={() => resetUser(r)} className="ml-3 text-red-600 hover:underline">
                        {t.admin.resetData}
                      </button>
                      <button onClick={() => removeUser(r)} className="ml-3 text-red-700 font-medium hover:underline">
                        {t.admin.removeUser}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab !== 'criteria' && tab !== 'places' && tab !== 'personas' && (
        <p className="text-xs text-turquoise-800/50 mt-2">{view.length}</p>
      )}
    </main>
  )
}

function fmtNum(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString()
}

function fmt(iso: string | null | undefined, lang: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString(lang, { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return String(iso)
  }
}
