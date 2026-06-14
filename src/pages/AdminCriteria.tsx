// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { Fragment, useEffect, useState } from 'react'

import { useT } from '../i18n'
import { api } from '../services/api'
import { refreshCriteria } from '../services/criteria'

// Structured editor for the criteria registry (the admin-editable reference data).
// Members are deactivated, not deleted (the `active` toggle). Saving PUTs the whole
// registry and refreshes the cached catalog used across the app.
export function AdminCriteria() {
  const { t } = useT()
  const [reg, setReg] = useState<any>(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => { api.getAdminCriteria().then(setReg).catch(() => setReg(null)) }, [])

  if (!reg) return <p className="p-4 text-turquoise-800/60">{t.common.loading}</p>

  const nodes: any[] = reg.nodes || []
  const categories = nodes.filter((n) => n.parent == null)
  const isActive = (m: any) => m.active !== false

  function update() { setReg({ ...reg }); setMsg('') }
  function setNode(key: string, patch: any) {
    const n = nodes.find((x) => x.key === key)
    if (n) { Object.assign(n, patch); update() }
  }
  function addNode(parent: string | null) {
    const key = window.prompt(t.adminCriteria.newKey)
    if (!key) return
    nodes.push({ key: key.trim(), parent, kind: parent ? 'objective' : undefined,
                 label_fr: key, label_en: key, tags: [], active: true })
    update()
  }

  async function save() {
    setSaving(true)
    try {
      await api.putAdminCriteria(reg)
      refreshCriteria()  // next board/settings view refetches the updated catalog
      setMsg(t.adminCriteria.saved)
    } catch (e: any) {
      setMsg(e?.message || 'Error')
    } finally {
      setSaving(false)
    }
  }

  function nodeRow(n: any, depth: number) {
    return (
      <tr key={n.key} className={`border-t border-turquoise-50 ${isActive(n) ? '' : 'opacity-40'}`}>
        <td className="py-1.5 pr-2" style={{ paddingLeft: `${depth * 16 + 4}px` }}>
          <span className="font-mono text-xs text-turquoise-800/50">{n.key}</span>
          {n.kind && <span className="ml-2 text-[10px] uppercase text-turquoise-800/40">{n.kind}</span>}
        </td>
        <td className="py-1.5 pr-2">
          <input value={n.label_en || ''} onChange={(e) => setNode(n.key, { label_en: e.target.value })}
            className="w-32 border border-turquoise-100 rounded px-2 py-0.5 text-sm" placeholder="EN" />
          <input value={n.label_fr || ''} onChange={(e) => setNode(n.key, { label_fr: e.target.value })}
            className="w-32 border border-turquoise-100 rounded px-2 py-0.5 text-sm ml-1" placeholder="FR" />
        </td>
        <td className="py-1.5 pr-2">
          {n.kind && (
            <input type="number" min={0} max={5} step={0.5} value={n.default_weight ?? 0}
              onChange={(e) => setNode(n.key, { default_weight: Number(e.target.value) })}
              className="w-14 border border-turquoise-100 rounded px-1 py-0.5 text-sm" />
          )}
        </td>
        <td className="py-1.5 pr-2">
          <input value={(n.tags || []).join(', ')}
            onChange={(e) => setNode(n.key, { tags: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })}
            className="w-40 border border-turquoise-100 rounded px-2 py-0.5 text-sm" placeholder="tags" />
        </td>
        <td className="py-1.5 pr-2 text-right">
          <label className="inline-flex items-center gap-1 text-xs">
            <input type="checkbox" checked={isActive(n)} className="accent-turquoise-600"
              onChange={(e) => setNode(n.key, { active: e.target.checked })} />
            {t.adminCriteria.active}
          </label>
        </td>
      </tr>
    )
  }

  return (
    <div>
      <p className="text-sm text-turquoise-800/60 mb-3">{t.adminCriteria.hint}</p>
      <table className="w-full text-sm mb-4">
        <thead>
          <tr className="text-left text-turquoise-800/60">
            <th className="py-1">{t.adminCriteria.key}</th>
            <th className="py-1">{t.adminCriteria.labels}</th>
            <th className="py-1">{t.adminCriteria.weight}</th>
            <th className="py-1">{t.adminCriteria.tags}</th>
            <th className="py-1 text-right">{t.adminCriteria.active}</th>
          </tr>
        </thead>
        <tbody>
          {categories.map((cat) => (
            <Fragment key={cat.key}>
              {nodeRow(cat, 0)}
              {nodes.filter((n) => n.parent === cat.key).map((leaf) => nodeRow(leaf, 1))}
              <tr>
                <td colSpan={5} className="py-1 pl-5">
                  <button onClick={() => addNode(cat.key)} className="text-xs text-turquoise-600 hover:underline">
                    + {t.adminCriteria.addLeaf}
                  </button>
                </td>
              </tr>
            </Fragment>
          ))}
        </tbody>
      </table>

      <div className="flex items-center gap-3">
        <button onClick={() => addNode(null)} className="border border-turquoise-100 rounded-md px-3 py-1.5 text-sm">
          + {t.adminCriteria.addCategory}
        </button>
        <button onClick={save} disabled={saving}
          className="bg-turquoise-600 text-turquoise-50 rounded-md px-4 py-1.5 text-sm disabled:opacity-50">
          {saving ? t.common.loading : t.adminCriteria.save}
        </button>
        {msg && <span className="text-sm text-turquoise-600">{msg}</span>}
      </div>
    </div>
  )
}
