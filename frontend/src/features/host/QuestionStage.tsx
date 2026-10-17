import { useTranslation } from 'react-i18next'
import { ANSWER_STYLES, Shape } from '../../components/Shapes'
import { CountdownRing } from '../../components/CountdownRing'
import { cx } from '../../components/ui'
import type { PublicQuestion, Reveal } from '../../lib/types'

interface Props {
  question: PublicQuestion
  remainingMs: number
  active: boolean
  paused: boolean
  answered: number
  totalPlayers: number
  distribution: Record<string, number>
  showDistribution: boolean
  reveal: Reveal | null
}

export default function QuestionStage({
  question,
  remainingMs,
  active,
  paused,
  answered,
  totalPlayers,
  distribution,
  showDistribution,
  reveal,
}: Props) {
  const { t } = useTranslation()
  const counts = question.options.map((o) => distribution[o.id] ?? 0)
  const max = Math.max(1, ...counts)
  const showBars = reveal !== null || showDistribution
  const dist = reveal?.distribution ?? distribution

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <p className="tabular text-xl font-bold text-muted">
          {t('host.qOf', 'Question {{n}} of {{total}}', {
            n: question.index + 1,
            total: question.total,
          })}
        </p>
        <p className="tabular text-xl font-bold" aria-live="polite">
          {answered}/{totalPlayers} {t('host.answered', 'answered')}
        </p>
      </div>

      <div className="flex items-start gap-6">
        <h2 className="flex-1 text-3xl font-extrabold md:text-5xl">{question.text}</h2>
        {(active || paused) && (
          <CountdownRing
            remainingMs={remainingMs}
            totalMs={question.time_limit_sec * 1000}
            size={110}
          />
        )}
      </div>

      {question.type === 'multi_select' && (
        <p className="font-bold text-muted">{t('host.multiHint', 'Select all correct answers')}</p>
      )}

      <ul className="grid gap-3 md:grid-cols-2">
        {question.options.map((o, i) => {
          const style = ANSWER_STYLES[i]
          const isCorrect = reveal?.correct_option_ids.includes(o.id)
          const n = Number(dist[o.id] ?? 0)
          return (
            <li
              key={o.id}
              className={cx(
                'relative overflow-hidden rounded-2xl text-white',
                style.bg,
                reveal && !isCorrect && 'opacity-40',
                reveal && isCorrect && 'ring-4 ring-good ring-offset-2 ring-offset-paper',
              )}
            >
              {showBars && (
                <span
                  aria-hidden="true"
                  className="absolute inset-y-0 start-0 bg-black/25 transition-[width] duration-300"
                  style={{
                    width: `${(n / (reveal ? Math.max(1, ...Object.values(dist).map(Number)) : max)) * 100}%`,
                  }}
                />
              )}
              <div className="relative flex items-center gap-4 p-5 text-2xl font-bold md:text-3xl">
                <Shape name={style.shape} className="h-9 w-9 shrink-0" />
                <span className="min-w-0 flex-1">{o.text}</span>
                {isCorrect && (
                  <span aria-label="Correct answer" className="text-3xl">
                    ✓
                  </span>
                )}
                {showBars && <span className="tabular font-display">{n}</span>}
              </div>
            </li>
          )
        })}
      </ul>

      {reveal && (
        <div className="rounded-2xl border border-line bg-card p-5">
          {reveal.explanation && <p className="text-xl">{reveal.explanation}</p>}
          <p className="tabular mt-2 text-muted">
            {reveal.correct_count ?? 0}/{reveal.answered ?? 0}{' '}
            {t('host.correct', 'answered correctly')}
            {reveal.avg_response_ms
              ? ` · ${(reveal.avg_response_ms / 1000).toFixed(1)}s ${t('host.avg', 'average')}`
              : ''}
          </p>
        </div>
      )}
    </div>
  )
}
