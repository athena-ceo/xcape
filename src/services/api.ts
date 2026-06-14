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
  register: (body: {
    email: string; password: string; locale: string
    first_name?: string; last_name?: string
  }) =>
    request<{ access_token: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () =>
    request<{
      id: number; email: string; is_admin: boolean; locale: string
      first_name?: string; last_name?: string; current_country?: string; citizenships?: string[]
    }>('/auth/me'),
  updateMe: (body: {
    first_name?: string; last_name?: string; current_country?: string; citizenships?: string[]
  }) => request('/auth/me', { method: 'PATCH', body: JSON.stringify(body) }),

  getProfile: () => request('/profile'),
  updateProfile: (data: unknown) =>
    request('/profile', { method: 'PUT', body: JSON.stringify(data) }),

  listSearches: () => request<any[]>('/searches'),
  createSearch: (title: string) =>
    request<any>('/searches', { method: 'POST', body: JSON.stringify({ title }) }),
  buildShortlist: (id: number) =>
    request<any[]>(`/searches/${id}/shortlist`, { method: 'POST' }),
  listCandidates: (id: number) => request<any[]>(`/searches/${id}/candidates`),
  addCandidate: (id: number, body: { place_id?: number; place_name?: string }) =>
    request<any>(`/searches/${id}/candidates`, { method: 'POST', body: JSON.stringify(body) }),
  removeCandidate: (id: number, candidateId: number) =>
    request<void>(`/searches/${id}/candidates/${candidateId}`, { method: 'DELETE' }),
  setSelected: (id: number, candidateId: number, selected: boolean) =>
    request<any>(`/searches/${id}/candidates/${candidateId}`, {
      method: 'PATCH',
      body: JSON.stringify({ selected }),
    }),
  scoreExplanation: (id: number, candidateId: number) =>
    request<{ score: number; weight_total: number; rows: any[] }>(
      `/searches/${id}/candidates/${candidateId}/explanation`,
    ),
  addCriterion: (id: number, key: string) =>
    request<any[]>(`/searches/${id}/criteria`, { method: 'POST', body: JSON.stringify({ key }) }),
  listCustomCriteria: (id: number) =>
    request<{ key: string; label: string; description?: string; weight?: number }[]>(
      `/searches/${id}/custom-criteria`,
    ),
  addCustomCriterion: (id: number, label: string, description?: string) =>
    request<any[]>(`/searches/${id}/custom-criteria`, {
      method: 'POST',
      body: JSON.stringify({ label, description }),
    }),
  discriminate: (id: number) =>
    request<{ questions: any[] }>(`/searches/${id}/discriminate`, { method: 'POST' }),
  getBaseline: (id: number) => request<any | null>(`/searches/${id}/baseline`),

  listPlaces: (kind?: string) =>
    request<any[]>(`/places${kind ? `?kind=${kind}` : ''}`),
  getPlace: (id: number) => request<any>(`/places/${id}`),
  getFacts: (id: number) => request<any>(`/places/${id}/facts`),
  getDetail: (id: number, lang: string) =>
    request<{ criteria: any[] }>(`/places/${id}/detail?lang=${lang}`),
  getMedia: (id: number) => request<any[]>(`/places/${id}/media`),

  getAdminUsers: () => request<any[]>('/admin/users'),
  getAdminSearches: () => request<any[]>('/admin/searches'),
  getAdminPlaces: () => request<any[]>('/admin/places'),
  getAdminAiLog: () => request<any[]>('/admin/ai-log'),
  adminResetPassword: (userId: number, password: string) =>
    request<void>(`/admin/users/${userId}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

  getChat: (id: number) => request<any[]>(`/searches/${id}/chat`),
  // Tool-enabled chat: returns the assistant reply and whether it changed the search.
  sendChat: (id: number, message: string) =>
    request<{ reply: string; changed: boolean }>(`/searches/${id}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
}

export { API_URL }
