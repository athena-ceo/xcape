// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useT } from '../i18n'
import { placeName } from '../i18n/places'
import { useHearts } from '../services/hearts'

interface Props {
  place: { id: number; name: string; iso_code?: string | null }
  // 'sm' for table headers and list rows; 'md' (44px target) for cards and page titles.
  size?: 'sm' | 'md'
  className?: string
}

// ♥ a country: a personal "this one speaks to me" marker that follows the user across searches.
// It never changes a score — the numbers stay the same everywhere.
export function HeartButton({ place, size = 'md', className = '' }: Props) {
  const { t, lang } = useT()
  const { isHearted, toggle } = useHearts()
  const on = isHearted(place.id)
  const name = placeName(place, lang)
  const box = size === 'sm' ? 'w-7 h-7' : 'w-11 h-11'
  const icon = size === 'sm' ? 16 : 22
  return (
    <button type="button" onClick={(e) => { e.preventDefault(); e.stopPropagation(); void toggle(place) }}
      aria-pressed={on} aria-label={(on ? t.hearts.remove : t.hearts.add).replace('{country}', name)}
      title={(on ? t.hearts.remove : t.hearts.add).replace('{country}', name)}
      className={`inline-flex shrink-0 items-center justify-center rounded-full transition hover:bg-rose-50 ${
        on ? 'text-rose-600' : 'text-turquoise-800/40 hover:text-rose-500'} ${box} ${className}`}>
      <svg width={icon} height={icon} viewBox="0 0 24 24" fill={on ? 'currentColor' : 'none'}
        stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 20.5s-7.5-4.6-9.4-9.5C1.3 7.5 3.6 4 7.1 4c2 0 3.6 1.1 4.9 2.8C13.3 5.1 14.9 4 16.9 4c3.5 0 5.8 3.5 4.5 7-1.9 4.9-9.4 9.5-9.4 9.5z" />
      </svg>
    </button>
  )
}
