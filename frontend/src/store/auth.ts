import { create } from 'zustand'
import { api, tokens } from '../lib/api'

interface AuthState {
  user: { id: string; email: string; display_name: string } | null
  loading: boolean
  load: () => Promise<void>
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string, name: string) => Promise<void>
  signOut: () => void
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loading: tokens.hasSession(),
  load: async () => {
    if (!tokens.hasSession()) return set({ loading: false, user: null })
    try {
      set({ user: await api.me(), loading: false })
    } catch {
      set({ user: null, loading: false })
    }
  },
  signIn: async (email, password) => {
    const t = await api.login(email, password)
    tokens.set(t.access_token, t.refresh_token)
    set({ user: await api.me() })
  },
  signUp: async (email, password, name) => {
    const t = await api.register(email, password, name)
    tokens.set(t.access_token, t.refresh_token)
    set({ user: await api.me() })
  },
  signOut: () => {
    tokens.clear()
    set({ user: null })
  },
}))
