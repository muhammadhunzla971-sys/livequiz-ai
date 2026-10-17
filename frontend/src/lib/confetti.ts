import confetti from 'canvas-confetti'

let running = false

export function celebrate(): void {
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
  running = true
  const end = Date.now() + 1500
  const colors = ['#ffc93c', '#2563eb', '#0d9488', '#c026d3']
  const frame = () => {
    if (!running) return
    confetti({ particleCount: 4, angle: 60, spread: 60, origin: { x: 0 }, colors })
    confetti({ particleCount: 4, angle: 120, spread: 60, origin: { x: 1 }, colors })
    if (Date.now() < end) requestAnimationFrame(frame)
  }
  frame()
}

/** Stops the burst and clears confetti still on screen, e.g. when the page is left. */
export function stopConfetti(): void {
  running = false
  confetti.reset()
}
