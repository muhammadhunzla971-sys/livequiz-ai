import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Button, Empty, ErrorNote, Spinner } from '../components/ui'
import { ApiError, api } from '../lib/api'
import type { ReportListItem } from '../lib/types'

export default function Reports() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<ReportListItem[] | null>(null)
  const [err, setErr] = useState('')
  const [confirm, setConfirm] = useState<string | null>(null)

  useEffect(() => {
    api
      .listReports()
      .then(setRows)
      .catch((ex) => {
        setErr(
          ex instanceof ApiError
            ? ex.message
            : t('err.generic', 'Something went wrong. Try again.'),
        )
        setRows([])
      })
  }, [t])

  async function remove(id: string) {
    try {
      await api.deleteSession(id)
      setRows((r) => (r ?? []).filter((x) => x.id !== id))
    } catch {
      setErr(t('err.generic', 'Something went wrong. Try again.'))
    } finally {
      setConfirm(null)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-4xl font-extrabold">{t('reports.title', 'Past games')}</h1>
      <ErrorNote>{err}</ErrorNote>
      {rows === null ? (
        <div className="grid place-items-center py-16">
          <Spinner />
        </div>
      ) : rows.length === 0 ? (
        <Empty
          title={t('reports.none', 'No finished games yet')}
          body={t('reports.noneBody', 'Run a live game and its report will appear here.')}
          action={
            <Link
              to="/teacher"
              className="inline-flex min-h-[44px] items-center rounded-xl bg-ink px-5 font-display font-bold text-paper"
            >
              {t('nav.dashboard', 'My quizzes')}
            </Link>
          }
        />
      ) : (
        <ul className="space-y-3">
          {rows.map((r) => (
            <li
              key={r.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-card p-4"
            >
              <div className="min-w-0">
                <p className="truncate text-xl font-extrabold">{r.title}</p>
                <p className="tabular text-muted">
                  {new Date(r.created_at).toLocaleString()} · {r.players}{' '}
                  {r.players === 1 ? t('play.player', 'player') : t('play.players', 'players')}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  to={`/teacher/reports/${r.id}`}
                  className="inline-flex min-h-[44px] items-center rounded-xl bg-ink px-5 font-display font-bold text-paper"
                >
                  {t('reports.open', 'Open report')}
                </Link>
                {confirm === r.id ? (
                  <>
                    <Button variant="danger" onClick={() => void remove(r.id)}>
                      {t('reports.yesDelete', 'Yes, delete')}
                    </Button>
                    <Button variant="ghost" onClick={() => setConfirm(null)}>
                      {t('common.cancel', 'Cancel')}
                    </Button>
                  </>
                ) : (
                  <Button variant="ghost" onClick={() => setConfirm(r.id)}>
                    {t('reports.delete', 'Delete')}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
