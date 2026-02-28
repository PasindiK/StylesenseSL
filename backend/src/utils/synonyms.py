"""Canonical synonyms for categories, colors, fabrics and style tags.

This file provides small dictionaries used by the DataLoader to normalize
incoming product data to canonical values.
"""

category_synonyms = {
    # Male-focused canonical categories aligned to dataset
    "t-shirts": ["t-shirt", "tshirt", "tee", "tees", "t shirts", "tshirts"],
    "oversize tee": ["oversize t-shirt", "oversize tshirt", "oversize tees"],
    "shorts": ["short", "bermuda"],
    "chinos": ["chino"],
    "joggers & pants": ["joggers", "pants", "trousers", "pant"],
    "track pants": ["tracks", "track"],
    "utility pants": ["cargo", "utility"],
    "denim jackets": ["jean jacket", "denim"],
    "blazers": ["blazer"],
    "coats": ["coat"],
    "cardigans": ["cardigan"],
    "beach wear": ["beachwear", "beach"],
}

color_synonyms = {
    "dark blue": ["navy", "navy blue"],
    "light blue": ["sky blue", "baby blue", "pastel blue"],
    "red": ["crimson", "maroon"],
    "green": ["olive", "lime"],
    "brown": ["chocolate", "tan"],
    "multi-color": ["multi", "multicolor"],
}

fabric_synonyms = {
    "cotton": ["cotton blend", "100% cotton"],
    "linen": ["linen blend"],
}

style_synonyms = {
    "beach wear": ["beachwear", "beach"],
    "casual": ["everyday", "relaxed"],
    "formal": ["party", "evening"],
}
