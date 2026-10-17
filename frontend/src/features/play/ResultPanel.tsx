import { useTranslation } from 'react-i18next'
import { ANSWER_STYLES, Shape } from '../../components/Shapes'
import { cx } from '../../components/ui'
import type { PublicQuestion, Reveal, YouResult } from '../../lib/types'

export type Outcome = 'waiting' | 'correct' | 'partial' | 'wrong' | 'missed'

export function outcomeOf(reveal: Reveal | null, you: YouResult | null): Outcome {
  if (!reveal || !you) return 'waiting'
  if (!you.answered) return 'missed'
  if (you.is_correct) return 'correct'
  return you.accuracy > 0 ? 'partial' : 'wrong'
}

interface Props {
  question: PublicQuestion
  reveal: Reveal | null
  you: YouResult | null
  /** What this player sent, used before the reveal arrives. */
  myChoice: string[] | null
}

export default function ResultPanel({ question, reveal, you, myChoice }: Props) {
  const { t } = useTranslation()
  const outcome = outcomeOf(reveal, you)
  const picked = you?.chosen ?? myChoice ?? []

  const banner: Record<Outcome, { icon: string; text: string; tone: string }> = {
    waiting: {
      icon: '⏳',
      text:
        myChoice === null
          ? t('play.timeUpNoAnswer', 'Time is up. You did not answer.')
          : t('play.timeUpWaiting', 'Time is up! Waiting for the teacher to show the answer…'),
      tone: 'border-line bg-card',
    },
    correct: {
      icon: '✓',
      text: t('play.correct', 'Correct!'),
      tone: 'border-good/60 bg-good/15',
    },
    partial: {
      icon: '◐',
      text: t('play.partial', 'Partly right'),
      tone: 'border-signal bg-signal/20',
    },
    wrong: {
      icon: '✗',
      text: t('play.wrong', 'Not this time'),
      tone: 'border-bad/60 bg-bad/10',
    },
    missed: {
      icon: '⏱',
      text: t('play.missed', 'Too slow. No answer sent.'),
      tone: 'border-line bg-card',
    },
  }
  const b = banner[outcome]

  return (
    <div className="space-y-4">
      <div
        role="status"
        aria-live="polite"
        className={cx('rounded-2xl border-2 p-5 text-center', b.tone)}
      >
        <p className="text-5xl" aria-hidden="true">
          {b.icon}
        </p>
        <p className="mt-1 text-3xl font-extrabold">{b.text}</p>
        {you && outcome !== 'waiting' && (
          <div className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-lg">
            <span className="tabular font-display font-extrabold">
              +{you.points.toLocaleString()} {t('play.pts', 'points')}
            </span>
            {you.streak >= 2 && (
              <span className="rounded-full bg-signal px-3 font-bold text-[#0f1b33]">
                🔥 {you.streak}
              </span>
            )}
          </div>
        )}
        {you && outcome !== 'waiting' && (
          <p className="tabular mt-2 text-muted">
            {t('play.total', 'Total')} {you.score.toLocaleString()}
            {you.rank ? ` · ${t('play.rank', 'Rank')} #${you.rank}` : ''}
            {you.rank_change > 0 && (
              <span className="ms-2 font-bold text-good">▲ {you.rank_change}</span>
            )}
            {you.rank_change < 0 && (
              <span className="ms-2 font-bold text-bad">▼ {-you.rank_change}</span>
            )}
          </p>
        )}
      </div>

      <h2 className="text-xl font-extrabold">{question.text}</h2>
      <ul className="space-y-2">
        {question.options.map((o, i) => {
          const style = ANSWER_STYLES[i]
          const isCorrect = reveal?.correct_option_ids.includes(o.id)
          const mine = picked.includes(o.id)
          return (
            <li
              key={o.id}
              className={cx(
                'flex items-center gap-3 rounded-xl p-3 font-bold text-white',
                style.bg,
                reveal && !isCorrect && 'opacity-40',
                reveal && isCorrect && 'ring-4 ring-good ring-offset-2 ring-offset-paper',
              )}
            >
              <Shape name={style.shape} className="h-6 w-6 shrink-0" />
              <span className="min-w-0 flex-1 break-words">{o.text}</span>
              {mine && (
                <span className="rounded-full bg-black/30 px-2 text-sm">
                  {t('play.yourPick', 'Your pick')}
                </span>
              )}
              {isCorrect && (
                <span aria-label={t('play.correctAnswer', 'Correct answer')} className="text-xl">
                  ✓
                </span>
              )}
            </li>
          )
        })}
      </ul>

      {reveal?.explanation && (
        <div className="rounded-2xl border border-line bg-card p-4">
          <p className="text-sm font-bold text-muted">{t('play.why', 'Why')}</p>
          <p className="mt-1 text-lg">{reveal.explanation}</p>
        </div>
      )}
    </div>
  )
}
