// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

// Shared option vocabularies for the onboarding wizard and the profile editor, so the
// two stay in lock-step.

export const HOUSEHOLDS = ['single', 'couple', 'family'] as const
export const REASON_KEYS = [
  'politics', 'economy', 'safety', 'discrimination', 'patrimoine', 'retirement', 'climate',
  'cost', 'healthcare', 'lifestyle', 'career',
] as const
export const CLIMATE_KEYS = ['cold', 'temperate', 'mild', 'warm', 'tropical'] as const
export const PRIORITY_KEYS = [
  'cost_of_living', 'healthcare', 'safety', 'political_stability', 'inclusion',
  'gender_equality', 'climate', 'language_ease', 'culture', 'food', 'tax', 'visa', 'nature',
] as const
// Fallback community list (used only if the registry hasn't loaded yet) — the live set
// comes from the criteria registry (active communities). Drives the inclusion criterion.
export const MINORITY_GROUPS = [
  'lgbtq', 'jewish', 'muslim', 'ethnic_minorities', 'other_religious_minority',
] as const
// Canonical (English) language names — must match the country `languages` data.
export const LANG_OPTIONS = [
  'French', 'English', 'Spanish', 'German', 'Italian', 'Portuguese', 'Dutch', 'Arabic',
] as const
export const LOCALE_LANGUAGE: Record<string, string> = { fr: 'French', en: 'English' }

export const PRIORITY_WEIGHT = 2.0

// Weight for a priority by its rank in the user's ordered list: the top priority weighs most
// (3.0), stepping down to 1.0 for the last — so ordering directly shapes the ranking.
export function rankWeight(rank: number, total: number): number {
  if (total <= 1) return 3
  return Math.round((3 - (rank * 2) / (total - 1)) * 2) / 2  // 3.0 → 1.0 in 0.5 steps
}

export function toggle<T>(list: T[], value: T, max = Infinity): T[] {
  if (list.includes(value)) return list.filter((v) => v !== value)
  if (list.length >= max) return list
  return [...list, value]
}
