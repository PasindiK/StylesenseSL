# Baseline-Driven Semantic Drift Detection with Self-Healing Ingestion

## What is semantic drift?

Traditional checks often accept a column if the **name** and **primitive type** match. Semantic drift means the **business meaning** diverges—for example `quantity` still looks numeric, but values represent **warehouse stock** instead of **units sold**.

## How is the baseline created?

Upload an approved CSV via `POST /api/semantic-drift/baseline/create`. The service:

- Validates required columns for the demo sales schema.
- Attaches **rule-based** semantic profiles (business meaning, role, domain, unit, scale).
- Persists the baseline and profiles in **ChromaDB** (`semantic_baseline_registry`, `baseline_column_profiles`).

## How is drift detected? (interpretation drift)

For each **matched** column (same name / synonym mapping):

1. **Meaning drift** — **embedding similarity only** on a rich text card (name, meaning, role, domain, unit, scale, value direction). No fixed 40/25/10 field-weight score in the hot path.
2. **Numeric encoding drift** — when baseline CSV snapshot stats exist (`ref_mean`, `ref_std`, … stored at baseline creation), the service proposes **identity / affine / min-max** transforms and scores alignment to the baseline distribution. Alignment is folded into the **combined** decision **only when an encoding shift is suspected** (e.g. very different value span vs baseline, or affine clearly beats identity). Otherwise batch-level mean shifts do not false-trigger review.
3. **Decisions** — `APPEND`, `SELF_HEAL` (safe numeric transform + existing renames/casts/dates), `HUMAN_REVIEW`, or `QUARANTINE`. Cutoffs live in `interpretation_calibration.json` (tunable per environment; raise `append_min` when using full SentenceTransformer instead of TF-IDF tests).

**Governance guards** (configurable in the same JSON, default: sold-order quantity vs inventory/stock meaning) force **QUARANTINE** — not a hidden Python constant.

## Self-healing (safe only)

Allowed: synonym column renames (`sales_amt`→`sales_amount`, `qty`→`quantity`), numeric coercion, date standardization, optional `discount_amount` if missing, and **interpretation-approved affine/min-max** transforms when the batch decision is `SELF_HEAL`.

Not allowed: auto-heal when any column is `HUMAN_REVIEW` or `QUARANTINE`, reinterpret stock as sold without guard review, auto-updating baselines, or silent major meaning changes.

## Human review path

If aggregate decision is `HUMAN_REVIEW`, ingestion finishes with status **`pending_human_review`**, `accepted_rows=0`, and detailed rows in `drift_results` (see `interpretation` + `transform_proposal`). No quarantine row is written; operators reconcile calibration or approve a follow-up ingest.

## When data is appended

If the batch ends **accepted** or **accepted_after_repair**, each row is written to the Chroma collection `sales_transactions` with a unique `record_id`, `ingestion_batch_id`, and `baseline_version`.

## When data is quarantined

The upload is recorded in `quarantined_datasets` with a reason and suggested action. **No** rows are appended to sales.

## Why no fine-tuning for v1?

The novelty is **governance + explainability**: a frozen baseline plus transparent rules and similarity scoring. Fine-tuning can be future work if labeled drift pairs are collected at scale.

## Download final Chroma tables (CSV)

After ingest, the JSON body includes **`export_download_paths`** with ready-to-call paths. You can also call directly:

| GET | Purpose |
|-----|---------|
| `/api/semantic-drift/export/sales?batch_id=<bat_…>` | Final **sales_transactions** rows for that ingest (post drift + repairs). |
| `/api/semantic-drift/export/sales` | All sales rows in Chroma. |
| `/api/semantic-drift/export/drift-results/<batch_id>` | Drift / interpretation rows for the batch. |
| `/api/semantic-drift/export/batches` | All ingestion batch metadata. |

Responses are `text/csv` with `Content-Disposition: attachment`.

## Demo sequence

1. `POST /baseline/create` with `demo_data/baseline_sales.csv`
2. `GET /baseline/{dataset_name}`
3. `POST /ingest` with `no_drift_upload.csv`
4. `POST /ingest` with `column_rename_upload.csv` (expect repairs)
5. `POST /ingest` with `semantic_drift_upload.csv` (expect quarantine)
6. `GET /sales` and `GET /quarantine`
7. `GET /api/semantic-drift/export/sales?batch_id=<from_step_3>` to download the final table for that batch

CLI: `python scripts/run_semantic_drift_demo.py` (optionally `SEMANTIC_DRIFT_CHROMA_DEMO_DIR` for a clean store).
