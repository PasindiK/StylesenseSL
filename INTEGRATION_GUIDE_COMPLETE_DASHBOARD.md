# Phase 4 Complete Dashboard Integration Guide

## Quick Start: Integrate All Components into FeatureOpsWorkflowPanel

### 1. Import All Components

```tsx
// frontend/src/modules/agentic_ai/components/FeatureOpsWorkflowPanel.tsx

import {
  ReleaseGate,
  TwinBaselineComparison,
  TriageMatrixCard,
  RelationalAnchorsCard,
  LearnedScoresChart,
  ProfilerResults,
  DriftExplanation,
  RowLevelDrift,
} from './phase4'
```

---

## 2. Update Component State

Add state for tabs and data:

```tsx
export const FeatureOpsWorkflowPanel = () => {
  // Existing state...
  const [activeTab, setActiveTab] = useState<
    'upload' | 'profiler' | 'drift-explanation' | 'row-level' | 'release' | 'baseline' | 'matrix' | 'anchors' | 'scores'
  >('upload')
  
  const [driftResponse, setDriftResponse] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(false)

  // Existing handlers...
  const handleFileUpload = async (file: File) => {
    setIsLoading(true)
    const formData = new FormData()
    formData.append('file', file)
    
    try {
      const response = await fetch('/api/featureops/drift/detect-full', {
        method: 'POST',
        body: formData,
      })
      
      const data = await response.json()
      setDriftResponse(data)
      setActiveTab('profiler') // Start with profiler
    } finally {
      setIsLoading(false)
    }
  }
```

---

## 3. Create Tab Navigation

```tsx
return (
  <section className="featureops-shell" style={{ display: 'grid', gap: 24 }}>
    {/* Header - Keep Upload Feature */}
    <div className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap', padding: '14px 16px' }}>
      <div>
        <div style={{ fontSize: 18, fontWeight: 800, color: '#ecf6ff' }}>
          Agentic AI FeatureOps Dashboard
        </div>
        <div style={{ fontSize: 12, color: '#98abc8', marginTop: 4 }}>
          Semantic Drift Monitoring with Real Dataset Insights
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input 
          ref={fileInputRef} 
          type="file" 
          accept=".csv,.json" 
          onChange={handleFileUpload}
          disabled={isLoading}
          style={{ display: 'none' }} 
        />
        <button 
          type="button" 
          className="df-btn" 
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
        >
          {isLoading ? 'Processing...' : 'Upload Dataset'}
        </button>
        {driftResponse && (
          <button 
            type="button" 
            className="df-btn secondary" 
            onClick={() => setDriftResponse(null)}
          >
            Clear Results
          </button>
        )}
      </div>
    </div>

    {/* Tab Navigation */}
    {driftResponse && (
      <div
        style={{
          display: 'flex',
          gap: 8,
          borderBottom: '1px solid #E5E7EB',
          overflowX: 'auto',
          paddingBottom: 8,
        }}
      >
        {[
          { id: 'profiler', label: '📊 Profiler', icon: '📊' },
          { id: 'drift-explanation', label: '🔍 Drift Explanations', icon: '🔍' },
          { id: 'row-level', label: '📍 Row Analysis', icon: '📍' },
          { id: 'release', label: '🚀 Release Decision', icon: '🚀' },
          { id: 'baseline', label: '⚖️ Twin-Baseline', icon: '⚖️' },
          { id: 'matrix', label: '📋 Triage Matrix', icon: '📋' },
          { id: 'anchors', label: '🔗 Relational Anchors', icon: '🔗' },
          { id: 'scores', label: '📈 Learned Scores', icon: '📈' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            style={{
              padding: '8px 16px',
              borderRadius: '6px 6px 0 0',
              border: activeTab === tab.id ? '1px solid #D1D5DB' : 'none',
              borderBottom: activeTab === tab.id ? 'none' : '1px solid transparent',
              background: activeTab === tab.id ? '#FFFFFF' : 'transparent',
              color: activeTab === tab.id ? '#111827' : '#6B7280',
              fontSize: 12,
              fontWeight: activeTab === tab.id ? 700 : 500,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              if (activeTab !== tab.id) {
                (e.currentTarget as any).style.background = '#F9FAFB'
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== tab.id) {
                (e.currentTarget as any).style.background = 'transparent'
              }
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>
    )}

    {/* Tab Content */}
    <div style={{ padding: '12px 0' }}>
      {/* Profiler Tab */}
      {activeTab === 'profiler' && driftResponse && (
        <ProfilerResults
          columnProfiles={driftResponse.profiles.current.column_profiles}
          datasetName={driftResponse.dataset_name}
          rowCount={driftResponse.profiles.current.row_count}
          columnCount={driftResponse.profiles.current.column_count}
          isLoading={isLoading}
        />
      )}

      {/* Drift Explanations Tab */}
      {activeTab === 'drift-explanation' && driftResponse && (
        <DriftExplanation
          drifts={driftResponse.drift_explanations || []}
          isLoading={isLoading}
        />
      )}

      {/* Row-Level Drift Tab */}
      {activeTab === 'row-level' && driftResponse && (
        <RowLevelDrift
          rowDrifts={driftResponse.row_level_drifts || []}
          totalRows={driftResponse.profiles.current.row_count}
          isLoading={isLoading}
        />
      )}

      {/* Release Gate Tab */}
      {activeTab === 'release' && driftResponse && (
        <ReleaseGate
          finalDecision={driftResponse.final_label}
          overallScore={driftResponse.overall_drift_score}
          confidence={driftResponse.learned_scores?.avg_confidence || 0.5}
          reasoning={driftResponse.reasons || []}
          featureSafeCount={driftResponse.feature_stats?.safe_count || 0}
          featureConditionalCount={driftResponse.feature_stats?.conditional_count || 0}
          featureQuarantinedCount={driftResponse.feature_stats?.quarantined_count || 0}
          onApprove={() => handleApprove(driftResponse)}
          onReview={() => setActiveTab('baseline')}
          onReject={() => handleReject(driftResponse)}
          isLoading={isLoading}
        />
      )}

      {/* Twin-Baseline Tab */}
      {activeTab === 'baseline' && driftResponse && (
        <TwinBaselineComparison
          internalBaseline={driftResponse.profiles.internal}
          currentUpload={driftResponse.profiles.current}
          externalBaseline={driftResponse.profiles.external}
          isLoading={isLoading}
        />
      )}

      {/* Triage Matrix Tab */}
      {activeTab === 'matrix' && driftResponse && (
        <TriageMatrixCard
          cells={driftResponse.triage_matrix?.cells || []}
          totalRows={driftResponse.profiles.current.row_count}
          isLoading={isLoading}
          onCellClick={(cell) => {
            console.log('Clicked cell:', cell)
            // Handle cell click
          }}
        />
      )}

      {/* Relational Anchors Tab */}
      {activeTab === 'anchors' && driftResponse && (
        <RelationalAnchorsCard
          anchors={driftResponse.relational_anchors || []}
          isLoading={isLoading}
          onAnchorClick={(anchor) => {
            console.log('Clicked anchor:', anchor)
            // Handle anchor click
          }}
        />
      )}

      {/* Learned Scores Tab */}
      {activeTab === 'scores' && driftResponse && (
        <LearnedScoresChart
          scoreDistribution={driftResponse.learned_scores?.distribution}
          featureImportance={driftResponse.learned_scores?.feature_importance}
          modelAccuracy={driftResponse.learned_scores?.model_accuracy}
          avgConfidence={driftResponse.learned_scores?.avg_confidence}
          isLoading={isLoading}
        />
      )}

      {/* Empty State */}
      {!driftResponse && (
        <div
          style={{
            padding: 60,
            textAlign: 'center',
            color: '#6B7280',
            border: '2px dashed #D1D5DB',
            borderRadius: 12,
            background: '#FAFAFA',
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
            Ready to analyze your dataset
          </div>
          <div style={{ fontSize: 12 }}>
            Upload a CSV file to start drift detection and analysis
          </div>
        </div>
      )}
    </div>
  </section>
)
```

---

## Backend API Response Format

The `/api/featureops/drift/detect-full` endpoint should return:

```json
{
  "status": "success",
  "drift_run_id": "uuid",
  "dataset_name": "apparel_inventory.csv",
  "created_at": "2025-01-06T14:25:00",
  
  "final_label": "CONDITIONAL",
  "overall_drift_score": 0.45,
  "severity": "moderate",
  "reasons": [
    "Price distribution has shifted 2.3x from baseline",
    "5 relational anchors weakened",
    "15% of rows show market-shift pattern"
  ],
  
  "profiles": {
    "current": {
      "dataset_name": "apparel_inventory.csv",
      "row_count": 500,
      "column_count": 8,
      "created_at": "2025-01-06T14:25:00",
      "column_profiles": [
        {
          "column_name": "price",
          "inferred_type": "numeric",
          "missing_percent": 0.02,
          "unique_percent": 0.85,
          "min": 10,
          "max": 5000,
          "mean": 850,
          "std": 450,
          "sample_values": ["99.99", "199.99", "49.99", "299.99"],
          "scale_pattern": "continuous",
          "detected_unit": "currency",
          "detected_direction": "higher means premium"
        }
      ]
    },
    "internal": { /* internal baseline profile */ },
    "external": { /* external market baseline */ }
  },
  
  "feature_stats": {
    "safe_count": 425,
    "conditional_count": 65,
    "quarantined_count": 10
  },
  
  "drift_explanations": [
    {
      "column_name": "price",
      "drift_type": "numeric",
      "severity": "high",
      "reason": "Mean price increased 2.3x (₹850 → ₹1950)",
      "baseline_stats": { "mean": 850, "std": 450, "min": 10, "max": 5000 },
      "current_stats": { "mean": 1950, "std": 980, "min": 50, "max": 8500 },
      "impact": "Entire catalog pricing shifted upward. Could indicate new premium line or cost inflation.",
      "recommendation": "Review if this aligns with business strategy. Update internal baseline if intentional market expansion."
    }
  ],
  
  "row_level_drifts": [
    {
      "row_id": 1,
      "row_index": 0,
      "status": "CONDITIONAL",
      "confidence": 0.89,
      "affected_columns": ["price", "rating"],
      "reasons": ["Price increased 2.5x, rating stable"],
      "internal_similarity": 0.72,
      "external_similarity": 0.84
    }
  ],
  
  "triage_matrix": {
    "cells": [
      {
        "internal": "Aligned",
        "external": "Aligned",
        "decision": "SAFE",
        "rowCount": 425,
        "percentage": 85,
        "description": "Stable, no drift"
      },
      {
        "internal": "Drifted",
        "external": "Aligned",
        "decision": "CONDITIONAL",
        "rowCount": 65,
        "percentage": 13,
        "description": "Market shift detected"
      },
      {
        "internal": "Drifted",
        "external": "Outlier",
        "decision": "QUARANTINED",
        "rowCount": 10,
        "percentage": 2,
        "description": "Genuine drift"
      }
    ]
  },
  
  "relational_anchors": [
    {
      "anchor_id": "price_rating",
      "type": "numeric-numeric",
      "column_1": "price",
      "column_2": "rating",
      "status": "weakened",
      "baseline_correlation": 0.78,
      "current_correlation": 0.45,
      "confidence": 0.91,
      "description": "Premium products should have higher ratings",
      "violation_reason": "High-priced items now have mixed ratings (some cheap items rated highly)"
    }
  ],
  
  "learned_scores": {
    "distribution": {
      "SAFE": 425,
      "CONDITIONAL": 65,
      "QUARANTINED": 10
    },
    "feature_importance": {
      "internal_mean_distance": 0.868,
      "external_mean_distance": 0.663,
      "max_column_drift": 0.523,
      "text_similarity_to_external": 0.521,
      "text_similarity_to_internal": 0.482
    },
    "model_accuracy": 0.987,
    "avg_confidence": 0.923
  }
}
```

---

## Data Flow

```
User Upload CSV
     ↓
[Upload Button Keeps Data]
     ↓
[Call /detect-full endpoint]
     ↓
Backend Returns Complete Response (see above)
     ↓
Frontend Displays Tabs:
  1. Profiler → Shows column statistics
  2. Drift Explanation → Shows why each column drifted
  3. Row-Level → Shows which rows are affected
  4. Release Gate → Final decision
  5-8. Learned Model Details
```

---

## CSS Additions (Optional)

Add to FeatureOpsWorkflowPanel.css:

```css
.featureops-tabs {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid #e5e7eb;
  overflow-x: auto;
  padding-bottom: 8px;
  margin: 0;
  list-style: none;
}

.featureops-tabs button {
  padding: 8px 16px;
  border-radius: 6px 6px 0 0;
  border: 1px solid transparent;
  background: transparent;
  color: #6b7280;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.featureops-tabs button:hover {
  background: #f9fafb;
  color: #374151;
}

.featureops-tabs button.active {
  background: #ffffff;
  color: #111827;
  font-weight: 700;
  border: 1px solid #d1d5db;
  border-bottom: none;
}

.featureops-tab-content {
  padding: 24px;
  background: #ffffff;
  border-radius: 8px;
  min-height: 400px;
}
```

---

## Key Features

✅ **Keep existing upload feature** - Use same file input mechanism
✅ **Tab-based navigation** - Users can explore data at their own pace
✅ **Profiler first** - Show what was analyzed before decisions
✅ **Drift explanations** - Per-column breakdown with impact and recommendations
✅ **Row-level analysis** - Zoom into which rows have issues
✅ **Release decision** - Final triage decision with context
✅ **Full model details** - Learn curves, feature importance, anchors

---

## Testing the Integration

```bash
# 1. Upload a CSV with your apparel data
# 2. Click "Profiler" tab to see column analysis
# 3. Click "Drift Explanations" to understand why
# 4. Click "Row Analysis" to find problematic rows
# 5. Click "Release Decision" for final verdict
# 6. Explore details in other tabs
```

Done! ✅
