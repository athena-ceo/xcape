// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useRef, useState } from 'react'

import { API_URL } from '../services/api'

interface Props {
  onTranscript: (text: string) => void
  title?: string
  className?: string
}

// Standard microphone icon (Tabler "microphone" outline). Filled red while recording.
function MicIcon({ recording }: { recording: boolean }) {
  return (
    <svg
      width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M9 2m0 3a3 3 0 0 1 3 -3a3 3 0 0 1 3 3v5a3 3 0 0 1 -3 3a3 3 0 0 1 -3 -3z"
        fill={recording ? 'currentColor' : 'none'} />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <path d="M8 21l8 0" />
      <path d="M12 17l0 4" />
    </svg>
  )
}

// A microphone toggle that records mic audio and posts it to /voice/transcribe,
// calling onTranscript with the recognised text. Always pair this next to a text
// input so there is never voice-only entry.
export function VoiceButton({ onTranscript, title, className }: Props) {
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const recorderRef = useRef<MediaRecorder | null>(null)

  async function start() {
    if (busy) return
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mr = new MediaRecorder(stream)
    const chunks: Blob[] = []
    mr.ondataavailable = (e) => chunks.push(e.data)
    mr.onstop = async () => {
      stream.getTracks().forEach((tr) => tr.stop())
      setBusy(true)
      try {
        const form = new FormData()
        form.append('audio', new Blob(chunks, { type: 'audio/webm' }), 'audio.webm')
        const res = await fetch(`${API_URL}/api/v1/voice/transcribe`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${localStorage.getItem('xcape_token')}` },
          body: form,
        })
        if (res.ok) {
          const text = (await res.json()).text?.trim()
          if (text) onTranscript(text)
        }
      } catch {
        // transcription unavailable — ignore, text input still works
      } finally {
        setBusy(false)
      }
    }
    mr.start()
    recorderRef.current = mr
    setRecording(true)
  }

  function stop() {
    recorderRef.current?.stop()
    setRecording(false)
  }

  return (
    <button
      type="button"
      onClick={recording ? stop : start}
      disabled={busy}
      aria-label={title ?? 'Voice input'}
      aria-pressed={recording}
      title={title ?? 'Voice input'}
      className={
        className ??
        `inline-flex items-center justify-center transition disabled:opacity-40 ${
          recording ? 'text-red-600 animate-pulse' : 'text-turquoise-600 hover:text-turquoise-800'
        }`
      }
    >
      <MicIcon recording={recording} />
    </button>
  )
}
