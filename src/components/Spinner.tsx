// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

// Small animated spinner shown while an AI / network operation is in flight.
export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="loading"
      className={`inline-block w-4 h-4 border-2 border-turquoise-200 border-t-turquoise-600 rounded-full animate-spin align-[-3px] ${className ?? ''}`}
    />
  )
}
