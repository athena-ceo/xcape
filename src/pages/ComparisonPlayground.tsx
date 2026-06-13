// Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
// Proprietary and confidential — unauthorized copying or distribution is prohibited.

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { VoiceInput } from '../components/VoiceInput'
import { useT } from '../i18n'
import { api } from '../services/api'

const CRITERIA = ['cost_of_living', 'climate', 'language_ease', 'healthcare', 'political_stability'] as const

// Scaffold of the spreadsheet-like comparison board (plan §6, mock-up #2). The top
// candidates from the shortlist are shown as columns; criteria as rows. Add/remove
// columns & criteria and the chat sidebar are build-phase tasks.
export function ComparisonPlayground() {
  const { t } = useT()
  const { searchId } = useParams()
  const [candidates, setCandidates] = useState<any[]>([])
  const [places, setPlaces] = useState<Record<number, any>>({})
  const [chat, setChat] = useState('')

  useEffect(() => {
    async function load() {
      const [cands, pls] = await Promise.all([
        api.listCandidates(Number(searchId)),
        api.listPlaces('country'),
      ])
      setCandidates(cands.slice(0, 5))
      setPlaces(Object.fromEntries(pls.map((p) => [p.id, p])))
    }
    load()
  }, [searchId])

  async function ask(message: string) {
    if (!message.trim()) return
    await api.sendChat(Number(searchId), message)
    setChat('')
  }

  return (
    <main className="max-w-4xl mx-auto px-5 py-8">
      <div className="flex items-center mb-4">
        <h1 className="text-xl font-medium text-turquoise-900">{t.comparison.title}</h1>
        <div className="ml-auto flex gap-2 text-sm">
          <button className="border border-turquoise-100 rounded-md px-3 py-1.5">
            + {t.comparison.addCriterion}
          </button>
          <button className="border border-turquoise-100 rounded-md px-3 py-1.5">
            + {t.comparison.addCountry}
          </button>
        </div>
      </div>

      <div className="overflow-x-auto bg-white border border-turquoise-100 rounded-lg mb-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-turquoise-50 text-left">
              <th className="p-3 font-medium">{t.comparison.criterion}</th>
              {candidates.map((c) => (
                <th key={c.id} className="p-3 font-medium">{places[c.place_id]?.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {CRITERIA.map((key) => (
              <tr key={key} className="border-t border-turquoise-100">
                <td className="p-3 text-turquoise-800/70">{t.criteria[key]}</td>
                {candidates.map((c) => (
                  <td key={c.id} className="p-3 text-center">
                    {String(c.per_criterion?.[key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
            <tr className="border-t border-turquoise-200 bg-turquoise-50">
              <td className="p-3 font-medium">{t.comparison.matchScore}</td>
              {candidates.map((c) => (
                <td key={c.id} className="p-3 text-center font-medium text-turquoise-600">
                  {Math.round(c.match_score)}%
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="bg-turquoise-50 border border-turquoise-100 rounded-lg p-3">
        <p className="text-sm font-medium text-turquoise-600 mb-2">{t.comparison.askAssistant}</p>
        <div className="flex items-center gap-2 bg-white rounded-md px-3 py-2">
          <input
            value={chat}
            onChange={(e) => setChat(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && ask(chat)}
            placeholder={t.comparison.placeholder}
            className="flex-1 outline-none text-sm"
          />
          <VoiceInput onTranscript={(text) => setChat(text)} />
          <button onClick={() => ask(chat)} className="text-turquoise-600">→</button>
        </div>
      </div>
    </main>
  )
}
