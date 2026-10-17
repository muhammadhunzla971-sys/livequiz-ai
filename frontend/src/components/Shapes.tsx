import { cx } from './ui'

/** Colour + shape coding so answers are distinguishable without relying on colour alone. */
export const ANSWER_STYLES = [
  { bg: 'bg-a1', shape: 'triangle' },
  { bg: 'bg-a2', shape: 'diamond' },
  { bg: 'bg-a3', shape: 'circle' },
  { bg: 'bg-a4', shape: 'square' },
  { bg: 'bg-a5', shape: 'hexagon' },
] as const

const paths: Record<string, string> = {
  triangle: 'M12 3 22 20H2z',
  diamond: 'M12 2 22 12 12 22 2 12z',
  circle: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z',
  square: 'M4 4h16v16H4z',
  hexagon: 'M12 2 21 7v10l-9 5-9-5V7z',
}

export function Shape({ name, className }: { name: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={cx('h-7 w-7 fill-current', className)}>
      <path d={paths[name]} />
    </svg>
  )
}
