/**
 * Where the backend lives. Empty in local dev (Vite proxies /api and /ws to localhost:8000).
 * In production set VITE_API_URL (e.g. https://livequiz-api.onrender.com) on the frontend host.
 * WebSockets cannot go through Vercel rewrites, so they connect straight to the backend.
 */
export const API_BASE: string = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export function wsBase(): string {
  if (API_BASE) return API_BASE.replace(/^http/, 'ws')
  return `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`
}
