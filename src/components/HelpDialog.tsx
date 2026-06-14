// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useState } from 'react'

import { useT } from '../i18n'

interface Props {
  onClose: () => void
}

// A short, paginated walkthrough of how xCape works — reachable any time from the
// header so users aren't left guessing what the table, criteria and chat do.
export function HelpDialog({ onClose }: Props) {
  const { t } = useT()
  const steps = t.help.steps as { title: string; body: string }[]
  const [i, setI] = useState(0)
  const last = i === steps.length - 1
  const step = steps[i]

  return (
    <div onClick={onClose}
      className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl max-w-md w-full p-6">
        <div className="flex items-start justify-between mb-1">
          <p className="text-sm text-turquoise-600">{t.help.title}</p>
          <button onClick={onClose} aria-label={t.common.cancel}
            className="text-turquoise-800/40 hover:text-turquoise-800 -mt-1">✕</button>
        </div>

        <h2 className="text-xl font-medium text-turquoise-900 mb-2">{step.title}</h2>
        <p className="text-turquoise-800/80 mb-5 leading-relaxed">{step.body}</p>

        {/* progress dots */}
        <div className="flex items-center justify-center gap-1.5 mb-5">
          {steps.map((_, n) => (
            <span key={n} className={`h-1.5 rounded-full transition-all ${
              n === i ? 'w-5 bg-turquoise-500' : 'w-1.5 bg-turquoise-200'}`} />
          ))}
        </div>

        <div className="flex items-center gap-3">
          {i > 0 && (
            <button onClick={() => setI((n) => n - 1)}
              className="border border-turquoise-100 rounded-md px-4 py-2 text-sm">
              {t.help.back}
            </button>
          )}
          <button onClick={() => (last ? onClose() : setI((n) => n + 1))}
            className="flex-1 bg-turquoise-600 text-turquoise-50 rounded-md py-2 text-sm">
            {last ? t.help.done : t.help.next}
          </button>
        </div>
      </div>
    </div>
  )
}
