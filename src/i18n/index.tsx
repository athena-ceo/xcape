// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { createContext, useContext, useState, type ReactNode } from 'react'

import { en } from './en'
import { fr } from './fr'

export type Language = 'fr' | 'en'
export type Dict = typeof fr

const dictionaries: Record<Language, Dict> = { fr, en }

interface I18nContextValue {
  lang: Language
  setLang: (lang: Language) => void
  t: Dict
}

const I18nContext = createContext<I18nContextValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  // Default locale is French (per product decision).
  const [lang, setLang] = useState<Language>('fr')
  return (
    <I18nContext.Provider value={{ lang, setLang, t: dictionaries[lang] }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useT() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useT must be used within I18nProvider')
  return ctx
}
