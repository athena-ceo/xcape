// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8030'

function token(): string | null {
  return localStorage.getItem('xcape_token')
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  const t = token()
  if (t) headers.Authorization = `Bearer ${t}`

  const res = await fetch(`${API_URL}/api/v1${path}`, { ...options, headers })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail ?? `Request failed: ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  register: (email: string, password: string, locale: string) =>
    request<{ access_token: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, locale }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ id: number; email: string; is_admin: boolean; locale: string }>('/auth/me'),

  getProfile: () => request('/profile'),
  updateProfile: (data: unknown) =>
    request('/profile', { method: 'PUT', body: JSON.stringify(data) }),

  listSearches: () => request<any[]>('/searches'),
  createSearch: (title: string) =>
    request<any>('/searches', { method: 'POST', body: JSON.stringify({ title }) }),
  buildShortlist: (id: number) =>
    request<any[]>(`/searches/${id}/shortlist`, { method: 'POST' }),
  listCandidates: (id: number) => request<any[]>(`/searches/${id}/candidates`),

  listPlaces: (kind?: string) =>
    request<any[]>(`/places${kind ? `?kind=${kind}` : ''}`),

  sendChat: (id: number, message: string) =>
    request<any>(`/searches/${id}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
}

export { API_URL }
