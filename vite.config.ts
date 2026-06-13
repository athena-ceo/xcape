// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  // Served at the site root in dev, and under /xcape/ in production (path-based on
  // apps.athenadecisions.com). Set VITE_BASE_PATH=/ to serve at a subdomain root.
  base: process.env.VITE_BASE_PATH || '/',
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
  },
})
