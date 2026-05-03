# Demo datasets: five baselines + five semantic-drift uploads

All CSVs live in this repo (no external host required). **“Download”** = copy them out of the clone, or use the script / raw GitHub URLs below.

## A) Five baseline CSVs (register first in FeatureOps)

Aligned with the five **predefined architecture** schemas (`product_catalog`, `user_profiles`, `sales_transactions`, `shop_directory`, `fashion_trends`).

| # | File | Use as `dataset_name` (suggestion) |
|---|------|-------------------------------------|
| 1 | `demo_architecture_baselines/01_product_catalog_baseline.csv` | `product_catalog` |
| 2 | `demo_architecture_baselines/02_user_profiles_baseline.csv` | `user_profiles` |
| 3 | `demo_architecture_baselines/03_sales_transactions_baseline.csv` | `sales_transactions` |
| 4 | `demo_architecture_baselines/04_shop_directory_baseline.csv` | `shop_directory` |
| 5 | `demo_architecture_baselines/05_fashion_trends_baseline.csv` | `fashion_trends` |

### Copy locally (Windows PowerShell, from repo root)

```powershell
$dst = "$env:USERPROFILE\Downloads\StyleSense_demo_baselines"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item "backend\data\demo_architecture_baselines\*.csv" -Destination $dst
```

### Optional: raw GitHub (after you push)

Replace `OWNER`, `REPO`, and `BRANCH`:

```text
https://raw.githubusercontent.com/OWNER/REPO/BRANCH/backend/data/demo_architecture_baselines/01_product_catalog_baseline.csv
```

(Same path pattern for `02_` … `05_`.)

---

## B) Five follow-up uploads (semantic drift storyboard)

| File | Demo story |
|------|------------|
| `demo_semantic_drift_uploads/01_products_followup_no_drift.csv` | Same columns/meaning → treat as **no drift** follow-up to products baseline. |
| `demo_semantic_drift_uploads/02_users_followup_no_drift.csv` | Same schema → **no drift** for users. |
| `demo_semantic_drift_uploads/03_transactions_followup_no_drift.csv` | Same schema → **no drift** for transactions. |
| `demo_semantic_drift_uploads/04_transactions_column_rename.csv` | Uses **`qty`** instead of **`quantity`** → **self-heal / synonym** style demo for transactions. |
| `demo_semantic_drift_uploads/05_transactions_semantic_stock_meaning.csv` | **`quantity`** with **warehouse / stock_location / inventory_status** → **semantic drift** (sold vs stock) + extra columns → **quarantine** style demo. |

### Copy drift pack

```powershell
$dst = "$env:USERPROFILE\Downloads\StyleSense_demo_drift_uploads"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item "backend\data\demo_semantic_drift_uploads\*.csv" -Destination $dst
```

---

## C) Suggested viva order

1. Create baseline family from `01_…` … `05_…` (or ingest via `/api/semantic-drift/baseline/create` if you use that module with matching rules).
2. Upload `01_products_followup…` → explain **accepted / no drift**.
3. Upload `04_transactions_column_rename…` → explain **rename / self-heal**.
4. Upload `05_transactions_semantic_stock…` → explain **same column name, different business meaning** → **quarantine / human review**.
