import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Leaderboard } from '../../components/Leaderboard'
import { celebrate, stopConfetti } from '../../lib/confetti'
import { sound } from '../../lib/sound'
import type { LeaderboardEntry } from '../../lib/types'

const HEIGHT = ['h-40', 'h-28', 'h-20']
const ORDER = [1, 0, 2] // silver, gold, bronze left to right

export default function Finished({
  podium,
  leaderboard,
  reason,
  sessionId,
}: {
  podium: LeaderboardEntry[]
  leaderboard: LeaderboardEntry[]
  reason: string | null
  sessionId?: string
}) {
  const { t } = useTranslation()
  useEffect(() => {
    sound.play('win')
    celebrate()
    return stopConfetti
  }, [])

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h2 className="text-5xl font-extrabold">{t('host.over', 'Game over')}</h2>
        {reason === 'host_ended' && (
          <p className="mt-1 text-muted">{t('host.endedEarly', 'You ended the game early.')}</p>
        )}
      </div>

      {podium.length > 0 && (
        <ol className="mx-auto flex max-w-xl items-end justify-center gap-3" aria-label="Podium">
          {ORDER.map((i) => {
            const p = podium[i]
            if (!p) return <li key={i} className="flex-1" />
            return (
              <li key={p.player_id} className="flex flex-1 flex-col items-center gap-2 text-center">
                <span className="text-4xl" aria-hidden="true">
                  {p.avatar}
                </span>
                <span className="w-full truncate font-extrabold">{p.nickname}</span>
                <span className="tabular text-muted">{p.score.toLocaleString()}</span>
                <span
                  className={`grid w-full place-items-center rounded-t-2xl bg-signal font-display text-4xl font-extrabold text-[#0f1b33] ${HEIGHT[i]}`}
                >
                  {i + 1}
                </span>
              </li>
            )
          })}
        </ol>
      )}

      <div className="mx-auto max-w-2xl">
        <Leaderboard entries={leaderboard} big />
      </div>

      <div className="flex flex-wrap justify-center gap-3">
        {sessionId && (
          <Link
            to={`/teacher/reports/${sessionId}`}
            className="inline-flex min-h-[48px] items-center rounded-xl bg-signal px-6 font-display font-bold text-[#0f1b33]"
          >
            {t('host.viewReport', 'View full report')}
          </Link>
        )}
        <Link
          to="/teacher"
          className="inline-flex min-h-[48px] items-center rounded-xl bg-ink px-6 font-display font-bold text-paper"
        >
          {t('host.toDash', 'Back to my quizzes')}
        </Link>
      </div>
    </div>
  )
}
