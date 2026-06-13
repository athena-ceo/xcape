// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

import { useT } from '../i18n'
import { api } from '../services/api'

// Resolves "My search" to the user's most recent search (the API lists them newest
// first). If they have none yet but already have a profile (e.g. filled in via the
// profile page), build one from that profile and go straight to the comparison board —
// don't send them back through onboarding.
export function SearchRedirect() {
  const { t } = useT()
  const navigate = useNavigate()

  useEffect(() => {
    async function resolve() {
      try {
        const searches = await api.listSearches()
        if (searches.length) {
          navigate(`/compare/${searches[0].id}`, { replace: true })
          return
        }
        const search = await api.createSearch(t.shortlist.title)
        await api.buildShortlist(search.id)
        navigate(`/compare/${search.id}`, { replace: true })
      } catch {
        navigate('/onboarding', { replace: true })
      }
    }
    resolve()
  }, [navigate, t.shortlist.title])

  return <p className="p-8 text-center">{t.common.loading}</p>
}
