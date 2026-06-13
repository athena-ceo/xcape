// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

// Shared option vocabularies for the onboarding wizard and the profile editor, so the
// two stay in lock-step.

export const HOUSEHOLDS = ['single', 'couple', 'family'] as const
export const REASON_KEYS = [
  'politics', 'economy', 'safety', 'climate', 'cost', 'healthcare', 'lifestyle', 'career',
] as const
export const CLIMATE_KEYS = ['cold', 'temperate', 'mild', 'warm', 'tropical'] as const
export const PRIORITY_KEYS = [
  'cost_of_living', 'healthcare', 'safety', 'political_stability',
  'climate', 'language_ease', 'tax', 'visa', 'nature',
] as const
// Canonical (English) language names — must match the country `languages` data.
export const LANG_OPTIONS = [
  'French', 'English', 'Spanish', 'German', 'Italian', 'Portuguese', 'Dutch', 'Arabic',
] as const
export const LOCALE_LANGUAGE: Record<string, string> = { fr: 'French', en: 'English' }

export const MAX_PRIORITIES = 3
export const PRIORITY_WEIGHT = 2.0

export function toggle<T>(list: T[], value: T, max = Infinity): T[] {
  if (list.includes(value)) return list.filter((v) => v !== value)
  if (list.length >= max) return list
  return [...list, value]
}
