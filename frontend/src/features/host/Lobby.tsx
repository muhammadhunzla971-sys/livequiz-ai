import { useTranslation } from 'react-i18next'
import { Button, Card, cx } from '../../components/ui'
import { API_BASE } from '../../lib/config'
import type { RoomSettings, RosterPlayer } from '../../lib/types'

interface Props {
  pin: string
  players: RosterPlayer[]
  locked: boolean
  settings: RoomSettings | null
  send: (type: string, payload?: Record<string, unknown>) => void
}

const SETTING_LABELS: [keyof RoomSettings, string][] = [
  ['show_distribution', 'Show answer distribution live'],
  ['live_leaderboard', 'Live leaderboard during questions'],
  ['auto_close', 'End question when everyone has answered'],
  ['auto_reveal', 'Reveal the answer automatically'],
]

export default function Lobby({ pin, players, locked, settings, send }: Props) {
  const { t } = useTranslation()
  const joinUrl = `${location.origin}/join`
  const spaced = pin ? `${pin.slice(0, 3)} ${pin.slice(3)}` : '------'

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
      <Card className="flex flex-col items-center gap-4 text-center">
        <p className="text-xl text-muted">
          {t('host.joinAt', 'Join at')}{' '}
          <strong className="text-ink">{joinUrl.replace(/^https?:\/\//, '')}</strong>
        </p>
        <p className="text-muted">{t('host.pin', 'Game PIN')}</p>
        <p
          className="tabular whitespace-nowrap font-display text-6xl font-extrabold tracking-wider sm:text-7xl lg:text-6xl xl:text-7xl"
          aria-label={`PIN ${pin.split('').join(' ')}`}
        >
          {spaced}
        </p>
        {pin && (
          <img
            src={`${API_BASE}/api/join/qr/${pin}.svg`}
            alt={t('host.qrAlt', 'QR code that opens the join page')}
            width={220}
            height={220}
            className="rounded-xl bg-white p-2"
          />
        )}
        <label className="flex min-h-[44px] cursor-pointer items-center gap-2 font-bold">
          <input
            type="checkbox"
            checked={locked}
            onChange={(e) => send('host.lock', { locked: e.target.checked })}
          />
          {t('host.lock', 'Lock room (no new players)')}
        </label>
      </Card>

      <div className="space-y-4">
        <Card>
          <h2 className="text-2xl font-extrabold">
            {t('host.players', 'Players')}{' '}
            <span className="tabular text-muted">({players.length})</span>
          </h2>
          {players.length === 0 ? (
            <p className="mt-3 text-muted" aria-live="polite">
              {t('host.waiting', 'Waiting for players to join…')}
            </p>
          ) : (
            <ul className="mt-3 flex flex-wrap gap-2" aria-live="polite">
              {players.map((p) => (
                <li
                  key={p.id}
                  className={cx(
                    'flex items-center gap-2 rounded-full border border-line bg-paper py-1 ps-3 pe-1',
                    p.connected === false && 'opacity-50',
                  )}
                >
                  <span className="font-bold">
                    {p.avatar} {p.nickname}
                  </span>
                  <button
                    className="grid h-9 w-9 place-items-center rounded-full hover:bg-bad/15"
                    aria-label={`Remove ${p.nickname}`}
                    onClick={() => send('host.kick', { player_id: p.id })}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {settings && (
          <Card>
            <h2 className="text-xl font-extrabold">{t('host.settings', 'Game settings')}</h2>
            <div className="mt-2 grid gap-1">
              {SETTING_LABELS.map(([key, label]) => (
                <label key={key} className="flex min-h-[44px] cursor-pointer items-center gap-3">
                  <input
                    type="checkbox"
                    checked={settings[key]}
                    onChange={(e) => send('host.settings', { [key]: e.target.checked })}
                  />
                  {label}
                </label>
              ))}
            </div>
          </Card>
        )}

        <Button
          variant="signal"
          big
          className="w-full"
          disabled={players.length === 0}
          onClick={() => send('host.start')}
        >
          {t('host.start', 'Start game')}
        </Button>
        {players.length === 0 && (
          <p className="text-center text-muted">
            {t('host.needOne', 'At least one player must join first.')}
          </p>
        )}
      </div>
    </div>
  )
}
