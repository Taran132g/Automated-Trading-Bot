import { create } from 'zustand'

interface AuthState {
  token: string | null
  authenticated: boolean
  setToken: (token: string) => void
  clearToken: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('quant_token'),
  authenticated: !!localStorage.getItem('quant_token'),
  setToken: (token) => {
    localStorage.setItem('quant_token', token)
    set({ token, authenticated: true })
  },
  clearToken: () => {
    localStorage.removeItem('quant_token')
    set({ token: null, authenticated: false })
  },
}))
