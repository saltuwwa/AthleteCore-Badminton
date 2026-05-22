import axios from 'axios'
import { useCallback, useEffect, useRef, useState } from 'react'
import { transcribeAudio } from '../api/transcribe'

const transcribeErrorMessage = (err: unknown): string => {
  if (axios.isAxiosError(err)) {
    if (!err.response) {
      return 'Backend недоступен. Запусти: cd backend && uvicorn app.main:app --reload --port 8000'
    }
    const detail = err.response.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ') || err.message
    }
    return `Ошибка ${err.response.status}: ${err.message}`
  }
  return err instanceof Error ? err.message : 'Ошибка транскрипции'
}

export type VoiceRecorderState = {
  isRecording: boolean
  isTranscribing: boolean
  seconds: number
  transcriptNote: string
  error: string | null
  startRecording: () => Promise<void>
  stopRecording: () => Promise<string | null>
  toggleRecording: () => Promise<void>
}

const formatTime = (sec: number) => {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export const useVoiceRecorder = (): VoiceRecorderState => {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [transcriptNote, setTranscriptNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<number | null>(null)

  const cleanupStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => () => cleanupStream(), [cleanupStream])

  const startRecording = useCallback(async () => {
    setError(null)
    setTranscriptNote('')
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Микрофон недоступен в этом браузере')
      return
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    streamRef.current = stream
    chunksRef.current = []

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm'

    const recorder = new MediaRecorder(stream, { mimeType })
    mediaRecorderRef.current = recorder

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }

    recorder.start(250)
    setIsRecording(true)
    setSeconds(0)
    timerRef.current = window.setInterval(() => setSeconds((s) => s + 1), 1000)
  }, [])

  const stopRecording = useCallback(async (): Promise<string | null> => {
    const recorder = mediaRecorderRef.current
    if (!recorder || recorder.state === 'inactive') {
      cleanupStream()
      setIsRecording(false)
      return null
    }

    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () => {
        const type = recorder.mimeType || 'audio/webm'
        resolve(new Blob(chunksRef.current, { type }))
      }
      recorder.stop()
    })

    cleanupStream()
    setIsRecording(false)
    mediaRecorderRef.current = null

    if (blob.size < 1000) {
      setError('Запись слишком короткая')
      return null
    }

    setIsTranscribing(true)
    try {
      const result = await transcribeAudio(blob)
      const text = (result?.text ?? '').trim()
      if (!text) {
        setError('Не удалось распознать речь')
        return null
      }
      const dur = result.duration_sec ?? seconds
      setTranscriptNote(`Голосовой лог · ${formatTime(Math.round(dur))}`)
      return text
    } catch (err) {
      setError(transcribeErrorMessage(err))
      return null
    } finally {
      setIsTranscribing(false)
    }
  }, [cleanupStream, seconds])

  const toggleRecording = useCallback(async () => {
    if (isTranscribing) return
    if (isRecording) {
      await stopRecording()
      return
    }
    await startRecording()
  }, [isRecording, isTranscribing, startRecording, stopRecording])

  return {
    isRecording,
    isTranscribing,
    seconds,
    transcriptNote,
    error,
    startRecording,
    stopRecording,
    toggleRecording,
  }
}
