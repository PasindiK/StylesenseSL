"""Generate synthetic CSV dataset for query structuring: style, event, budget."""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

STYLES = ["casual", "formal", "boho", "streetwear", "minimal", "ethnic", "athleisure", "smart_casual"]
EVENTS = ["office", "beach", "wedding", "party", "travel", "gym", "date_night", "daily_wear"]
BUDGETS = ["low", "mid", "high"]

CATEGORY = ["dress", "shirt", "blazer", "jeans", "sneakers", "heels", "saree", "jacket", "kurta"]
COLORS = ["black", "white", "blue", "red", "green", "beige", "pink", "navy"]

PRICE_HINTS = {
    "low": ["under 3000", "below 2500", "budget friendly", "cheap", "affordable"],
    "mid": ["under 7000", "around 6000", "mid range", "quality for price"],
    "high": ["premium", "luxury", "designer", "under 15000", "high end"],
}


def make_query(style: str, event: str, budget: str) -> str:
    category = random.choice(CATEGORY)
    color = random.choice(COLORS)
    price = random.choice(PRICE_HINTS[budget])

    style_phrase = style.replace("_", " ")
    templates = [
        "show me {color} {category} in {style_phrase} style for {event} {price}",
        "need a {style_phrase} {category} suitable for {event} and {price}",
        "recommend {style_phrase} outfit for {event} in {color} {price}",
        "find {color} {category} for {event} with a {budget} budget and {style_phrase} look",
        "looking for {style_phrase} wear for {event}, {price}",
    ]
    return random.choice(templates).format(
        style=style,
        style_phrase=style_phrase,
        event=event.replace("_", " "),
        budget=budget,
        category=category,
        color=color,
        price=price,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate query structuring CSV")
    parser.add_argument("--output", default="src/services/agentic_ai/data/query_structuring/query_structuring_12000.csv")
    parser.add_argument("--rows", type=int, default=12000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for _ in range(args.rows):
        style = random.choice(STYLES)
        event = random.choice(EVENTS)
        budget = random.choice(BUDGETS)
        rows.append({
            "query": make_query(style, event, budget),
            "style": style,
            "event": event,
            "budget": budget,
        })

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "style", "event", "budget"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"generated_rows={args.rows}")
    print(f"output={out_path}")


if __name__ == "__main__":
    main()
