// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
  },
})
