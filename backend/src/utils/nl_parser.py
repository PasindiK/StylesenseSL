import re
from typing import Dict, Optional, List

try:
    from rapidfuzz import process, fuzz
except Exception:
    process = None
    fuzz = None


def _fuzzy_pick(query: str, choices: List[str], threshold: int = 70) -> Optional[str]:
    if not query or not choices or process is None:
        return None
    try:
        hits = process.extract(query, choices, scorer=fuzz.token_sort_ratio, limit=3)
        hits = [h for h in hits if h[1] >= threshold]
        return hits[0][0] if hits else None
    except Exception:
        return None


def parse_intent(text: str, known_shops: Optional[List[str]] = None, known_categories: Optional[List[str]] = None) -> Dict[str, Optional[object]]:
    """Parse natural language into structured intent with fuzzy mapping.

    Returns keys: intent, category, shop, color, max_price, occasion, gender, raw_text.
    """
    if not text:
        return {
            "intent": "search",
            "category": None,
            "shop": None,
            "color": None,
            "max_price": None,
            "occasion": None,
            "gender": "male",
            "raw_text": text,
        }

    txt = text.strip()
    res = {
        "intent": "search",
        "category": None,
        "shop": None,
        "color": None,
        "max_price": None,
        "occasion": None,
        "gender": "male",  # default to male as dataset focus
        "raw_text": txt,
    }

    low = txt.lower()
    # intent type heuristic
    if any(k in low for k in ["recommend", "suggest", "what should", "what would"]):
        res["intent"] = "recommendation"
    elif any(k in low for k in ["how", "what is", "can i", "where can"]):
        res["intent"] = "question"
    else:
        res["intent"] = "search"

    # price: 'under/below 5000'
    m = re.search(r"(?:under|below)\s+([0-9,]+)", txt, flags=re.IGNORECASE)
    if m:
        try:
            res["max_price"] = int(m.group(1).replace(",", ""))
        except Exception:
            res["max_price"] = None

    # shop: 'from/at/in <shop>'
    m = re.search(r"(?:from|at|in)\s+([A-Za-z0-9&\- ]{2,40})", txt, flags=re.IGNORECASE)
    if m:
        raw_shop = m.group(1).strip()
        if known_shops:
            match = _fuzzy_pick(raw_shop, known_shops, threshold=65)
            res["shop"] = match or raw_shop
        else:
            res["shop"] = raw_shop

    # occasion
    for occ in ("beach", "casual", "formal", "party", "office", "winter", "summer", "sporty"):
        if re.search(r"\b" + re.escape(occ) + r"\b", low):
            res["occasion"] = occ
            break

    # category / tag: detect 'wear' or known categories
    m = re.search(r"([A-Za-z ]+wear)\b", txt, flags=re.IGNORECASE)
    if m:
        res["category"] = m.group(1).strip()
    else:
        # look for dataset categories using fuzzy match
        if known_categories:
            # tokenize to prioritize likely tokens
            tokens = [t for t in re.split(r"[ ,]+", low) if t]
            candidate = None
            for t in tokens:
                candidate = _fuzzy_pick(t, known_categories, threshold=70) or candidate
            if not candidate:
                # try whole string fuzzy
                candidate = _fuzzy_pick(low, known_categories, threshold=60)
            res["category"] = candidate

    # color: common colors
    for color in ("red", "blue", "white", "black", "green", "yellow", "pink", "beige", "brown", "navy", "grey", "orange"):
        if re.search(r"\b" + re.escape(color) + r"\b", low):
            res["color"] = color
            break

    return res
