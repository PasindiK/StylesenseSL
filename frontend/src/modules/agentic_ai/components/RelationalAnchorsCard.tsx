import React, { useState } from 'react'

interface RelationalAnchor {
  anchor_id: string
  type: 'numeric-numeric' | 'numeric-text' | 'categorical-text'
  column_1: string
  column_2: string
  status: 'valid' | 'violated' | 'weakened'
  current_correlation?: number
  baseline_correlation?: number
  confidence: number
  description: string
  violation_reason?: string
}

interface RelationalAnchorsCardProps {
  anchors: RelationalAnchor[]
  isLoading?: boolean
  onAnchorClick?: (anchor: RelationalAnchor) => void
}

const getStatusColor = (status: string) => {
  switch (status) {
    case 'valid':
      return { bg: '#F0FDF4', border: '#10B981', text: '#065F46', badge: '#059669' }
    case 'violated':
      return { bg: '#FEF2F2', border: '#EF4444', text: '#7F1D1D', badge: '#DC2626' }
    case 'weakened':
      return { bg: '#FFFBEB', border: '#F59E0B', text: '#92400E', badge: '#D97706' }
    default:
      return { bg: '#F3F4F6', border: '#D1D5DB', text: '#374151', badge: '#6B7280' }
  }
}

const getTypeLabel = (type: string) => {
  switch (type) {
    case 'numeric-numeric':
      return '# ↔ #'
    case 'numeric-text':
      return '# ↔ 📝'
    case 'categorical-text':
      return 'Cat ↔ 📝'
    default:
      return type
  }
}

export const RelationalAnchorsCard: React.FC<RelationalAnchorsCardProps> = ({
  anchors = [],
  isLoading = false,
  onAnchorClick,
}) => {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#6B7280' }}>
        Loading relational anchors...
      </div>
    )
  }

  if (!anchors || anchors.length === 0) {
    return (
      <div
        style={{
          padding: 20,
          textAlign: 'center',
          color: '#6B7280',
          border: '1px dashed #D1D5DB',
          borderRadius: 8,
          background: '#FAFAFA',
        }}
      >
        No relational anchors discovered
      </div>
    )
  }

  const validCount = anchors.filter((a) => a.status === 'valid').length
  const violatedCount = anchors.filter((a) => a.status === 'violated').length
  const weakenedCount = anchors.filter((a) => a.status === 'weakened').length

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div
        style={{
          fontSize: 12,
          fontWeight: 700,
          color: '#111827',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>Relational Anchors ({anchors.length})</div>
        <div style={{ fontSize: 10, color: '#6B7280', fontWeight: 400, display: 'flex', gap: 12 }}>
          <span>
            <span style={{ fontWeight: 600, color: '#059669' }}>{validCount}</span> Valid
          </span>
          <span>
            <span style={{ fontWeight: 600, color: '#D97706' }}>{weakenedCount}</span> Weakened
          </span>
          <span>
            <span style={{ fontWeight: 600, color: '#DC2626' }}>{violatedCount}</span> Violated
          </span>
        </div>
      </div>

      <div style={{ display: 'grid', gap: 8, maxHeight: 400, overflowY: 'auto' }}>
        {anchors.map((anchor) => {
          const color = getStatusColor(anchor.status)
          const isExpanded = expandedId === anchor.anchor_id

          return (
            <div
              key={anchor.anchor_id}
              onClick={() => {
                setExpandedId(isExpanded ? null : anchor.anchor_id)
                onAnchorClick?.(anchor)
              }}
              style={{
                padding: 12,
                borderRadius: 8,
                border: `1px solid ${color.border}`,
                background: color.bg,
                cursor: 'pointer',
                transition: 'all 0.2s',
                display: 'grid',
                gap: isExpanded ? 10 : 0,
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as any).style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)'
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as any).style.boxShadow = 'none'
              }}
            >
              {/* Header row */}
              <div style={{ display: 'grid', gridTemplateColumns: 'auto auto 1fr auto auto', gap: 12, alignItems: 'center' }}>
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: '#FFFFFF',
                    background: color.badge,
                    padding: '3px 8px',
                    borderRadius: 4,
                  }}
                >
                  {getTypeLabel(anchor.type)}
                </div>

                <div style={{ fontSize: 11, fontWeight: 600, color: color.text }}>
                  <span>{anchor.column_1}</span>
                  <span style={{ margin: '0 4px' }}>↔</span>
                  <span>{anchor.column_2}</span>
                </div>

                <div />

                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: color.badge,
                    background: 'rgba(255,255,255,0.5)',
                    padding: '2px 6px',
                    borderRadius: 3,
                    textTransform: 'uppercase',
                  }}
                >
                  {anchor.status}
                </div>

                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 900,
                    color: color.text,
                  }}
                >
                  {(anchor.confidence * 100).toFixed(0)}%
                </div>
              </div>

              {/* Expanded details */}
              {isExpanded && (
                <div style={{ display: 'grid', gap: 8, paddingTop: 8, borderTop: `1px solid ${color.border}` }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 11 }}>
                    <div>
                      <div style={{ color: color.text, fontSize: 9, fontWeight: 600, marginBottom: 2 }}>
                        Description
                      </div>
                      <div style={{ color: color.text }}>{anchor.description}</div>
                    </div>
                    <div>
                      <div style={{ color: color.text, fontSize: 9, fontWeight: 600, marginBottom: 2 }}>
                        Correlation
                      </div>
                      <div style={{ color: color.text }}>
                        {anchor.baseline_correlation !== undefined ? (
                          <>
                            Baseline: {anchor.baseline_correlation.toFixed(3)} →
                            Current: {anchor.current_correlation?.toFixed(3) || 'N/A'}
                          </>
                        ) : (
                          'N/A'
                        )}
                      </div>
                    </div>
                  </div>

                  {anchor.violation_reason && (
                    <div>
                      <div style={{ color: color.text, fontSize: 9, fontWeight: 600, marginBottom: 2 }}>
                        Violation Reason
                      </div>
                      <div style={{ color: color.text, fontSize: 10 }}>{anchor.violation_reason}</div>
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                    <button
                      type="button"
                      style={{
                        flex: 1,
                        padding: '6px 12px',
                        borderRadius: 4,
                        border: `1px solid ${color.border}`,
                        background: 'transparent',
                        color: color.text,
                        fontSize: 10,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                      onClick={(e) => {
                        e.stopPropagation()
                        // Handle review action
                      }}
                    >
                      Review
                    </button>
                    <button
                      type="button"
                      style={{
                        flex: 1,
                        padding: '6px 12px',
                        borderRadius: 4,
                        border: `1px solid ${color.border}`,
                        background: 'transparent',
                        color: color.text,
                        fontSize: 10,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                      onClick={(e) => {
                        e.stopPropagation()
                        // Handle investigate action
                      }}
                    >
                      Investigate
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Summary statistics */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 8,
          padding: '8px 0',
          borderTop: '1px solid #E5E7EB',
        }}
      >
        <div style={{ textAlign: 'center', padding: '8px' }}>
          <div style={{ fontSize: 10, color: '#6B7280', marginBottom: 2 }}>Validation Rate</div>
          <div style={{ fontSize: 14, fontWeight: 900, color: '#059669' }}>
            {validCount > 0 ? ((validCount / anchors.length) * 100).toFixed(0) : 0}%
          </div>
        </div>
        <div style={{ textAlign: 'center', padding: '8px' }}>
          <div style={{ fontSize: 10, color: '#6B7280', marginBottom: 2 }}>Avg Confidence</div>
          <div style={{ fontSize: 14, fontWeight: 900, color: '#6B7280' }}>
            {(anchors.reduce((sum, a) => sum + a.confidence, 0) / anchors.length * 100).toFixed(0)}%
          </div>
        </div>
        <div style={{ textAlign: 'center', padding: '8px' }}>
          <div style={{ fontSize: 10, color: '#6B7280', marginBottom: 2 }}>Violations</div>
          <div style={{ fontSize: 14, fontWeight: 900, color: violatedCount > 0 ? '#DC2626' : '#059669' }}>
            {violatedCount}
          </div>
        </div>
      </div>
    </div>
  )
}
