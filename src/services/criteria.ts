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
  if (!_promise) _promise = api.getCriteria().then((r: Registry) => { _cache = r; return r })
  return _promise
}

// Drop the cached catalog so the next read refetches (after an admin edit).
export function refreshCriteria(): void {
  _cache = null
  _promise = null
}

export function useCriteria(): Registry | null {
  const [reg, setReg] = useState<Registry | null>(_cache)
  useEffect(() => { if (!reg) loadCriteria().then(setReg).catch(() => {}) }, [reg])
  return reg
}

// --- pure helpers over a registry ---------------------------------------------------
export function nodeOf(reg: Registry | null, key: string): CritNode | undefined {
  return reg?.nodes.find((n) => n.key === key)
}

export function labelOf(reg: Registry | null, key: string, lang: string, custom?: { key: string; label: string }[]): string {
  const n = nodeOf(reg, key)
  if (n) return (lang === 'fr' ? n.label_fr : n.label_en) || n.label_en || key
  return custom?.find((c) => c.key === key)?.label ?? key
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
