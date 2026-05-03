import React from 'react'

type ReleaseDecision = 'SAFE' | 'CONDITIONAL' | 'QUARANTINED'

interface ReleaseGateProps {
  finalDecision: ReleaseDecision
  overallScore: number
  confidence: number
  reasoning: string[]
  featureSafeCount: number
  featureConditionalCount: number
  featureQuarantinedCount: number
  onApprove?: () => void
  onReview?: () => void
  onReject?: () => void
  isLoading?: boolean
}

const getColorClass = (decision: ReleaseDecision) => {
  switch (decision) {
    case 'SAFE':
      return '#10B981'
    case 'CONDITIONAL':
      return '#F59E0B'
    case 'QUARANTINED':
      return '#EF4444'
    default:
      return '#6B7280'
  }
}

const getBackgroundClass = (decision: ReleaseDecision) => {
  switch (decision) {
    case 'SAFE':
      return '#F0FDF4'
    case 'CONDITIONAL':
      return '#FFFBEB'
    case 'QUARANTINED':
      return '#FEF2F2'
    default:
      return '#F3F4F6'
  }
}

const getTextColorClass = (decision: ReleaseDecision) => {
  switch (decision) {
    case 'SAFE':
      return '#065F46'
    case 'CONDITIONAL':
      return '#92400E'
    case 'QUARANTINED':
      return '#7F1D1D'
    default:
      return '#374151'
  }
}

export const ReleaseGate: React.FC<ReleaseGateProps> = ({
  finalDecision,
  overallScore,
  confidence,
  reasoning,
  featureSafeCount,
  featureConditionalCount,
  featureQuarantinedCount,
  onApprove,
  onReview,
  onReject,
  isLoading = false,
}) => {
  const color = getColorClass(finalDecision)
  const bgColor = getBackgroundClass(finalDecision)
  const textColor = getTextColorClass(finalDecision)
  
  const totalFeatures = featureSafeCount + featureConditionalCount + featureQuarantinedCount

  return (
    <div
      style={{
        borderRadius: 12,
        border: `2px solid ${color}`,
        background: bgColor,
        padding: '24px 20px',
        display: 'grid',
        gap: 16,
      }}
    >
      <div style={{ display: 'grid', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 16,
              height: 16,
              borderRadius: '50%',
              backgroundColor: color,
            }}
          />
          <div style={{ fontSize: 24, fontWeight: 900, color, textTransform: 'uppercase' }}>
            {finalDecision}
          </div>
        </div>
        <div style={{ fontSize: 13, color: textColor }}>
          Dataset status: <strong>{finalDecision}</strong> for release
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <div style={{ background: 'rgba(16, 185, 129, 0.1)', padding: 10, borderRadius: 8, textAlign: 'center' }}>
          <div style={{ fontSize: 12, color: '#059669', fontWeight: 600 }}>Safe Features</div>
          <div style={{ fontSize: 20, fontWeight: 900, color: '#10B981', marginTop: 4 }}>{featureSafeCount}</div>
          {totalFeatures > 0 && (
            <div style={{ fontSize: 10, color: '#047857', marginTop: 2 }}>
              {((featureSafeCount / totalFeatures) * 100).toFixed(0)}%
            </div>
          )}
        </div>
        <div style={{ background: 'rgba(245, 158, 11, 0.1)', padding: 10, borderRadius: 8, textAlign: 'center' }}>
          <div style={{ fontSize: 12, color: '#B45309', fontWeight: 600 }}>Conditional Features</div>
          <div style={{ fontSize: 20, fontWeight: 900, color: '#F59E0B', marginTop: 4 }}>{featureConditionalCount}</div>
          {totalFeatures > 0 && (
            <div style={{ fontSize: 10, color: '#92400E', marginTop: 2 }}>
              {((featureConditionalCount / totalFeatures) * 100).toFixed(0)}%
            </div>
          )}
        </div>
        <div style={{ background: 'rgba(239, 68, 68, 0.1)', padding: 10, borderRadius: 8, textAlign: 'center' }}>
          <div style={{ fontSize: 12, color: '#DC2626', fontWeight: 600 }}>Quarantined Features</div>
          <div style={{ fontSize: 20, fontWeight: 900, color: '#EF4444', marginTop: 4 }}>{featureQuarantinedCount}</div>
          {totalFeatures > 0 && (
            <div style={{ fontSize: 10, color: '#991B1B', marginTop: 2 }}>
              {((featureQuarantinedCount / totalFeatures) * 100).toFixed(0)}%
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: textColor, fontWeight: 600, marginBottom: 4 }}>Drift Score</div>
          <div style={{ fontSize: 28, fontWeight: 900, color }}>
            {(overallScore * 100).toFixed(1)}%
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: textColor, fontWeight: 600, marginBottom: 4 }}>Confidence</div>
          <div style={{ fontSize: 28, fontWeight: 900, color }}>
            {(confidence * 100).toFixed(1)}%
          </div>
        </div>
      </div>

      {reasoning && reasoning.length > 0 && (
        <div style={{ display: 'grid', gap: 6 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: textColor }}>Key Findings:</div>
          <ul style={{ margin: 0, paddingLeft: 20, display: 'grid', gap: 4 }}>
            {reasoning.slice(0, 4).map((reason, idx) => (
              <li key={idx} style={{ fontSize: 11.5, color: textColor }}>
                {reason}
              </li>
            ))}
            {reasoning.length > 4 && (
              <li style={{ fontSize: 11.5, color: textColor, fontWeight: 600 }}>
                +{reasoning.length - 4} more finding{reasoning.length - 4 !== 1 ? 's' : ''}
              </li>
            )}
          </ul>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {finalDecision === 'SAFE' && (
          <>
            <button
              type="button"
              style={{
                flex: 1,
                minWidth: 120,
                padding: '10px 16px',
                borderRadius: 6,
                border: 'none',
                background: color,
                color: 'white',
                fontWeight: 700,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading ? 0.6 : 1,
                fontSize: 12,
              }}
              onClick={onApprove}
              disabled={isLoading}
            >
              {isLoading ? 'Processing...' : 'Approve & Release'}
            </button>
            <button
              type="button"
              style={{
                flex: 1,
                minWidth: 120,
                padding: '10px 16px',
                borderRadius: 6,
                border: `1px solid ${color}`,
                background: 'transparent',
                color: color,
                fontWeight: 700,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading ? 0.6 : 1,
                fontSize: 12,
              }}
              onClick={onReview}
              disabled={isLoading}
            >
              Review Details
            </button>
          </>
        )}
        {finalDecision === 'CONDITIONAL' && (
          <>
            <button
              type="button"
              style={{
                flex: 1,
                minWidth: 120,
                padding: '10px 16px',
                borderRadius: 6,
                border: 'none',
                background: color,
                color: 'white',
                fontWeight: 700,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading ? 0.6 : 1,
                fontSize: 12,
              }}
              onClick={onReview}
              disabled={isLoading}
            >
              {isLoading ? 'Processing...' : 'Review Conditions'}
            </button>
            <button
              type="button"
              style={{
                flex: 1,
                minWidth: 120,
                padding: '10px 16px',
                borderRadius: 6,
                border: `1px solid ${color}`,
                background: 'transparent',
                color: color,
                fontWeight: 700,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading ? 0.6 : 1,
                fontSize: 12,
              }}
              onClick={onReject}
              disabled={isLoading}
            >
              Reject
            </button>
          </>
        )}
        {finalDecision === 'QUARANTINED' && (
          <button
            type="button"
            style={{
              flex: 1,
              minWidth: 120,
              padding: '10px 16px',
              borderRadius: 6,
              border: 'none',
              background: color,
              color: 'white',
              fontWeight: 700,
              cursor: isLoading ? 'not-allowed' : 'pointer',
              opacity: isLoading ? 0.6 : 1,
              fontSize: 12,
            }}
            onClick={onReview}
            disabled={isLoading}
          >
            {isLoading ? 'Processing...' : 'View Quarantine Reasons'}
          </button>
        )}
      </div>
    </div>
  )
}
