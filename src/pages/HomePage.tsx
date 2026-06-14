// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { PasswordField } from '../components/PasswordField'
import { useT } from '../i18n'
import { useAuth } from '../store/auth'

export function HomePage() {
  const { t } = useT()
  const navigate = useNavigate()
  const token = useAuth((s) => s.token)
  const login = useAuth((s) => s.login)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await login(email, password)
      navigate('/search')
    } catch {
      setError(t.auth.error)
    }
  }

  return (
    <main className="max-w-5xl mx-auto px-5 py-12 md:py-16">
      <div className="grid md:grid-cols-2 gap-10 items-start">
        {/* Marketing */}
        <section>
          <p className="text-turquoise-600 font-medium mb-2">{t.tagline}</p>
          <h1 className="text-3xl md:text-4xl font-medium text-turquoise-900 mb-4">{t.home.heroTitle}</h1>
          <p className="text-lg text-turquoise-800/80 mb-8">{t.home.heroSubtitle}</p>
          <ul className="space-y-4">
            {t.home.features.map((f) => (
              <li key={f.title} className="flex gap-3">
                <span className="mt-1 w-2 h-2 rounded-full bg-turquoise-400 shrink-0" />
                <div>
                  <p className="font-medium text-turquoise-900">{f.title}</p>
                  <p className="text-sm text-turquoise-800/70">{f.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* Auth card */}
        <aside className="bg-white border border-turquoise-100 rounded-xl p-6 md:mt-10">
          {token ? (
            <>
              <h2 className="text-xl font-medium text-turquoise-900 mb-4">{t.appName}</h2>
              <Link to="/search"
                className="block text-center bg-turquoise-600 text-turquoise-50 rounded-lg py-2.5">
                {t.home.continueSearch}
              </Link>
            </>
          ) : (
            <>
              <h2 className="text-xl font-medium text-turquoise-900 mb-4">{t.auth.loginTitle}</h2>
              <form onSubmit={submit} className="space-y-3">
                <input type="email" required placeholder={t.auth.email}
                  value={email} onChange={(e) => setEmail(e.target.value)}
                  className="w-full border border-turquoise-100 rounded-md px-3 py-2" />
                <PasswordField required placeholder={t.auth.password} autoComplete="current-password"
                  value={password} onChange={setPassword} />
                {error && <p className="text-red-600 text-sm">{error}</p>}
                <button type="submit" className="w-full bg-turquoise-600 text-turquoise-50 rounded-md py-2.5">
                  {t.auth.submitLogin}
                </button>
              </form>
              <div className="mt-4 pt-4 border-t border-turquoise-100 text-center text-sm">
                <span className="text-turquoise-800/70">{t.home.noAccount} </span>
                <Link to="/register" className="text-turquoise-600 font-medium">{t.nav.register}</Link>
              </div>
            </>
          )}
        </aside>
      </div>
    </main>
  )
}
