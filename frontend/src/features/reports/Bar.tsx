import { cx } from '../../components/ui'

/** One thin horizontal bar: track + rounded fill. Pure display; the number is shown beside it. */
export function Bar({
  pct,
  className = 'bg-a1',
  label,
}: {
  pct: number
  className?: string
  label: string
}) {
  const w = Math.max(0, Math.min(100, pct))
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={w}
      className="h-2.5 w-full overflow-hidden rounded-full bg-ink/10"
    >
      <div className={cx('h-full rounded-full', className)} style={{ width: `${w}%` }} />
    </div>
  )
}

export function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-card p-4">
      <p className="text-sm font-bold text-muted">{label}</p>
      <p className="tabular mt-1 font-display text-3xl font-extrabold">{value}</p>
      {hint && <p className="text-sm text-muted">{hint}</p>}
    </div>
  )
}
