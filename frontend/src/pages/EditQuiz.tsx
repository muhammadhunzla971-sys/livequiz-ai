import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button, Card, ErrorNote, Input, Select, Spinner } from '../components/ui'
import { ApiError, api } from '../lib/api'
import type { Level, Quiz, QuestionType } from '../lib/types'
import QuestionEditor from '../features/quiz-editor/QuestionEditor'
import { saveBlob } from '../features/reports/format'
import {
  type EditableQuestion,
  fromQuiz,
  moveItem,
  newQuestion,
  toPayload,
  validateQuestion,
} from '../features/quiz-editor/model'

interface Meta {
  title: string
  topic: string
  level: Level
  learning_goal: string
  language: string
  tags: string
  base_points: number
  speed_bonus: boolean
  streak_step_pct: number
  streak_cap_pct: number
}

function toMeta(q: Quiz): Meta {
  const sc = q.scoring_config
  return {
    title: q.title,
    topic: q.topic,
    level: q.level,
    learning_goal: q.learning_goal,
    language: q.language,
    tags: q.tags.join(', '),
    base_points: Number(sc.base_points ?? 1000),
    speed_bonus: sc.speed_bonus !== false,
    streak_step_pct: Math.round(Number(sc.streak_step ?? 0.1) * 100),
    streak_cap_pct: Math.round(Number(sc.streak_cap ?? 0.5) * 100),
  }
}

const snapshot = (m: Meta, qs: EditableQuestion[]) => JSON.stringify([m, qs.map(toPayload)])

export default function EditQuiz() {
  const { quizId = '' } = useParams()
  const { t } = useTranslation()
  const nav = useNavigate()
  const [quiz, setQuiz] = useState<Quiz | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [questions, setQuestions] = useState<EditableQuestion[]>([])
  const [saved, setSaved] = useState('')
  const [loadErr, setLoadErr] = useState('')
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState<'save' | 'publish' | 'launch' | string | null>(null)

  const apply = useCallback((q: Quiz) => {
    const m = toMeta(q)
    const qs = fromQuiz(q)
    setQuiz(q)
    setMeta(m)
    setQuestions(qs)
    setSaved(snapshot(m, qs))
  }, [])

  useEffect(() => {
    api
      .getQuiz(quizId)
      .then(apply)
      .catch((ex) =>
        setLoadErr(
          ex instanceof ApiError && ex.status === 404
            ? t('edit.notFound', 'This quiz does not exist or belongs to another account.')
            : t('err.generic', 'Something went wrong. Try again.'),
        ),
      )
  }, [quizId, apply, t])

  const dirty = meta !== null && snapshot(meta, questions) !== saved
  const problems = useMemo(
    () => questions.reduce((n, q) => n + (validateQuestion(q).length ? 1 : 0), 0),
    [questions],
  )

  useEffect(() => {
    if (!dirty) return
    const h = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', h)
    return () => window.removeEventListener('beforeunload', h)
  }, [dirty])

  async function save(status?: 'draft' | 'published'): Promise<Quiz | null> {
    if (!meta) return null
    setErr('')
    setNote('')
    try {
      const body = {
        title: meta.title.trim() || 'Untitled quiz',
        topic: meta.topic.trim() || 'General',
        level: meta.level,
        learning_goal: meta.learning_goal.trim(),
        language: meta.language,
        tags: meta.tags
          .split(',')
          .map((x) => x.trim())
          .filter(Boolean),
        scoring_config: {
          base_points: meta.base_points,
          speed_bonus: meta.speed_bonus,
          streak_step: meta.streak_step_pct / 100,
          streak_cap: meta.streak_cap_pct / 100,
        },
        questions: questions.map(toPayload),
        ...(status ? { status } : {}),
      }
      const out = await api.updateQuiz(quizId, body)
      apply(out)
      return out
    } catch (ex) {
      setErr(
        ex instanceof ApiError ? ex.message : t('err.generic', 'Something went wrong. Try again.'),
      )
      return null
    }
  }

  async function onExport() {
    setErr('')
    try {
      saveBlob(await api.exportQuizCsv(quizId), `quiz-${quizId.slice(0, 8)}.csv`)
      setNote(t('edit.exported', 'Exported the last saved version.'))
    } catch (ex) {
      setErr(
        ex instanceof ApiError ? ex.message : t('err.generic', 'Something went wrong. Try again.'),
      )
    }
  }

  async function onSave(status?: 'draft' | 'published') {
    setBusy(status === 'published' ? 'publish' : 'save')
    const out = await save(status)
    if (out)
      setNote(
        status === 'published' ? t('edit.published', 'Published.') : t('edit.saved', 'Saved.'),
      )
    setBusy(null)
  }

  async function launch() {
    setBusy('launch')
    if (dirty && !(await save())) return setBusy(null)
    try {
      const s = await api.createSession(quizId)
      nav(`/teacher/host/${s.id}`)
    } catch (ex) {
      setErr(
        ex instanceof ApiError ? ex.message : t('err.generic', 'Something went wrong. Try again.'),
      )
      setBusy(null)
    }
  }

  async function regenerate(q: EditableQuestion, feedback: string) {
    if (!q.id) return
    setBusy(q.key)
    // The server regenerates from its own copy, so unsaved edits must be saved first.
    if (dirty && !(await save())) return setBusy(null)
    try {
      apply(await api.regenerateQuestion(quizId, q.id, feedback))
      setNote(t('edit.regenDone', 'Question replaced.'))
    } catch (ex) {
      setErr(
        ex instanceof ApiError ? ex.message : t('err.generic', 'Something went wrong. Try again.'),
      )
    }
    setBusy(null)
  }

  const addQ = (type: QuestionType) => setQuestions((cur) => [...cur, newQuestion(type)])

  if (loadErr)
    return (
      <Card className="mt-8 text-center">
        <p className="text-bad">{loadErr}</p>
        <Link to="/teacher" className="mt-4 inline-block font-bold underline">
          {t('edit.back', 'Back to my quizzes')}
        </Link>
      </Card>
    )
  if (!quiz || !meta)
    return (
      <div className="grid place-items-center py-24">
        <Spinner />
      </div>
    )

  const set = <K extends keyof Meta>(k: K, v: Meta[K]) => setMeta({ ...meta, [k]: v })
  const blocked = problems > 0 || questions.length === 0

  return (
    <div className="space-y-6 pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to="/teacher" className="text-muted underline">
            ← {t('edit.back', 'Back to my quizzes')}
          </Link>
          <h1 className="mt-1 text-4xl font-extrabold">{t('edit.title', 'Review and edit')}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`rounded-full px-3 py-1 text-sm font-bold ${quiz.status === 'published' ? 'bg-good/15 text-good' : 'bg-ink/10 text-muted'}`}
          >
            {quiz.status === 'published'
              ? t('dash.published', 'Published')
              : t('dash.draft', 'Draft')}
          </span>
          {dirty && (
            <span className="text-sm font-bold text-bad">
              {t('edit.unsaved', 'Unsaved changes')}
            </span>
          )}
        </div>
      </div>

      <Card className="space-y-4">
        <Input
          label={t('edit.quizTitle', 'Quiz title')}
          value={meta.title}
          maxLength={200}
          onChange={(e) => set('title', e.target.value)}
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <Input
            label={t('create.topic', 'Topic')}
            value={meta.topic}
            maxLength={300}
            onChange={(e) => set('topic', e.target.value)}
          />
          <Select
            label={t('create.level', 'Level')}
            value={meta.level}
            onChange={(e) => set('level', e.target.value as Level)}
          >
            <option value="beginner">Beginner</option>
            <option value="intermediate">Intermediate</option>
            <option value="advanced">Advanced</option>
          </Select>
          <Input
            label={t('edit.tags', 'Tags')}
            value={meta.tags}
            onChange={(e) => set('tags', e.target.value)}
            hint={t('edit.tagsHint', 'Comma separated, e.g. biology, grade 8')}
          />
        </div>
        <details>
          <summary className="min-h-[44px] cursor-pointer py-2 font-bold">
            {t('edit.scoring', 'Scoring rules')}
          </summary>
          <div className="mt-2 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Input
              label={t('edit.base', 'Base points')}
              type="number"
              min={0}
              max={10000}
              value={meta.base_points}
              onChange={(e) => set('base_points', Number(e.target.value))}
            />
            <Input
              label={t('edit.streak', 'Streak bonus per answer (%)')}
              type="number"
              min={0}
              max={100}
              value={meta.streak_step_pct}
              onChange={(e) => set('streak_step_pct', Number(e.target.value))}
            />
            <Input
              label={t('edit.cap', 'Streak bonus cap (%)')}
              type="number"
              min={0}
              max={200}
              value={meta.streak_cap_pct}
              onChange={(e) => set('streak_cap_pct', Number(e.target.value))}
            />
            <label className="flex min-h-[48px] items-center gap-2 self-end font-bold">
              <input
                type="checkbox"
                checked={meta.speed_bonus}
                onChange={(e) => set('speed_bonus', e.target.checked)}
              />
              {t('edit.speed', 'Faster answers earn more')}
            </label>
          </div>
        </details>
      </Card>

      <section aria-labelledby="qs">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 id="qs" className="text-2xl font-extrabold">
            {t('edit.questions', 'Questions')} ({questions.length})
          </h2>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => addQ('mcq')}>
              + {t('edit.addMcq', 'Multiple choice')}
            </Button>
            <Button variant="ghost" onClick={() => addQ('true_false')}>
              + {t('edit.addTf', 'True / False')}
            </Button>
            <Button variant="ghost" onClick={() => addQ('multi_select')}>
              + {t('edit.addMulti', 'Multi-select')}
            </Button>
          </div>
        </div>
        {questions.length === 0 ? (
          <Card className="text-center text-muted">
            {t('edit.noQs', 'No questions yet. Add one with the buttons above.')}
          </Card>
        ) : (
          <ul className="space-y-3">
            {questions.map((q, i) => (
              <QuestionEditor
                key={q.key}
                q={q}
                index={i}
                total={questions.length}
                defaultOpen={i === 0 && questions.length === 1}
                busy={busy === q.key}
                onChange={(next) =>
                  setQuestions((cur) => cur.map((x) => (x.key === q.key ? next : x)))
                }
                onMove={(dir) => setQuestions((cur) => moveItem(cur, i, dir))}
                onDelete={() => setQuestions((cur) => cur.filter((x) => x.key !== q.key))}
                onRegenerate={q.id ? (fb) => void regenerate(q, fb) : undefined}
              />
            ))}
          </ul>
        )}
      </section>

      <div className="sticky bottom-0 -mx-4 space-y-2 border-t border-line bg-paper/95 px-4 py-3 backdrop-blur">
        <ErrorNote>{err}</ErrorNote>
        {problems > 0 && (
          <p className="text-bad" role="status">
            {t('edit.fix', 'Fix the {{n}} question(s) marked in red before saving.', {
              n: problems,
            })}
          </p>
        )}
        {note && !err && (
          <p className="font-bold text-good" role="status">
            {note}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <Button busy={busy === 'save'} disabled={blocked || !dirty} onClick={() => void onSave()}>
            {t('edit.save', 'Save')}
          </Button>
          <Button
            variant="ghost"
            busy={busy === 'publish'}
            disabled={blocked || (!dirty && quiz.status === 'published')}
            onClick={() => void onSave('published')}
          >
            {t('edit.publish', 'Save and publish')}
          </Button>
          <Button variant="ghost" onClick={() => void onExport()}>
            {t('edit.export', 'Export CSV')}
          </Button>
          {quiz.status === 'published' && (
            <Button variant="ghost" disabled={blocked} onClick={() => void onSave('draft')}>
              {t('edit.unpublish', 'Move back to draft')}
            </Button>
          )}
          <Button
            variant="signal"
            busy={busy === 'launch'}
            disabled={blocked}
            onClick={() => void launch()}
          >
            {t('dash.launch', 'Launch live')}
          </Button>
        </div>
      </div>
    </div>
  )
}
