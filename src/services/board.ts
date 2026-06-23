// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { api } from './api'

// The comparison board holds at most this many countries (mirrors backend shortlist.MAX_COMPARE).
// The backend enforces the real cap; this drives the "replace the weakest" prompt threshold.
export const MAX_BOARD = 5

export type BoardMember = { place_id: number; name: string; score: number }

// Add a country to the comparison board, shared by the Explore list and the board's own
// "+ add country" so the full-board pruning isn't duplicated. When the board is full it proposes
// replacing the weakest-scoring member (the user confirms by name); on confirm the backend evicts
// that member and selects the new country atomically. Returns 'added' or 'cancelled'.
export async function addCountryToBoard(
  searchId: number,
  add: { place_id?: number; place_name?: string; label: string },
  board: BoardMember[],
  replaceConfirm: string,  // t.explore.replaceConfirm — has {weakest} {score} {new} placeholders
): Promise<'added' | 'cancelled'> {
  let evict_place_id: number | undefined
  if (board.length >= MAX_BOARD) {
    const weakest = board.reduce((a, b) => (b.score < a.score ? b : a))
    const msg = replaceConfirm
      .replace('{weakest}', weakest.name).replace('{score}', String(weakest.score))
      .replace('{new}', add.label)
    if (!confirm(msg)) return 'cancelled'
    evict_place_id = weakest.place_id
  }
  await api.addCandidate(searchId, { place_id: add.place_id, place_name: add.place_name, evict_place_id })
  return 'added'
}
