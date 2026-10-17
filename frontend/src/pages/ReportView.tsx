import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { ANSWER_STYLES, Shape } from '../components/Shapes'
import { Button, Card, ErrorNote, Spinner, cx } from '../components/ui'
import { Bar, Tile } from '../features/reports/Bar'
import {
  fmtSeconds,
  needsSupport,
  noAnswers,
  optionIndex,
  questionBadge,
  topWrongOption,
  saveBlob,
} from '../features/reports/format'
import { ApiError, api } from '../lib/api'
import type { Report } from '../lib/types'

export default function ReportView() {
  const { sessionId = '' } = useParams()
  const { t } = useTranslation()
  const [r, setR] = useState<Report | null>(null)
  const [err, setErr] = useState('')
  const [preparing, setPreparing] = useState(false)
  const [busy, setBusy] = useState<'ai' | 'csv' | 'pdf' | null>(null)
  const [aiErr, setAiErr] = useState('')

  const load = useCallback(
    async (attempt = 0) => {
      try {
        setErr('')
        setR(await api.report(sessionId))
        setPreparing(false)
      } catch (ex) {
        // The game was only just finished; the server is still saving results. Try again shortly.
        if (ex instanceof ApiError && ex.status === 409 && attempt < 6) {
          setPreparing(true)
          setTimeout(() => void load(attempt + 1), 1500)
          return
        }
        setPreparing(false)
        setErr(
          ex instanceof ApiError && ex.status === 404
            ? t('report.notFound', 'This report was not found.')
            : ex instanceof ApiError && ex.status === 409
              ? t('report.notReady', 'The report is ready once the game has ended.')
              : t('err.generic', 'Something went wrong. Try again.'),
        )
      }
    },
    [sessionId, t],
  )

  useEffect(() => {
    void load()
  }, [load])

  async function summarize() {
    setBusy('ai')
    setAiErr('')
    try {
      const s = await api.summarize(sessionId)
      setR((cur) => (cur ? { ...cur, ai_summary: s } : cur))
    } catch (ex) {
      setAiErr(
        ex instanceof ApiError && ex.status === 429
          ? t('report.aiLimit', 'You have used the AI limit for now. Try again later.')
          : ex instanceof ApiError
            ? ex.message
            : t('err.generic', 'Something went wrong. Try again.'),
      )
    } finally {
      setBusy(null)
    }
  }

  async function download(kind: 'csv' | 'pdf') {
    setBusy(kind)
    try {
      saveBlob(await api.download(sessionId, kind), `report-${sessionId.slice(0, 8)}.${kind}`)
    } catch {
      setErr(t('err.generic', 'Something went wrong. Try again.'))
    } finally {
      setBusy(null)
    }
  }

  if (!r)
    return (
      <div className="grid place-items-center gap-3 py-24 text-center">
        {err ? (
          <>
            <ErrorNote>{err}</ErrorNote>
            <Link to="/teacher/reports" className="font-bold underline">
              {t('report.back', 'Back to past games')}
            </Link>
          </>
        ) : (
          <>
            <Spinner />
            {preparing && (
              <p className="text-muted">{t('report.preparing', 'Preparing your report…')}</p>
            )}
          </>
        )}
      </div>
    )

  const o = r.overall
  const subtopics = [...r.subtopics].sort((a, b) => a.accuracy_pct - b.accuracy_pct)
  const weak = new Set(r.weak_subtopics.map((s) => s.subtopic))

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/teacher/reports" className="text-sm font-bold text-muted hover:underline">
            ← {t('report.back', 'Back to past games')}
          </Link>
          <h1 className="mt-1 text-4xl font-extrabold">{r.title}</h1>
          {r.topic && <p className="text-muted">{r.topic}</p>}
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" busy={busy === 'csv'} onClick={() => void download('csv')}>
            {t('report.csv', 'Download CSV')}
          </Button>
          <Button variant="signal" busy={busy === 'pdf'} onClick={() => void download('pdf')}>
            {t('report.pdf', 'Download PDF')}
          </Button>
        </div>
      </div>
      <ErrorNote>{err}</ErrorNote>

      <section aria-label={t('report.overview', 'Overview')}>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <Tile label={t('report.players', 'Players')} value={String(o.players)} />
          <Tile label={t('report.questions', 'Questions')} value={String(o.questions)} />
          <Tile
            label={t('report.avgScore', 'Average score')}
            value={o.avg_score.toLocaleString()}
          />
          <Tile label={t('report.accuracy', 'Class accuracy')} value={`${o.accuracy_pct}%`} />
          <Tile label={t('report.avgTime', 'Average time')} value={fmtSeconds(o.avg_response_ms)} />
          <Tile
            label={t('report.participation', 'Participation')}
            value={`${o.participation_pct}%`}
            hint={t('report.partHint', 'answers given')}
          />
        </div>
      </section>

      <section aria-label={t('report.ai', 'AI summary')}>
        <Card className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-2xl font-extrabold">✨ {t('report.ai', 'AI summary')}</h2>
            <Button
              variant={r.ai_summary ? 'ghost' : 'primary'}
              busy={busy === 'ai'}
              onClick={() => void summarize()}
            >
              {r.ai_summary
                ? t('report.aiAgain', 'Write it again')
                : t('report.aiMake', 'Generate AI summary')}
            </Button>
          </div>
          <ErrorNote>{aiErr}</ErrorNote>
          {r.ai_summary ? (
            <div className="space-y-4">
              <p className="text-lg">{r.ai_summary.class_insight}</p>
              {r.ai_summary.reteach.length > 0 && (
                <div>
                  <h3 className="font-extrabold">{t('report.reteach', 'Worth re-teaching')}</h3>
                  <ul className="mt-1 list-disc space-y-1 ps-5">
                    {r.ai_summary.reteach.map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                </div>
              )}
              {Object.keys(r.ai_summary.study_tips).length > 0 && (
                <div>
                  <h3 className="font-extrabold">{t('report.tips', 'Study tips')}</h3>
                  <dl className="mt-1 space-y-2">
                    {Object.entries(r.ai_summary.study_tips).map(([k, v]) => (
                      <div key={k} className="rounded-xl bg-ink/5 p-3">
                        <dt className="font-bold">{k}</dt>
                        <dd>{v}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
              <p className="text-sm text-muted">
                {t('report.aiNote', 'Written by AI from anonymous class totals. Please check it.')}
              </p>
            </div>
          ) : (
            <p className="text-muted">
              {t(
                'report.aiEmpty',
                'Get a short plain-language insight, what to re-teach and study tips. Only anonymous class totals are sent to the AI, never names.',
              )}
            </p>
          )}
        </Card>
      </section>

      {subtopics.length > 0 && (
        <section aria-label={t('report.topics', 'Topics')} className="space-y-3">
          <h2 className="text-2xl font-extrabold">{t('report.topics', 'Topics')}</h2>
          <ul className="space-y-3">
            {subtopics.map((s) => (
              <li key={s.subtopic} className="rounded-2xl border border-line bg-card p-4">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold">{s.subtopic || t('report.general', 'General')}</span>
                  <span className="tabular flex items-center gap-2">
                    {weak.has(s.subtopic) && (
                      <span className="rounded-full bg-signal px-2 text-sm font-bold text-[#0f1b33]">
                        ⚠ {t('report.weak', 'Needs review')}
                      </span>
                    )}
                    <span className="font-display font-extrabold">{s.accuracy_pct}%</span>
                    <span className="text-sm text-muted">
                      {s.attempts} {t('report.answersWord', 'answers')}
                    </span>
                  </span>
                </div>
                <Bar pct={s.accuracy_pct} label={`${s.subtopic} ${s.accuracy_pct}%`} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label={t('report.byQuestion', 'Questions')} className="space-y-3">
        <h2 className="text-2xl font-extrabold">{t('report.byQuestion', 'Questions')}</h2>
        <ol className="space-y-4">
          {r.per_question.map((q) => {
            const badge = questionBadge(q, r)
            const wrong = topWrongOption(q)
            const keys = Object.keys(q.distribution).sort()
            const max = Math.max(1, ...Object.values(q.distribution).map(Number))
            return (
              <li key={q.question_id} className="rounded-2xl border border-line bg-card p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h3 className="min-w-0 flex-1 text-lg font-extrabold">
                    <span className="tabular text-muted">{q.position + 1}.</span> {q.text}
                  </h3>
                  <div className="flex items-center gap-2">
                    {badge && (
                      <span
                        className={cx(
                          'rounded-full px-2 text-sm font-bold',
                          badge === 'hardest' ? 'bg-bad/15 text-bad' : 'bg-good/15 text-good',
                        )}
                      >
                        {badge === 'hardest'
                          ? `▼ ${t('report.hardest', 'Hardest')}`
                          : `▲ ${t('report.easiest', 'Easiest')}`}
                      </span>
                    )}
                    <span className="tabular font-display text-2xl font-extrabold">
                      {q.accuracy_pct}%
                    </span>
                  </div>
                </div>
                <p className="tabular text-sm text-muted">
                  {q.subtopic && `${q.subtopic} · `}
                  {fmtSeconds(q.avg_response_ms)} {t('report.avgShort', 'average')} · {q.answered}{' '}
                  {t('report.answersWord', 'answers')}
                </p>
                {q.answered === 0 && (
                  <p className="mt-2 font-bold text-muted">
                    {t('report.nobody', 'Nobody answered this question.')}
                  </p>
                )}
                {wrong && (
                  <p className="mt-2 font-bold text-bad">
                    {t('report.commonWrong', 'Most common wrong answer: {{opt}} ({{n}} students)', {
                      opt: wrong.id,
                      n: wrong.count,
                    })}
                  </p>
                )}
                {keys.length > 0 && q.answered > 0 && (
                  <ul className="mt-3 space-y-2">
                    {keys.map((k, i) => {
                      const style = ANSWER_STYLES[optionIndex(k, i)] ?? ANSWER_STYLES[0]
                      const n = Number(q.distribution[k])
                      const right = q.correct_option_ids.includes(k)
                      return (
                        <li key={k} className="flex items-center gap-3">
                          <span
                            className={cx(
                              'grid h-8 w-8 shrink-0 place-items-center rounded-lg text-white',
                              style.bg,
                            )}
                          >
                            <Shape name={style.shape} className="h-4 w-4" />
                          </span>
                          <span className="w-5 font-bold">{k}</span>
                          <div className="min-w-0 flex-1">
                            <Bar
                              pct={(n / max) * 100}
                              className={style.bg}
                              label={`Option ${k}: ${n}`}
                            />
                          </div>
                          <span className="tabular w-8 text-end font-bold">{n}</span>
                          <span
                            className={cx(
                              'w-6 text-center font-bold text-good',
                              !right && 'invisible',
                            )}
                            aria-label={
                              right ? t('play.correctAnswer', 'Correct answer') : undefined
                            }
                          >
                            ✓
                          </span>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </li>
            )
          })}
        </ol>
      </section>

      <section aria-label={t('report.students', 'Students')} className="space-y-3">
        <h2 className="text-2xl font-extrabold">{t('report.students', 'Students')}</h2>
        <div className="overflow-x-auto rounded-2xl border border-line bg-card">
          <table className="w-full min-w-[560px] text-start">
            <thead>
              <tr className="border-b border-line text-sm text-muted">
                <th scope="col" className="px-4 py-3 text-start">
                  #
                </th>
                <th scope="col" className="px-4 py-3 text-start">
                  {t('report.student', 'Student')}
                </th>
                <th scope="col" className="px-4 py-3 text-end">
                  {t('report.score', 'Score')}
                </th>
                <th scope="col" className="px-4 py-3 text-end">
                  {t('report.right', 'Correct')}
                </th>
                <th scope="col" className="px-4 py-3 text-end">
                  {t('report.accuracyShort', 'Accuracy')}
                </th>
                <th scope="col" className="px-4 py-3 text-end">
                  {t('report.avgTime', 'Average time')}
                </th>
              </tr>
            </thead>
            <tbody>
              {r.per_student.map((s) => (
                <tr key={s.player_id} className="border-b border-line last:border-0">
                  <td className="tabular px-4 py-3 font-bold">{s.rank ?? '–'}</td>
                  <td className="px-4 py-3 font-bold">
                    {s.avatar} {s.nickname}
                    {noAnswers(s) && (
                      <span className="ms-2 rounded-full bg-ink/10 px-2 text-xs font-bold">
                        {t('report.noAnswers', 'No answers')}
                      </span>
                    )}
                    {needsSupport(s) && (
                      <span className="ms-2 rounded-full bg-signal px-2 text-xs font-bold text-[#0f1b33]">
                        {t('report.support', 'Needs support')}
                      </span>
                    )}
                  </td>
                  <td className="tabular px-4 py-3 text-end">{s.score.toLocaleString()}</td>
                  <td className="tabular px-4 py-3 text-end">
                    {s.correct}/{o.questions}
                  </td>
                  <td className="tabular px-4 py-3 text-end">{s.accuracy_pct}%</td>
                  <td className="tabular px-4 py-3 text-end">{fmtSeconds(s.avg_response_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
