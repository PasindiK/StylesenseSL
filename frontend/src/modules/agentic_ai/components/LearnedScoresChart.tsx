import React, { useState } from 'react'

interface ScoreDistribution {
  SAFE: number
  CONDITIONAL: number
  QUARANTINED: number
}

interface FeatureImportance {
  [featureName: string]: number
}

interface LearnedScoresChartProps {
  scoreDistribution?: ScoreDistribution
  featureImportance?: FeatureImportance
  modelAccuracy?: number
  avgConfidence?: number
  isLoading?: boolean
}

export const LearnedScoresChart: React.FC<LearnedScoresChartProps> = ({
  scoreDistribution,
  featureImportance,
  modelAccuracy,
  avgConfidence,
  isLoading = false,
}) => {
  const [showImportance, setShowImportance] = useState(true)

  if (isLoading) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#6B7280' }}>
        Loading learned scores...
      </div>
    )
  }

  if (!scoreDistribution && !featureImportance) {
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
        No score data available
      </div>
    )
  }

  const dist = scoreDistribution || { SAFE: 0, CONDITIONAL: 0, QUARANTINED: 0 }
  const total = dist.SAFE + dist.CONDITIONAL + dist.QUARANTINED || 1

  const safePercent = (dist.SAFE / total) * 100
  const conditionalPercent = (dist.CONDITIONAL / total) * 100
  const quarantinedPercent = (dist.QUARANTINED / total) * 100

  // Get top 5 features
  const topFeatures = featureImportance
    ? Object.entries(featureImportance)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5)
    : []

  const maxImportance = topFeatures.length > 0 ? topFeatures[0][1] : 1

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
        <div>Learned Drift Scores</div>
        <div style={{ fontSize: 10, color: '#6B7280', fontWeight: 400 }}>
          {modelAccuracy !== undefined && (
            <span>
              Model Accuracy: <span style={{ fontWeight: 600, color: '#059669' }}>
                {(modelAccuracy * 100).toFixed(1)}%
              </span>
            </span>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Score Distribution */}
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#6B7280' }}>Score Distribution</div>

          {/* Pie chart representation */}
          <div style={{ display: 'grid', gap: 8 }}>
            {/* SAFE */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <div style={{ fontSize: 10, color: '#065F46', fontWeight: 600 }}>Safe</div>
                <div style={{ fontSize: 10, fontWeight: 900, color: '#10B981' }}>
                  {dist.SAFE} ({safePercent.toFixed(1)}%)
                </div>
              </div>
              <div style={{ height: 8, background: '#E5E7EB', borderRadius: 4, overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    background: '#10B981',
                    width: `${safePercent}%`,
                    transition: 'width 0.3s',
                  }}
                />
              </div>
            </div>

            {/* CONDITIONAL */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <div style={{ fontSize: 10, color: '#92400E', fontWeight: 600 }}>Conditional</div>
                <div style={{ fontSize: 10, fontWeight: 900, color: '#F59E0B' }}>
                  {dist.CONDITIONAL} ({conditionalPercent.toFixed(1)}%)
                </div>
              </div>
              <div style={{ height: 8, background: '#E5E7EB', borderRadius: 4, overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    background: '#F59E0B',
                    width: `${conditionalPercent}%`,
                    transition: 'width 0.3s',
                  }}
                />
              </div>
            </div>

            {/* QUARANTINED */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <div style={{ fontSize: 10, color: '#7F1D1D', fontWeight: 600 }}>Quarantined</div>
                <div style={{ fontSize: 10, fontWeight: 900, color: '#EF4444' }}>
                  {dist.QUARANTINED} ({quarantinedPercent.toFixed(1)}%)
                </div>
              </div>
              <div style={{ height: 8, background: '#E5E7EB', borderRadius: 4, overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    background: '#EF4444',
                    width: `${quarantinedPercent}%`,
                    transition: 'width 0.3s',
                  }}
                />
              </div>
            </div>
          </div>

          {/* Model metrics */}
          {avgConfidence !== undefined && (
            <div
              style={{
                marginTop: 8,
                padding: 8,
                borderRadius: 6,
                background: '#F3F4F6',
                border: '1px solid #E5E7EB',
              }}
            >
              <div style={{ fontSize: 10, color: '#6B7280', marginBottom: 4 }}>Avg Confidence</div>
              <div style={{ fontSize: 14, fontWeight: 900, color: '#111827' }}>
                {(avgConfidence * 100).toFixed(1)}%
              </div>
            </div>
          )}
        </div>

        {/* Feature Importance */}
        {topFeatures.length > 0 && (
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#6B7280' }}>Top Features</div>

            <div style={{ display: 'grid', gap: 10 }}>
              {topFeatures.map(([featureName, importance], idx) => (
                <div key={featureName}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                    <div style={{ fontSize: 10, color: '#374151', fontWeight: 600, wordBreak: 'break-word' }}>
                      {featureName.replace(/_/g, ' ')}
                    </div>
                    <div style={{ fontSize: 10, fontWeight: 900, color: '#111827' }}>
                      {(importance * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div
                    style={{
                      height: 6,
                      background: '#E5E7EB',
                      borderRadius: 3,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        height: '100%',
                        background:
                          idx === 0
                            ? '#6366F1'
                            : idx === 1
                              ? '#8B5CF6'
                              : idx === 2
                                ? '#D946EF'
                                : idx === 3
                                  ? '#EC4899'
                                  : '#F43F5E',
                        width: `${(importance / maxImportance) * 100}%`,
                        transition: 'width 0.3s',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>

            <div
              style={{
                marginTop: 8,
                padding: 8,
                borderRadius: 6,
                background: '#EEF2FF',
                border: '1px solid #C7D2FE',
              }}
            >
              <div style={{ fontSize: 9, color: '#3730A3', fontWeight: 600 }}>
                Top feature "{topFeatures[0]?.[0]?.replace(/_/g, ' ')}" drives {(topFeatures[0]?.[1] * 100).toFixed(0)}% of
                model decisions
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Model Info */}
      <div
        style={{
          padding: 12,
          borderRadius: 8,
          background: '#F0F9FF',
          border: '1px solid #BFE7FF',
          display: 'grid',
          gap: 6,
        }}
      >
        <div style={{ fontSize: 10, fontWeight: 700, color: '#0369A1' }}>Model Information</div>
        <div style={{ fontSize: 10, color: '#0C4A6E', lineHeight: 1.6 }}>
          <div>
            • This model uses <strong>Logistic Regression</strong> to predict drift triage status
          </div>
          <div>
            • Trained on <strong>15-dimensional</strong> semantic drift features
          </div>
          <div>
            • Supports <strong>multi-class</strong> classification (SAFE, CONDITIONAL, QUARANTINED)
          </div>
          <div>
            • No hard-coded thresholds—decisions learned from training data
          </div>
        </div>
      </div>
    </div>
  )
}
