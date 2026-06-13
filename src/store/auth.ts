// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { create } from 'zustand'

import { api } from '../services/api'

interface AuthState {
  token: string | null
  email: string | null
  isAdmin: boolean
  login: (email: string, password: string) => Promise<void>
  register: (body: {
    email: string; password: string; locale: string
    first_name?: string; last_name?: string
  }) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

export const useAuth = create<AuthState>((set) => ({
  token: localStorage.getItem('xcape_token'),
  email: null,
  isAdmin: false,

  login: async (email, password) => {
    const { access_token } = await api.login(email, password)
    localStorage.setItem('xcape_token', access_token)
    set({ token: access_token })
    const me = await api.me()
    set({ email: me.email, isAdmin: me.is_admin })
  },

  register: async (body) => {
    const { access_token } = await api.register(body)
    localStorage.setItem('xcape_token', access_token)
    set({ token: access_token })
    const me = await api.me()
    set({ email: me.email, isAdmin: me.is_admin })
  },

  logout: () => {
    localStorage.removeItem('xcape_token')
    set({ token: null, email: null, isAdmin: false })
  },

  refresh: async () => {
    try {
      const me = await api.me()
      set({ email: me.email, isAdmin: me.is_admin })
    } catch {
      localStorage.removeItem('xcape_token')
      set({ token: null, email: null, isAdmin: false })
    }
  },
}))
