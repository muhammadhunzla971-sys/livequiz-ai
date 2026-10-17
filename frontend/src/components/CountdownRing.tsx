import { useEffect, useState } from 'react'

/** Seconds left on the server clock. `skew` = serverTime - clientTime. */
export function useCountdown(endAt: number, skew: () => number, frozenMs: number | null): number {
  const [now, setNow] = useState(() => Date.now() + skew())
  useEffect(() => {
    if (frozenMs !== null) return
    const id = setInterval(() => setNow(Date.now() + skew()), 100)
    return () => clearInterval(id)
  }, [skew, frozenMs])
  return frozenMs !== null ? frozenMs : Math.max(0, endAt - now)
}

export function CountdownRing({
  remainingMs,
  totalMs,
  size = 96,
}: {
  remainingMs: number
  totalMs: number
  size?: number
}) {
  const r = (size - 10) / 2
  const c = 2 * Math.PI * r
  const frac = totalMs > 0 ? Math.min(1, remainingMs / totalMs) : 0
  const secs = Math.ceil(remainingMs / 1000)
  const urgent = secs <= 5
  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="timer"
      aria-label={`${secs} seconds left`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="rgb(var(--line))"
          strokeWidth="8"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={urgent ? 'rgb(var(--bad))' : 'rgb(var(--signal))'}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - frac)}
          style={{ transition: 'stroke-dashoffset 120ms linear' }}
        />
      </svg>
      <span
        aria-hidden="true"
        className="tabular absolute inset-0 grid place-items-center font-display text-3xl font-extrabold"
      >
        {secs}
      </span>
    </div>
  )
}
