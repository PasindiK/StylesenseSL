## Agentic AI Dashboard Data

`AgenticAIDashboard.tsx` pulls live data from these backend endpoints:

- `GET /api/dashboard/metrics`
- `GET /api/users/{user_id}/profile`
- `PUT /api/users/{user_id}/profile/preferences`
- `PUT /api/users/{user_id}/profile`

The dashboard auto-refreshes metrics every 10 seconds, so changes from user interactions appear without page reload.

## Simulate Full Dashboard Activity

Use the backend simulator script to generate chat, search, feedback, and preference updates.

From `c:\Test\backend`:

```powershell
& ".\.venv\Scripts\python.exe" .\scripts\simulate_dashboard_interactions.py --base-url http://127.0.0.1:8000 --rounds 50 --users 8 --delay 0.2
```

What this updates:

- `chat_requests`, `agent_success`, `query_logs`
- `recommendations_served`, `real_time_feed`
- `intent_distribution`, strategy usage
- user profile preferences and order feedback

## Quick Validation

1. Start backend API on `:8000`.
2. Start frontend and open the Agentic AI dashboard.
3. Run the simulator command above.
4. Watch System Overview, Knowledge Graph, and Recommendation Feedback sections update over time.
