import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { setLang } from '../i18n'
import { sound } from '../lib/sound'
import type { ConnStatus } from '../ws/client'
import { cx } from './ui'

function useTheme() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      const s = localStorage.getItem('lq.theme')
      if (s === 'dark' || s === 'light') return s
    } catch {
      /* ignore */
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('lq.theme', theme)
    } catch {
      /* ignore */
    }
  }, [theme])
  return [theme, setTheme] as const
}

export function Logo({ className }: { className?: string }) {
  return (
    <Link
      to="/"
      className={cx('flex items-center gap-2 font-display text-xl font-extrabold', className)}
    >
      <svg viewBox="0 0 64 64" className="h-8 w-8" aria-hidden="true">
        <rect width="64" height="64" rx="14" fill="#0f1b33" />
        <path d="M32 12 50 44H14z" fill="#ffc93c" />
        <circle cx="32" cy="38" r="5" fill="#0f1b33" />
      </svg>
      LiveQuiz
    </Link>
  )
}

export function Toggles() {
  const { t, i18n } = useTranslation()
  const [theme, setTheme] = useTheme()
  const [muted, setMuted] = useState(sound.isMuted())
  const btn =
    'grid h-11 min-w-[44px] place-items-center rounded-xl border border-line bg-card px-2 text-sm font-bold hover:bg-ink/5'
  return (
    <div className="flex gap-2">
      <button
        className={btn}
        onClick={() => setLang(i18n.language === 'ur' ? 'en' : 'ur')}
        aria-label={t('toggle.lang', 'Switch language')}
      >
        {i18n.language === 'ur' ? 'EN' : 'اردو'}
      </button>
      <button
        className={btn}
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        aria-label={t('toggle.theme', 'Switch light or dark mode')}
      >
        {theme === 'dark' ? '☀' : '☾'}
      </button>
      <button
        className={btn}
        aria-pressed={muted}
        onClick={() => {
          sound.setMuted(!muted)
          setMuted(!muted)
        }}
        aria-label={t('toggle.sound', 'Sound')}
      >
        {muted ? '🔇' : '🔊'}
      </button>
    </div>
  )
}

export function ConnectionBanner({ status }: { status: ConnStatus }) {
  const { t } = useTranslation()
  if (status === 'open') return null
  const text =
    status === 'closed'
      ? t('conn.closed', 'Disconnected')
      : t('conn.reconnecting', 'Connection lost. Reconnecting…')
  return (
    <div
      role="status"
      className="fixed inset-x-0 top-0 z-50 bg-signal px-4 py-2 text-center text-sm font-bold text-[#0f1b33]"
    >
      {status === 'connecting' ? t('conn.connecting', 'Connecting…') : text}
    </div>
  )
}

export function Shell({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4">
        <Logo />
        <Toggles />
      </header>
      <main className={cx('mx-auto px-4 pb-16', wide ? 'max-w-6xl' : 'max-w-3xl')}>{children}</main>
    </div>
  )
}
