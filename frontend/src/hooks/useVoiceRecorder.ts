import { useCallback, useEffect, useRef, useState } from 'react'
import { transcribeAudio } from '../api/transcribe'
import { idleWaveformLevels } from '../components/chat/RecordingWaveform'

const BAR_COUNT = 28

export type VoiceRecorderState = {
  isRecording: boolean
  isTranscribing: boolean
  seconds: number
  error: string | null
  audioLevels: number[]
  useLevelFallback: boolean
  startRecording: () => Promise<void>
  stopRecording: () => Promise<string | null>
  toggleRecording: () => Promise<void>
}

const emptyLevels = () => idleWaveformLevels()

export const useVoiceRecorder = (): VoiceRecorderState => {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [audioLevels, setAudioLevels] = useState<number[]>(emptyLevels)
  const [useLevelFallback, setUseLevelFallback] = useState(false)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<number | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const rafRef = useRef<number | null>(null)
  const lowLevelSinceRef = useRef<number | null>(null)

  const stopLevelMonitor = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    analyserRef.current = null
    if (audioContextRef.current) {
      void audioContextRef.current.close().catch(() => undefined)
      audioContextRef.current = null
    }
    lowLevelSinceRef.current = null
    setAudioLevels(emptyLevels())
    setUseLevelFallback(false)
  }, [])

  const cleanupStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    stopLevelMonitor()
  }, [stopLevelMonitor])

  useEffect(() => () => cleanupStream(), [cleanupStream])

  const startLevelMonitor = useCallback((stream: MediaStream) => {
    try {
      const ctx = new AudioContext()
      const source = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 128
      analyser.smoothingTimeConstant = 0.72
      source.connect(analyser)
      audioContextRef.current = ctx
      analyserRef.current = analyser

      const data = new Uint8Array(analyser.frequencyBinCount)
      const step = Math.max(1, Math.floor(data.length / BAR_COUNT))

      const tick = () => {
        analyser.getByteFrequencyData(data)
        let peak = 0
        const next = Array.from({ length: BAR_COUNT }, (_, i) => {
          let sum = 0
          const start = i * step
          for (let j = 0; j < step && start + j < data.length; j++) {
            sum += data[start + j] ?? 0
          }
          const avg = sum / step / 255
          const level = Math.max(0.12, Math.min(1, avg * 2.2 + 0.06))
          peak = Math.max(peak, level)
          return level
        })

        const now = performance.now()
        if (peak < 0.2) {
          if (lowLevelSinceRef.current === null) lowLevelSinceRef.current = now
          setUseLevelFallback(now - (lowLevelSinceRef.current ?? now) > 700)
        } else {
          lowLevelSinceRef.current = null
          setUseLevelFallback(false)
        }

        if (peak < 0.2 && now - (lowLevelSinceRef.current ?? now) > 700) {
          const t = now / 220
          setAudioLevels(
            next.map((_, i) => 0.16 + 0.14 * Math.abs(Math.sin(t + i * 0.45))),
          )
        } else {
          setAudioLevels(next)
        }

        rafRef.current = requestAnimationFrame(tick)
      }

      rafRef.current = requestAnimationFrame(tick)
    } catch {
      setUseLevelFallback(true)
      const animate = () => {
        const t = performance.now() / 220
        setAudioLevels(
          Array.from({ length: BAR_COUNT }, (_, i) => 0.16 + 0.14 * Math.abs(Math.sin(t + i * 0.45))),
        )
        rafRef.current = requestAnimationFrame(animate)
      }
      rafRef.current = requestAnimationFrame(animate)
    }
  }, [])

  const startRecording = useCallback(async () => {
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Микрофон недоступен в этом браузере')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []
      startLevelMonitor(stream)

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
    } catch {
      cleanupStream()
      setError('Не удалось получить доступ к микрофону')
      setIsRecording(false)
    }
  }, [cleanupStream, startLevelMonitor])

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
        setError('Не удалось распознать голос')
        return null
      }
      return text
    } catch {
      setError('Не удалось распознать голос')
      return null
    } finally {
      setIsTranscribing(false)
    }
  }, [cleanupStream])

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
    error,
    audioLevels,
    useLevelFallback,
    startRecording,
    stopRecording,
    toggleRecording,
  }
}
