import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { Logo, Toggles } from './Chrome'
import { Spinner } from './ui'

/** Guards teacher routes and renders the shared header. */
export default function TeacherShell({ bare }: { bare?: boolean }) {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { user, loading, load, signOut } = useAuth()

  useEffect(() => {
    void load()
  }, [load])

  if (loading)
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner />
      </div>
    )
  if (!user) return <Navigate to="/login" replace />
  if (bare) return <Outlet />

  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4">
        <div className="flex items-center gap-6">
          <Logo />
          <nav aria-label="Teacher" className="flex gap-5">
            <Link to="/teacher" className="font-bold hover:underline">
              {t('nav.dashboard', 'My quizzes')}
            </Link>
            <Link to="/teacher/reports" className="font-bold hover:underline">
              {t('nav.reports', 'Past games')}
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-muted sm:inline">{user.display_name}</span>
          <Toggles />
          <button
            className="min-h-[44px] rounded-xl border border-line px-4 font-bold hover:bg-ink/5"
            onClick={() => {
              signOut()
              nav('/')
            }}
          >
            {t('nav.logout', 'Log out')}
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 pb-20">
        <Outlet />
      </main>
    </div>
  )
}
