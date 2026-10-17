import { useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { Shape } from '../components/Shapes'
import { Logo, Toggles } from '../components/Chrome'
import { Button, ErrorNote } from '../components/ui'
import { ApiError, api } from '../lib/api'
import { useAuth } from '../store/auth'

export default function Landing() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const user = useAuth((s) => s.user)
  const [pin, setPin] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function go(e: FormEvent) {
    e.preventDefault()
    setErr('')
    if (!/^\d{6}$/.test(pin)) return setErr(t('landing.pinFormat', 'A game PIN has 6 digits.'))
    setBusy(true)
    try {
      await api.lookupPin(pin)
      nav(`/join?pin=${pin}`)
    } catch (ex) {
      setErr(
        ex instanceof ApiError && ex.status === 404
          ? t(
              'landing.notFound',
              'No game with that PIN. Check the number on the teacher’s screen.',
            )
          : ex instanceof ApiError
            ? ex.message
            : t('err.generic', 'Something went wrong. Try again.'),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Logo />
        <div className="flex items-center gap-3">
          <Toggles />
          <Link
            to={user ? '/teacher' : '/login'}
            className="hidden min-h-[44px] items-center rounded-xl border border-line px-4 font-bold hover:bg-ink/5 sm:inline-flex"
          >
            {user ? t('nav.dashboard', 'My quizzes') : t('nav.login', 'Teacher log in')}
          </Link>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-10 px-4 pb-20 pt-8 md:grid-cols-[1.1fr_1fr] md:items-center md:pt-20">
        <form onSubmit={go} className="space-y-5" aria-label={t('landing.join', 'Join a game')}>
          <h1 className="text-5xl font-extrabold md:text-7xl">
            {t('landing.title', 'Enter the game PIN')}
          </h1>
          <label className="block">
            <span className="sr-only">{t('landing.pinLabel', 'Game PIN')}</span>
            <input
              inputMode="numeric"
              autoComplete="off"
              maxLength={6}
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
              placeholder="000000"
              aria-invalid={!!err || undefined}
              className="tabular w-full rounded-2xl border-2 border-ink bg-card px-6 py-5 text-center font-display text-5xl font-extrabold tracking-[0.25em] placeholder:text-line md:text-7xl"
            />
          </label>
          <ErrorNote>{err}</ErrorNote>
          <Button type="submit" variant="signal" big busy={busy} className="w-full">
            {t('landing.go', 'Join game')}
          </Button>
          <p className="text-muted">
            {t('landing.noAccount', 'No account needed. You only pick a nickname.')}
          </p>
        </form>

        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3" aria-hidden="true">
            {(['triangle', 'diamond', 'circle', 'square'] as const).map((s, i) => (
              <div
                key={s}
                className={`grid aspect-[4/3] place-items-center rounded-2xl text-white ${['bg-a1', 'bg-a2', 'bg-a3', 'bg-a4'][i]}`}
              >
                <Shape name={s} className="h-12 w-12" />
              </div>
            ))}
          </div>
          <div className="rounded-2xl border border-line bg-card p-5">
            <h2 className="text-2xl font-extrabold">
              {t('landing.teacherTitle', 'Teaching? Make a quiz from a topic.')}
            </h2>
            <p className="mt-2 text-muted">
              {t(
                'landing.teacherBody',
                'Type a topic, level and learning goal. The quiz is ready in seconds, and you can edit every question before you go live.',
              )}
            </p>
            <Link
              to="/signup"
              className="mt-4 inline-flex min-h-[44px] items-center rounded-xl bg-ink px-5 font-display font-bold text-paper"
            >
              {t('landing.teacherCta', 'Create a free teacher account')}
            </Link>
          </div>
        </div>
      </main>
    </div>
  )
}
