Data Architecture frontend module files go here.

Live Validation Demo Flow
- Open the `Live Validation` tab in the Data Architecture dashboard.
- Select a baseline dataset from `Step 1` to show the current input schema and sample rows.
- Upload a new CSV in `Step 2` and run validation.
- Use `Step 3` to present:
	- drift/no-drift outcome,
	- exact schema changes,
	- before vs after analytics values.

Demo CSV files (ready for viva)
- `backend/src/services/data_architecture/demo/live_validation/transactions_no_drift.csv`
- `backend/src/services/data_architecture/demo/live_validation/transactions_with_drift.csv`

Expected behavior
- `transactions_no_drift.csv`: should show `No Schema Drift`.
- `transactions_with_drift.csv`: should show schema drift with new/missing/type change details.
- When ingestion is enabled, dashboard summary analytics refresh so other pages reflect updated values.
