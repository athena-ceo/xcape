// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useRef, useState } from 'react'

import { useT } from '../i18n'
import { Spinner } from './Spinner'

// A reassuring "please wait" line for slow AI work: spinner + rotating messages + an
// elapsed-seconds timer, so the user can see something is happening and how long it's taken.
export function Waiting({ messages }: { messages?: string[] }) {
  const { t } = useT()
  const msgs = messages && messages.length ? messages : (t.waiting.messages as string[])
  const [i, setI] = useState(0)
  const [secs, setSecs] = useState(0)
  const start = useRef(Date.now())

  useEffect(() => {
    const tick = setInterval(() => setSecs(Math.round((Date.now() - start.current) / 1000)), 1000)
    const rot = setInterval(() => setI((n) => (n + 1) % msgs.length), 3500)
    return () => { clearInterval(tick); clearInterval(rot) }
  }, [msgs.length])

  return (
    <p className="text-sm text-turquoise-800/70 flex items-center gap-2">
      <Spinner />
      <span>{msgs[i]}</span>
      <span className="text-turquoise-800/40">· {secs}s</span>
    </p>
  )
}
