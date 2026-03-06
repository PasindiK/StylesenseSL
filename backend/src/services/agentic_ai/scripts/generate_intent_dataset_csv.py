"""Generate a 7k+ synthetic intent dataset CSV for DistilBERT training."""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path
from typing import Dict, List

from src.services.agentic_ai.agents.intent_taxonomy import INTENT_TYPES


def _templates() -> Dict[str, List[str]]:
    categories = ["t shirts", "dresses", "shirts", "jeans", "skirts", "blazers", "sneakers", "heels", "joggers"]
    colors = ["black", "white", "blue", "red", "green", "beige", "pink", "navy"]
    occasions = ["office", "beach", "party", "casual", "wedding", "gym"]
    budget = ["3000", "5000", "7000", "9000", "12000"]

    search = [
        "show me {color} {category} under {price}",
        "find {occasion} {category} for women",
        "i need {category} for {occasion}",
        "recommend {color} {category}",
    ]
    style = [
        "how to style {color} {category}",
        "outfit tips for {occasion} look",
        "what goes well with {category}",
        "fashion advice for {occasion} wear",
    ]

    data = {
        "greeting": ["hi", "hello", "hey there", "good morning", "good evening"],
        "farewell": ["bye", "thank you", "thanks bye", "see you", "take care"],
        "small_talk": ["how are you", "hows your day", "what's new", "are you available", "how is it going"],
        "product_search": [t.format(color=random.choice(colors), category=random.choice(categories), occasion=random.choice(occasions), price=random.choice(budget)) for t in search],
        "styling_advice": [t.format(color=random.choice(colors), category=random.choice(categories), occasion=random.choice(occasions)) for t in style],
        "feedback_positive": ["this is perfect", "i love this", "great recommendation", "amazing choices", "exactly what i wanted"],
        "feedback_negative": ["not my style", "show me something else", "too expensive", "i dont like this", "different options please"],
        "clarification": ["maybe", "not sure", "idk", "anything", "can you help"],
        "add_to_cart": ["add this to cart", "add first one to cart", "put this item in my cart", "add item two", "add these to my shopping cart"],
        "view_cart": ["show my cart", "view cart", "what is in my cart", "open shopping cart", "check cart items"],
        "clear_cart": ["clear cart", "empty my cart", "remove all items from cart", "delete everything in cart", "reset cart"],
        "order_request": ["checkout now", "place my order", "buy this now", "i want to purchase", "proceed to payment"],
    }

    # Expand search/style templates each call for more diversity.
    for _ in range(200):
        data["product_search"].append(
            random.choice(search).format(
                color=random.choice(colors),
                category=random.choice(categories),
                occasion=random.choice(occasions),
                price=random.choice(budget),
            )
        )
        data["styling_advice"].append(
            random.choice(style).format(
                color=random.choice(colors),
                category=random.choice(categories),
                occasion=random.choice(occasions),
            )
        )

    return data


def generate_dataset(output_csv: Path, total_rows: int = 8400, seed: int = 42) -> None:
    random.seed(seed)
    templates = _templates()

    per_intent = total_rows // len(INTENT_TYPES)
    rows = []
    for intent in INTENT_TYPES:
        options = templates[intent]
        for _ in range(per_intent):
            rows.append({"text": random.choice(options), "label": intent})

    remainder = total_rows - len(rows)
    if remainder > 0:
        for _ in range(remainder):
            intent = random.choice(INTENT_TYPES)
            rows.append({"text": random.choice(templates[intent]), "label": intent})

    random.shuffle(rows)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text", "label"])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic intent CSV data")
    parser.add_argument(
        "--output",
        default="src/services/agentic_ai/data/intent/intent_dataset_8400.csv",
        help="Output CSV path",
    )
    parser.add_argument("--rows", type=int, default=8400, help="Number of rows")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    generate_dataset(Path(args.output), total_rows=args.rows, seed=args.seed)
    print(f"generated_rows={args.rows}")
    print(f"output={args.output}")
