import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { Button, Card, Empty, ErrorNote, Spinner } from '../components/ui'
import { ApiError, api } from '../lib/api'
import type { QuizSummary, SessionOut } from '../lib/types'

const LEVELS: Record<string, string> = {
  beginner: 'Beginner',
  intermediate: 'Intermediate',
  advanced: 'Advanced',
}

function errText(ex: unknown, fallback: string): string {
  return ex instanceof ApiError ? ex.message : fallback
}

export default function Dashboard() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const [quizzes, setQuizzes] = useState<QuizSummary[] | null>(null)
  const [live, setLive] = useState<SessionOut[]>([])
  const [q, setQ] = useState('')
  const [tag, setTag] = useState('')
  const [err, setErr] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      setErr('')
      setQuizzes(await api.listQuizzes(q.trim(), tag))
    } catch (ex) {
      setErr(errText(ex, t('err.generic', 'Something went wrong. Try again.')))
      setQuizzes((cur) => cur ?? [])
    }
  }, [q, tag, t])

  // Debounce so typing in the search box doesn't fire a request per keystroke.
  useEffect(() => {
    const id = setTimeout(() => void load(), 250)
    return () => clearTimeout(id)
  }, [load])

  useEffect(() => {
    api
      .listSessions()
      .then((rows) =>
        setLive(rows.filter((s) => ['created', 'lobby', 'active', 'paused'].includes(s.status))),
      )
      .catch(() => setLive([]))
  }, [])

  async function launch(id: string) {
    setBusyId(id)
    setErr('')
    try {
      const s = await api.createSession(id)
      nav(`/teacher/host/${s.id}`)
    } catch (ex) {
      setErr(errText(ex, t('err.generic', 'Something went wrong. Try again.')))
      setBusyId(null)
    }
  }

  async function duplicate(id: string) {
    setBusyId(id)
    try {
      await api.duplicateQuiz(id)
      await load()
    } catch (ex) {
      setErr(errText(ex, t('err.generic', 'Something went wrong. Try again.')))
    } finally {
      setBusyId(null)
    }
  }

  async function remove(id: string) {
    setBusyId(id)
    try {
      await api.deleteQuiz(id)
      setConfirmId(null)
      await load()
    } catch (ex) {
      setErr(errText(ex, t('err.generic', 'Something went wrong. Try again.')))
    } finally {
      setBusyId(null)
    }
  }

  async function onImport(file: File | undefined) {
    if (!file) return
    setErr('')
    try {
      const quiz = await api.importQuizCsv(
        file.name.replace(/\.csv$/i, '') || 'Imported quiz',
        await file.text(),
      )
      nav(`/teacher/quiz/${quiz.id}`)
    } catch (ex) {
      setErr(errText(ex, t('err.generic', 'Something went wrong. Try again.')))
    } finally {
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3 pt-4">
        <h1 className="text-4xl font-extrabold">{t('dash.title', 'My quizzes')}</h1>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          aria-label={t('dash.importFile', 'Choose a CSV file to import')}
          onChange={(e) => void onImport(e.target.files?.[0])}
        />
        <Button variant="ghost" onClick={() => fileRef.current?.click()}>
          {t('dash.import', 'Import CSV')}
        </Button>
        <Link
          to="/teacher/new"
          className="inline-flex min-h-[48px] items-center rounded-xl bg-signal px-6 font-display font-bold text-[#0f1b33] hover:brightness-95"
        >
          + {t('dash.new', 'New quiz')}
        </Link>
      </div>

      {live.length > 0 && (
        <Card className="border-signal">
          <h2 className="text-xl font-extrabold">{t('dash.live', 'Games in progress')}</h2>
          <ul className="mt-3 space-y-2">
            {live.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  <strong>{s.title || 'Quiz'}</strong>{' '}
                  <span className="tabular text-muted">PIN {s.pin}</span>
                </span>
                <Link className="font-bold underline" to={`/teacher/host/${s.id}`}>
                  {t('dash.reopen', 'Open host screen')}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <label className="min-w-[220px] flex-1">
          <span className="sr-only">{t('dash.search', 'Search quizzes')}</span>
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('dash.search', 'Search quizzes')}
            className="min-h-[48px] w-full rounded-xl border border-line bg-card px-4"
          />
        </label>
        {tag && (
          <button
            className="min-h-[44px] rounded-full border border-ink bg-signal/30 px-4 font-bold"
            onClick={() => setTag('')}
            aria-label={`Clear tag filter ${tag}`}
          >
            #{tag} ✕
          </button>
        )}
      </div>

      <ErrorNote>{err}</ErrorNote>

      {quizzes === null ? (
        <div className="grid place-items-center py-16">
          <Spinner />
        </div>
      ) : quizzes.length === 0 ? (
        q || tag ? (
          <Empty
            title={t('dash.noMatch', 'No quizzes match')}
            body={t('dash.noMatchBody', 'Try a different search.')}
          />
        ) : (
          <Empty
            title={t('dash.empty', 'No quizzes yet')}
            body={t(
              'dash.emptyBody',
              'Type a topic and the AI drafts a quiz for you in seconds. You can edit everything before going live.',
            )}
            action={
              <Link
                to="/teacher/new"
                className="inline-flex min-h-[48px] items-center rounded-xl bg-ink px-6 font-display font-bold text-paper"
              >
                {t('dash.createFirst', 'Create your first quiz')}
              </Link>
            }
          />
        )
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {quizzes.map((z) => (
            <li key={z.id}>
              <Card className="flex h-full flex-col gap-3">
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="text-2xl font-extrabold">{z.title}</h2>
                    <span
                      className={`shrink-0 rounded-full px-3 py-0.5 text-sm font-bold ${z.status === 'published' ? 'bg-good/15 text-good' : 'bg-ink/10 text-muted'}`}
                    >
                      {z.status === 'published'
                        ? t('dash.published', 'Published')
                        : t('dash.draft', 'Draft')}
                    </span>
                  </div>
                  <p className="text-muted">
                    {LEVELS[z.level] ?? z.level} · {z.question_count}{' '}
                    {t('dash.questions', 'questions')} ·{' '}
                    {new Date(z.updated_at).toLocaleDateString()}
                  </p>
                  {z.tags.length > 0 && (
                    <p className="mt-2 flex flex-wrap gap-2">
                      {z.tags.map((tg) => (
                        <button
                          key={tg}
                          onClick={() => setTag(tg)}
                          className="rounded-full border border-line px-3 text-sm hover:bg-ink/5"
                        >
                          #{tg}
                        </button>
                      ))}
                    </p>
                  )}
                </div>
                <div className="mt-auto flex flex-wrap gap-2">
                  <Button
                    variant="signal"
                    busy={busyId === z.id}
                    disabled={z.question_count === 0}
                    title={
                      z.question_count === 0 ? t('dash.noQs', 'Add questions first') : undefined
                    }
                    onClick={() => void launch(z.id)}
                  >
                    {t('dash.launch', 'Launch live')}
                  </Button>
                  <Link
                    to={`/teacher/quiz/${z.id}`}
                    className="inline-flex min-h-[44px] items-center rounded-xl border border-line px-5 font-display font-bold hover:bg-ink/5"
                  >
                    {t('dash.edit', 'Edit')}
                  </Link>
                  <Button
                    variant="ghost"
                    disabled={busyId === z.id}
                    onClick={() => void duplicate(z.id)}
                  >
                    {t('dash.duplicate', 'Duplicate')}
                  </Button>
                  {confirmId === z.id ? (
                    <>
                      <Button
                        variant="danger"
                        busy={busyId === z.id}
                        onClick={() => void remove(z.id)}
                      >
                        {t('dash.confirmDelete', 'Yes, delete')}
                      </Button>
                      <Button variant="ghost" onClick={() => setConfirmId(null)}>
                        {t('common.cancel', 'Cancel')}
                      </Button>
                    </>
                  ) : (
                    <Button variant="ghost" onClick={() => setConfirmId(z.id)}>
                      {t('dash.delete', 'Delete')}
                    </Button>
                  )}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
