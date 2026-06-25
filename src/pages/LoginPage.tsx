// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { PasswordField } from '../components/PasswordField'
import { useT } from '../i18n'
import { api } from '../services/api'
import { useAuth } from '../store/auth'

export function LoginPage() {
  const { t } = useT()
  const login = useAuth((s) => s.login)
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function doLogin() {
    setError('')
    try {
      await login(email, password)
      // A returning user with a finished search lands straight on their comparison board; a user
      // who never finished goes to onboarding, which resumes from their saved draft if any.
      const searches = await api.listSearches().catch(() => [])
      navigate(searches.length ? `/compare/${searches[0].id}` : '/onboarding')
    } catch {
      setError(t.auth.error)
    }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault()
    void doLogin()
  }

  return (
    <main className="max-w-sm mx-auto px-5 py-16">
      <h1 className="text-2xl font-medium text-turquoise-900 mb-6">{t.auth.loginTitle}</h1>
      <form onSubmit={submit} className="space-y-4">
        <input
          type="email" required placeholder={t.auth.email}
          value={email} onChange={(e) => setEmail(e.target.value)}
          className="w-full border border-turquoise-100 rounded-md px-3 py-2"
        />
        <PasswordField required placeholder={t.auth.password} autoComplete="current-password"
          value={password} onChange={setPassword}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void doLogin() } }} />
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button type="submit" className="w-full bg-turquoise-600 text-turquoise-50 rounded-md py-2.5">
          {t.auth.submitLogin}
        </button>
      </form>
    </main>
  )
}
