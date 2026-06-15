// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { createContext, useContext, useState, type ReactNode } from 'react'

import { api } from '../services/api'
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

const STORAGE_KEY = 'xcape_lang'

// Default locale is French (per product decision); a saved choice wins.
function initialLang(): Language {
  const saved = localStorage.getItem(STORAGE_KEY)
  return saved === 'en' || saved === 'fr' ? saved : 'fr'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>(initialLang)

  // Persist the choice so it survives reloads AND so the server-side locale (used for the
  // PDF report, emails, etc.) matches what the user is reading. Best-effort on the server.
  function setLang(next: Language) {
    setLangState(next)
    try { localStorage.setItem(STORAGE_KEY, next) } catch { /* ignore */ }
    if (localStorage.getItem('xcape_token')) {
      api.updateMe({ locale: next }).catch(() => { /* non-blocking */ })
    }
  }

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
