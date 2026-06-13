// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

// IMPORTANT — this store is a SHORT-TERM CACHE, never a source of truth.
// The server owns all state. `token` is the only durable client value (a credential).
// The cached identity (name/email/isAdmin) is re-read from /auth/me on app mount and
// after any identity mutation; `isAdmin` only toggles UI — every privileged action is
// authorised server-side. Do NOT put application state (profile, searches, candidates,
// places, …) here; fetch it from the server per view and re-read when freshness is in
// doubt.

import { create } from 'zustand'

import { api } from '../services/api'

interface AuthState {
  token: string | null
  email: string | null
  firstName: string | null
  lastName: string | null
  isAdmin: boolean
  login: (email: string, password: string) => Promise<void>
  register: (body: {
    email: string; password: string; locale: string
    first_name?: string; last_name?: string
  }) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

function setFromMe(me: {
  email: string; is_admin: boolean; first_name?: string; last_name?: string
}) {
  return {
    email: me.email,
    isAdmin: me.is_admin,
    firstName: me.first_name ?? null,
    lastName: me.last_name ?? null,
  }
}

export const useAuth = create<AuthState>((set) => ({
  token: localStorage.getItem('xcape_token'),
  email: null,
  firstName: null,
  lastName: null,
  isAdmin: false,

  login: async (email, password) => {
    const { access_token } = await api.login(email, password)
    localStorage.setItem('xcape_token', access_token)
    set({ token: access_token })
    set(setFromMe(await api.me()))
  },

  register: async (body) => {
    const { access_token } = await api.register(body)
    localStorage.setItem('xcape_token', access_token)
    set({ token: access_token })
    set(setFromMe(await api.me()))
  },

  logout: () => {
    localStorage.removeItem('xcape_token')
    set({ token: null, email: null, firstName: null, lastName: null, isAdmin: false })
  },

  refresh: async () => {
    try {
      set(setFromMe(await api.me()))
    } catch {
      localStorage.removeItem('xcape_token')
      set({ token: null, email: null, firstName: null, lastName: null, isAdmin: false })
    }
  },
}))
