// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useState } from 'react'

import { useT } from '../i18n'

interface Props {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  required?: boolean
  minLength?: number
  autoComplete?: string
}

// Password input with a standard show/hide (eye) toggle.
export function PasswordField({ value, onChange, placeholder, required, minLength, autoComplete }: Props) {
  const { t } = useT()
  const [show, setShow] = useState(false)

  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        value={value}
        required={required}
        minLength={minLength}
        autoComplete={autoComplete}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-turquoise-100 rounded-md pl-3 pr-10 py-2"
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? t.auth.hidePassword : t.auth.showPassword}
        title={show ? t.auth.hidePassword : t.auth.showPassword}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-turquoise-600 hover:text-turquoise-800"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          {show ? (
            <>
              <path d="M10.585 10.587a2 2 0 0 0 2.829 2.828" />
              <path d="M16.681 16.673a8.717 8.717 0 0 1 -4.681 1.327c-3.6 0 -6.6 -2 -9 -6c1.272 -2.12 2.712 -3.678 4.32 -4.674m2.86 -1.146a9.055 9.055 0 0 1 1.82 -.18c3.6 0 6.6 2 9 6c-.666 1.11 -1.379 2.067 -2.138 2.87" />
              <path d="M3 3l18 18" />
            </>
          ) : (
            <>
              <path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0" />
              <path d="M21 12c-2.4 4 -5.4 6 -9 6c-3.6 0 -6.6 -2 -9 -6c2.4 -4 5.4 -6 9 -6c3.6 0 6.6 2 9 6" />
            </>
          )}
        </svg>
      </button>
    </div>
  )
}
