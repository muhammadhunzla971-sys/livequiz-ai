import { useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { Shell } from '../components/Chrome'
import { Button, Card, ErrorNote, Input } from '../components/ui'
import { ApiError } from '../lib/api'
import { useAuth } from '../store/auth'

export default function Auth({ mode }: { mode: 'login' | 'signup' }) {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { signIn, signUp } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const signup = mode === 'signup'

  async function submit(e: FormEvent) {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      if (signup) await signUp(email, password, name)
      else await signIn(email, password)
      nav('/teacher')
    } catch (ex) {
      setErr(
        ex instanceof ApiError
          ? ex.status === 401
            ? t('auth.badCreds', 'Email or password is incorrect.')
            : ex.status === 409
              ? t('auth.exists', 'That email already has an account. Log in instead.')
              : ex.message
          : t('err.generic', 'Something went wrong. Try again.'),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell>
      <Card className="mx-auto mt-8 max-w-md">
        <h1 className="mb-5 text-3xl font-extrabold">
          {signup
            ? t('auth.signupTitle', 'Create your teacher account')
            : t('auth.loginTitle', 'Log in')}
        </h1>
        <form onSubmit={submit} className="space-y-4">
          {signup && (
            <Input
              label={t('auth.name', 'Your name')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoComplete="name"
            />
          )}
          <Input
            label={t('auth.email', 'Email')}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
          <Input
            label={t('auth.password', 'Password')}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={signup ? 8 : 1}
            hint={signup ? t('auth.passwordHint', 'At least 8 characters.') : undefined}
            autoComplete={signup ? 'new-password' : 'current-password'}
          />
          <ErrorNote>{err}</ErrorNote>
          <Button type="submit" busy={busy} className="w-full">
            {signup ? t('auth.signup', 'Create account') : t('auth.login', 'Log in')}
          </Button>
        </form>
        <p className="mt-4 text-muted">
          {signup ? (
            <>
              {t('auth.haveAccount', 'Already have an account?')}{' '}
              <Link className="font-bold text-ink underline" to="/login">
                {t('auth.login', 'Log in')}
              </Link>
            </>
          ) : (
            <>
              {t('auth.noAccount', 'New here?')}{' '}
              <Link className="font-bold text-ink underline" to="/signup">
                {t('auth.signup', 'Create account')}
              </Link>
            </>
          )}
        </p>
      </Card>
    </Shell>
  )
}
