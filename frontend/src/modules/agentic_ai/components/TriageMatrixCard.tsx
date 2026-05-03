import React from 'react'

type TriageStatus = 'SAFE' | 'CONDITIONAL' | 'QUARANTINED'
type InternalStatus = 'Aligned' | 'Drifted'
type ExternalStatus = 'Aligned' | 'Outlier'

interface TriageCell {
  internal: InternalStatus
  external: ExternalStatus
  decision: TriageStatus
  rowCount: number
  percentage: number
  description: string
  reasoning: string[]
}

interface TriageMatrixCardProps {
  cells: TriageCell[]
  totalRows: number
  isLoading?: boolean
  onCellClick?: (cell: TriageCell) => void
}

const getColorForDecision = (decision: TriageStatus) => {
  switch (decision) {
    case 'SAFE':
      return { bg: '#F0FDF4', border: '#10B981', text: '#065F46', dot: '#10B981' }
    case 'CONDITIONAL':
      return { bg: '#FFFBEB', border: '#F59E0B', text: '#92400E', dot: '#F59E0B' }
    case 'QUARANTINED':
      return { bg: '#FEF2F2', border: '#EF4444', text: '#7F1D1D', dot: '#EF4444' }
    default:
      return { bg: '#F3F4F6', border: '#D1D5DB', text: '#374151', dot: '#6B7280' }
  }
}

export const TriageMatrixCard: React.FC<TriageMatrixCardProps> = ({
  cells = [],
  totalRows = 0,
  isLoading = false,
  onCellClick,
}) => {
  if (isLoading) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#6B7280' }}>
        Loading triage matrix...
      </div>
    )
  }

  if (!cells || cells.length === 0) {
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
        No triage data available
      </div>
    )
  }

  // Group cells by quadrant
  const quadrants: Record<string, TriageCell | undefined> = {
    'AlignedAligned': cells.find((c) => c.internal === 'Aligned' && c.external === 'Aligned'),
    'AlignedOutlier': cells.find((c) => c.internal === 'Aligned' && c.external === 'Outlier'),
    'DriftedAligned': cells.find((c) => c.internal === 'Drifted' && c.external === 'Aligned'),
    'DriftedOutlier': cells.find((c) => c.internal === 'Drifted' && c.external === 'Outlier'),
  }

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
        <div>Twin-Baseline Triage Matrix</div>
        <div style={{ fontSize: 11, color: '#6B7280', fontWeight: 400 }}>
          {totalRows} total rows analyzed
        </div>
      </div>

      {/* Matrix Grid */}
      <div style={{ display: 'grid', gap: 12 }}>
        {/* Top header */}
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr 1fr', gap: 8 }}>
          <div />
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: '#6B7280',
              textAlign: 'center',
              padding: '8px 0',
            }}
          >
            External Aligned
          </div>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: '#6B7280',
              textAlign: 'center',
              padding: '8px 0',
            }}
          >
            External Outlier
          </div>
        </div>

        {/* Top row: Internal Aligned */}
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr 1fr', gap: 8 }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: '#6B7280',
              writingMode: 'vertical-rl',
              textOrientation: 'mixed',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: 120,
            }}
          >
            Internal Aligned
          </div>

          {/* AlignedAligned */}
          {(() => {
            const cell = quadrants['AlignedAligned']
            const color = getColorForDecision(cell?.decision || 'SAFE')
            return (
              <div
                onClick={() => cell && onCellClick?.(cell)}
                style={{
                  padding: 12,
                  borderRadius: 8,
                  border: `2px solid ${color.border}`,
                  background: color.bg,
                  cursor: cell ? 'pointer' : 'default',
                  transition: 'all 0.2s',
                  display: 'grid',
                  gap: 6,
                }}
                onMouseEnter={(e) => {
                  if (cell) (e.currentTarget as any).style.transform = 'scale(1.02)'
                }}
                onMouseLeave={(e) => {
                  if (cell) (e.currentTarget as any).style.transform = 'scale(1)'
                }}
              >
                {cell ? (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          backgroundColor: color.dot,
                        }}
                      />
                      <div style={{ fontSize: 12, fontWeight: 700, color: color.text }}>
                        {cell.decision}
                      </div>
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 900, color: color.text }}>
                      {cell.rowCount}
                    </div>
                    <div style={{ fontSize: 9, color: color.text }}>
                      {cell.percentage.toFixed(1)}%
                    </div>
                    <div style={{ fontSize: 9, color: color.text, fontStyle: 'italic' }}>
                      {cell.description}
                    </div>
                  </>
                ) : (
                  <div style={{ color: '#9CA3AF', fontSize: 11 }}>No data</div>
                )}
              </div>
            )
          })()}

          {/* AlignedOutlier */}
          {(() => {
            const cell = quadrants['AlignedOutlier']
            const color = getColorForDecision(cell?.decision || 'CONDITIONAL')
            return (
              <div
                onClick={() => cell && onCellClick?.(cell)}
                style={{
                  padding: 12,
                  borderRadius: 8,
                  border: `2px solid ${color.border}`,
                  background: color.bg,
                  cursor: cell ? 'pointer' : 'default',
                  transition: 'all 0.2s',
                  display: 'grid',
                  gap: 6,
                }}
                onMouseEnter={(e) => {
                  if (cell) (e.currentTarget as any).style.transform = 'scale(1.02)'
                }}
                onMouseLeave={(e) => {
                  if (cell) (e.currentTarget as any).style.transform = 'scale(1)'
                }}
              >
                {cell ? (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          backgroundColor: color.dot,
                        }}
                      />
                      <div style={{ fontSize: 12, fontWeight: 700, color: color.text }}>
                        {cell.decision}
                      </div>
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 900, color: color.text }}>
                      {cell.rowCount}
                    </div>
                    <div style={{ fontSize: 9, color: color.text }}>
                      {cell.percentage.toFixed(1)}%
                    </div>
                    <div style={{ fontSize: 9, color: color.text, fontStyle: 'italic' }}>
                      {cell.description}
                    </div>
                  </>
                ) : (
                  <div style={{ color: '#9CA3AF', fontSize: 11 }}>No data</div>
                )}
              </div>
            )
          })()}
        </div>

        {/* Bottom row: Internal Drifted */}
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr 1fr', gap: 8 }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: '#6B7280',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: 120,
            }}
          >
            Internal Drifted
          </div>

          {/* DriftedAligned */}
          {(() => {
            const cell = quadrants['DriftedAligned']
            const color = getColorForDecision(cell?.decision || 'CONDITIONAL')
            return (
              <div
                onClick={() => cell && onCellClick?.(cell)}
                style={{
                  padding: 12,
                  borderRadius: 8,
                  border: `2px solid ${color.border}`,
                  background: color.bg,
                  cursor: cell ? 'pointer' : 'default',
                  transition: 'all 0.2s',
                  display: 'grid',
                  gap: 6,
                }}
                onMouseEnter={(e) => {
                  if (cell) (e.currentTarget as any).style.transform = 'scale(1.02)'
                }}
                onMouseLeave={(e) => {
                  if (cell) (e.currentTarget as any).style.transform = 'scale(1)'
                }}
              >
                {cell ? (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          backgroundColor: color.dot,
                        }}
                      />
                      <div style={{ fontSize: 12, fontWeight: 700, color: color.text }}>
                        {cell.decision}
                      </div>
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 900, color: color.text }}>
                      {cell.rowCount}
                    </div>
                    <div style={{ fontSize: 9, color: color.text }}>
                      {cell.percentage.toFixed(1)}%
                    </div>
                    <div style={{ fontSize: 9, color: color.text, fontStyle: 'italic' }}>
                      {cell.description}
                    </div>
                  </>
                ) : (
                  <div style={{ color: '#9CA3AF', fontSize: 11 }}>No data</div>
                )}
              </div>
            )
          })()}

          {/* DriftedOutlier */}
          {(() => {
            const cell = quadrants['DriftedOutlier']
            const color = getColorForDecision(cell?.decision || 'QUARANTINED')
            return (
              <div
                onClick={() => cell && onCellClick?.(cell)}
                style={{
                  padding: 12,
                  borderRadius: 8,
                  border: `2px solid ${color.border}`,
                  background: color.bg,
                  cursor: cell ? 'pointer' : 'default',
                  transition: 'all 0.2s',
                  display: 'grid',
                  gap: 6,
                }}
                onMouseEnter={(e) => {
                  if (cell) (e.currentTarget as any).style.transform = 'scale(1.02)'
                }}
                onMouseLeave={(e) => {
                  if (cell) (e.currentTarget as any).style.transform = 'scale(1)'
                }}
              >
                {cell ? (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          backgroundColor: color.dot,
                        }}
                      />
                      <div style={{ fontSize: 12, fontWeight: 700, color: color.text }}>
                        {cell.decision}
                      </div>
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 900, color: color.text }}>
                      {cell.rowCount}
                    </div>
                    <div style={{ fontSize: 9, color: color.text }}>
                      {cell.percentage.toFixed(1)}%
                    </div>
                    <div style={{ fontSize: 9, color: color.text, fontStyle: 'italic' }}>
                      {cell.description}
                    </div>
                  </>
                ) : (
                  <div style={{ color: '#9CA3AF', fontSize: 11 }}>No data</div>
                )}
              </div>
            )
          })()}
        </div>
      </div>

      {/* Legend */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: 8,
          marginTop: 8,
          padding: '8px 0',
          borderTop: '1px solid #E5E7EB',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#10B981' }} />
          <span style={{ color: '#6B7280' }}>Safe</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#F59E0B' }} />
          <span style={{ color: '#6B7280' }}>Conditional</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#EF4444' }} />
          <span style={{ color: '#6B7280' }}>Quarantined</span>
        </div>
      </div>
    </div>
  )
}
