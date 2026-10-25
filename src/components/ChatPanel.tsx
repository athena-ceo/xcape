// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useRef, useState } from 'react'

import { useT } from '../i18n'
import { api, ApiError } from '../services/api'
import { Markdown } from './Markdown'
import { Spinner } from './Spinner'
import { VoiceButton } from './VoiceButton'

interface Props {
  searchId: number
  // When set (drill-down page), that country's details are added to the assistant's context.
  placeId?: number
  // Called when the assistant changed the search (so the host page can re-read its data).
  onChanged?: () => void
}

// After a dropped request, how long to keep looking for the reply the server saved anyway.
// The server-side tool loop stops starting new model rounds after ~100 s.
const RECOVER_POLL_MS = 4000
const RECOVER_POLLS = 40

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

// The relocation assistant, shared by the comparison and drill-down pages. History is keyed
// by searchId, so both pages show the SAME conversation; placeId only enriches the context
// of new turns sent from a country's drill-down.
export function ChatPanel({ searchId, placeId, onChanged }: Props) {
  const { t } = useT()
  const [chat, setChat] = useState('')
  const [messages, setMessages] = useState<any[]>([])
  const [chatBusy, setChatBusy] = useState(false)
  const [recovering, setRecovering] = useState(false)
  // The message whose answer never arrived (shown with a retry button).
  const [failed, setFailed] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const lastReplyRef = useRef<HTMLDivElement | null>(null)
  const busyRef = useRef(false)

  useEffect(() => { api.getChat(searchId).then(setMessages).catch(() => {}) }, [searchId])

  // Phones drop in-flight requests when the app is backgrounded or the network hands over
  // (prod 2026-10-25: iOS 499s). The server still saves the reply, so re-read the thread
  // whenever the page comes back into view.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible' && !busyRef.current) {
        api.getChat(searchId).then(setMessages).catch(() => {})
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [searchId])

  // On a new assistant reply, scroll so the TOP of that reply is visible (read from the
  // start of the answer); otherwise pin to the bottom (spinner / new user message).
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const last = messages[messages.length - 1]
    if (!chatBusy && last?.role === 'assistant' && lastReplyRef.current) {
      el.scrollTop = lastReplyRef.current.offsetTop - el.offsetTop
    } else {
      el.scrollTop = el.scrollHeight
    }
  }, [messages, chatBusy])

  // Poll the saved thread for an answer to `message` posted after the first `baseline`
  // persisted turns. Returns true (and shows the thread) once it's there.
  async function recoverReply(message: string, baseline: number): Promise<boolean> {
    for (let i = 0; i < RECOVER_POLLS; i++) {
      const thread = await api.getChat(searchId).catch(() => null)
      if (thread) {
        const asked = thread.findIndex((m, idx) => idx >= baseline && m.role === 'user' && m.content === message)
        if (asked >= 0 && thread.slice(asked + 1).some((m) => m.role === 'assistant')) {
          setMessages(thread)
          return true
        }
      }
      await sleep(RECOVER_POLL_MS)
    }
    return false
  }

  async function send(message: string) {
    if (!message.trim() || chatBusy) return
    const baseline = messages.filter((m) => typeof m.id === 'number').length // persisted turns
    setChat('')
    setFailed(null)
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: 'user', content: message }])
    setChatBusy(true)
    busyRef.current = true
    try {
      const res = await api.sendChat(searchId, message, placeId)
      setMessages(await api.getChat(searchId)) // sync the persisted thread (user + assistant)
      if (res.changed) onChanged?.()
    } catch (e) {
      // A 4xx means the server refused the message: nothing to wait for. Otherwise (dropped
      // connection, proxy timeout, 5xx) the reply may still have been saved — look for it.
      const refused = e instanceof ApiError && e.status < 500
      setRecovering(!refused)
      const ok = !refused && (await recoverReply(message, baseline))
      if (ok) {
        onChanged?.() // we can't know whether the assistant changed the board — re-read it
      } else {
        setFailed(message)
        api.getChat(searchId).then(setMessages).catch(() => {})
      }
    } finally {
      setChatBusy(false)
      setRecovering(false)
      busyRef.current = false
    }
  }

  return (
    <div className="bg-turquoise-50 border border-turquoise-100 rounded-lg p-3">
      <p className="text-sm font-medium text-turquoise-600 mb-2">{t.comparison.askAssistant}</p>
      <div ref={scrollRef} className="space-y-2 mb-3 max-h-72 overflow-y-auto">
        {messages.length === 0 && (
          <p className="text-sm text-turquoise-800/50">{t.comparison.chatEmpty}</p>
        )}
        {messages.map((m, i) => (
          <div key={m.id}
            ref={i === messages.length - 1 && m.role === 'assistant' ? lastReplyRef : undefined}
            className={`text-sm rounded-lg px-3 py-2 ${
              m.role === 'user' ? 'bg-turquoise-600 text-turquoise-50 ml-8'
                                : 'bg-white border border-turquoise-100 mr-8'}`}>
            {m.role === 'user' ? m.content : <Markdown>{m.content}</Markdown>}
          </div>
        ))}
        {chatBusy && (
          <p className="text-sm text-turquoise-800/50 flex items-center gap-2">
            <Spinner /> {recovering ? t.comparison.chatReconnecting : t.comparison.thinking}
          </p>
        )}
        {failed && !chatBusy && (
          <div role="alert" className="text-sm rounded-lg px-3 py-2 bg-amber-50 border border-amber-200 text-amber-900 mr-8">
            <p className="italic text-amber-900/70">“{failed}”</p>
            <p>{t.comparison.chatFailed}</p>
            <button onClick={() => send(failed)}
              className="mt-1 font-medium text-turquoise-700 underline underline-offset-2">
              {t.comparison.chatRetry}
            </button>
          </div>
        )}
      </div>
      <div className="flex items-center gap-1 bg-white rounded-md pl-3 pr-1.5 py-1">
        <input value={chat} onChange={(e) => setChat(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send(chat)}
          placeholder={t.comparison.placeholder}
          className="flex-1 outline-none text-sm py-2" />
        {/* Separate, comfortably-sized tap targets: a divider keeps the mic clear of the
            send arrow so they're not mis-tapped on mobile. */}
        <span className="w-px h-6 bg-turquoise-100 mx-1" aria-hidden="true" />
        <VoiceButton
          className="inline-flex items-center justify-center w-10 h-10 rounded-full transition hover:bg-turquoise-50 disabled:opacity-40"
          onTranscript={(text) => setChat((c) => (c.trim() ? `${c.trim()} ${text}` : text))} />
        <button onClick={() => send(chat)} disabled={chatBusy} aria-label={t.comparison.send}
          className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-turquoise-600 text-turquoise-50 text-lg disabled:opacity-40">→</button>
      </div>
    </div>
  )
}
