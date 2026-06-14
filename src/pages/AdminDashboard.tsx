// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'

import { useT } from '../i18n'
import { api } from '../services/api'

export function AdminDashboard() {
  const { t } = useT()
  const [users, setUsers] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getAdminUsers().then(setUsers).finally(() => setLoading(false))
  }, [])

  async function resetPassword(u: any) {
    const pw = window.prompt(`${t.admin.resetPrompt} ${u.email}`)
    if (pw === null) return
    if (pw.length < 8) {
      window.alert(t.admin.resetTooShort)
      return
    }
    await api.adminResetPassword(u.id, pw)
    window.alert(t.admin.resetDone)
  }

  return (
    <main className="max-w-4xl mx-auto px-5 py-10">
      <h1 className="text-2xl font-medium text-turquoise-900 mb-1">{t.admin.title}</h1>
      <p className="text-turquoise-800/70 mb-6">{t.admin.subtitle}</p>

      <h2 className="text-lg font-medium text-turquoise-900 mb-3">{t.admin.usersTitle}</h2>
      {loading ? (
        <p className="text-turquoise-800/60">{t.common.loading}</p>
      ) : (
        <div className="overflow-x-auto bg-white border border-turquoise-100 rounded-lg">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-turquoise-50 text-left">
                <th className="p-3 font-medium">{t.admin.colName}</th>
                <th className="p-3 font-medium">{t.admin.colEmail}</th>
                <th className="p-3 font-medium">{t.admin.colAdmin}</th>
                <th className="p-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-turquoise-100">
                  <td className="p-3">{[u.first_name, u.last_name].filter(Boolean).join(' ') || '—'}</td>
                  <td className="p-3">{u.email}</td>
                  <td className="p-3">{u.is_admin ? t.admin.yes : ''}</td>
                  <td className="p-3 text-right">
                    <button onClick={() => resetPassword(u)}
                      className="text-turquoise-600 hover:underline">
                      {t.admin.resetPassword}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}
