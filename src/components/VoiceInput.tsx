// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useState } from 'react'

import { API_URL } from '../services/api'

interface Props {
  onTranscript: (text: string) => void
  label?: string
}

// Records mic audio and posts it to /voice/transcribe. Falls back gracefully if the
// backend transcription is not yet wired (returns an error the caller can ignore).
export function VoiceInput({ onTranscript, label }: Props) {
  const [recording, setRecording] = useState(false)
  const [recorder, setRecorder] = useState<MediaRecorder | null>(null)

  async function start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mr = new MediaRecorder(stream)
    const chunks: Blob[] = []
    mr.ondataavailable = (e) => chunks.push(e.data)
    mr.onstop = async () => {
      stream.getTracks().forEach((tr) => tr.stop())
      const blob = new Blob(chunks, { type: 'audio/webm' })
      const form = new FormData()
      form.append('audio', blob, 'audio.webm')
      try {
        const res = await fetch(`${API_URL}/api/v1/voice/transcribe`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${localStorage.getItem('xcape_token')}` },
          body: form,
        })
        if (res.ok) onTranscript((await res.json()).text)
      } catch {
        // transcription not available yet — silently ignore
      }
    }
    mr.start()
    setRecorder(mr)
    setRecording(true)
  }

  function stop() {
    recorder?.stop()
    setRecording(false)
  }

  return (
    <button
      type="button"
      onClick={recording ? stop : start}
      className="flex items-center gap-2 text-turquoise-600 text-sm"
      aria-label={label ?? 'voice input'}
    >
      <span className={recording ? 'text-red-600' : ''}>●</span>
      {label}
    </button>
  )
}
