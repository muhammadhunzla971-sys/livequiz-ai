import { forwardRef } from 'react'
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from 'react'

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

type Variant = 'primary' | 'ghost' | 'danger' | 'signal'
const variants: Record<Variant, string> = {
  primary: 'bg-ink text-paper hover:opacity-90',
  signal: 'bg-signal text-[#0f1b33] hover:brightness-95',
  ghost: 'bg-transparent text-ink border border-line hover:bg-ink/5',
  danger: 'bg-bad text-paper hover:opacity-90',
}

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; big?: boolean; busy?: boolean }
>(function Button({ variant = 'primary', big, busy, className, children, disabled, ...rest }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl px-5 font-display font-bold transition disabled:cursor-not-allowed disabled:opacity-50',
        big && 'min-h-[56px] px-8 text-xl',
        variants[variant],
        className,
      )}
      {...rest}
    >
      {busy && <Spinner small />}
      {children}
    </button>
  )
})

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string }
>(function Input({ label, hint, error, id, className, ...rest }, ref) {
  const fid = id ?? `f-${label.replace(/\W+/g, '-').toLowerCase()}`
  return (
    <label htmlFor={fid} className="block">
      <span className="mb-1 block text-sm font-bold">{label}</span>
      <input
        ref={ref}
        id={fid}
        aria-invalid={!!error || undefined}
        aria-describedby={error ? `${fid}-err` : hint ? `${fid}-hint` : undefined}
        className={cx(
          'min-h-[48px] w-full rounded-xl border bg-card px-4 text-ink placeholder:text-muted',
          error ? 'border-bad' : 'border-line',
          className,
        )}
        {...rest}
      />
      {hint && !error && (
        <span id={`${fid}-hint`} className="mt-1 block text-sm text-muted">
          {hint}
        </span>
      )}
      {error && (
        <span id={`${fid}-err`} role="alert" className="mt-1 block text-sm text-bad">
          {error}
        </span>
      )}
    </label>
  )
})

export function Select({
  label,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-bold">{label}</span>
      <select
        className="min-h-[48px] w-full rounded-xl border border-line bg-card px-3 text-ink"
        {...rest}
      >
        {children}
      </select>
    </label>
  )
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx('rounded-2xl border border-line bg-card p-5', className)}>{children}</div>
  )
}

export function Spinner({ small }: { small?: boolean }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cx(
        'inline-block animate-spin rounded-full border-2 border-current border-t-transparent',
        small ? 'h-4 w-4' : 'h-8 w-8',
      )}
    />
  )
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null
  return (
    <p role="alert" className="rounded-xl border border-bad/40 bg-bad/10 px-4 py-3 text-bad">
      {children}
    </p>
  )
}

export function Empty({
  title,
  body,
  action,
}: {
  title: string
  body?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-line px-6 py-14 text-center">
      <h2 className="text-2xl font-extrabold">{title}</h2>
      {body && <p className="max-w-md text-muted">{body}</p>}
      {action}
    </div>
  )
}

export { cx }
