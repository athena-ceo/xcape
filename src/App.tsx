// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'

import { Header } from './components/Header'
import { AdminDashboard } from './pages/AdminDashboard'
import { ComparisonPlayground } from './pages/ComparisonPlayground'
import { Drilldown } from './pages/Drilldown'
import { ExplorePage } from './pages/ExplorePage'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { Onboarding } from './pages/Onboarding'
import { ProfilePage } from './pages/ProfilePage'
import { RegisterPage } from './pages/RegisterPage'
import { SearchRedirect } from './pages/SearchRedirect'
import { useAuth } from './store/auth'

function RequireAuth({ children }: { children: JSX.Element }) {
  const token = useAuth((s) => s.token)
  return token ? children : <Navigate to="/login" replace />
}

// The old country-checklist step was dropped; send any lingering /shortlist links to the
// comparison table (now the single entry point, pre-filled with the top matches).
function ShortlistRedirect() {
  const { searchId } = useParams()
  return <Navigate to={`/compare/${searchId}`} replace />
}

export default function App() {
  // On load (and reload), if a token is stored, fetch the user so the greeting and
  // name are available on every page.
  const token = useAuth((s) => s.token)
  const refresh = useAuth((s) => s.refresh)
  useEffect(() => {
    if (token) refresh()
  }, [token, refresh])

  return (
    // overflow-x-hidden: keep any single wide element (a comparison table, a long nav) from
    // widening the mobile layout viewport — which would push page content off-screen. Wide tables
    // get their OWN horizontal scroll via an inner overflow-x-auto, so nothing is lost.
    <div className="min-h-screen overflow-x-hidden">
      <Header />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/onboarding" element={<RequireAuth><Onboarding /></RequireAuth>} />
        <Route path="/profile" element={<RequireAuth><ProfilePage /></RequireAuth>} />
        <Route path="/search" element={<RequireAuth><SearchRedirect /></RequireAuth>} />
        <Route path="/shortlist/:searchId" element={<RequireAuth><ShortlistRedirect /></RequireAuth>} />
        <Route path="/compare/:searchId" element={<RequireAuth><ComparisonPlayground /></RequireAuth>} />
        <Route path="/explore/:searchId" element={<RequireAuth><ExplorePage /></RequireAuth>} />
        <Route path="/drilldown/:placeId" element={<RequireAuth><Drilldown /></RequireAuth>} />
        <Route path="/admin" element={<RequireAuth><AdminDashboard /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}
