# Phase 4: Dashboard Integration Plan

## Current State (After Phase 3)

- ✅ Backend: 4 agents complete (ProfilerAgent, BaselineAgent, RelationalAnchorAgent, LearnedScoringAgent)
- ✅ API endpoints: Existing drift detection routes functional
- ✅ Models: Logistic Regression trained and saved
- ⏳ Frontend: Needs new UI components for:
  1. Twin-Baseline Comparison
  2. Triage Matrix
  3. Relational Anchor Violations
  4. Learned Score Distribution
  5. Release Gate (Final Decision)

## Phase 4 Tasks

### 1. Create New React Components

**Components to Create**:

#### a) TriageMatrixCard.tsx
- Shows 2x2 matrix: Internal (Aligned/Drifted) × External (Aligned/Outlier)
- Colors: SAFE (green), CONDITIONAL (yellow), QUARANTINED (red)
- Click to see examples of each

#### b) RelationalAnchorsCard.tsx
- Table view of discovered anchors
- Columns: anchor_id, type, status, confidence, violation_count
- Expandable rows showing details

#### c) LearnedScoresChart.tsx
- Pie chart or stacked bar: P(SAFE), P(CONDITIONAL), P(QUARANTINED)
- Show confidence intervals
- Display top features contributing to prediction

#### d) TwinBaselineComparison.tsx
- Side-by-side view: Internal | Current | External
- Row_count, column_count, dataset_name, built_at
- Visual diff of column differences

#### e) ReleaseGate.tsx
- Large button showing final decision
- Color-coded: Green (SAFE), Yellow (CONDITIONAL), Red (QUARANTINED)
- Reasoning text below button
- Action buttons: Approve / Review / Reject

### 2. Update Existing Components

#### FeatureOpsWorkflowPanel.tsx
- Add new section for triage results
- Tab-based navigation:
  - Tab 1: Twin-Baseline Comparison
  - Tab 2: Triage Matrix
  - Tab 3: Relational Anchors
  - Tab 4: Learned Scores
  - Tab 5: Release Decision

### 3. Update API Integration

**Endpoints to Use**:
- `POST /api/featureops/drift/detect-internal` (existing)
- `POST /api/featureops/drift/detect-external` (existing)
- `GET /api/featureops/drift/baselines` (existing)

**Response Structure** (ensure backend returns):
```json
{
  "drift_run_id": "uuid",
  "final_label": "SAFE|CONDITIONAL|QUARANTINED",
  "overall_drift_score": 0.423,
  "severity": "low|moderate|high",
  "reasons": ["reason1", "reason2"],
  "internal_status": "Aligned|Drifted",
  "external_status": "Market-Aligned|Outlier",
  "row_results": [{
    "row_id": "N0",
    "internal_status": "Drifted",
    "external_status": "Outlier",
    "final_label": "QUARANTINED",
    "reasoning": "...",
    "internal_similarity": 0.237,
    "external_similarity": 0.266
  }],
  "profiles": {
    "current_profile": {...},
    "internal_baseline": {...},
    "external_baseline": {...}
  }
}
```

### 4. Styling & Layout

**CSS Updates**:
- Dashboard grid layout (3+ columns)
- Card-based design (TailwindCSS)
- Color scheme:
  - SAFE: Green (#10B981)
  - CONDITIONAL: Amber (#F59E0B)
  - QUARANTINED: Red (#EF4444)

### 5. Data Flow

```
User Uploads CSV
  ↓
API: /detect-internal
  ↓
Backend processes (Profiler → Baseline → Anchor → Scorer)
  ↓
Response with profiles + scores
  ↓
Frontend displays:
  - TwinBaselineComparison
  - TriageMatrix
  - RelationalAnchorsCard
  - LearnedScoresChart
  - ReleaseGate
```

## Timeline

**Phase 4 Estimate**: 3-4 hours

- Component creation: 1.5-2h
- API integration: 0.5-1h
- Styling & testing: 1-1.5h

## Success Criteria

✅ All 5 new React components created and functional
✅ Data flows from API response to UI components
✅ Colors and layout match Figma design (or wireframe)
✅ Clicking elements reveals detailed information
✅ No TypeScript errors
✅ Responsive on mobile and desktop

## Files to Create

```
frontend/src/modules/agentic_ai/components/
  ├─ TriageMatrixCard.tsx         (NEW)
  ├─ RelationalAnchorsCard.tsx    (NEW)
  ├─ LearnedScoresChart.tsx       (NEW)
  ├─ TwinBaselineComparison.tsx   (NEW)
  ├─ ReleaseGate.tsx              (NEW)
  └─ FeatureOpsWorkflowPanel.tsx  (MODIFY)

frontend/src/modules/agentic_ai/styles/
  └─ triage-components.css        (NEW, optional)
```

## Implementation Order

1. **ReleaseGate.tsx** - Simplest, shows final decision
2. **TwinBaselineComparison.tsx** - Shows side-by-side profiles
3. **TriageMatrixCard.tsx** - Shows 2x2 matrix
4. **RelationalAnchorsCard.tsx** - Shows anchor table
5. **LearnedScoresChart.tsx** - Shows score distribution
6. **Update FeatureOpsWorkflowPanel.tsx** - Integrate all components

## Notes

- All components should handle loading states
- Error handling: Show message if profiles are missing
- Tooltips for feature importance
- Export/download triage report (future enhancement)
