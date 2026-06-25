// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useT } from '../i18n'
import { api } from '../services/api'

// Editable place database: edit name / ISO inline, toggle active (deactivate,
// not delete — inactive places drop out of the shortlist pool and the picker
// but their data and any existing candidates are preserved), and add a new
// country / region / city.
export function AdminPlaces() {
  const { t } = useT()
  const navigate = useNavigate()
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [msg, setMsg] = useState('')
  const [form, setForm] = useState<{ kind: string; name: string; iso_code: string; parent_id: string }>(
    { kind: 'country', name: '', iso_code: '', parent_id: '' })

  function load() {
    setLoading(true)
    api.getAdminPlaces().then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }
  useEffect(load, [])

  const countries = useMemo(() => rows.filter((p) => p.kind === 'country'), [rows])
  const view = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? rows.filter((r) => JSON.stringify(r).toLowerCase().includes(q)) : rows
  }, [rows, query])

  async function patch(p: any, patchBody: any) {
    setRows((rs) => rs.map((r) => (r.id === p.id ? { ...r, ...patchBody } : r)))
    try { await api.updatePlace(p.id, patchBody); setMsg(t.adminPlaces.saved) }
    catch (e: any) { setMsg(e?.message || 'Error'); load() }
  }

  // Regenerate a country's AI data when it's reported outdated/incorrect: open its drill-down
  // and auto-run the full force-regenerate there (live progress + sources to verify the fix).
  function regenerate(p: any) {
    if (!confirm(t.adminPlaces.regenConfirm.replace('{name}', p.name))) return
    navigate(`/drilldown/${p.id}?regen=1`)
  }

  async function add() {
    if (!form.name.trim()) return
    try {
      await api.createPlace({
        kind: form.kind, name: form.name.trim(), iso_code: form.iso_code.trim() || undefined,
        parent_id: form.parent_id ? Number(form.parent_id) : undefined,
      })
      setForm({ kind: 'country', name: '', iso_code: '', parent_id: '' })
      load()
    } catch (e: any) { setMsg(e?.message || 'Error') }
  }

  return (
    <div>
      <div className="flex flex-wrap items-end gap-2 mb-4 bg-turquoise-50/50 border border-turquoise-100 rounded-lg p-3">
        <label className="text-sm">
          <span className="block text-xs text-turquoise-800/60">{t.adminPlaces.kind}</span>
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}
            className="border border-turquoise-100 rounded px-2 py-1 text-sm">
            <option value="country">{t.adminPlaces.country}</option>
            <option value="region">{t.adminPlaces.region}</option>
            <option value="city">{t.adminPlaces.city}</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-xs text-turquoise-800/60">{t.adminPlaces.name}</span>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="border border-turquoise-100 rounded px-2 py-1 text-sm" />
        </label>
        <label className="text-sm">
          <span className="block text-xs text-turquoise-800/60">ISO</span>
          <input value={form.iso_code} onChange={(e) => setForm({ ...form, iso_code: e.target.value })}
            className="w-20 border border-turquoise-100 rounded px-2 py-1 text-sm" />
        </label>
        {form.kind !== 'country' && (
          <label className="text-sm">
            <span className="block text-xs text-turquoise-800/60">{t.adminPlaces.parent}</span>
            <select value={form.parent_id} onChange={(e) => setForm({ ...form, parent_id: e.target.value })}
              className="border border-turquoise-100 rounded px-2 py-1 text-sm">
              <option value="">—</option>
              {countries.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
        )}
        <button onClick={add} disabled={!form.name.trim()}
          className="bg-turquoise-600 text-turquoise-50 rounded-md px-4 py-1.5 text-sm disabled:opacity-50">
          + {t.adminPlaces.add}
        </button>
        {msg && <span className="text-sm text-turquoise-600 ml-2">{msg}</span>}
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
                <th className="p-3 font-medium">{t.admin.colName}</th>
                <th className="p-3 font-medium">{t.admin.colKind}</th>
                <th className="p-3 font-medium">ISO</th>
                <th className="p-3 font-medium">{t.admin.colSource}</th>
                <th className="p-3 font-medium text-right">{t.adminPlaces.active}</th>
                <th className="p-3 font-medium text-right">{t.adminPlaces.regen}</th>
              </tr>
            </thead>
            <tbody>
              {view.map((p) => (
                <tr key={p.id} className={`border-t border-turquoise-100 ${p.active ? '' : 'opacity-40'}`}>
                  <td className="p-2">
                    <input defaultValue={p.name}
                      onBlur={(e) => e.target.value !== p.name && patch(p, { name: e.target.value })}
                      className="w-44 border border-transparent hover:border-turquoise-100 focus:border-turquoise-200 rounded px-2 py-1" />
                  </td>
                  <td className="p-3 text-turquoise-800/70">{p.kind}</td>
                  <td className="p-2">
                    <input defaultValue={p.iso_code || ''}
                      onBlur={(e) => e.target.value !== (p.iso_code || '') && patch(p, { iso_code: e.target.value })}
                      className="w-16 border border-transparent hover:border-turquoise-100 focus:border-turquoise-200 rounded px-2 py-1" />
                  </td>
                  <td className="p-3 text-turquoise-800/70">{p.source}</td>
                  <td className="p-3 text-right">
                    <label className="inline-flex items-center gap-1 text-xs">
                      <input type="checkbox" checked={!!p.active} className="accent-turquoise-600"
                        onChange={(e) => patch(p, { active: e.target.checked })} />
                      {t.adminPlaces.active}
                    </label>
                  </td>
                  <td className="p-3 text-right">
                    {p.kind === 'country' && (
                      <button onClick={() => regenerate(p)} title={t.adminPlaces.regenHint}
                        className="text-xs text-turquoise-600 hover:underline whitespace-nowrap">
                        ↻ {t.adminPlaces.regen}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-turquoise-800/50 mt-2">{view.length}</p>
    </div>
  )
}
