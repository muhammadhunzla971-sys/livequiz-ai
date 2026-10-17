import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { ConnectionBanner, Logo, Toggles } from '../components/Chrome'
import { CountdownRing, useCountdown } from '../components/CountdownRing'
import { Leaderboard } from '../components/Leaderboard'
import { Button, Card, ErrorNote, Spinner } from '../components/ui'
import AnswerPad from '../features/play/AnswerPad'
import PlayerFinal from '../features/play/PlayerFinal'
import ResultPanel, { outcomeOf } from '../features/play/ResultPanel'
import { playerStore } from '../lib/device'
import { sound } from '../lib/sound'
import { useGame } from '../store/game'
import { useRoom, wsUrl } from '../ws/useRoom'

const NOTICES: Record<string, string> = {
  late: 'Too late. Time had already run out.',
  paused: 'The game is paused. Wait for the teacher.',
  not_active: 'This question is not open any more.',
  wrong_question: 'That question has already moved on.',
  invalid_option: 'That answer was not valid.',
  offline: 'Not connected yet. Try again in a moment.',
  rate_limited: 'Slow down a little.',
  internal: 'Something went wrong. Try again.',
}

export default function Play() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const me = useMemo(() => playerStore.get(), [])
  const [epoch, setEpoch] = useState(0)
  const g = useGame()

  const sock = useRoom('player', me ? `${me.player_id}:${epoch}` : null, () =>
    wsUrl(`/ws/player/${me?.room_id}`, me?.player_token ?? ''),
  )
  const skew = useCallback(() => sock.current?.skewMs ?? 0, [sock])
  const remaining = useCountdown(g.endAt, skew, g.remainingMs)

  useEffect(() => {
    if (!me) nav('/', { replace: true })
  }, [me, nav])

  const leave = useCallback(() => {
    playerStore.set(null)
    nav('/')
  }, [nav])

  const answer = useCallback(
    (ids: string[]) => {
      const q = useGame.getState().question
      if (!q) return
      if (sock.current?.send('player.answer', { question_id: q.question_id, option_ids: ids })) {
        useGame.getState().choose(ids)
        navigator.vibrate?.(25)
      } else useGame.setState({ error: 'offline' })
    },
    [sock],
  )

  // Notices (late, offline...) fade away by themselves.
  useEffect(() => {
    const reason = g.ackReason || g.error
    if (!reason || reason === 'kicked') return
    const id = setTimeout(() => useGame.setState({ error: null, ackReason: null }), 5000)
    return () => clearTimeout(id)
  }, [g.ackReason, g.error])

  // Tick in the last five seconds, only while you can still answer.
  const lastTick = useRef(0)
  useEffect(() => {
    if (g.phase !== 'question_active' || g.myChoice !== null || remaining <= 0 || remaining > 5000)
      return
    const sec = Math.ceil(remaining / 1000)
    if (sec !== lastTick.current) {
      lastTick.current = sec
      sound.play('tick')
    }
  }, [g.phase, g.myChoice, remaining])

  // Feedback when the result arrives.
  useEffect(() => {
    if (!g.you || !g.reveal) return
    const o = outcomeOf(g.reveal, g.you)
    if (o === 'correct') sound.play('good')
    else if (o === 'wrong' || o === 'partial') sound.play('bad')
    if (o === 'correct') navigator.vibrate?.([40, 30, 40])
  }, [g.you, g.reveal])

  useEffect(() => {
    document.title = g.title ? `${g.title} · LiveQuiz` : 'LiveQuiz'
  }, [g.title])

  if (!me) return null

  // ---- the connection is gone for good ---------------------------------------------------
  const kicked = g.error === 'kicked' || g.closeCode === 4410
  if (kicked || (g.conn === 'closed' && g.closeCode !== null)) {
    const code = g.closeCode
    const [title, body, retry] = kicked
      ? [
          t('play.kicked', 'You were removed from the game'),
          t('play.kickedBody', 'The teacher removed you. You can join again with a new nickname.'),
          false,
        ]
      : code === 4404
        ? [
            t('play.gone', 'This game has ended'),
            t('play.goneBody', 'The game was not found. It may be over.'),
            false,
          ]
        : code === 4401 || code === 4403
          ? [
              t('play.expired', 'Your session expired'),
              t('play.expiredBody', 'Please join the game again.'),
              false,
            ]
          : code === 4409
            ? [
                t('play.replaced', 'Open in another tab'),
                t('play.replacedBody', 'You joined from another tab. Use this one instead?'),
                true,
              ]
            : [
                t('play.closed', 'Disconnected'),
                t('play.closedBody', 'Check your connection and try again.'),
                true,
              ]
    return (
      <div className="mx-auto grid min-h-screen max-w-lg place-items-center px-4">
        <Card className="w-full text-center">
          <h1 className="text-3xl font-extrabold">{title}</h1>
          <p className="mt-2 text-muted">{body}</p>
          <div className="mt-5 flex flex-wrap justify-center gap-3">
            {retry && (
              <Button onClick={() => setEpoch((e) => e + 1)}>{t('play.retry', 'Reconnect')}</Button>
            )}
            <Button variant={retry ? 'ghost' : 'primary'} onClick={leave}>
              {t('play.another', 'Join another game')}
            </Button>
          </div>
        </Card>
      </div>
    )
  }

  const phase = g.phase
  const paused = phase === 'paused'
  const notice = g.error
    ? (NOTICES[g.error] ?? t('err.generic', 'Something went wrong. Try again.'))
    : g.ackReason && g.ackReason !== 'duplicate'
      ? (NOTICES[g.ackReason] ?? '')
      : ''
  const q = g.question

  let body: React.ReactNode
  if (phase === null) {
    body = (
      <div className="grid place-items-center py-24">
        <Spinner />
      </div>
    )
  } else if (phase === 'lobby' || phase === 'created') {
    body = (
      <Card className="mt-6 text-center">
        <p className="text-6xl" aria-hidden="true">
          {me.avatar ?? '🙂'}
        </p>
        <h1 className="mt-2 text-3xl font-extrabold">
          {t('play.in', 'You are in, {{name}}!', { name: me.nickname })}
        </h1>
        <p className="mt-2 text-lg text-muted">
          {t('play.lookUp', 'Watch the big screen. The game starts when the teacher is ready.')}
        </p>
        <p className="tabular mt-4 font-display text-2xl font-extrabold" aria-live="polite">
          {g.playersCount}{' '}
          {g.playersCount === 1 ? t('play.player', 'player') : t('play.players', 'players')}
        </p>
        <Button variant="ghost" className="mt-6" onClick={leave}>
          {t('play.leave', 'Leave game')}
        </Button>
      </Card>
    )
  } else if (phase === 'finished' || phase === 'archived') {
    body = (
      <PlayerFinal
        me={g.me}
        title={g.title}
        podium={g.podium}
        meId={me.player_id}
        reason={g.finishReason}
        onLeave={leave}
      />
    )
  } else if (phase === 'leaderboard') {
    const mine = g.leaderboard.find((e) => e.player_id === me.player_id)
    body = (
      <div className="space-y-4">
        <h1 className="text-3xl font-extrabold">{t('lb.title', 'Leaderboard')}</h1>
        <Leaderboard entries={g.leaderboard} meId={me.player_id} limit={5} />
        {!mine && g.you?.rank && (
          <p className="tabular rounded-xl border border-signal bg-signal/20 px-4 py-3 text-center font-bold">
            {t('play.you', 'You')}: #{g.you.rank} · {g.you.score.toLocaleString()}
          </p>
        )}
        <p className="text-center text-muted">
          {g.isLast
            ? t('play.finalNext', 'Final results are next.')
            : t('play.nextUp', 'Next question coming up…')}
        </p>
      </div>
    )
  } else if (q && (phase === 'question_active' || paused)) {
    const answered = g.myChoice !== null
    body = (
      <div className="space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="tabular font-bold text-muted">
              {t('host.qOf', 'Question {{n}} of {{total}}', { n: q.index + 1, total: q.total })}
            </p>
            <h1 className="mt-1 break-words text-2xl font-extrabold sm:text-3xl">{q.text}</h1>
          </div>
          <CountdownRing remainingMs={remaining} totalMs={q.time_limit_sec * 1000} size={84} />
        </div>
        {paused && (
          <p
            role="status"
            className="rounded-xl bg-signal px-4 py-3 text-center text-lg font-extrabold text-[#0f1b33]"
          >
            ⏸ {t('play.paused', 'Game paused')}
          </p>
        )}
        <AnswerPad
          question={q}
          chosen={g.myChoice}
          disabled={paused || g.conn !== 'open'}
          onSubmit={answer}
        />
        {answered && (
          <p role="status" className="text-center text-lg font-bold" aria-live="polite">
            ✓ {t('play.locked', 'Answer locked in. Wait for the result…')}
          </p>
        )}
      </div>
    )
  } else if (q && phase === 'question_closed') {
    body = <ResultPanel question={q} reveal={g.reveal} you={g.you} myChoice={g.myChoice} />
  } else {
    body = (
      <div className="grid place-items-center py-24">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <ConnectionBanner status={g.conn} />
      <header className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-4">
        <Logo />
        <div className="flex items-center gap-3">
          <span className="hidden max-w-[10rem] truncate font-bold sm:inline">
            {me.avatar} {me.nickname}
          </span>
          {g.you && phase !== 'finished' && (
            <span className="tabular rounded-full bg-ink px-3 py-1 font-display font-bold text-paper">
              {g.you.score.toLocaleString()}
            </span>
          )}
          <Toggles />
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 pb-16">
        {notice && (
          <div className="mb-4">
            <ErrorNote>{notice}</ErrorNote>
          </div>
        )}
        {body}
      </main>
    </div>
  )
}
