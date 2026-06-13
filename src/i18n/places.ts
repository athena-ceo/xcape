// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import type { Dict, Language } from './index'

// Country names are stored canonically (English) with an ISO 3166-1 alpha-2 code.
// We render them in the active language via Intl.DisplayNames — so "Spain" shows as
// "Espagne" in French, "United States" as "États-Unis", etc. Regions/cities (no ISO
// code) fall back to the stored name.
const _displayNames: Partial<Record<Language, Intl.DisplayNames>> = {}

function displayNames(lang: Language): Intl.DisplayNames | null {
  if (!_displayNames[lang]) {
    try {
      _displayNames[lang] = new Intl.DisplayNames([lang], { type: 'region' })
    } catch {
      return null
    }
  }
  return _displayNames[lang] ?? null
}

export function placeName(
  place: { name: string; iso_code?: string | null } | null | undefined,
  lang: Language,
): string {
  if (!place) return ''
  const code = place.iso_code?.trim().toUpperCase()
  if (code && code.length === 2) {
    try {
      return displayNames(lang)?.of(code) ?? place.name
    } catch {
      return place.name
    }
  }
  return place.name
}

// Localize an attribute value (low/medium/high, mild, strong, …) for display.
export function attrValue(t: Dict, value: unknown): string {
  if (value == null || value === '') return '—'
  const key = String(value).toLowerCase()
  return (t.values as Record<string, string>)[key] ?? String(value)
}

// The "language" criterion always shows the country's actual languages (consistent),
// localized. Falls back to the static ease label for places without language data.
export function languageCell(t: Dict, attrs: Record<string, unknown> | undefined): string {
  const langs = attrs?.languages
  if (Array.isArray(langs) && langs.length) {
    return langs.map((l) => (t.langNames as Record<string, string>)[String(l)] ?? String(l)).join(', ')
  }
  return attrValue(t, attrs?.language_ease)
}
