// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

// Selectable pill used for single- and multi-select choices.
export function Chip({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-lg border px-4 py-2.5 text-sm text-left transition ${
        active ? 'border-turquoise-400 bg-turquoise-50 text-turquoise-600'
               : 'border-turquoise-100 hover:border-turquoise-200'
      }`}
    >
      {children}
    </button>
  )
}
