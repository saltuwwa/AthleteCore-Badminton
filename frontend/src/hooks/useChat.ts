import axios from 'axios'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { sendMessage } from '../api/chat'
import {
  agentLabel,
  mapAnalysisToMessage,
  mapAnalysisToRows,
  mapChatActions,
  mapStructuredAnalysis,
} from '../lib/chatMappers'
import {
  clearChatHistory,
  loadChatHistory,
  saveChatHistory,
} from '../lib/chatHistoryStorage'
import { stripAnalysisJsonFromText } from '../lib/stripAnalysisJson'
import type { AnalysisErrorRow } from '../lib/chatMappers'
import type { ChatMessage } from '../types'

const THREAD_KEY = 'athletecore-thread-id'

export type UseChatOptions = {
  /** Persist visible messages to localStorage (Chat page only). */
  persistHistory?: boolean
}

const chatErrorMessage = (err: unknown): string => {
  if (axios.isAxiosError(err)) {
    if (!err.response) {
      return (
        'Backend недоступен. Запусти из папки backend:\n' +
        'uvicorn app.main:app --reload --port 8001\n' +
        '(на Windows порт 8000 часто занят — используй 8001 и VITE_API_PROXY_TARGET в frontend/.env)'
      )
    }
    const detail = err.response.data?.detail
    if (typeof detail === 'string') return detail
    return `Ошибка сервера (${err.response.status})`
  }
  return err instanceof Error ? err.message : 'Неизвестная ошибка'
}

export const welcomeMessage = (): ChatMessage => {
  const now = new Date()
  const ts = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  return {
    id: 'welcome',
    role: 'ai',
    agentLabel: 'ATHLETE CORE',
    timestamp: ts,
    content:
      'Опиши матч или тренировку — Analyst подключит память только когда это нужно (не для погоды или переноса одного события в календаре).',
  }
}

const initialMessages = (persistHistory: boolean): ChatMessage[] => {
  if (persistHistory) {
    const restored = loadChatHistory()
    if (restored?.length) {
      return restored
    }
  }
  return [welcomeMessage()]
}

export const useChat = (options?: UseChatOptions) => {
  const persistHistory = options?.persistHistory ?? false

  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    initialMessages(persistHistory),
  )
  const [isSending, setIsSending] = useState(false)
  const [threadId, setThreadId] = useState<string | null>(() => sessionStorage.getItem(THREAD_KEY))
  const [needsMemory, setNeedsMemory] = useState<boolean | null>(null)
  const [lastAgents, setLastAgents] = useState<string[]>([])
  const [analysisRows, setAnalysisRows] = useState<AnalysisErrorRow[]>([])

  useEffect(() => {
    if (!persistHistory) return
    saveChatHistory(messages)
  }, [messages, persistHistory])

  const clearChat = useCallback(() => {
    if (persistHistory) {
      clearChatHistory()
    }
    try {
      sessionStorage.removeItem(THREAD_KEY)
    } catch {
      // ignore
    }
    setMessages([welcomeMessage()])
    setThreadId(null)
    setNeedsMemory(null)
    setLastAgents([])
    setAnalysisRows([])
    setIsSending(false)
  }, [persistHistory])

  const addAiMessage = useCallback((content: string) => {
    const trimmed = content.trim()
    if (!trimmed) return
    const now = new Date()
    const ts = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'ai',
        agentLabel: 'ТУРНИР · документ',
        timestamp: ts,
        content: trimmed,
      },
    ])
  }, [])

  const send = useCallback(async (text: string) => {
    if (!text.trim() || isSending) return
    const now = new Date()
    const hh = String(now.getHours()).padStart(2, '0')
    const mm = String(now.getMinutes()).padStart(2, '0')
    const ts = `${hh}:${mm}`

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      agentLabel: 'YOU',
      timestamp: ts,
      content: text,
    }
    const processingId = crypto.randomUUID()
    const processingMessage: ChatMessage = {
      id: processingId,
      role: 'ai',
      agentLabel: 'ROUTING…',
      timestamp: ts,
      processing: true,
    }

    setMessages((prev) => [...prev, userMessage, processingMessage])
    setIsSending(true)

    const sendClickedAt = performance.now()
    const requestStartAt = performance.now()

    try {
      const response = await sendMessage(text, { threadId: threadId ?? undefined })
      const responseReceivedAt = performance.now()
      if (response.thread_id) {
        setThreadId(response.thread_id)
        sessionStorage.setItem(THREAD_KEY, response.thread_id)
      }
      setNeedsMemory(response.needs_memory)
      setLastAgents(response.agents_used ?? [])
      setAnalysisRows(
        response.comparison_status === 'not_found' ? [] : mapAnalysisToRows(response.analysis),
      )

      const label = agentLabel(response.agents_used)
      const blockedNotFound = response.comparison_status === 'not_found'
      const structured = blockedNotFound ? undefined : mapStructuredAnalysis(response.analysis)
      const analysis = structured ? undefined : mapAnalysisToMessage(response.analysis)
      const visibleMessage =
        structured || blockedNotFound
          ? response.message
          : response.analysis
            ? stripAnalysisJsonFromText(response.message)
            : response.message

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === processingId
            ? {
                ...msg,
                processing: false,
                agentLabel: label,
                content: visibleMessage,
                analysis,
                structured,
                chatActions: mapChatActions(response.chat_actions),
                comparisonStatus: response.comparison_status ?? undefined,
              }
            : msg,
        ),
      )

      const renderDoneAt = performance.now()
      const clientTotalMs = Math.round(renderDoneAt - sendClickedAt)
      const backendTotalMs = response.latency_trace?.total_ms
      const networkPlusRenderMs =
        backendTotalMs != null
          ? Math.round(clientTotalMs - backendTotalMs)
          : Math.round(responseReceivedAt - requestStartAt)

      if (import.meta.env.DEV) {
        console.log('[chat latency]', {
          request_id: response.latency_trace?.request_id ?? null,
          backend_total_ms: backendTotalMs ?? null,
          client_total_ms: clientTotalMs,
          network_plus_render_ms: networkPlusRenderMs,
          send_clicked_at: sendClickedAt,
          request_start: requestStartAt,
          response_received: responseReceivedAt,
          render_done: renderDoneAt,
        })
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === processingId
            ? {
                ...msg,
                processing: false,
                agentLabel: 'SYSTEM',
                content: chatErrorMessage(err),
              }
            : msg,
        ),
      )
      setNeedsMemory(null)
    } finally {
      setIsSending(false)
    }
  }, [isSending, threadId])

  return useMemo(
    () => ({
      messages,
      send,
      isSending,
      threadId,
      needsMemory,
      lastAgents,
      analysisRows,
      addAiMessage,
      clearChat,
    }),
    [messages, send, isSending, threadId, needsMemory, lastAgents, analysisRows, addAiMessage, clearChat],
  )
}
