// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useT, type Language } from '../i18n'
import { api } from '../services/api'
import { useAuth } from '../store/auth'
import { HelpDialog } from './HelpDialog'

export function Header() {
  const { t, lang, setLang } = useT()
  const { token, isAdmin, logout, firstName, email } = useAuth()
  const navigate = useNavigate()
  const [resetOpen, setResetOpen] = useState(false)
  const [resetSid, setResetSid] = useState<number | null>(null)
  const [working, setWorking] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  // Friendly greeting with the user's name; fall back to the email handle if the
  // account has no first name yet.
  const displayName = firstName || email?.split('@')[0] || ''

  // Open the start-over dialog; resolve the latest search so we can offer to save its PDF.
  async function openReset() {
    let sid: number | null = null
    try {
      const searches = await api.listSearches()
      sid = searches.length ? searches[0].id : null
    } catch { /* ignore */ }
    setResetSid(sid)
    setResetOpen(true)
  }

  // Start over: optionally save the current search as a PDF first, then wipe + onboard.
  async function doReset(savePdf: boolean) {
    setWorking(true)
    try {
      if (savePdf && resetSid != null) await api.downloadReport(resetSid)
      await api.resetAccount()
    } catch { /* proceed to onboarding regardless */ } finally {
      setWorking(false)
      setResetOpen(false)
      navigate('/onboarding')
    }
  }

  return (
    <header className="flex items-center gap-4 px-5 py-3 bg-white border-b border-turquoise-100">
      <Link to="/" className="flex items-center gap-2 font-medium text-turquoise-600 text-lg">
        <span className="w-7 h-7 rounded-lg bg-turquoise-600 text-turquoise-50 grid place-items-center">✈</span>
        {t.appName}
      </Link>

      <nav className="ml-auto flex items-center gap-3 text-sm">
        <select
          aria-label="language"
          value={lang}
          onChange={(e) => setLang(e.target.value as Language)}
          className="border border-turquoise-100 rounded-md px-2 py-1"
        >
          <option value="fr">FR</option>
          <option value="en">EN</option>
        </select>

        <button onClick={() => setHelpOpen(true)} title={t.nav.help} aria-label={t.nav.help}
          className="inline-flex items-center justify-center w-7 h-7 rounded-full border border-turquoise-100 text-turquoise-600 font-medium">?</button>

        {token ? (
          <>
            {displayName && (
              <span className="text-turquoise-800/80">
                {t.nav.greeting}, <span className="font-medium text-turquoise-900">{displayName}</span>
              </span>
            )}
            <Link to="/search" className="text-turquoise-600">{t.nav.search}</Link>
            <button onClick={openReset} className="text-turquoise-600">{t.nav.newRequest}</button>
            <Link to="/profile" className="text-turquoise-600">{t.nav.profile}</Link>
            {isAdmin && <Link to="/admin" className="text-turquoise-600">{t.nav.admin}</Link>}
            <button
              onClick={() => { logout(); navigate('/') }}
              className="text-turquoise-600"
            >
              {t.nav.logout}
            </button>
          </>
        ) : (
          <>
            <Link to="/login" className="text-turquoise-600">{t.nav.login}</Link>
            <Link
              to="/register"
              className="bg-turquoise-600 text-turquoise-50 rounded-md px-3 py-1.5"
            >
              {t.nav.register}
            </Link>
          </>
        )}
      </nav>

      {resetOpen && (
        <div onClick={() => !working && setResetOpen(false)}
          className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-xl max-w-sm w-full p-5">
            <h2 className="font-medium text-turquoise-900 mb-1">{t.nav.newRequest}</h2>
            <p className="text-sm text-turquoise-800/70 mb-4">{t.nav.newRequestConfirm}</p>
            <div className="flex flex-col gap-2">
              {resetSid != null && (
                <button onClick={() => doReset(true)} disabled={working}
                  className="bg-turquoise-600 text-turquoise-50 rounded-md px-4 py-2 text-sm disabled:opacity-50">
                  {t.nav.resetSavePdf}
                </button>
              )}
              <button onClick={() => doReset(false)} disabled={working}
                className="border border-turquoise-200 text-turquoise-700 rounded-md px-4 py-2 text-sm disabled:opacity-50">
                {t.nav.resetNoSave}
              </button>
              <button onClick={() => setResetOpen(false)} disabled={working}
                className="text-turquoise-800/60 text-sm px-4 py-1.5">
                {t.common.cancel}
              </button>
            </div>
          </div>
        </div>
      )}

      {helpOpen && <HelpDialog onClose={() => setHelpOpen(false)} />}
    </header>
  )
}
