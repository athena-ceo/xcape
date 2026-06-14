// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useState } from 'react'

import { MINORITY_GROUPS, toggle } from '../data/profileOptions'
import { useT } from '../i18n'
import { Chip } from './Chip'

interface Props {
  value: string[]
  onChange: (groups: string[]) => void
}

// Preset communities as toggle chips, plus a free-text field so users can name any other
// community that matters to them (stored verbatim in the same list).
export function CommunitySelect({ value, onChange }: Props) {
  const { t } = useT()
  const [draft, setDraft] = useState('')
  const presets = MINORITY_GROUPS as readonly string[]
  const custom = value.filter((g) => !presets.includes(g))

  function addCustom() {
    const v = draft.trim()
    if (!v || value.includes(v)) { setDraft(''); return }
    onChange([...value, v])
    setDraft('')
  }

  return (
    <div>
      <div className="grid sm:grid-cols-2 gap-3">
        {MINORITY_GROUPS.map((g) => (
          <Chip key={g} active={value.includes(g)} onClick={() => onChange(toggle(value, g))}>
            {t.groups[g]}
          </Chip>
        ))}
      </div>

      {custom.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {custom.map((g) => (
            <span key={g}
              className="inline-flex items-center gap-1 bg-turquoise-50 text-turquoise-700 rounded-full px-3 py-1 text-sm">
              {g}
              <button type="button" aria-label="remove"
                onClick={() => onChange(value.filter((x) => x !== g))}
                className="text-turquoise-800/50 hover:text-red-600">×</button>
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 mt-3">
        <input value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustom() } }}
          placeholder={t.onboarding.communities.addPrompt}
          className="flex-1 border border-turquoise-100 rounded-md px-3 py-2 text-sm" />
        <button type="button" onClick={addCustom} disabled={!draft.trim()}
          className="border border-turquoise-100 rounded-md px-3 py-2 text-sm disabled:opacity-50">
          {t.onboarding.communities.add}
        </button>
      </div>
    </div>
  )
}
