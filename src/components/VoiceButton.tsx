// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useRef, useState } from 'react'

import { useT } from '../i18n'
import { API_URL } from '../services/api'

interface Props {
  onTranscript: (text: string) => void
  title?: string
  className?: string
}

// Pick a recording format the browser actually supports. iOS Safari/WebKit (and so every
// iOS browser, incl. "Firefox") can't produce webm — it records mp4/aac — so we must
// negotiate rather than assume webm, and upload with a matching extension so the AI
// provider can decode it.
const MIME_CANDIDATES = [
  'audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac', 'audio/mpeg',
  'audio/ogg;codecs=opus',
]
function pickMimeType(): string | undefined {
  const MR = typeof MediaRecorder !== 'undefined' ? MediaRecorder : undefined
  if (!MR || typeof MR.isTypeSupported !== 'function') return undefined
  return MIME_CANDIDATES.find((c) => MR.isTypeSupported(c))
}
function extForMime(mime: string): string {
  if (mime.includes('webm')) return 'webm'
  if (mime.includes('mp4')) return 'mp4'
  if (mime.includes('aac')) return 'm4a'
  if (mime.includes('mpeg')) return 'mp3'
  if (mime.includes('ogg')) return 'ogg'
  return 'webm'
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
  const { t } = useT()
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)

  function fail(message: string) {
    console.error('[voice]', message)
    setError(message)
    setTimeout(() => setError(null), 4000)
  }

  async function start() {
    if (busy) return
    setError(null)
    // Mobile browsers only expose getUserMedia in a SECURE context (https or localhost). Over a
    // plain-http LAN address (e.g. http://192.168.x.x:3030 on a phone) `navigator.mediaDevices`
    // is undefined — surface that explicitly instead of the generic "mic blocked", which is the
    // usual reason voice "doesn't work on mobile" while it works on a desktop at localhost.
    if (!navigator.mediaDevices?.getUserMedia) {
      fail(window.isSecureContext ? t.voice.unsupported : t.voice.insecure)
      return
    }
    if (typeof MediaRecorder === 'undefined') {
      fail(t.voice.unsupported)
      return
    }
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      // Log the real error name (NotAllowedError, NotFoundError, …) so mobile failures are
      // diagnosable from the console even though the user-facing hint stays simple.
      console.error('[voice] getUserMedia', (e as Error)?.name, e)
      fail(t.voice.micBlocked)
      return
    }
    const mime = pickMimeType()
    let mr: MediaRecorder
    try {
      mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
    } catch {
      mr = new MediaRecorder(stream)
    }
    const chunks: Blob[] = []
    mr.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
    mr.onstop = async () => {
      stream.getTracks().forEach((tr) => tr.stop())
      setBusy(true)
      try {
        const token = localStorage.getItem('xcape_token')
        if (!token) {
          fail(t.voice.needAuth)
          return
        }
        // Use the format the browser actually recorded in (mr.mimeType), so the upload
        // extension matches the bytes — critical on iOS, which records mp4 not webm.
        const actual = mr.mimeType || mime || 'audio/webm'
        if (!chunks.length) { fail(t.voice.noSpeech); return }
        const form = new FormData()
        form.append('audio', new Blob(chunks, { type: actual }), `audio.${extForMime(actual)}`)
        const res = await fetch(`${API_URL}/api/v1/voice/transcribe`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: form,
        })
        if (!res.ok) {
          const detail = await res.json().catch(() => ({}))
          fail(`${t.voice.failed} (${res.status}). ${detail.detail ?? ''}`.trim())
          return
        }
        const text = (await res.json()).text?.trim()
        if (text) onTranscript(text)
        else fail(t.voice.noSpeech)
      } catch (e) {
        fail(e instanceof Error ? e.message : t.voice.failed)
      } finally {
        setBusy(false)
      }
    }
    // Record WITHOUT a timeslice. On iOS Safari, MediaRecorder.start(timeslice) emits fragmented
    // mp4 chunks that don't reassemble into a decodable file (the combined Blob lacks a proper
    // moov atom), so the upload transcribes to nothing — the main reason voice failed on iPhones.
    // With no timeslice, ondataavailable fires once on stop with a single, finalised file that
    // every browser (incl. iOS) can decode.
    mr.start()
    recorderRef.current = mr
    setRecording(true)
  }

  function stop() {
    recorderRef.current?.stop()
    setRecording(false)
  }

  const color = error
    ? 'text-red-500'
    : recording
      ? 'text-red-600 animate-pulse'
      : 'text-turquoise-600 hover:text-turquoise-800'

  return (
    <button
      type="button"
      onClick={recording ? stop : start}
      disabled={busy}
      aria-label={error ?? title ?? t.voice.label}
      aria-pressed={recording}
      title={error ?? title ?? t.voice.label}
      className={`${className ?? 'inline-flex items-center justify-center transition disabled:opacity-40'} ${color}`}
    >
      <MicIcon recording={recording} />
    </button>
  )
}
