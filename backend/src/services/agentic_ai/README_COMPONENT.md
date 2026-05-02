# Agentic Semantic FeatureOps Component

This branch replaces the legacy weighted recommendation equation with a governed,
standalone-capable Agentic AI component made of two layers:

1. `featureops/`
   - contract validation
   - semantic drift tracking
   - non-compensatory feature release gate
   - file-backed feature registry
2. ranking
   - semantic candidate retrieval from the existing `CatalogAgent`
   - governed feature generation
   - LambdaMART-ready reranking
   - geometric non-linear fallback when no trained ranker artifact is present
   - MMR diversification

## Key integration points

- Existing app path stays the same:
  - `src.api.app -> PersonalizationAgent -> MultiStageRanker`
- Existing response contract stays the same:
  - `results`
  - `best_matches`
  - `new_suggestions`
  - `explanations`
- Other platform components remain untouched:
  - Data Architecture
  - Data Fabric
  - Data Mesh

## Standalone usage

From the `backend/` directory:

```powershell
python -m src.services.agentic_ai.scripts.run_featureops_component
```

## Optional ranker training

Train the LambdaMART-ready model artifact:

```powershell
python -m src.services.agentic_ai.scripts.train_ltr_ranker
```

The trained model is saved under:

`src/services/agentic_ai/agents/models/ltr/lambdamart_ranker.joblib`

If the model file is absent, the component still works using the governed
geometric fallback ranker.
