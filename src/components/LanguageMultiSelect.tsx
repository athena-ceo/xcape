// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useMemo } from 'react'

import { useT, type Language } from '../i18n'

// ISO 639-1 codes — a broad set covering the world's widely-spoken and official
// languages. Names are derived via Intl.DisplayNames, so the list is localized and
// effectively open-ended ("any language").
const CODES = [
  'ab', 'aa', 'af', 'ak', 'sq', 'am', 'ar', 'hy', 'as', 'ay', 'az', 'bm', 'be', 'bn',
  'bs', 'bg', 'my', 'ca', 'ceb', 'ny', 'zh', 'co', 'hr', 'cs', 'da', 'dv', 'nl', 'dz',
  'en', 'eo', 'et', 'ee', 'fo', 'fj', 'fil', 'fi', 'fr', 'gl', 'ka', 'de', 'el', 'gn',
  'gu', 'ht', 'ha', 'haw', 'he', 'hi', 'hmn', 'hu', 'is', 'ig', 'id', 'ga', 'it', 'ja',
  'jv', 'kn', 'kk', 'km', 'rw', 'ko', 'ku', 'ky', 'lo', 'la', 'lv', 'ln', 'lt', 'lb',
  'mk', 'mg', 'ms', 'ml', 'mt', 'mi', 'mr', 'mn', 'ne', 'no', 'or', 'om', 'ps', 'fa',
  'pl', 'pt', 'pa', 'qu', 'ro', 'ru', 'sm', 'gd', 'sr', 'st', 'sn', 'sd', 'si', 'sk',
  'sl', 'so', 'es', 'su', 'sw', 'sv', 'tg', 'ta', 'tt', 'te', 'th', 'bo', 'ti', 'to',
  'tr', 'tk', 'uk', 'ur', 'ug', 'uz', 'vi', 'cy', 'fy', 'xh', 'yi', 'yo', 'zu',
]

interface Props {
  value: string[] // canonical English language names
  onChange: (langs: string[]) => void
  addLabel: string
}

export function LanguageMultiSelect({ value, onChange, addLabel }: Props) {
  const { lang } = useT()

  const { options, labelOf } = useMemo(() => {
    let en: Intl.DisplayNames | null = null
    let loc: Intl.DisplayNames | null = null
    try {
      en = new Intl.DisplayNames(['en'], { type: 'language' })
      loc = new Intl.DisplayNames([lang as Language], { type: 'language' })
    } catch {
      /* unsupported — fall back to raw stored names */
    }
    const opts: { value: string; label: string }[] = []
    const labels: Record<string, string> = {}
    for (const code of CODES) {
      const value = en?.of(code)
      const label = loc?.of(code) ?? value
      if (value && label && value !== code) {
        opts.push({ value, label })
        labels[value] = label
      }
    }
    opts.sort((a, b) => a.label.localeCompare(b.label, lang))
    return { options: opts, labelOf: labels }
  }, [lang])

  return (
    <div>
      <select value="" onChange={(e) => {
        const v = e.target.value
        if (v && !value.includes(v)) onChange([...value, v])
      }} className="border border-turquoise-100 rounded-md px-2 py-2 text-sm w-full">
        <option value="">{addLabel}…</option>
        {options.filter((o) => !value.includes(o.value)).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>

      {value.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {value.map((v) => (
            <span key={v}
              className="inline-flex items-center gap-1 bg-turquoise-50 text-turquoise-700 rounded-full px-3 py-1 text-sm">
              {labelOf[v] ?? v}
              <button type="button" aria-label="remove"
                onClick={() => onChange(value.filter((x) => x !== v))}
                className="text-turquoise-800/50 hover:text-red-600">×</button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
