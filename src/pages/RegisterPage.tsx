// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useT } from '../i18n'
import { useAuth } from '../store/auth'

export function RegisterPage() {
  const { t, lang } = useT()
  const register = useAuth((s) => s.register)
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await register(email, password, lang)
      navigate('/onboarding')
    } catch (err) {
      setError(err instanceof Error ? err.message : t.auth.error)
    }
  }

  return (
    <main className="max-w-sm mx-auto px-5 py-16">
      <h1 className="text-2xl font-medium text-turquoise-900 mb-6">{t.auth.registerTitle}</h1>
      <form onSubmit={submit} className="space-y-4">
        <input
          type="email" required placeholder={t.auth.email}
          value={email} onChange={(e) => setEmail(e.target.value)}
          className="w-full border border-turquoise-100 rounded-md px-3 py-2"
        />
        <input
          type="password" required minLength={8} placeholder={t.auth.password}
          value={password} onChange={(e) => setPassword(e.target.value)}
          className="w-full border border-turquoise-100 rounded-md px-3 py-2"
        />
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button className="w-full bg-turquoise-600 text-turquoise-50 rounded-md py-2.5">
          {t.auth.submitRegister}
        </button>
      </form>
    </main>
  )
}
