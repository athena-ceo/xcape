// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { ChatPanel } from '../components/ChatPanel'
import { Spinner } from '../components/Spinner'
import { useT } from '../i18n'
import { placeName } from '../i18n/places'
import { api } from '../services/api'
import { categories, labelOf, useCriteria } from '../services/criteria'
import { useAuth } from '../store/auth'

// Drill-down on a country: facts, map, photos, and per-criterion AI detail grouped by
// category (collapsed by default except the one the user clicked). The details fill in
// progressively — the clicked criterion first, then visible ones, then the rest — and the
// chat assistant (shared with the comparison page) is available with this country's context.
export function Drilldown() {
  const { t, lang } = useT()
  const reg = useCriteria()
  const { placeId } = useParams()
  const navigate = useNavigate()
  const { hash, search } = useLocation()
  const id = Number(placeId)
  const clickedKey = hash.startsWith('#criterion-') ? hash.slice('#criterion-'.length) : null

  const [place, setPlace] = useState<any>(null)
  const [facts, setFacts] = useState<any>(null)
  const [detail, setDetail] = useState<any[] | null>(null)
  const [media, setMedia] = useState<any[]>([])
  const [loadingDetail, setLoadingDetail] = useState(true)
  const [loadingMedia, setLoadingMedia] = useState(true)
  const [searchId, setSearchId] = useState<number | null>(null)
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [currency, setCurrency] = useState<string>('EUR')  // the user's budgeting currency (for labels)
  const [customWeights, setCustomWeights] = useState<Record<string, number>>({})
  const [customCats, setCustomCats] = useState<Record<string, string>>({})
  const [showZero, setShowZero] = useState(false)
  const [visa, setVisa] = useState<{ categories: any[]; best: string | null } | null>(null)
  const visaDrainRef = useRef(false)
  const visaLoadRef = useRef(false)
  // The visa-pathways panel is collapsed by default and loads lazily — no fetch or AI pathway
  // generation happens until the user expands it. Open/closed is persisted.
  const [visaOpen, setVisaOpen] = useState<boolean>(() => {
    try { return localStorage.getItem('xcape_visa_open') === '1' } catch { return false }
  })
  const [afford, setAfford] = useState<any>(null)
  const [budgetInput, setBudgetInput] = useState<number | null>(null)
  const [householdInput, setHouseholdInput] = useState<number | null>(null)
  // The calculator is collapsed by default and loads lazily — no fetch or AI cost-breakdown
  // generation happens until the user expands it. Open/closed is persisted.
  const [afOpen, setAfOpen] = useState<boolean>(() => {
    try { return localStorage.getItem('xcape_afford_open') === '1' } catch { return false }
  })
  const afLoadRef = useRef(false)
  const afGenRef = useRef(false)
  const afTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [costWhy, setCostWhy] = useState<any>(null)  // breakdown entry whose explanation popup is open
  const isAdmin = useAuth((s) => s.isAdmin)
  const [regenerating, setRegenerating] = useState(false)

  // Collapse state per category (persisted). Default collapsed except the clicked criterion's.
  const [openCats, setOpenCats] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem('xcape_open_detail_cats') || '{}') } catch { return {} }
  })

  const detailRef = useRef<any[]>([])
  const openCatsRef = useRef(openCats)
  const drainingRef = useRef(false)
  useEffect(() => { detailRef.current = detail ?? [] }, [detail])
  useEffect(() => { openCatsRef.current = openCats }, [openCats])

  // Resolve a search id for the chat: prefer ?search=, else the user's latest search so the
  // drill-down attaches to (and shares) the same conversation thread.
  useEffect(() => {
    const fromUrl = new URLSearchParams(search).get('search')
    if (fromUrl) { setSearchId(Number(fromUrl)); return }
    api.listSearches().then((s) => setSearchId(s.length ? s[0].id : null)).catch(() => setSearchId(null))
  }, [search])

  // Build category groups (registry order) limited to criteria present in the detail, plus a
  // trailing group for custom criteria (not in the registry tree).
  const groups = useMemo(() => {
    const rows = detail ?? []
    const byKey = new Set(rows.map((r) => r.key))
    const cats = categories(reg)
    const inCats = new Set(cats.flatMap((c) => c.leaves))
    // Custom criteria with a category join that built-in category; the rest go to "Your criteria".
    const out = cats
      .map((c) => ({
        key: c.key, label: labelOf(reg, c.key, lang),
        keys: [
          ...c.leaves.filter((k) => byKey.has(k)),
          ...rows.map((r) => r.key).filter((k) => byKey.has(k) && customCats[k] === c.key),
        ],
      }))
      .filter((g) => g.keys.length)
    const extra = rows.map((r) => r.key).filter((k) => !inCats.has(k) && !customCats[k])
    if (extra.length) out.push({ key: '__custom', label: t.comparison.customGroup, keys: extra })
    return out
  }, [detail, reg, lang, t, customCats])

  const clickedCat = useMemo(() => {
    if (!clickedKey) return null
    const cats = categories(reg)
    const cat = cats.find((c) => c.leaves.includes(clickedKey))
    return cat ? cat.key : (groups.find((g) => g.keys.includes(clickedKey))?.key ?? null)
  }, [clickedKey, reg, groups])

  // Always open the category the user clicked through to (overriding any persisted collapse),
  // so the drill-down reliably lands on that criterion. The user can still collapse it after.
  useEffect(() => {
    if (clickedCat) setOpenCats((o) => ({ ...o, [clickedCat]: true }))
  }, [clickedCat])

  function isOpen(catKey: string): boolean {
    if (catKey in openCats) return openCats[catKey]
    return catKey === clickedCat  // default: only the clicked criterion's category is open
  }
  function toggleCat(catKey: string) {
    setOpenCats((o) => {
      const next = { ...o, [catKey]: !isOpen(catKey) }
      try { localStorage.setItem('xcape_open_detail_cats', JSON.stringify(next)) } catch { /* ignore */ }
      return next
    })
    setTimeout(drain, 0)  // a newly-expanded category bumps its criteria up the queue
  }

  // The order to generate still-pending criteria: clicked → visible (open) → collapsed.
  function orderedPending(): string[] {
    const rows = detailRef.current
    const pending = new Set(rows.filter((r) => r.pending).map((r) => r.key))
    if (!pending.size) return []
    const order: string[] = []
    const push = (k: string) => { if (pending.has(k) && !order.includes(k)) order.push(k) }
    if (clickedKey) push(clickedKey)
    for (const g of groups) if (isOpen(g.key)) g.keys.forEach(push)
    for (const g of groups) if (!isOpen(g.key)) g.keys.forEach(push)
    rows.filter((r) => r.pending).forEach((r) => push(r.key))  // safety net
    return order
  }

  // Fill pending criteria a couple at a time, re-rendering each batch, until none remain.
  async function drain() {
    if (drainingRef.current) return
    drainingRef.current = true
    try {
      for (let i = 0; i < 60; i++) {
        const keys = orderedPending()
        if (!keys.length) break
        const res = await api.generateDetail(id, { keys, limit: 2 }, lang, searchId ?? undefined)
        detailRef.current = res.criteria
        setDetail(res.criteria)
      }
    } finally {
      drainingRef.current = false
    }
  }

  // Admin-only: force-regenerate EVERYTHING for this country (e.g. after a prompt change) — every
  // criterion's detail text, the visa pathways, and the budget cost breakdown — in chunks, forcing
  // regeneration regardless of the cache.
  async function regenerateAll() {
    if (drainingRef.current || regenerating) return
    if (!confirm(t.drilldown.regenConfirm)) return
    setRegenerating(true)
    drainingRef.current = true
    try {
      // 1. Per-criterion detail text.
      const keys = detailRef.current.filter((r) => r.key !== 'proximity').map((r) => r.key)
      for (let i = 0; i < keys.length; i += 2) {
        const chunk = keys.slice(i, i + 2)
        const res = await api.generateDetail(
          id, { keys: chunk, limit: chunk.length, force: true }, lang, searchId ?? undefined)
        detailRef.current = res.criteria
        setDetail(res.criteria)
      }
      // 2. Visa pathways (every relevant category, forced). The panel may not be loaded yet (it's
      // collapsed by default), so fetch the relevant categories first.
      let vpanel = visa
      if (vpanel == null) {
        vpanel = await api.getVisaPathways(id, lang, searchId ?? undefined).catch(() => null)
        if (vpanel) setVisa(vpanel)
      }
      const vcats = (vpanel?.categories ?? []).map((c: any) => c.category)
      for (let i = 0; i < vcats.length; i += 2) {
        const chunk = vcats.slice(i, i + 2)
        const res = await api.generateVisaPathways(
          id, { limit: chunk.length, force: true, categories: chunk }, lang, searchId ?? undefined)
        setVisa(res)
      }
      visaLoadRef.current = true  // panel is now populated; expanding it won't refetch
      // 3. Budget cost breakdown (forced). Mark it loaded so expanding the panel won't refetch.
      const af = await api.generateAffordability(
        id, { force: true, budget: budgetInput ?? undefined, household: householdInput ?? undefined }, lang)
      setAfford(af)
      afLoadRef.current = true
      if (budgetInput == null) setBudgetInput(af.budget_monthly ?? null)
      if (householdInput == null) setHouseholdInput(af.household_size ?? 1)
    } finally {
      drainingRef.current = false
      setRegenerating(false)
    }
  }

  useEffect(() => {
    setLoadingDetail(true)
    api.getPlace(id).then(setPlace)
    api.getFacts(id).then(setFacts).catch(() => {})
    api.getMedia(id).then(setMedia).catch(() => {}).finally(() => setLoadingMedia(false))
    api.getProfile().then((p: any) => {
      setWeights(p?.criteria_weights ?? {})
      if (p?.currency) setCurrency(p.currency)
    }).catch(() => {})
  }, [id])

  // Custom-criterion weights come from the search's definitions, not the profile.
  useEffect(() => {
    if (searchId == null) return
    api.listCustomCriteria(searchId)
      .then((list: any[]) => {
        setCustomWeights(Object.fromEntries(list.map((c) => [c.key, c.weight ?? 1])))
        setCustomCats(Object.fromEntries(list.filter((c) => c.category).map((c) => [c.key, c.category])))
      })
      .catch(() => {})
  }, [searchId])

  const weightOf = (key: string) => (key in customWeights ? customWeights[key] : (weights[key] ?? 0))
  // Edit a criterion's importance inline; persists (custom → the per-search def, else the profile).
  async function setWeight(key: string, raw: number) {
    const v = Math.max(0, Math.min(8, raw))
    if (key in customWeights) {
      setCustomWeights((w) => ({ ...w, [key]: v }))
      if (searchId != null) await api.updateCustomCriterion(searchId, key, { weight: v }).catch(() => {})
      return
    }
    const next = { ...weights, [key]: v }
    setWeights(next)
    await api.updateProfile({ criteria_weights: next }).catch(() => {})
  }

  // Load the (instant) assembled detail, then progressively generate the pending criteria.
  // Re-runs when the search context resolves (so custom criteria are included).
  useEffect(() => {
    let cancelled = false
    api.getDetail(id, lang, searchId ?? undefined)
      .then((d) => { if (!cancelled) { setDetail(d.criteria ?? []); detailRef.current = d.criteria ?? [] } })
      .catch(() => { if (!cancelled) setDetail([]) })
      .finally(() => { if (!cancelled) { setLoadingDetail(false); void drain() } })
    return () => { cancelled = true }
  }, [id, lang, searchId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Visa pathways: progressively generate the still-pending relevant categories on-demand.
  async function drainVisa(initial?: { categories: any[]; best: string | null }) {
    if (visaDrainRef.current) return
    visaDrainRef.current = true
    try {
      let cur = initial ?? visa
      for (let i = 0; i < 10; i++) {
        if (cur && !cur.categories.some((c) => c.pending)) break
        const res = await api.generateVisaPathways(id, { limit: 2 }, lang, searchId ?? undefined)
        cur = res
        setVisa(res)
      }
    } finally {
      visaDrainRef.current = false
    }
  }

  // Reset the (lazily-loaded) visa panel when the country / language / search context changes.
  useEffect(() => { setVisa(null); visaLoadRef.current = false }, [id, lang, searchId])

  function toggleVisa() {
    setVisaOpen((o) => {
      const next = !o
      try { localStorage.setItem('xcape_visa_open', next ? '1' : '0') } catch { /* ignore */ }
      return next
    })
  }

  // Load the panel only once the user expands it: the instant cached panel (relevant categories),
  // then generate the pending ones on-demand. Gated on `visaOpen` so a collapsed panel costs nothing.
  useEffect(() => {
    if (!visaOpen || visaLoadRef.current) return
    visaLoadRef.current = true
    let cancelled = false
    api.getVisaPathways(id, lang, searchId ?? undefined)
      .then((p) => { if (!cancelled) { setVisa(p); void drainVisa(p) } })
      .catch(() => { if (!cancelled) { setVisa(null); visaLoadRef.current = false } })
    return () => { cancelled = true }
  }, [visaOpen, id, lang, searchId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Reset the (lazily-loaded) calculator when the country or language changes, so reopening it
  // refetches for the new context.
  useEffect(() => { setAfford(null); afLoadRef.current = false }, [id, lang])

  function toggleAfford() {
    setAfOpen((o) => {
      const next = !o
      try { localStorage.setItem('xcape_afford_open', next ? '1' : '0') } catch { /* ignore */ }
      return next
    })
  }

  // Load the calculator only once the user expands it: the instant payload (cost breakdown from
  // cache, the budget comparison, the visa income tie-in), prefilling the editable inputs from the
  // profile defaults the server returns, then generating the per-country cost breakdown on-demand
  // if it isn't cached yet. Gated on `afOpen` so a collapsed panel costs nothing.
  useEffect(() => {
    if (!afOpen || afLoadRef.current) return
    afLoadRef.current = true
    let cancelled = false
    api.getAffordability(id, lang)
      .then(async (r) => {
        if (cancelled) return
        setAfford(r)
        setBudgetInput(r.budget_monthly ?? null)
        setHouseholdInput(r.household_size ?? 1)
        if (r.pending && !afGenRef.current) {
          afGenRef.current = true
          try {
            const g = await api.generateAffordability(
              id, { budget: r.budget_monthly ?? undefined, household: r.household_size ?? undefined }, lang)
            if (!cancelled) setAfford(g)
          } finally { afGenRef.current = false }
        }
      })
      .catch(() => { if (!cancelled) { setAfford(null); afLoadRef.current = false } })
    return () => { cancelled = true }
  }, [afOpen, id, lang]) // eslint-disable-line react-hooks/exhaustive-deps

  // Re-run the (server-side, deterministic) calculation when the user edits budget or household —
  // debounced; the breakdown is cached so this is instant.
  async function recomputeAfford(budget: number | null, household: number | null) {
    try {
      const r = await api.getAffordability(id, lang, budget ?? undefined, household ?? undefined)
      setAfford(r)
    } catch { /* ignore */ }
  }
  function scheduleRecompute(budget: number | null, household: number | null) {
    if (afTimerRef.current) clearTimeout(afTimerRef.current)
    afTimerRef.current = setTimeout(() => void recomputeAfford(budget, household), 350)
  }

  // After detail first renders, scroll to the clicked criterion with a brief highlight.
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
  const detailByKey: Record<string, any> = useMemo(
    () => Object.fromEntries((detail ?? []).map((r) => [r.key, r])), [detail],
  )

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

  function cleanSummary(s: string): string {
    return s
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')  // markdown link → its text (prose stays clean)
      .replace(/https?:\/\/\S+/g, '')
      .replace(/\s*\b(Voir|Sources?|See)\b\s*:?/gi, '')
      .replace(/\s*[;,]\s*\./g, '.')
      .replace(/\s{2,}/g, ' ')
      .replace(/\s+([.,;])/g, '$1')
      .trim()
  }

  // Render inline text, turning markdown links [label](url) and bare URLs into clickable links
  // (used for the trend "metric" line, which cites a source inline).
  function renderInline(text: string): (string | JSX.Element)[] {
    const out: (string | JSX.Element)[] = []
    const re = /\[([^\]]+)\]\((https?:\/\/[^)]+)\)|(https?:\/\/[^\s)]+)/g
    let last = 0, i = 0, m: RegExpExecArray | null
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) out.push(text.slice(last, m.index))
      const url = m[2] || m[3]
      let label = m[1]
      if (!label) { try { label = new URL(url).hostname.replace(/^www\./, '') } catch { label = url } }
      out.push(<a key={i++} href={url} target="_blank" rel="noreferrer"
        className="text-turquoise-600 hover:underline">{label}</a>)
      last = re.lastIndex
    }
    if (last < text.length) out.push(text.slice(last))
    return out
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

  // Structured trend block for trend-lens criteria (community safety, safety, stability):
  // current level + trajectory arrow + window + the factual basis (metric).
  function trendLine(meta: any) {
    const tr = meta?.trend as 'improving' | 'stable' | 'worsening' | undefined
    const lvl = meta?.level as 'high' | 'moderate' | 'low' | undefined
    const arrow = tr === 'improving' ? '↗' : tr === 'worsening' ? '↘' : '→'
    const arrowCls = tr === 'improving' ? 'text-emerald-600' : tr === 'worsening' ? 'text-red-600' : 'text-turquoise-800/50'
    const tt = t.trend as Record<string, string>
    return (
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {lvl && (
          <span className="text-turquoise-800/70">
            {tt.level}: <span className="font-medium text-turquoise-900">{tt[lvl] ?? lvl}</span>
          </span>
        )}
        {tr && (
          <span className="text-turquoise-800/70">
            {tt.trendLabel}: <span className={`font-medium ${arrowCls}`}>{arrow} {tt[tr] ?? tr}</span>
          </span>
        )}
        {meta?.window && <span className="text-turquoise-800/50">({meta.window})</span>}
        {meta?.metric && <span className="basis-full text-turquoise-800/60 italic">{renderInline(String(meta.metric))}</span>}
      </div>
    )
  }

  // Service criteria (healthcare, education) — show the quality vs newcomer-access split.
  function serviceLine(meta: any) {
    const tt = t.trend as Record<string, string>
    const chip = (lbl: string, v: number) => (
      <span className="text-turquoise-800/70">{lbl}: <span className="font-medium text-turquoise-900">{v}/100</span></span>
    )
    return (
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        {meta.quality != null && chip(tt.quality, meta.quality)}
        {meta.access != null && chip(tt.access, meta.access)}
      </div>
    )
  }

  // Format a money amount in the given currency (locale-aware symbol); null passes through so
  // callers can hide an absent figure. Backend money is already converted to the user's currency.
  function fmtMoney(x: any, currency?: string): string | null {
    if (x == null) return null
    const cur = (currency || 'EUR').toUpperCase()
    try {
      return new Intl.NumberFormat(lang, { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(Number(x))
    } catch {
      return `${Number(x).toLocaleString(lang)} ${cur}`
    }
  }

  // One visa-pathway category card (the gate: how this user could legally settle there).
  function visaCard(c: any) {
    const v = t.drilldown.visa as Record<string, string>
    const summary = lang === 'fr' ? c.summary_fr : c.summary_en
    const money = (x: any) => fmtMoney(x, c.currency)
    const years = (x: any) => (x == null ? null : `${x} ${v.years}`)
    const tier = (d: number) => (d >= 70 ? 'text-emerald-700' : d >= 45 ? 'text-turquoise-700' : 'text-amber-700')
    const term = (label: string, val: string | null) =>
      val && <span>{label}: <b className="text-turquoise-900">{val}</b></span>
    return (
      <div key={c.category} className="bg-white border border-turquoise-100 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-1">
          <p className="text-sm font-medium text-turquoise-900">{c.label}</p>
          {!c.pending && c.exists && (
            <span className={`ml-auto text-sm font-medium ${tier(c.difficulty ?? 0)}`}>{c.difficulty}/100</span>
          )}
        </div>
        {c.pending ? (
          <p className="text-sm text-turquoise-800/50 italic flex items-center gap-2"><Spinner /> {t.drilldown.generating}</p>
        ) : !c.exists ? (
          <p className="text-sm text-turquoise-800/40 italic">{v.noRoute}</p>
        ) : (
          <>
            {summary && <p className="text-sm text-turquoise-800/80">{cleanSummary(summary)}</p>}
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-turquoise-800/70">
              {term(v.income, money(c.income))}
              {term(v.investment, money(c.investment))}
              {term(v.pr, years(c.pr_years))}
              {term(v.citizenship, years(c.citizenship_years))}
            </div>
            {Array.isArray(c.requirements) && c.requirements.length > 0 && (
              <ul className="mt-2 list-disc list-inside text-xs text-turquoise-800/70 space-y-0.5">
                {c.requirements.map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
            )}
            {Array.isArray(c.sources) && c.sources.length > 0 && (
              <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
                <span className="text-xs text-turquoise-800/50">{t.drilldown.sources}:</span>
                {c.sources.map((s: string, i: number) => {
                  const p = parseSource(s)
                  return p ? <a key={i} href={p.url} target="_blank" rel="noreferrer"
                    className="text-xs text-turquoise-600 hover:underline">{p.label}</a> : null
                })}
              </div>
            )}
          </>
        )}
      </div>
    )
  }

  // Budget / affordability calculator body: editable budget + household, estimated cost vs budget
  // with a verdict + breakdown, and the visa income tie-in (which income-based routes the income
  // clears). Rendered only once the (collapsible) panel is expanded.
  function affordBody() {
    const a = afford
    const af = t.drilldown.afford as any
    if (!a) {
      return (
        <div className="bg-white border border-turquoise-100 rounded-lg p-4">
          <p className="text-sm text-turquoise-800/50 italic flex items-center gap-2">
            <Spinner /> {af.generating}
          </p>
        </div>
      )
    }
    const comps = af.components as Record<string, string>
    const money = (x: any) => fmtMoney(x, a.currency) ?? '—'
    const hasBudget = a.budget_monthly != null
    const ratio = a.ratio as number | null
    const fillPct = ratio != null ? Math.min(100, Math.round((1 / ratio) * 100)) : 0
    const verdictCls =
      a.verdict === 'comfortable' ? 'text-emerald-800 bg-emerald-50 border-emerald-200'
      : a.verdict === 'manageable' ? 'text-turquoise-800 bg-turquoise-50 border-turquoise-200'
      : a.verdict === 'tight' ? 'text-amber-800 bg-amber-50 border-amber-200'
      : 'text-red-800 bg-red-50 border-red-200'
    const barCls =
      a.verdict === 'comfortable' ? 'bg-emerald-500'
      : a.verdict === 'manageable' ? 'bg-turquoise-500'
      : a.verdict === 'tight' ? 'bg-amber-500' : 'bg-red-500'
    const incomeRoutes = (a.income_pathways ?? []) as any[]

    return (
        <div className="bg-white border border-turquoise-100 rounded-lg p-4">
          {/* Inputs */}
          <div className="flex flex-wrap gap-4 mb-3">
            <label className="flex flex-col gap-1 text-xs text-turquoise-800/60">
              {af.budgetLabel}
              <span className="flex items-center gap-1.5">
                <input type="number" min={0} step={100} value={budgetInput ?? ''}
                  onChange={(e) => {
                    const v = e.target.value === '' ? null : Number(e.target.value)
                    setBudgetInput(v); scheduleRecompute(v, householdInput)
                  }}
                  className="w-32 border border-turquoise-200 rounded px-2 py-1 text-sm text-turquoise-900" />
                <span className="text-turquoise-800/60">{a.currency}</span>
              </span>
            </label>
            <label className="flex flex-col gap-1 text-xs text-turquoise-800/60">
              {af.householdLabel}
              <input type="number" min={1} max={12} step={1} value={householdInput ?? 1}
                onChange={(e) => {
                  const v = Math.max(1, Number(e.target.value) || 1)
                  setHouseholdInput(v); scheduleRecompute(budgetInput, v)
                }}
                className="w-24 border border-turquoise-200 rounded px-2 py-1 text-sm text-turquoise-900" />
            </label>
          </div>

          {a.pending ? (
            <p className="text-sm text-turquoise-800/50 italic flex items-center gap-2">
              <Spinner /> {af.generating}
            </p>
          ) : a.cost_total != null && (
            <>
              {/* Cost vs budget */}
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm mb-2">
                <span className="text-turquoise-800/70">{af.estimatedCost}:
                  <b className="text-turquoise-900"> {money(a.cost_total)}{af.perMonth}</b></span>
                {hasBudget && (
                  <span className="text-turquoise-800/70">{af.yourBudget}:
                    <b className="text-turquoise-900"> {money(a.budget_monthly)}{af.perMonth}</b></span>
                )}
                {hasBudget && a.surplus != null && (
                  <span className={a.surplus >= 0 ? 'text-emerald-700' : 'text-red-700'}>
                    {a.surplus >= 0 ? af.surplus : af.deficit}:
                    <b> {money(Math.abs(a.surplus))}{af.perMonth}</b>
                  </span>
                )}
              </div>
              {hasBudget && ratio != null && (
                <div className="h-2 w-full bg-turquoise-50 rounded-full overflow-hidden mb-2">
                  <div className={`h-full ${barCls}`} style={{ width: `${fillPct}%` }} />
                </div>
              )}
              {hasBudget && a.verdict ? (
                <p className={`text-sm rounded-md border px-3 py-2 ${verdictCls}`}>
                  {af.verdict[a.verdict]}
                </p>
              ) : !hasBudget && (
                <p className="text-sm text-turquoise-800/50 italic">{af.noBudget}</p>
              )}

              {/* Breakdown */}
              {Array.isArray(a.breakdown) && a.breakdown.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-turquoise-800/50 mb-1">{af.breakdownTitle}</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {a.breakdown.map((b: any) => (
                      <button key={b.key} type="button" onClick={() => setCostWhy(b)}
                        title={af.howCalculated}
                        className="text-left bg-turquoise-50/60 hover:bg-turquoise-100/60 rounded-md px-3 py-2 transition-colors">
                        <p className="text-xs text-turquoise-800/60 flex items-center gap-1">
                          {comps[b.key] ?? b.key}
                          <span className="text-turquoise-400" aria-hidden>ⓘ</span>
                        </p>
                        <p className="text-sm font-medium text-turquoise-900">{money(b.amount)}</p>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {(lang === 'fr' ? a.summary_fr : a.summary_en) && (
                <p className="text-sm text-turquoise-800/70 mt-3">
                  {cleanSummary(lang === 'fr' ? a.summary_fr : a.summary_en)}
                </p>
              )}
              {Array.isArray(a.sources) && a.sources.length > 0 && (
                <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
                  <span className="text-xs text-turquoise-800/50">{t.drilldown.sources}:</span>
                  {a.sources.map((s: string, i: number) => {
                    const p = parseSource(s)
                    return p ? <a key={i} href={p.url} target="_blank" rel="noreferrer"
                      className="text-xs text-turquoise-600 hover:underline">{p.label}</a> : null
                  })}
                </div>
              )}
            </>
          )}

          {/* Visa income tie-in */}
          {incomeRoutes.length > 0 && (
            <div className="mt-4 border-t border-turquoise-50 pt-3">
              <p className="text-sm font-medium text-turquoise-900">{af.incomeTitle}</p>
              {a.annual_income != null && (
                <p className="text-xs text-turquoise-800/60 mb-2">
                  {af.incomeHint.replace('{income}', money(a.annual_income))}
                </p>
              )}
              <div className="space-y-1.5">
                {incomeRoutes.map((r: any) => (
                  <div key={r.category} className="flex items-center gap-2 text-sm">
                    <span className="text-turquoise-900">{r.label ?? r.category}</span>
                    <span className="text-xs text-turquoise-800/60">
                      {af.threshold}: {money(r.income)}{af.perYear}
                    </span>
                    <span className={`ml-auto text-xs font-medium rounded-full px-2 py-0.5 ${
                      r.qualifies ? 'text-emerald-700 bg-emerald-50' : 'text-amber-700 bg-amber-50'}`}>
                      {r.qualifies ? `✓ ${af.qualifies}` : af.belowThreshold}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
    )
  }

  // Per-entry explanation popup: how a cost figure was derived (the AI's localized justification),
  // plus the per-person base scaled to the household. Reuses the board's overlay-modal pattern.
  function costWhyModal() {
    if (!costWhy) return null
    const af = t.drilldown.afford as any
    const comps = af.components as Record<string, string>
    const money = (x: any) => fmtMoney(x, afford?.currency) ?? '—'
    const note = lang === 'fr' ? costWhy.note_fr : costWhy.note_en
    const size = householdInput ?? 1
    return (
      <div onClick={() => setCostWhy(null)}
        className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center p-4 z-50">
        <div onClick={(e) => e.stopPropagation()} className="bg-white rounded-xl max-w-sm w-full p-5">
          <div className="flex items-start gap-3 mb-2">
            <p className="font-medium text-turquoise-900">{comps[costWhy.key] ?? costWhy.key}</p>
            <button onClick={() => setCostWhy(null)} aria-label={af.close}
              className="ml-auto text-turquoise-800/50 hover:text-turquoise-900">×</button>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm mb-3">
            <span className="text-turquoise-800/70">{af.perPerson}:
              <b className="text-turquoise-900"> {money(costWhy.single)}{af.perMonth}</b></span>
            {size > 1 && (
              <span className="text-turquoise-800/70">
                {af.yourHouseholdN.replace('{n}', String(size))}:
                <b className="text-turquoise-900"> {money(costWhy.amount)}{af.perMonth}</b>
              </span>
            )}
          </div>
          <p className="text-xs text-turquoise-800/50 mb-1">{af.howCalculated}</p>
          <p className="text-sm text-turquoise-800/80">{note ? cleanSummary(note) : '—'}</p>
        </div>
      </div>
    )
  }

  // Collapsible wrapper: the calculator is hidden behind a toggle so it doesn't crowd the page —
  // expanding it lazily loads the data (and generates the cost breakdown) on first open.
  function affordSection() {
    const af = t.drilldown.afford as any
    return (
      <>
        <section className="mb-6">
          <button onClick={toggleAfford}
            className="w-full flex items-center gap-2 text-left bg-turquoise-50/70 border border-turquoise-100 rounded-lg px-3 py-2">
            <span className="inline-block w-4 text-turquoise-600">{afOpen ? '▾' : '▸'}</span>
            <span className="text-lg font-medium text-turquoise-900">{af.title}</span>
            {afOpen && afford == null && <Spinner />}
            <span className="ml-auto text-xs text-turquoise-800/50">{afford?.currency ?? currency}</span>
          </button>
          {afOpen && (
            <div className="mt-2">
              <p className="text-sm text-turquoise-800/60 mb-3">{af.hint}</p>
              {affordBody()}
            </div>
          )}
        </section>
        {costWhyModal()}
      </>
    )
  }

  function criterionBox(key: string) {
    const d = detailByKey[key]
    if (!d) return null
    return (
      <div key={key} id={`criterion-${key}`}
        className="bg-white border border-turquoise-100 rounded-lg p-4 scroll-mt-4 transition-shadow">
        <div className="flex items-center gap-2 mb-1">
          <p className="text-sm font-medium text-turquoise-900">
            {/* Registry's localized label (e.g. tax_treaty → "Conventions fiscales"), else the
                custom criterion's own label (passed through), else a humanized key — all via the
                central labelOf. */}
            {labelOf(reg, key, lang, d.label ? [{ key, label: d.label }] : undefined)}
            {d.score != null && <span className="text-turquoise-600"> · {d.score}/100</span>}
          </p>
          <label className="ml-auto flex items-center gap-1 text-xs text-turquoise-800/50">
            {t.comparison.importance}
            <input type="number" min={0} max={8} step={0.5} value={weightOf(key)}
              onChange={(e) => setWeight(key, Number(e.target.value))}
              className="w-12 border border-turquoise-100 rounded px-1 py-0.5 text-turquoise-800/70" />
          </label>
        </div>
        {d.pending ? (
          <p className="text-sm text-turquoise-800/50 italic flex items-center gap-2">
            <Spinner /> {t.drilldown.generating}
          </p>
        ) : (
          <p className={`text-sm ${d.summary ? 'text-turquoise-800/80' : 'text-turquoise-800/40 italic'}`}>
            {d.summary ? cleanSummary(d.summary) : t.drilldown.assessmentPending}
          </p>
        )}
        {d.meta && (d.meta.trend ? trendLine(d.meta)
          : (d.meta.quality != null || d.meta.access != null) ? serviceLine(d.meta) : null)}
        {Array.isArray(d.sources) && d.sources.length > 0 && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
            <span className="text-xs text-turquoise-800/50">{t.drilldown.sources}:</span>
            {d.sources.map((s: string, i: number) => {
              const src = parseSource(s)
              return src && (
                <a key={i} href={src.url} target="_blank" rel="noreferrer"
                  className="text-xs text-turquoise-600 hover:underline">{src.label}</a>
              )
            })}
          </div>
        )}
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
        {isAdmin && (
          <button onClick={regenerateAll} disabled={regenerating || loadingDetail}
            title={t.drilldown.regenHint}
            className="ml-auto shrink-0 text-xs border border-turquoise-200 text-turquoise-700 rounded-md px-2.5 py-1 hover:bg-turquoise-50 disabled:opacity-50 flex items-center gap-1.5">
            {regenerating ? <><Spinner /> {t.drilldown.regenerating}</> : `↻ ${t.drilldown.regenerate}`}
          </button>
        )}
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

      {/* Budget / affordability calculator — does this user's budget cover living here */}
      {affordSection()}

      {/* Visa pathways — the gate: how this user could legally settle here (collapsible, lazy) */}
      <section className="mb-6">
        <button onClick={toggleVisa}
          className="w-full flex items-center gap-2 text-left bg-turquoise-50/70 border border-turquoise-100 rounded-lg px-3 py-2">
          <span className="inline-block w-4 text-turquoise-600">{visaOpen ? '▾' : '▸'}</span>
          <span className="text-lg font-medium text-turquoise-900">{t.drilldown.visa.title}</span>
          {visaOpen && (visa == null || visa.categories.some((c: any) => c.pending)) && <Spinner />}
        </button>
        {visaOpen && (
          <div className="mt-2">
            <p className="text-sm text-turquoise-800/60 mb-3">{t.drilldown.visa.hint}</p>
            {visa == null ? (
              <p className="text-sm text-turquoise-800/50 italic flex items-center gap-2">
                <Spinner /> {t.drilldown.generating}
              </p>
            ) : (
              <div className="space-y-3">{visa.categories.map(visaCard)}</div>
            )}
          </div>
        )}
      </section>

      {/* Per-criterion detail, grouped by category (collapsed except the clicked one) */}
      <div className="flex items-center gap-3 mb-3">
        <h2 className="text-lg font-medium text-turquoise-900">{t.drilldown.detailTitle}</h2>
      </div>
      {loadingDetail && (
        <p className="text-turquoise-800/60 mb-4 flex items-center gap-2">
          <Spinner /> {t.drilldown.loadingDetail}
        </p>
      )}
      <div className="space-y-3 mb-6">
        {groups.map((g) => {
          // Hide weight-0 (unimportant) criteria unless revealed — but always show the one the
          // user clicked through from the table, so the drill-down lands on it.
          const vis = showZero ? g.keys : g.keys.filter((k) => weightOf(k) > 0 || k === clickedKey)
          if (!vis.length) return null
          const open = isOpen(g.key)
          const pendingCount = vis.filter((k) => detailByKey[k]?.pending).length
          return (
            <Fragment key={g.key}>
              <button onClick={() => toggleCat(g.key)}
                className="w-full flex items-center gap-2 text-left bg-turquoise-50/70 border border-turquoise-100 rounded-lg px-3 py-2">
                <span className="inline-block w-4 text-turquoise-600">{open ? '▾' : '▸'}</span>
                <span className="font-medium text-turquoise-900">{g.label}</span>
                {pendingCount > 0 && <Spinner />}
                <span className="ml-auto text-xs text-turquoise-800/50">{vis.length}</span>
              </button>
              {open && <div className="space-y-3 pl-1">{vis.map((k) => criterionBox(k))}</div>}
            </Fragment>
          )
        })}
        {(() => {
          const hidden = groups.reduce((n, g) => n + g.keys.filter((k) => weightOf(k) === 0).length, 0)
          if (!hidden) return null
          return (
            <button onClick={() => setShowZero((s) => !s)}
              className="text-xs text-turquoise-600 hover:underline">
              {showZero ? t.comparison.hideUnimportant : `${t.comparison.showUnimportant} (${hidden})`}
            </button>
          )
        })()}
      </div>

      {/* Assistant — same conversation as the comparison page, with this country's context */}
      {searchId != null && (
        <div className="mb-6">
          <ChatPanel searchId={searchId} placeId={id} />
        </div>
      )}

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
