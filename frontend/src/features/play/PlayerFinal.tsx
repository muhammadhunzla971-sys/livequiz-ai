import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Leaderboard } from '../../components/Leaderboard'
import { Button, Card } from '../../components/ui'
import { celebrate, stopConfetti } from '../../lib/confetti'
import { downloadResultCard } from '../../lib/resultCard'
import { sound } from '../../lib/sound'
import type { FinalMe, LeaderboardEntry } from '../../lib/types'

interface Props {
  me: FinalMe | null
  title: string
  podium: LeaderboardEntry[]
  meId: string
  reason: string | null
  onLeave: () => void
}

export default function PlayerFinal({ me, title, podium, meId, reason, onLeave }: Props) {
  const { t } = useTranslation()
  const top3 = !!me?.rank && me.rank <= 3

  useEffect(() => {
    sound.play(top3 ? 'win' : 'start')
    if (top3) celebrate()
    return stopConfetti
  }, [top3])

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-4xl font-extrabold">{t('play.over', 'Game over')}</h1>
        {reason === 'host_ended' && (
          <p className="mt-1 text-muted">{t('play.endedEarly', 'The teacher ended the game.')}</p>
        )}
      </div>

      {me && (
        <Card className="text-center">
          <p className="text-muted">{me.nickname}</p>
          <p className="tabular font-display text-7xl font-extrabold" aria-label="Your rank">
            {me.rank ? `#${me.rank}` : '–'}
          </p>
          <p className="tabular text-2xl font-bold">
            {me.score.toLocaleString()} {t('play.pts', 'points')}
          </p>
          <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-xl bg-ink/5 p-3">
              <dd className="tabular text-2xl font-extrabold">{me.accuracy_pct}%</dd>
              <dt className="text-sm text-muted">{t('play.accuracy', 'Correct')}</dt>
            </div>
            <div className="rounded-xl bg-ink/5 p-3">
              <dd className="tabular text-2xl font-extrabold">
                {me.correct}/{me.total_questions}
              </dd>
              <dt className="text-sm text-muted">{t('play.answers', 'Right answers')}</dt>
            </div>
            <div className="rounded-xl bg-ink/5 p-3">
              <dd className="tabular text-2xl font-extrabold">🔥 {me.best_streak}</dd>
              <dt className="text-sm text-muted">{t('play.bestStreak', 'Best streak')}</dt>
            </div>
          </dl>
        </Card>
      )}

      {podium.length > 0 && (
        <section aria-label={t('play.top', 'Top players')} className="space-y-2">
          <h2 className="text-xl font-extrabold">{t('play.top', 'Top players')}</h2>
          <Leaderboard entries={podium} meId={meId} />
        </section>
      )}

      <div className="flex flex-col gap-3 sm:flex-row">
        {me && (
          <Button
            variant="signal"
            big
            className="flex-1"
            onClick={() => downloadResultCard(me, title)}
          >
            {t('play.download', 'Download my result card')}
          </Button>
        )}
        <Link
          to="/play/review"
          className="inline-flex min-h-[56px] flex-1 items-center justify-center rounded-xl bg-ink px-8 font-display text-xl font-bold text-paper"
        >
          {t('play.review', 'Review my answers')}
        </Link>
        <Button variant="ghost" big className="flex-1" onClick={onLeave}>
          {t('play.another', 'Join another game')}
        </Button>
      </div>
    </div>
  )
}
