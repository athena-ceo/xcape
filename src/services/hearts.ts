// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'

import { api } from './api'

// The user's hearted countries, shared by every page that shows a heart (board, phone cards,
// Explore, country page) so a tap in one place is reflected everywhere without refetching.
export type HeartedPlace = { place_id: number; name: string; iso_code: string | null }

let cache: HeartedPlace[] | null = null
let inflight: Promise<void> | null = null
const listeners = new Set<(h: HeartedPlace[]) => void>()

function publish(next: HeartedPlace[]) {
  cache = next
  listeners.forEach((l) => l(next))
}

function load(): Promise<void> {
  inflight ??= api.getHearts().then(publish).catch(() => publish([])).finally(() => { inflight = null })
  return inflight
}

// Forget the cache (sign-out / account switch).
export function resetHearts() { cache = null }

export function useHearts() {
  const [hearts, setHearts] = useState<HeartedPlace[]>(cache ?? [])
  useEffect(() => {
    listeners.add(setHearts)
    if (cache == null) void load()
    else setHearts(cache)
    return () => { listeners.delete(setHearts) }
  }, [])

  const isHearted = (placeId: number) => hearts.some((h) => h.place_id === placeId)

  // Optimistic: flip locally, then persist; roll back if the server refuses.
  async function toggle(place: { id: number; name: string; iso_code?: string | null }) {
    const before = cache ?? []
    const on = before.some((h) => h.place_id === place.id)
    publish(on ? before.filter((h) => h.place_id !== place.id)
               : [{ place_id: place.id, name: place.name, iso_code: place.iso_code ?? null }, ...before])
    try {
      if (on) await api.removeHeart(place.id)
      else await api.addHeart(place.id)
    } catch {
      publish(before)
    }
  }

  return { hearts, isHearted, toggle }
}
