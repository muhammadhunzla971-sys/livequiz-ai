import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ConnectionBanner, Logo, Toggles } from '../components/Chrome'
import { useCountdown } from '../components/CountdownRing'
import { Leaderboard } from '../components/Leaderboard'
import { Button, Card, ErrorNote, Spinner } from '../components/ui'
import Controls from '../features/host/Controls'
import Finished from '../features/host/Finished'
import Lobby from '../features/host/Lobby'
import QuestionStage from '../features/host/QuestionStage'
import { api, tokens } from '../lib/api'
import { sound } from '../lib/sound'
import { useGame } from '../store/game'
import { useRoom, wsUrl } from '../ws/useRoom'

const ERRORS: Record<string, string> = {
  no_players: 'Wait for at least one player to join.',
  no_questions: 'This quiz has no questions.',
  illegal_transition: 'That action is not available right now.',
  not_revealed: 'Reveal the answer first.',
  forbidden: 'That action is not allowed.',
  bad_payload: 'That action was not understood.',
  internal: 'Something went wrong on the server. Try again.',
}

export default function HostGame() {
  const { sessionId = '' } = useParams()
  const { t } = useTranslation()
  const nav = useNavigate()
  const [epoch, setEpoch] = useState(0)
  const sock = useRoom('host', sessionId ? `${sessionId}:${epoch}` : null, () =>
    wsUrl(`/ws/host/${sessionId}`, tokens.access() ?? ''),
  )
  const g = useGame()

  const send = useCallback(
    (type: string, payload?: Record<string, unknown>) => {
      if (!sock.current?.send(type, payload ?? {})) useGame.setState({ error: 'internal' })
    },
    [sock],
  )
  const skew = useCallback(() => sock.current?.skewMs ?? 0, [sock])
  const remaining = useCountdown(g.endAt, skew, g.remainingMs)

  // The access token lives 15 minutes; on "unauthorized" refresh it through a REST call and retry.
  useEffect(() => {
    if (g.conn === 'closed' && g.closeCode === 4401 && epoch < 3)
      api
        .me()
        .then(() => setEpoch((e) => e + 1))
        .catch(() => nav('/login'))
  }, [g.conn, g.closeCode, epoch, nav])

  // Errors are transient notices.
  useEffect(() => {
    if (!g.error) return
    const id = setTimeout(() => useGame.setState({ error: null }), 6000)
    return () => clearTimeout(id)
  }, [g.error])

  const lastTick = useRef(0)
  useEffect(() => {
    if (g.phase !== 'question_active' || remaining <= 0 || remaining > 5000) return
    const sec = Math.ceil(remaining / 1000)
    if (sec !== lastTick.current) {
      lastTick.current = sec
      sound.play('tick')
    }
  }, [g.phase, remaining])

  useEffect(() => {
    document.title = g.title ? `${g.title} · LiveQuiz` : 'LiveQuiz'
  }, [g.title])

  if (g.conn === 'closed' && g.closeCode !== 4401)
    return (
      <div className="mx-auto grid min-h-screen max-w-lg place-items-center px-4">
        <Card className="text-center">
          <h1 className="text-3xl font-extrabold">
            {g.closeCode === 4404 || g.closeCode === 4403
              ? t('host.gone', 'This game was not found')
              : t('host.closed', 'Disconnected from the game')}
          </h1>
          <p className="mt-2 text-muted">
            {g.closeCode === 4404
              ? t('host.goneBody', 'It may have ended, or the link is wrong.')
              : g.closeCode === 4403
                ? t('host.notYours', 'This game belongs to another teacher.')
                : t('host.closedBody', 'Check your connection and reload the page.')}
          </p>
          <div className="mt-5 flex justify-center gap-3">
            <Button onClick={() => setEpoch((e) => e + 1)}>{t('host.retry', 'Reconnect')}</Button>
            <Link
              to="/teacher"
              className="inline-flex min-h-[44px] items-center rounded-xl border border-line px-5 font-display font-bold"
            >
              {t('host.toDash', 'Back to my quizzes')}
            </Link>
          </div>
        </Card>
      </div>
    )

  const phase = g.phase
  const inGame =
    phase && ['question_active', 'paused', 'question_closed', 'leaderboard'].includes(phase)

  return (
    <div className="min-h-screen">
      <ConnectionBanner status={g.conn} />
      <header className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4">
        <div className="flex items-center gap-4">
          <Logo />
          {g.title && <span className="hidden font-bold text-muted sm:inline">{g.title}</span>}
        </div>
        <div className="flex items-center gap-4">
          {g.pin && phase !== 'lobby' && phase !== 'created' && (
            <span className="tabular font-display text-xl font-extrabold">PIN {g.pin}</span>
          )}
          <Toggles />
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-6">
        {g.error && (
          <div className="mb-4">
            <ErrorNote>
              {ERRORS[g.error] ?? t('err.generic', 'Something went wrong. Try again.')}
            </ErrorNote>
          </div>
        )}

        {phase === null ? (
          <div className="grid place-items-center py-24">
            <Spinner />
          </div>
        ) : phase === 'lobby' || phase === 'created' ? (
          <Lobby
            pin={g.pin}
            players={g.players}
            locked={g.locked}
            settings={g.settings}
            send={send}
          />
        ) : phase === 'finished' || phase === 'archived' ? (
          <Finished
            podium={g.podium}
            leaderboard={g.leaderboard}
            reason={g.finishReason}
            sessionId={sessionId}
          />
        ) : phase === 'leaderboard' ? (
          <div className="mx-auto max-w-3xl space-y-4">
            <h2 className="text-4xl font-extrabold">{t('lb.title', 'Leaderboard')}</h2>
            <Leaderboard entries={g.leaderboard} big />
          </div>
        ) : g.question ? (
          <div className="space-y-6">
            <QuestionStage
              question={g.question}
              remainingMs={remaining}
              active={phase === 'question_active'}
              paused={phase === 'paused'}
              answered={g.answered}
              totalPlayers={g.playersCount}
              distribution={g.distribution}
              showDistribution={!!g.settings?.show_distribution}
              reveal={g.reveal}
            />
            {g.settings?.live_leaderboard &&
              phase === 'question_active' &&
              g.leaderboard.length > 0 && <Leaderboard entries={g.leaderboard} limit={5} />}
            {phase === 'paused' && (
              <p
                role="status"
                className="rounded-xl bg-signal px-4 py-3 text-center text-xl font-extrabold text-[#0f1b33]"
              >
                ⏸ {t('host.paused', 'Game paused')}
              </p>
            )}
          </div>
        ) : null}
      </main>

      {inGame && (
        <div className="mx-auto max-w-6xl px-4">
          <Controls phase={phase} revealed={g.reveal !== null} isLast={g.isLast} send={send} />
        </div>
      )}
    </div>
  )
}
