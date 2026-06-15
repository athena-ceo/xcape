// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { I18nProvider } from './i18n'
import './index.css'

// Router basename follows the Vite base so client-side routes work whether the app
// is served at the site root (dev / subdomain) or under /xcape (path-based prod).
const basename = import.meta.env.BASE_URL.replace(/\/$/, '') || '/'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <BrowserRouter basename={basename}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </BrowserRouter>
    </I18nProvider>
  </React.StrictMode>,
)
