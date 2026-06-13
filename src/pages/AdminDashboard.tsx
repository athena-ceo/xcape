// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useT } from '../i18n'

// Scaffold placeholder. The full admin (users, searches, place-DB editor + refresh,
// AI usage log) mirrors golden-path's admin pages — build-phase task, plan §6.
export function AdminDashboard() {
  const { t } = useT()
  return (
    <main className="max-w-4xl mx-auto px-5 py-10">
      <h1 className="text-2xl font-medium text-turquoise-900 mb-2">{t.nav.admin}</h1>
      <p className="text-turquoise-800/70">
        Users · Searches · Place database · AI usage log — coming in the admin build phase.
      </p>
    </main>
  )
}
