import React, { useMemo, useState } from 'react'
import {
  COLD_START_QUESTIONS,
  toPreferenceSignal,
  type KGPreferenceSignal,
} from '../services/kgSignals'

export default function KGPreferenceCapture({
  userId,
  onSignal,
}: {
  userId: string
  onSignal?: (signal: KGPreferenceSignal) => void
}) {
  const disabled = useMemo(() => !userId || userId.trim().length === 0, [userId])
  const [selected, setSelected] = useState<Record<string, string>>({})

  return (
    <section
      style={{
        marginTop: 14,
        borderRadius: 14,
        padding: 16,
        background: 'linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%)',
        border: '1px solid #cbd5e1',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ margin: '0 0 6px 0', color: '#0f172a' }}>Quick Preference Capture</h4>
        <span style={{ fontSize: 11, color: '#334155', background: '#e2e8f0', borderRadius: 999, padding: '3px 8px' }}>
          Explicit KG Signals
        </span>
      </div>
      <p style={{ margin: '0 0 12px 0', color: '#334155', fontSize: 13 }}>
        Use these prompts for cold-start users to create explicit KG edges.
      </p>

      <div style={{ display: 'grid', gap: 10 }}>
        {COLD_START_QUESTIONS.map((q) => (
          <div key={q.id} style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 10, padding: 10 }}>
            <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 8 }}>{q.label}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {q.options.map((opt) => (
                <button
                  key={`${q.id}-${opt}`}
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    if (disabled || !onSignal) return
                    setSelected((prev) => ({ ...prev, [q.id]: opt }))
                    onSignal(toPreferenceSignal(userId, q.mapsTo, opt, 1))
                  }}
                  style={{
                    borderRadius: 999,
                    border: selected[q.id] === opt ? '1px solid #2563eb' : '1px solid #94a3b8',
                    background: disabled ? '#e2e8f0' : selected[q.id] === opt ? '#dbeafe' : '#f8fafc',
                    padding: '6px 10px',
                    color: selected[q.id] === opt ? '#1e3a8a' : '#0f172a',
                    cursor: disabled ? 'not-allowed' : 'pointer',
                    fontSize: 12,
                    fontWeight: selected[q.id] === opt ? 700 : 500,
                  }}
                >
                  {opt}
                </button>
              ))}
            </div>
            {selected[q.id] && (
              <div style={{ marginTop: 8, fontSize: 12, color: '#065f46' }}>
                Captured: <strong>{selected[q.id]}</strong>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
