#!/usr/bin/env python3
"""Generate realistic interaction traffic for the Agentic AI dashboard.

This script calls existing backend endpoints so dashboard metrics update exactly
like real user activity.
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


QUERY_POOL = [
    "black t-shirt under 5000",
    "casual joggers for daily wear",
    "formal shirt for office",
    "beach wear for weekend",
    "minimalist outfit ideas",
    "blue oversized tee",
    "streetwear hoodie",
    "comfortable pants for travel",
    "neutral color tops",
    "jacket for rainy weather",
]

COLOR_POOL = ["Black", "Blue", "White", "Grey", "Brown", "Green"]
CATEGORY_POOL = ["T-SHIRTS", "JOGGERS & PANTS", "COATS", "BEACH WEAR", "SHIRTS"]
STYLE_POOL = ["Casual", "Formal", "Streetwear", "Minimalist", "Athleisure"]


def _request_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 20) -> tuple[int, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            raw = response.read().decode("utf-8", errors="replace")
            try:
                return status, json.loads(raw)
            except json.JSONDecodeError:
                return status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed
    except Exception as exc:
        return 0, {"error": str(exc)}


def _pick_users(base_url: str, fallback: list[str], max_users: int) -> list[str]:
    status, payload = _request_json(f"{base_url}/api/users")
    if status == 200 and isinstance(payload, dict) and isinstance(payload.get("users"), list):
        users = [str(item.get("id")) for item in payload["users"] if item and item.get("id")]
        if users:
            return users[:max_users]
    return fallback[:max_users]


def _update_preferences(base_url: str, user_id: str, rng: random.Random) -> None:
    pref_payload = {
        "preferences": {
            "categories": rng.sample(CATEGORY_POOL, k=rng.randint(1, min(3, len(CATEGORY_POOL)))),
            "colors": rng.sample(COLOR_POOL, k=rng.randint(1, min(3, len(COLOR_POOL)))),
            "styles": rng.sample(STYLE_POOL, k=rng.randint(1, min(3, len(STYLE_POOL)))),
            "fabrics": ["Cotton", "Linen"] if rng.random() > 0.5 else ["Denim"],
            "shops": ["Urban Outfit", "Colombo Styles"] if rng.random() > 0.5 else ["Downtown Fashion"],
        }
    }
    _request_json(
        f"{base_url}/api/users/{urllib.parse.quote(user_id)}/profile/preferences",
        method="PUT",
        payload=pref_payload,
    )


def _send_chat(base_url: str, user_id: str, text: str) -> tuple[int, Any]:
    return _request_json(
        f"{base_url}/api/answer",
        method="POST",
        payload={"user_id": user_id, "text": text},
    )


def _send_search(base_url: str, user_id: str, text: str) -> tuple[int, Any]:
    encoded_q = urllib.parse.quote(text)
    encoded_uid = urllib.parse.quote(user_id)
    return _request_json(f"{base_url}/api/search?q={encoded_q}&limit=8&user_id={encoded_uid}")


def _send_feedback(base_url: str, user_id: str, action: str, rating: int) -> None:
    _request_json(
        f"{base_url}/api/order-assistant/feedback",
        method="POST",
        payload={
            "user_id": user_id,
            "action": action,
            "rating": rating,
            "session_id": f"sim-{int(time.time())}",
        },
    )


def _print_snapshot(base_url: str) -> None:
    status, metrics = _request_json(f"{base_url}/api/dashboard/metrics")
    if status != 200 or not isinstance(metrics, dict):
        print(f"[snapshot] failed to fetch metrics: status={status} payload={metrics}")
        return

    print("[snapshot] "
          f"active_users={metrics.get('active_users')} "
          f"recommendations_served={metrics.get('recommendations_served')} "
          f"chat_success_rate={metrics.get('agent_success_rate')}% "
          f"pipeline={metrics.get('pipeline_status')} "
          f"interaction_total={metrics.get('user_interactions', {}).get('total_interactions')}")


def run_simulation(base_url: str, rounds: int, users_count: int, delay: float, seed: int | None) -> None:
    rng = random.Random(seed)
    users = _pick_users(base_url, fallback=["alice", "bob", "charlie", "dina", "eric"], max_users=users_count)

    print(f"Using {len(users)} users: {', '.join(users)}")

    for i in range(1, rounds + 1):
        user_id = rng.choice(users)
        query = rng.choice(QUERY_POOL)

        # Simulate mixed traffic: chat + search + preference changes + feedback.
        chat_status, _ = _send_chat(base_url, user_id, query)
        search_status, _ = _send_search(base_url, user_id, query)

        if rng.random() > 0.4:
            _update_preferences(base_url, user_id, rng)

        if rng.random() > 0.5:
            _send_feedback(base_url, user_id, action="checkout", rating=rng.randint(3, 5))

        print(f"[round {i}/{rounds}] user={user_id} chat={chat_status} search={search_status} query='{query}'")

        if i == 1 or i % 5 == 0 or i == rounds:
            _print_snapshot(base_url)

        if delay > 0:
            time.sleep(delay)

    print("Simulation complete.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate dashboard interactions for Agentic AI.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL (default: http://127.0.0.1:8000)")
    parser.add_argument("--rounds", type=int, default=30, help="Number of interaction rounds (default: 30)")
    parser.add_argument("--users", type=int, default=5, help="Number of users to simulate (default: 5)")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay in seconds between rounds (default: 0.25)")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed for reproducibility")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.rounds < 1:
        raise SystemExit("--rounds must be >= 1")
    if args.users < 1:
        raise SystemExit("--users must be >= 1")

    run_simulation(
        base_url=str(args.base_url).rstrip("/"),
        rounds=int(args.rounds),
        users_count=int(args.users),
        delay=float(args.delay),
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
