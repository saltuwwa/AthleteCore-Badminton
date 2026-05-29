import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchVideoDebug, type VideoDebugBundle } from '../api/video'

type Segment = { start: string; end: string; reason?: string }

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5">
      <h2 className="font-display text-[18px] tracking-tight">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  )
}

function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre className="max-h-[420px] overflow-auto rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3 text-[11px] leading-relaxed text-[var(--text-soft)]">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4">
      <p className="font-mono-ui text-[10px] uppercase text-[var(--muted)]">{label}</p>
      <p className="font-display mt-1 text-[22px]">{value}</p>
    </article>
  )
}

function SegmentList({ title, items, showReason }: { title: string; items: Segment[]; showReason?: boolean }) {
  if (!items.length) return <p className="text-[12px] text-[var(--muted2)]">—</p>
  return (
    <div>
      <p className="mb-2 text-[11px] uppercase tracking-wide text-[var(--muted)]">{title}</p>
      <ul className="space-y-1.5">
        {items.map((s, i) => (
          <li key={i} className="font-mono-ui text-[12px] text-[var(--text-soft)]">
            {s.start}–{s.end}
            {showReason && s.reason ? ` — ${s.reason.replace(/_/g, '/')}` : ''}
          </li>
        ))}
      </ul>
    </div>
  )
}

export const VideoDebugPage = () => {
  const { videoId } = useParams<{ videoId: string }>()
  const [bundle, setBundle] = useState<VideoDebugBundle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!videoId) return
    setLoading(true)
    fetchVideoDebug(videoId)
      .then(setBundle)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Ошибка загрузки debug'))
      .finally(() => setLoading(false))
  }, [videoId])

  const meta = asRecord(bundle?.['01_video_metadata'])
  const players = asRecord(bundle?.['03_detected_players'])
  const tracking = asRecord(bundle?.['04_tracking_summary'])
  const segments = asRecord(bundle?.['05_segment_filtering'])
  const target = asRecord(bundle?.['06_target_selection'])
  const metrics = bundle?.['07_metrics']
  const memory = asRecord(bundle?.['08_memory_context'])
  const rag = asRecord(bundle?.['09_rag_context'])
  const geminiIn = bundle?.['10_gemini_input']
  const feedbackMd = typeof bundle?.['11_gemini_feedback'] === 'string' ? bundle['11_gemini_feedback'] : ''
  const timing = asRecord(bundle?.['12_timing_report'])
  const errors = asRecord(bundle?.['13_errors'])

  const validSegs = (segments?.valid_segments as Segment[]) ?? []
  const ignoredSegs = (segments?.ignored_segments as Segment[]) ?? []
  const ratio = Number(segments?.valid_gameplay_ratio ?? 0)
  const playerList = (players?.players as unknown[]) ?? []

  return (
    <div className="mx-auto min-h-screen max-w-4xl space-y-6 px-4 py-8 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-mono-ui text-[10px] uppercase text-[var(--accent)]">Eval / Debug</p>
          <h1 className="font-display text-[28px] tracking-tight">Video analysis debug</h1>
          <p className="mt-1 text-[12px] text-[var(--muted2)]">video_id: {videoId}</p>
        </div>
        <Link
          to="/analysis/video"
          className="rounded-lg border border-[var(--border)] px-4 py-2 text-[13px] hover:border-[var(--accent)]"
        >
          ← К анализу
        </Link>
      </header>

      {loading && <p className="text-[13px] text-[var(--muted2)]">Загрузка артефактов…</p>}
      {error && <p className="text-[13px] text-[var(--accent3)]">{error}</p>}

      {!loading && bundle && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <SummaryCard label="Игровых моментов" value={`${Math.round(ratio * 100)}%`} />
            <SummaryCard label="Игроков найдено" value={String(playerList.length)} />
            <SummaryCard
              label="Tracking stability"
              value={String(tracking?.tracking_consistency_score ?? '—')}
            />
            <SummaryCard
              label="Gemini"
              value={timing?.gemini_feedback_sec != null ? `${timing.gemini_feedback_sec} сек` : '—'}
            />
            <SummaryCard
              label="Total"
              value={timing?.total_sec != null ? `${timing.total_sec} сек` : '—'}
            />
          </div>

          <Section title="1. Видео">
            <JsonBlock data={meta} />
          </Section>

          <Section title="2. Игроки">
            <JsonBlock data={players} />
          </Section>

          <Section title="3. Фрагменты">
            <div className="grid gap-4 sm:grid-cols-2">
              <SegmentList title="Проанализировано" items={validSegs} />
              <SegmentList title="Исключено" items={ignoredSegs} showReason />
            </div>
          </Section>

          <Section title="4. Метрики">
            <JsonBlock data={metrics} />
          </Section>

          <Section title="5. Память">
            <JsonBlock data={memory} />
          </Section>

          <Section title="6. RAG">
            <JsonBlock data={rag} />
          </Section>

          <Section title="7. Gemini input">
            <JsonBlock data={geminiIn} />
          </Section>

          <Section title="8. Feedback">
            <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3 text-[12px] text-[var(--text-soft)]">
              {feedbackMd || '—'}
            </pre>
          </Section>

          <Section title="9. Время">
            <JsonBlock data={timing} />
          </Section>

          {(errors?.errors as unknown[])?.length ? (
            <Section title="Ошибки / fallback">
              <JsonBlock data={errors} />
            </Section>
          ) : null}

          {target && (
            <p className="text-center text-[11px] text-[var(--muted)]">
              Target: {String(target.target_label ?? target.target_track_ids)} ·{' '}
              {String(target.match_type)}
            </p>
          )}
        </>
      )}
    </div>
  )
}
