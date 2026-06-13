// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'

import { useT } from '../i18n'
import { placeName } from '../i18n/places'
import { api } from '../services/api'

interface Props {
  value: string[] // ISO alpha-2 codes
  onChange: (codes: string[]) => void
  addLabel: string
}

// Pick one or more countries (by localized name); stores ISO codes. Used for
// citizenship. Selected countries show as removable chips.
export function CountryMultiSelect({ value, onChange, addLabel }: Props) {
  const { lang } = useT()
  const [countries, setCountries] = useState<any[]>([])

  useEffect(() => {
    api.listPlaces('country').then((cs) => setCountries(cs.filter((c) => c.iso_code)))
  }, [])

  const sorted = [...countries].sort((a, b) => placeName(a, lang).localeCompare(placeName(b, lang)))

  return (
    <div>
      <select
        value=""
        onChange={(e) => {
          const code = e.target.value
          if (code && !value.includes(code)) onChange([...value, code])
        }}
        className="border border-turquoise-100 rounded-md px-2 py-2 text-sm w-full"
      >
        <option value="">{addLabel}…</option>
        {sorted.filter((c) => !value.includes(c.iso_code)).map((c) => (
          <option key={c.iso_code} value={c.iso_code}>{placeName(c, lang)}</option>
        ))}
      </select>

      {value.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {value.map((iso) => (
            <span key={iso}
              className="inline-flex items-center gap-1 bg-turquoise-50 text-turquoise-700 rounded-full px-3 py-1 text-sm">
              {placeName({ name: iso, iso_code: iso }, lang)}
              <button type="button" aria-label="remove"
                onClick={() => onChange(value.filter((v) => v !== iso))}
                className="text-turquoise-800/50 hover:text-red-600">×</button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
