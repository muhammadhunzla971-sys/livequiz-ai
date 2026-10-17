import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { Shell } from '../components/Chrome'
import { ANSWER_STYLES, Shape } from '../components/Shapes'
import { Card, ErrorNote, Spinner, cx } from '../components/ui'
import { Bar } from '../features/reports/Bar'
import { ApiError, api } from '../lib/api'
import { playerStore } from '../lib/device'
import type { StudentReport } from '../lib/types'

/** The student's own after-game review: where they did well and the questions they missed. */
export default function ReviewMine() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const me = playerStore.get()
  const [rep, setRep] = useState<StudentReport | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!me) return void nav('/', { replace: true })
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const load = (attempt: number) =>
      api
        .myReport(me.player_token)
        .then((r) => alive && setRep(r))
        .catch((ex) => {
          if (!alive) return
          // Results are saved a moment after the game ends; try again a few times.
          if (ex instanceof ApiError && ex.status === 409 && attempt < 5) {
            timer = setTimeout(() => void load(attempt + 1), 1500)
            return
          }
          setErr(
            ex instanceof ApiError && ex.status === 409
              ? t('review.notReady', 'Your review is ready when the game ends.')
              : ex instanceof ApiError && ex.status === 401
                ? t('review.expired', 'Your session expired, so the review is not available.')
                : t('err.generic', 'Something went wrong. Try again.'),
          )
        })
    void load(0)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [me, nav, t])

  return (
    <Shell>
      <div className="space-y-6 pt-4">
        <Link to="/play" className="text-sm font-bold text-muted hover:underline">
          ← {t('review.back', 'Back to results')}
        </Link>
        <h1 className="text-3xl font-extrabold">{t('review.title', 'Review my answers')}</h1>
        <ErrorNote>{err}</ErrorNote>
        {!rep && !err && (
          <div className="grid place-items-center py-16">
            <Spinner />
          </div>
        )}
        {rep && (
          <>
            <Card className="text-center">
              <p className="tabular font-display text-5xl font-extrabold">{rep.accuracy_pct}%</p>
              <p className="text-muted">
                {rep.correct} {t('review.of', 'right out of')} {rep.answered}{' '}
                {t('review.answered', 'answered')}
                {rep.rank ? ` · #${rep.rank}` : ''}
              </p>
            </Card>

            {rep.subtopics.length > 0 && (
              <section className="space-y-3" aria-label={t('review.topics', 'By topic')}>
                <h2 className="text-xl font-extrabold">{t('review.topics', 'By topic')}</h2>
                <ul className="space-y-3">
                  {rep.subtopics.map((s) => (
                    <li key={s.subtopic} className="rounded-2xl border border-line bg-card p-3">
                      <div className="mb-2 flex justify-between gap-2">
                        <span className="font-bold">
                          {s.subtopic || t('report.general', 'General')}
                        </span>
                        <span className="tabular flex items-center gap-2">
                          {s.accuracy_pct < 60 && (
                            <span className="rounded-full bg-signal px-2 text-sm font-bold text-[#0f1b33]">
                              {t('review.practice', 'Practise this')}
                            </span>
                          )}
                          <span className="font-display font-extrabold">{s.accuracy_pct}%</span>
                        </span>
                      </div>
                      <Bar pct={s.accuracy_pct} label={`${s.subtopic} ${s.accuracy_pct}%`} />
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="space-y-3" aria-label={t('review.missed', 'Questions to review')}>
              <h2 className="text-xl font-extrabold">
                {t('review.missed', 'Questions to review')}
              </h2>
              {rep.review.length === 0 ? (
                <Card className="text-center text-lg font-bold">
                  🎉 {t('review.perfect', 'You got every question right!')}
                </Card>
              ) : (
                <ol className="space-y-4">
                  {rep.review.map((q, n) => (
                    <li
                      key={q.question_id}
                      className="space-y-2 rounded-2xl border border-line bg-card p-4"
                    >
                      <h3 className="font-extrabold">
                        <span className="tabular text-muted">{n + 1}.</span> {q.text}
                      </h3>
                      <ul className="space-y-1.5">
                        {q.options.map((o, i) => {
                          const st = ANSWER_STYLES[i]
                          const right = q.correct_option_ids.includes(o.id)
                          const mine = q.chosen.includes(o.id)
                          return (
                            <li
                              key={o.id}
                              className={cx(
                                'flex items-center gap-3 rounded-xl p-2.5 font-bold text-white',
                                st.bg,
                                !right && !mine && 'opacity-40',
                                right && 'ring-4 ring-good ring-offset-2 ring-offset-paper',
                              )}
                            >
                              <Shape name={st.shape} className="h-5 w-5 shrink-0" />
                              <span className="min-w-0 flex-1 break-words">{o.text}</span>
                              {mine && (
                                <span className="rounded-full bg-black/30 px-2 text-sm">
                                  {t('play.yourPick', 'Your pick')}
                                </span>
                              )}
                              {right && (
                                <span aria-label={t('play.correctAnswer', 'Correct answer')}>
                                  ✓
                                </span>
                              )}
                            </li>
                          )
                        })}
                      </ul>
                      {q.chosen.length === 0 && (
                        <p className="font-bold text-muted">
                          {t('review.skipped', 'You did not answer this one.')}
                        </p>
                      )}
                      {q.explanation && (
                        <p className="rounded-xl bg-ink/5 p-3">
                          <span className="font-bold">{t('play.why', 'Why')}: </span>
                          {q.explanation}
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </>
        )}
      </div>
    </Shell>
  )
}
