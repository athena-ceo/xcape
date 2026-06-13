// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { Link, useNavigate } from 'react-router-dom'

import { useT, type Language } from '../i18n'
import { useAuth } from '../store/auth'

export function Header() {
  const { t, lang, setLang } = useT()
  const { token, isAdmin, logout, firstName, email } = useAuth()
  const navigate = useNavigate()

  // Friendly greeting with the user's name; fall back to the email handle if the
  // account has no first name yet.
  const displayName = firstName || email?.split('@')[0] || ''

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

        {token ? (
          <>
            {displayName && (
              <span className="text-turquoise-800/80">
                {t.nav.greeting}, <span className="font-medium text-turquoise-900">{displayName}</span>
              </span>
            )}
            <Link to="/search" className="text-turquoise-600">{t.nav.search}</Link>
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
    </header>
  )
}
