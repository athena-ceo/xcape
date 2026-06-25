// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'

import { api } from './api'

// The criteria registry, fetched once from GET /criteria — the single catalog the UI
// renders (so it reflects whatever the registry / admin defines, no hard-coded lists).
export interface CritNode {
  key: string
  parent: string | null
  kind?: 'objective' | 'computed'
  label_fr: string
  label_en: string
  tags?: string[]
  default_weight?: number
  value_labels?: Record<string, { fr: string; en: string }>
  scale?: Record<string, number>
}
export interface Persona {
  key: string
  label_fr: string
  label_en: string
  blurb_fr?: string
  blurb_en?: string
  match?: { reasons?: string[]; tags?: string[] }
  weights?: Record<string, number>
  filters?: string[]  // criteria that default to an "exclude-bad" hard filter
  ask?: string[]
  custom_criteria?: { label_en?: string; label_fr?: string; description?: string; per_community?: boolean }[]
}
export interface Registry {
  tags: Record<string, { label_fr: string; label_en: string; kind: string }>
  reason_tags: Record<string, string[]>
  communities: { key: string; label_fr: string; label_en: string }[]
  personas?: Persona[]
  nodes: CritNode[]
}

let _cache: Registry | null = null
let _promise: Promise<Registry> | null = null

export function loadCriteria(): Promise<Registry> {
  if (_cache) return Promise.resolve(_cache)
  if (!_promise) {
    _promise = api.getCriteria()
      .then((r: Registry) => { _cache = r; return r })
      // Never cache a FAILURE: a rejected promise stored here would be returned to every
      // subsequent caller for the whole session, permanently blanking the criteria UI
      // (no personas, no labels…) after a single transient error. Clear it so the next
      // call re-fetches, and re-throw so the caller can react / retry.
      .catch((e) => { _promise = null; throw e })
  }
  return _promise
}

// Drop the cached catalog so the next read refetches (after an admin edit).
export function refreshCriteria(): void {
  _cache = null
  _promise = null
}

export function useCriteria(): Registry | null {
  const [reg, setReg] = useState<Registry | null>(_cache)
  useEffect(() => {
    if (reg) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    const attemptLoad = () => {
      loadCriteria()
        .then((r) => { if (!cancelled) setReg(r) })
        .catch(() => {
          // A transient failure (cold start, dropped request, brief token gap) used to leave the
          // registry-driven UI blank forever with no way to recover on a device that can't reload.
          // Retry with capped exponential backoff until it loads; loadCriteria() cleared its cache
          // on failure, so each attempt genuinely re-fetches. Stops once mounted state is cancelled.
          if (cancelled) return
          attempt += 1
          const delay = Math.min(1000 * 2 ** (attempt - 1), 15000)  // 1s, 2s, 4s, … capped at 15s
          timer = setTimeout(attemptLoad, delay)
        })
    }
    attemptLoad()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [reg])
  return reg
}

// --- pure helpers over a registry ---------------------------------------------------
export function nodeOf(reg: Registry | null, key: string): CritNode | undefined {
  return reg?.nodes.find((n) => n.key === key)
}

// Last-resort readable label when the registry hasn't loaded yet (or a key is genuinely unknown):
// turn a raw criterion key like "cost_of_living" into "Cost of living" rather than exposing the
// slug. The registry holds the real localized labels — this only bridges the brief load window
// (the criteria fetch keeps retrying) so no surface ever shows snake_case keys to a user.
export function humanizeKey(key: string): string {
  return key.replace(/^custom_/, '').replace(/_/g, ' ').trim().replace(/^\w/, (c) => c.toUpperCase())
}

// The single entry point for every user-facing criterion label across the app: registry label in
// the active language → an explicitly-supplied custom label (localized when the def carries
// label_fr/label_en, else the raw label) → a humanized key. Always pass any known custom label
// via `custom` so it wins over the humanized fallback.
export type CustomCritLabel = { key: string; label?: string; label_fr?: string; label_en?: string }
export function labelOf(reg: Registry | null, key: string, lang: string, custom?: CustomCritLabel[]): string {
  const n = nodeOf(reg, key)
  if (n) return (lang === 'fr' ? n.label_fr : n.label_en) || n.label_en || humanizeKey(key)
  const c = custom?.find((c) => c.key === key)
  if (c) return (lang === 'fr' ? c.label_fr : c.label_en) || c.label_en || c.label_fr || c.label || humanizeKey(key)
  return humanizeKey(key)
}

export function leafKeys(reg: Registry | null): string[] {
  return (reg?.nodes ?? []).filter((n) => n.kind).map((n) => n.key)
}

// Top-level categories in registry order, each with its descendant leaf keys (any depth).
export function categories(reg: Registry | null): { key: string; node: CritNode; leaves: string[] }[] {
  if (!reg) return []
  const childrenOf = (key: string): string[] => {
    const out: string[] = []
    for (const n of reg.nodes) {
      if (n.parent !== key) continue
      if (n.kind) out.push(n.key)
      else out.push(...childrenOf(n.key))
    }
    return out
  }
  return reg.nodes.filter((n) => n.parent === null).map((n) => ({ key: n.key, node: n, leaves: childrenOf(n.key) }))
}

export function valueLabel(reg: Registry | null, key: string, tier: string | undefined, lang: string): string | null {
  const vl = nodeOf(reg, key)?.value_labels
  if (!vl || !tier || !vl[tier]) return null
  return lang === 'fr' ? vl[tier].fr : vl[tier].en
}
