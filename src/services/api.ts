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
      first_name?: string; last_name?: string; current_country?: string
      citizenships?: string[]; ancestry_countries?: string[]
    }>('/auth/me'),
  updateMe: (body: {
    first_name?: string; last_name?: string; current_country?: string
    citizenships?: string[]; ancestry_countries?: string[]; locale?: string
  }) => request('/auth/me', { method: 'PATCH', body: JSON.stringify(body) }),

  getCriteria: () => request<any>('/criteria'),
  // Rule-based persona from the first onboarding answers → {key, persona{...}}.
  derivePersona: (reasons: string[], priorities: string[]) =>
    request<{ key: string; persona: any }>('/persona/derive', {
      method: 'POST', body: JSON.stringify({ reasons, priorities }),
    }),
  getProfile: () => request('/profile'),
  updateProfile: (data: unknown) =>
    request('/profile', { method: 'PUT', body: JSON.stringify(data) }),
  // Start over: wipe the user's profile + searches (keeps the account).
  resetAccount: () => request<void>('/profile/reset', { method: 'POST' }),

  listSearches: () => request<any[]>('/searches'),
  createSearch: (title: string) =>
    request<any>('/searches', { method: 'POST', body: JSON.stringify({ title }) }),
  buildShortlist: (id: number) =>
    request<any[]>(`/searches/${id}/shortlist`, { method: 'POST' }),
  // Rebuild the list against current weights + filters, keeping the selected board and
  // topping it up (flagging any that don't meet the filters).
  repopulate: (id: number) =>
    request<any[]>(`/searches/${id}/repopulate`, { method: 'POST' }),
  // Add the user's persona's specific criteria (asset-tax, pension-visa, per-community tolerance…).
  applyPersona: (id: number) =>
    request<any[]>(`/searches/${id}/apply-persona`, { method: 'POST' }),
  updateCustomCriterion: (id: number, key: string, body: { weight?: number; min?: number | null }) =>
    request<any[]>(`/searches/${id}/custom-criteria/${encodeURIComponent(key)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  listCandidates: (id: number) => request<any[]>(`/searches/${id}/candidates`),
  wildcards: (id: number) => request<{
    place_id: number; name: string; iso_code: string | null; score: number
    standout_key: string; standout_value: number
  }[]>(`/searches/${id}/wildcards`),
  explore: (id: number) => request<{
    place_id: number; name: string; iso_code: string | null; score: number
    reasons: string[]; violations: string[]; pending: string[]; on_board: boolean
  }[]>(`/searches/${id}/explore`),
  filterAdvice: (id: number) => request<{
    qualified: number; board_size: number
    suggestions: { key: string; admits: number; best_score: number; best_country: string | null }[]
  }>(`/searches/${id}/filter-advice`),
  addCandidate: (id: number, body: { place_id?: number; place_name?: string }) =>
    request<any>(`/searches/${id}/candidates`, { method: 'POST', body: JSON.stringify(body) }),
  removeCandidate: (id: number, candidateId: number) =>
    request<void>(`/searches/${id}/candidates/${candidateId}`, { method: 'DELETE' }),
  setSelected: (id: number, candidateId: number, selected: boolean) =>
    request<any>(`/searches/${id}/candidates/${candidateId}`, {
      method: 'PATCH',
      body: JSON.stringify({ selected }),
    }),
  // Explicitly banish a country (override "out") — leaves the board and the excluded bar.
  excludeCandidate: (id: number, candidateId: number) =>
    request<any>(`/searches/${id}/candidates/${candidateId}/exclude`, { method: 'POST' }),
  // Clear a pin/exclusion (override null) — back to the neutral ranked pool.
  restoreCandidate: (id: number, candidateId: number) =>
    request<any>(`/searches/${id}/candidates/${candidateId}/restore`, { method: 'POST' }),
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
  evaluatePending: (id: number, limit = 4) =>
    request<any[]>(`/searches/${id}/evaluate-pending?limit=${limit}`, { method: 'POST' }),
  suggestCriteria: (id: number, tags: string[], text: string) =>
    request<any[]>(`/searches/${id}/suggest-criteria`, {
      method: 'POST',
      body: JSON.stringify({ tags, text }),
    }),
  // Fetch the PDF report as a blob (auth header) and trigger a browser download.
  // `lang` makes the PDF match the language the user is currently viewing.
  downloadReport: async (id: number, lang?: string) => {
    const t = token()
    const qs = lang ? `?lang=${lang}` : ''
    const res = await fetch(`${API_URL}/api/v1/searches/${id}/report.pdf${qs}`, {
      headers: t ? { Authorization: `Bearer ${t}` } : {},
    })
    if (!res.ok) throw new Error(`Report failed: ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `xcape-report-${id}.pdf`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
  getBaseline: (id: number) => request<any | null>(`/searches/${id}/baseline`),

  listPlaces: (kind?: string) =>
    request<any[]>(`/places${kind ? `?kind=${kind}` : ''}`),
  getPlace: (id: number) => request<any>(`/places/${id}`),
  getFacts: (id: number) => request<any>(`/places/${id}/facts`),
  getDetail: (id: number, lang: string, search?: number) =>
    request<{ criteria: any[] }>(
      `/places/${id}/detail?lang=${lang}${search != null ? `&search=${search}` : ''}`,
    ),
  // Generate up to `limit` of the still-pending criteria, in the given priority order.
  generateDetail: (id: number, body: { keys: string[]; limit: number }, lang: string, search?: number) =>
    request<{ criteria: any[] }>(
      `/places/${id}/detail/generate?lang=${lang}${search != null ? `&search=${search}` : ''}`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  // Visa pathways panel (drill-down): relevant categories with their terms, or pending.
  getVisaPathways: (id: number, lang: string, search?: number) =>
    request<{ categories: any[]; best: string | null }>(
      `/places/${id}/visa-pathways?lang=${lang}${search != null ? `&search=${search}` : ''}`,
    ),
  generateVisaPathways: (id: number, body: { limit: number }, lang: string, search?: number) =>
    request<{ categories: any[]; best: string | null }>(
      `/places/${id}/visa-pathways/generate?lang=${lang}${search != null ? `&search=${search}` : ''}`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  getMedia: (id: number) => request<any[]>(`/places/${id}/media`),

  getAdminUsers: () => request<any[]>('/admin/users'),
  getAdminSearches: (includeTest = false) =>
    request<any[]>(`/admin/searches${includeTest ? '?include_test=true' : ''}`),
  getAdminPlaces: () => request<any[]>('/admin/places'),
  getAdminAiLog: () => request<any[]>('/admin/ai-log'),
  adminResetPassword: (userId: number, password: string) =>
    request<void>(`/admin/users/${userId}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  adminResetUser: (userId: number) =>
    request<void>(`/admin/users/${userId}/reset`, { method: 'POST' }),
  getAdminCriteria: () => request<any>('/admin/criteria'),
  putAdminCriteria: (registry: any) =>
    request<{ ok: boolean }>('/admin/criteria', { method: 'PUT', body: JSON.stringify(registry) }),
  // Admin-time AI authoring of the persona set (returns a proposal; not saved).
  suggestPersonas: (prompt: string) =>
    request<{ personas: any[] }>('/admin/personas/suggest', {
      method: 'POST', body: JSON.stringify({ prompt }),
    }),
  createPlace: (body: any) =>
    request<any>('/admin/places', { method: 'POST', body: JSON.stringify(body) }),
  updatePlace: (id: number, body: any) =>
    request<{ ok: boolean }>(`/admin/places/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  getChat: (id: number) => request<any[]>(`/searches/${id}/chat`),
  // Tool-enabled chat: returns the assistant reply and whether it changed the search.
  // `placeId` (optional) adds that country's drill-down details to the assistant's context;
  // the conversation thread is shared across the comparison and drill-down pages.
  sendChat: (id: number, message: string, placeId?: number) =>
    request<{ reply: string; changed: boolean }>(
      `/searches/${id}/chat${placeId != null ? `?place_id=${placeId}` : ''}`,
      { method: 'POST', body: JSON.stringify({ message }) },
    ),
}

export { API_URL }
