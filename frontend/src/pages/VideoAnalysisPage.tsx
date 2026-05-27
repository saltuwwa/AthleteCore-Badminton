import { motion } from 'framer-motion'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  analyzeVideo,
  detectPlayers,
  uploadVideo,
  type AnalyzeVideoResponse,
  type DetectedPlayer,
  type MatchType,
} from '../api/video'
import { MemoryModal } from '../components/video/MemoryModal'
import { StepRail } from '../components/video/StepRail'

const MAX_MB = 250
const HINT_DURATION_MIN = 7

type MatchOption = { id: MatchType; label: string }

const MATCH_OPTIONS: MatchOption[] = [
  { id: 'singles', label: 'Одиночка' },
  { id: 'doubles', label: 'Парная' },
  { id: 'mixed', label: 'Микст' },
]

const ANALYZE_MESSAGES = [
  'Считаем скорость…',
  'Сравниваем с прошлым…',
  'Готовим фидбэк…',
] as const

function formatSpeed(v: number | undefined) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(0)}%`
}

function formatAttack(ratio: number | undefined) {
  if (ratio == null) return '—'
  return `${Math.round(ratio * 100)}%`
}

function formatFatigue(minute: number | null | undefined) {
  if (minute == null) return 'Норма'
  return `~${minute} мин`
}

export const VideoAnalysisPage = () => {
  const fileRef = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<0 | 1 | 2>(0)
  const [memoryOpen, setMemoryOpen] = useState(false)

  const [file, setFile] = useState<File | null>(null)
  const [videoId, setVideoId] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  const [players, setPlayers] = useState<DetectedPlayer[]>([])
  const [preview, setPreview] = useState<string | null>(null)
  const [detecting, setDetecting] = useState(false)
  const [detectError, setDetectError] = useState<string | null>(null)

  const [matchType, setMatchType] = useState<MatchType>('singles')
  const [selectedIds, setSelectedIds] = useState<number[]>([])

  const [loadingMsg, setLoadingMsg] = useState<string | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalyzeVideoResponse | null>(null)

  const requiredCount = matchType === 'singles' ? 1 : 2

  const runDetect = useCallback(async (id: string) => {
    setDetecting(true)
    setDetectError(null)
    try {
      const res = await detectPlayers(id)
      setPlayers(res.players)
      setPreview(res.preview_frame_base64)
      if (res.players.length > 0) {
        setSelectedIds([res.players[0].track_id])
      }
    } catch (e) {
      setDetectError(e instanceof Error ? e.message : 'Не удалось найти игроков')
    } finally {
      setDetecting(false)
    }
  }, [])

  useEffect(() => {
    if (step === 1 && videoId && players.length === 0 && !detecting && !detectError) {
      void runDetect(videoId)
    }
  }, [step, videoId, players.length, detecting, detectError, runDetect])

  const onPickFile = async (f: File) => {
    setUploadError(null)
    if (f.size > MAX_MB * 1024 * 1024) {
      setUploadError(`Файл больше ${MAX_MB} МБ`)
      return
    }
    setFile(f)
    setUploading(true)
    try {
      const res = await uploadVideo(f)
      setVideoId(res.video_id)
      setStep(1)
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Ошибка загрузки')
      setFile(null)
    } finally {
      setUploading(false)
    }
  }

  const togglePlayer = (tid: number) => {
    if (matchType === 'singles') {
      setSelectedIds([tid])
      return
    }
    setSelectedIds((prev) => {
      if (prev.includes(tid)) return prev.filter((x) => x !== tid)
      if (prev.length >= 2) return [prev[1], tid]
      return [...prev, tid]
    })
  }

  const runAnalyze = async () => {
    if (!videoId || selectedIds.length < requiredCount) return
    setAnalyzing(true)
    setAnalyzeError(null)
    setLoadingMsg(ANALYZE_MESSAGES[0])
    const timers = [
      window.setTimeout(() => setLoadingMsg(ANALYZE_MESSAGES[1]), 4000),
      window.setTimeout(() => setLoadingMsg(ANALYZE_MESSAGES[2]), 9000),
    ]
    try {
      const res = await analyzeVideo({
        video_id: videoId,
        match_type: matchType,
        target_track_ids: matchType === 'singles' ? [selectedIds[0]] : selectedIds.slice(0, 2),
      })
      setResult(res)
      setStep(2)
    } catch (e) {
      setAnalyzeError(e instanceof Error ? e.message : 'Ошибка анализа')
    } finally {
      timers.forEach(clearTimeout)
      setAnalyzing(false)
      setLoadingMsg(null)
    }
  }

  const primary = result?.metrics.singles ?? result?.metrics.doubles?.players?.[0]
  const mem = result?.memory_summary
  const segRatio = result?.metrics.raw_notes?.gameplay_segment_ratio
  const segWarning = result?.metrics.raw_notes?.segment_warning
  const excludedRepeatsAndPauses = result?.metrics.raw_notes?.excluded_replays_and_pauses

  return (
    <div className="thin-scrollbar flex h-full flex-col overflow-y-auto">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--border)] px-6 py-5 sm:px-8">
        <div>
          <Link
            to="/analysis"
            className="label-mono text-[10px] text-[var(--muted)] transition hover:text-[var(--accent)]"
          >
            ← Анализ
          </Link>
          <h1 className="font-display mt-1 text-[28px] leading-tight tracking-tight sm:text-[32px]">
            Разбор видео
          </h1>
        </div>
        <StepRail current={step} />
      </header>

      <div className="mx-auto w-full max-w-3xl flex-1 px-6 py-8 sm:px-8">
        {step === 0 && (
          <motion.section
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-8 backdrop-blur-sm"
          >
            <h2 className="font-display text-[22px] tracking-tight">Загрузи видео матча</h2>
            <p className="mt-1 text-[13px] text-[var(--muted2)]">
              MP4, MOV или WEBM · до {HINT_DURATION_MIN} минут
            </p>
            <p className="mt-4 text-[12px] text-[var(--muted)]">
              Мы анализируем движение, скорость и игровые паттерны.
            </p>

            <input
              ref={fileRef}
              type="file"
              accept="video/mp4,video/quicktime,video/webm,video/x-msvideo,.mp4,.mov,.webm,.avi"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void onPickFile(f)
              }}
            />

            <button
              type="button"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
              className="mt-8 w-full rounded-xl bg-[var(--accent)] py-3.5 text-[14px] font-semibold text-white transition hover:brightness-110 disabled:opacity-60"
            >
              {uploading ? 'Загружаем…' : 'Выбрать видео'}
            </button>

            {file && (
              <p className="mt-3 text-center font-mono-ui text-[11px] text-[var(--muted2)]">
                {file.name}
              </p>
            )}
            {uploadError && (
              <p className="mt-3 text-center text-[12px] text-[var(--accent3)]">{uploadError}</p>
            )}
          </motion.section>
        )}

        {step === 1 && (
          <motion.section
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-6"
          >
            {detecting && (
              <div className="flex items-center justify-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] py-8">
                <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--accent)]" />
                <span className="text-[13px] text-[var(--muted2)]">Ищем игроков…</span>
              </div>
            )}

            {detectError && (
              <div className="rounded-xl border border-[var(--accent3)]/40 bg-[var(--accent3)]/10 p-4 text-[13px]">
                {detectError}
                <button
                  type="button"
                  className="mt-2 block text-[var(--accent)]"
                  onClick={() => videoId && void runDetect(videoId)}
                >
                  Повторить
                </button>
              </div>
            )}

            {preview && !detecting && (
              <div className="overflow-hidden rounded-2xl border border-[var(--border)]">
                <img src={preview} alt="Кадр с игроками" className="w-full object-cover" />
              </div>
            )}

            <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-6">
              <h3 className="font-display text-[18px]">Тип игры</h3>
              <div className="mt-4 flex flex-wrap gap-2">
                {MATCH_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => {
                      setMatchType(opt.id)
                      setSelectedIds((prev) => prev.slice(0, opt.id === 'singles' ? 1 : 2))
                    }}
                    className={`rounded-lg border px-4 py-2 text-[13px] transition ${
                      matchType === opt.id
                        ? 'border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--text-primary)]'
                        : 'border-[var(--border)] text-[var(--muted2)] hover:border-[var(--border-strong)]'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {players.length > 0 && !detecting && (
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-6">
                <h3 className="font-display text-[18px]">
                  {matchType === 'singles' ? 'Кого анализировать?' : 'Выбери свою команду'}
                </h3>
                <p className="mt-1 text-[12px] text-[var(--muted)]">
                  {matchType === 'singles'
                    ? 'Один игрок на корте'
                    : 'Два игрока — ваша пара'}
                </p>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {players.map((p) => {
                    const on = selectedIds.includes(p.track_id)
                    return (
                      <button
                        key={p.track_id}
                        type="button"
                        onClick={() => togglePlayer(p.track_id)}
                        className={`rounded-xl border px-4 py-3 text-left transition ${
                          on
                            ? 'border-[var(--accent2)] bg-[var(--accent2)]/10'
                            : 'border-[var(--border)] hover:border-[var(--border-strong)]'
                        }`}
                      >
                        <span className="font-display text-[15px]">{p.label}</span>
                        <span className="mt-0.5 block font-mono-ui text-[10px] text-[var(--muted)]">
                          ID {p.track_id}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {(analyzing || loadingMsg) && (
              <div className="flex items-center justify-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] py-6">
                <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--accent2)]" />
                <span className="text-[13px] text-[var(--muted2)]">{loadingMsg}</span>
              </div>
            )}

            {analyzeError && (
              <p className="text-center text-[12px] text-[var(--accent3)]">{analyzeError}</p>
            )}

            <button
              type="button"
              disabled={
                detecting ||
                analyzing ||
                selectedIds.length < requiredCount ||
                !videoId
              }
              onClick={() => void runAnalyze()}
              className="w-full rounded-xl bg-[var(--accent2)] py-3.5 text-[14px] font-semibold text-[var(--bg)] transition hover:brightness-105 disabled:opacity-50"
            >
              Получить разбор
            </button>
          </motion.section>
        )}

        {step === 2 && result && (
          <motion.section
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-6"
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <MetricTile
                label="Скорость"
                value={formatSpeed(primary?.relative_movement_speed_avg)}
                hint={result.coaching_feedback.speed_trend.slice(0, 40)}
              />
              <MetricTile
                label="Усталость"
                value={formatFatigue(primary?.possible_fatigue_minute)}
                hint={
                  result.coaching_feedback.possible_fatigue_moment?.slice(0, 36) ?? 'Без явного спада'
                }
              />
              <MetricTile
                label="Атака"
                value={formatAttack(primary?.attack_like_ratio)}
                hint="По видимому движению"
              />
              <MetricTile
                label="Память"
                value={mem ? String(mem.past_video_count) : '0'}
                hint="Прошлых разборов"
              />
            </div>

            {segRatio != null ? (
              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3">
                <p className="font-mono-ui text-[11px] text-[var(--muted)]">
                  Проанализировано игровых моментов: {Math.round(segRatio * 100)}%
                </p>
                <p className="mt-1 text-[12px] text-[var(--text-soft)]">
                  {excludedRepeatsAndPauses ? 'Повторы и паузы исключены' : 'Повторы и паузы не найдены'}
                </p>
                {segWarning ? (
                  <p className="mt-1 text-[12px] text-[var(--accent3)]">{segWarning}</p>
                ) : null}
              </div>
            ) : null}

            <ResultBlock title="Главный вывод">
              <p className="text-[14px] leading-relaxed text-[var(--text-soft)]">
                {result.coaching_feedback.short_summary}
              </p>
            </ResultBlock>

            <ResultBlock title="Timeline">
              <ul className="space-y-2">
                {result.coaching_feedback.key_timeline_moments.map((t, i) => (
                  <li
                    key={i}
                    className="flex gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[13px]"
                  >
                    <span className="font-mono-ui text-[10px] text-[var(--accent)]">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span className="text-[var(--text-soft)]">{t}</span>
                  </li>
                ))}
              </ul>
            </ResultBlock>

            <ResultBlock title="Рекомендации">
              <ul className="space-y-2">
                {result.coaching_feedback.coaching_recommendations.map((r, i) => (
                  <li key={i} className="text-[13px] text-[var(--text-soft)]">
                    · {r}
                  </li>
                ))}
              </ul>
              <p className="mt-4 rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-3 py-2 text-[12px]">
                <span className="font-semibold text-[var(--accent-strong)]">Упражнение: </span>
                {result.coaching_feedback.drill_for_next_training}
              </p>
            </ResultBlock>

            <ResultBlock title="Паттерны">
              <div className="grid gap-3 sm:grid-cols-2">
                <PatternCard
                  title="Повторяется"
                  items={
                    result.coaching_feedback.repeated_mistakes.length
                      ? result.coaching_feedback.repeated_mistakes
                      : mem?.repeated_patterns ?? []
                  }
                  empty="Пока без повторов"
                />
                <PatternCard
                  title="Прогресс"
                  items={
                    result.coaching_feedback.improvements_noted.length
                      ? result.coaching_feedback.improvements_noted
                      : mem?.improvement_patterns ?? []
                  }
                  empty="Соберём после нескольких игр"
                />
                <PatternCard
                  title="Фокус недели"
                  items={
                    result.coaching_feedback.next_training_focus
                      ? [result.coaching_feedback.next_training_focus]
                      : []
                  }
                  empty="Следуй рекомендациям выше"
                />
                <PatternCard
                  title="Похожие видео"
                  items={
                    mem && mem.past_video_count > 0
                      ? [`Сравнили с ${mem.past_video_count} прошлыми разборами`]
                      : []
                  }
                  empty="Первый разбор — сравнение появится позже"
                />
              </div>
              {result.coaching_feedback.regressions_noted.length > 0 && (
                <div className="mt-3 rounded-lg border border-[var(--accent3)]/30 bg-[var(--accent3)]/8 px-3 py-2">
                  <p className="label-mono text-[10px] text-[var(--accent3)]">На что обратить внимание</p>
                  <ul className="mt-1 space-y-1">
                    {result.coaching_feedback.regressions_noted.map((r, i) => (
                      <li key={i} className="text-[12px] text-[var(--text-soft)]">
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </ResultBlock>

            <div className="flex flex-wrap gap-3 pt-2">
              <button
                type="button"
                onClick={() => {
                  setStep(0)
                  setFile(null)
                  setVideoId(null)
                  setPlayers([])
                  setPreview(null)
                  setResult(null)
                  setSelectedIds([])
                }}
                className="rounded-xl border border-[var(--border)] px-5 py-2.5 text-[13px] hover:border-[var(--accent)]"
              >
                Новое видео
              </button>
              <Link
                to="/chat"
                className="rounded-xl bg-[var(--accent)] px-5 py-2.5 text-[13px] font-semibold text-white"
              >
                Обсудить в чате
              </Link>
            </div>
          </motion.section>
        )}
      </div>

      <footer className="mt-auto border-t border-[var(--border)] px-6 py-4 sm:px-8">
        <p className="text-center text-[11px] text-[var(--muted)]">
          Видео используется только для анализа. В историю сохраняются метрики и выводы, не сам
          файл.{' '}
          <button
            type="button"
            onClick={() => setMemoryOpen(true)}
            className="text-[var(--accent)] underline-offset-2 hover:underline"
          >
            Как работает память?
          </button>
        </p>
      </footer>

      <MemoryModal open={memoryOpen} onClose={() => setMemoryOpen(false)} />
    </div>
  )
}

function MetricTile({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint: string
}) {
  return (
    <article className="rounded-xl border border-[var(--border)] bg-[var(--surface-glass)] p-4 backdrop-blur-sm">
      <p className="font-mono-ui text-[10px] uppercase tracking-wide text-[var(--muted)]">
        {label}
      </p>
      <p className="font-display mt-1 text-[26px] leading-none tracking-tight">{value}</p>
      <p className="mt-2 line-clamp-2 text-[10px] text-[var(--muted)]">{hint}</p>
    </article>
  )
}

function ResultBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
      <h3 className="font-display text-[17px] tracking-tight">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  )
}

function PatternCard({
  title,
  items,
  empty,
}: {
  title: string
  items: string[]
  empty: string
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
      <p className="font-mono-ui text-[10px] uppercase text-[var(--muted)]">{title}</p>
      {items.length === 0 ? (
        <p className="mt-2 text-[12px] text-[var(--muted2)]">{empty}</p>
      ) : (
        <ul className="mt-2 space-y-1">
          {items.slice(0, 4).map((x, i) => (
            <li key={i} className="text-[12px] leading-snug text-[var(--text-soft)]">
              {x}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
