// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { VoiceButton } from './VoiceButton'

interface Props {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  type?: string
  required?: boolean
  minLength?: number
  autoComplete?: string
  onEnter?: () => void
  className?: string
}

// A text input with an inline microphone. Use this for every free-text field so that
// text and voice are always offered together. Dictated text is appended to whatever
// is already typed.
export function VoiceField({
  value, onChange, placeholder, type = 'text',
  required, minLength, autoComplete, onEnter, className,
}: Props) {
  function appendTranscript(text: string) {
    onChange(value.trim() ? `${value.trim()} ${text}` : text)
  }

  return (
    <div className="relative">
      <input
        type={type}
        value={value}
        required={required}
        minLength={minLength}
        autoComplete={autoComplete}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && onEnter) onEnter() }}
        className={
          className ??
          'w-full border border-turquoise-100 rounded-md pl-3 pr-10 py-2'
        }
      />
      <span className="absolute right-2 top-1/2 -translate-y-1/2">
        <VoiceButton onTranscript={appendTranscript} />
      </span>
    </div>
  )
}
