import { AnimatePresence, motion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import type { LeaderboardEntry } from '../lib/types'
import { cx } from './ui'

function Change({ n }: { n: number }) {
  if (!n) return <span className="w-5" aria-hidden="true" />
  const up = n > 0
  return (
    <span
      className={cx('w-5 text-sm font-bold', up ? 'text-good' : 'text-bad')}
      aria-label={up ? `up ${n}` : `down ${-n}`}
    >
      {up ? '▲' : '▼'}
    </span>
  )
}

export function Leaderboard({
  entries,
  meId,
  big,
  limit,
}: {
  entries: LeaderboardEntry[]
  meId?: string
  big?: boolean
  limit?: number
}) {
  const { t } = useTranslation()
  const rows = limit ? entries.slice(0, limit) : entries
  if (rows.length === 0) return <p className="text-muted">{t('lb.empty', 'No scores yet.')}</p>
  return (
    <ol className="space-y-2" aria-live="polite" aria-label={t('lb.title', 'Leaderboard')}>
      <AnimatePresence initial={false}>
        {rows.map((e) => (
          <motion.li
            key={e.player_id}
            layout
            transition={{ type: 'spring', stiffness: 500, damping: 40 }}
            className={cx(
              'flex items-center gap-3 rounded-xl border px-4',
              big ? 'py-3 text-2xl' : 'py-2',
              e.player_id === meId ? 'border-signal bg-signal/20' : 'border-line bg-card',
            )}
          >
            <span className="tabular w-8 font-display font-extrabold">{e.rank}</span>
            <Change n={e.rank_change} />
            <span className="min-w-0 flex-1 truncate font-bold">
              {e.avatar} {e.nickname}
            </span>
            {e.streak >= 2 && (
              <span
                className="rounded-full bg-signal px-2 text-sm font-bold text-[#0f1b33]"
                title="Streak"
              >
                🔥{e.streak}
              </span>
            )}
            <span className="tabular font-display font-extrabold">{e.score.toLocaleString()}</span>
          </motion.li>
        ))}
      </AnimatePresence>
    </ol>
  )
}
