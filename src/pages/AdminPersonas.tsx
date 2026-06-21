// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'

import { useT } from '../i18n'
import { api } from '../services/api'
import { refreshCriteria } from '../services/criteria'

// Admin editor for relocation personas (archetypes). Edits live in the one registry document
// (reg.personas); saving PUTs the whole registry. An AI box proposes a whole persona set from
// a prompt — admin-time only; the proposal replaces the editable list for review before save.
export function AdminPersonas() {
  const { t } = useT()
  const [reg, setReg] = useState<any>(null)
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => { api.getAdminCriteria().then(setReg).catch(() => setReg(null)) }, [])
  if (!reg) return <p className="p-4 text-turquoise-800/60">{t.common.loading}</p>

  const personas: any[] = reg.personas || []
  const leafKeys: string[] = (reg.nodes || []).filter((n: any) => n.kind).map((n: any) => n.key)
  const reasonKeys: string[] = Object.keys(reg.reason_tags || {})

  function update() { setReg({ ...reg }); setMsg('') }
  function setP(i: number, patch: any) { personas[i] = { ...personas[i], ...patch }; reg.personas = personas; update() }
  function setMatch(i: number, field: 'reasons' | 'tags', csv: string) {
    setP(i, { match: { ...(personas[i].match || {}), [field]: csv.split(',').map((s) => s.trim()).filter(Boolean) } })
  }
  function setWeight(i: number, key: string, val: number) {
    const w = { ...(personas[i].weights || {}) }
    if (val > 0) w[key] = val; else delete w[key]
    setP(i, { weights: w })
  }
  // `filters` = criteria that default to an "exclude-bad" hard filter for this persona.
  function toggleFilter(i: number, key: string, on: boolean) {
    const f = new Set<string>(personas[i].filters || [])
    if (on) f.add(key); else f.delete(key)
    setP(i, { filters: [...f] })
  }
  function addPersona() {
    personas.push({ key: 'new_persona', label_en: '', label_fr: '', blurb_en: '', blurb_fr: '',
                    match: { reasons: [], tags: [] }, weights: {}, ask: [], active: true })
    update()
  }

  async function generate() {
    setBusy(true)
    try {
      const r = await api.suggestPersonas(prompt)
      reg.personas = r.personas
      update()
      setMsg(t.adminPersonas.generated)
    } catch (e: any) { setMsg(e?.message || 'Error') } finally { setBusy(false) }
  }

  async function save() {
    setBusy(true)
    try {
      await api.putAdminCriteria(reg)
      refreshCriteria()
      setMsg(t.adminPersonas.saved)
    } catch (e: any) { setMsg(e?.message || 'Error') } finally { setBusy(false) }
  }

  return (
    <div>
      <p className="text-sm text-turquoise-800/60 mb-3">{t.adminPersonas.hint}</p>

      {/* AI authoring */}
      <div className="bg-turquoise-50/60 border border-turquoise-100 rounded-lg p-3 mb-4">
        <p className="text-sm font-medium text-turquoise-700 mb-1">{t.adminPersonas.aiTitle}</p>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2}
          placeholder={t.adminPersonas.aiPlaceholder}
          className="w-full border border-turquoise-100 rounded-md px-3 py-2 text-sm mb-2" />
        <button onClick={generate} disabled={busy}
          className="border border-turquoise-200 text-turquoise-700 rounded-md px-3 py-1.5 text-sm disabled:opacity-50">
          {t.adminPersonas.generate}
        </button>
      </div>

      <div className="space-y-4">
        {personas.map((p, i) => (
          <div key={i} className={`border border-turquoise-100 rounded-lg p-3 ${p.active === false ? 'opacity-50' : ''}`}>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <input value={p.key || ''} onChange={(e) => setP(i, { key: e.target.value })}
                placeholder="key" className="font-mono text-xs w-40 border border-turquoise-100 rounded px-2 py-1" />
              <input value={p.label_en || ''} onChange={(e) => setP(i, { label_en: e.target.value })}
                placeholder="Label EN" className="text-sm border border-turquoise-100 rounded px-2 py-1" />
              <input value={p.label_fr || ''} onChange={(e) => setP(i, { label_fr: e.target.value })}
                placeholder="Libellé FR" className="text-sm border border-turquoise-100 rounded px-2 py-1" />
              <label className="ml-auto inline-flex items-center gap-1 text-xs">
                <input type="checkbox" checked={p.active !== false} className="accent-turquoise-600"
                  onChange={(e) => setP(i, { active: e.target.checked })} />
                {t.adminPersonas.active}
              </label>
            </div>
            <input value={p.blurb_en || ''} onChange={(e) => setP(i, { blurb_en: e.target.value })}
              placeholder="Blurb EN" className="w-full text-sm border border-turquoise-100 rounded px-2 py-1 mb-1" />
            <input value={p.blurb_fr || ''} onChange={(e) => setP(i, { blurb_fr: e.target.value })}
              placeholder="Blurb FR" className="w-full text-sm border border-turquoise-100 rounded px-2 py-1 mb-2" />
            <div className="flex flex-wrap gap-2 mb-2 text-xs">
              <label className="flex-1 min-w-[12rem]">
                <span className="block text-turquoise-800/60">{t.adminPersonas.matchReasons} ({reasonKeys.join(', ')})</span>
                <input value={(p.match?.reasons || []).join(', ')} onChange={(e) => setMatch(i, 'reasons', e.target.value)}
                  className="w-full border border-turquoise-100 rounded px-2 py-1" />
              </label>
              <label className="flex-1 min-w-[12rem]">
                <span className="block text-turquoise-800/60">{t.adminPersonas.matchTags}</span>
                <input value={(p.match?.tags || []).join(', ')} onChange={(e) => setMatch(i, 'tags', e.target.value)}
                  className="w-full border border-turquoise-100 rounded px-2 py-1" />
              </label>
            </div>
            <p className="text-xs text-turquoise-800/60 mb-1">{t.adminPersonas.weights}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-1">
              {leafKeys.map((k) => (
                <label key={k} className="flex items-center gap-1 text-xs">
                  <input type="number" min={0} max={3} step={0.5} value={p.weights?.[k] ?? 0}
                    onChange={(e) => setWeight(i, k, Number(e.target.value))}
                    className="w-12 border border-turquoise-100 rounded px-1 py-0.5" />
                  <span className="text-turquoise-800/60 truncate">{k}</span>
                </label>
              ))}
            </div>
            {/* Default hard filters: criteria where a country rated "À éviter" is excluded. */}
            <p className="text-xs text-turquoise-800/60 mt-2 mb-1">{t.adminPersonas.filters}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-1">
              {leafKeys.map((k) => (
                <label key={k} className="flex items-center gap-1 text-xs">
                  <input type="checkbox" className="accent-turquoise-600"
                    checked={(p.filters || []).includes(k)}
                    onChange={(e) => toggleFilter(i, k, e.target.checked)} />
                  <span className="text-turquoise-800/60 truncate">{k}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 mt-4">
        <button onClick={addPersona} className="border border-turquoise-100 rounded-md px-3 py-1.5 text-sm">
          + {t.adminPersonas.add}
        </button>
        <button onClick={save} disabled={busy}
          className="bg-turquoise-600 text-turquoise-50 rounded-md px-4 py-1.5 text-sm disabled:opacity-50">
          {busy ? t.common.loading : t.adminPersonas.save}
        </button>
        {msg && <span className="text-sm text-turquoise-600">{msg}</span>}
      </div>
    </div>
  )
}
