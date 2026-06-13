// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { Link } from 'react-router-dom'

import { useT } from '../i18n'
import { useAuth } from '../store/auth'

export function HomePage() {
  const { t } = useT()
  const token = useAuth((s) => s.token)

  return (
    <main className="max-w-3xl mx-auto px-5 py-20 text-center">
      <p className="text-turquoise-600 font-medium mb-3">{t.tagline}</p>
      <h1 className="text-4xl font-medium text-turquoise-900 mb-4">{t.home.heroTitle}</h1>
      <p className="text-lg text-turquoise-800/80 mb-8">{t.home.heroSubtitle}</p>
      <Link
        to={token ? '/onboarding' : '/register'}
        className="inline-block bg-turquoise-600 text-turquoise-50 rounded-lg px-6 py-3 text-lg"
      >
        {t.home.cta}
      </Link>
    </main>
  )
}
