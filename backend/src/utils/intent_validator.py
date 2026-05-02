"""Intent Quality Validator - filters garbage and out-of-domain queries."""

import re
from typing import Dict, Tuple


class IntentQualityValidator:
    """Validates if a user query is meaningful enough to search products."""
    
    def __init__(self):
        self.fashion_words = {
            "dress", "dresses", "shirt", "shirts", "pant", "pants", "trouser", "trousers",
            "jean", "jeans", "jacket", "coat", "hoodie", "sweater", "top", "tops", "skirt",
            "kurti", "saree", "shoe", "shoes", "sneaker", "sneakers", "heel", "heels",
            "bag", "bags", "watch", "watches", "fashion", "outfit", "outfits", "style",
            "styling", "apparel", "clothing", "clothes", "wear", "wearing", "formal", "casual",
            "party", "office", "wedding", "summer", "winter", "cotton", "denim", "silk",
            "black", "white", "blue", "red", "green", "pink", "beige", "navy",
            "size", "small", "medium", "large", "xl", "xxl", "budget", "price", "under",
            "recommend", "recommendation", "catalog", "product", "products", "shop", "shopping",
            "cart", "checkout", "order", "add", "buy", "purchase", "find", "show", "search",
        }

        self.conversation_words = {
            "hi", "hello", "hey", "bye", "goodbye", "thanks", "thank", "ok", "okay",
            "how", "are", "you", "doing", "good", "morning", "afternoon", "evening",
        }

        self.non_fashion_cues = {
            "weather", "temperature", "rain", "bitcoin", "stock", "politics", "election",
            "math", "equation", "code", "program", "python", "java", "translate", "recipe",
            "hospital", "medicine", "doctor", "movie", "cricket", "football", "news",
        }

        # Common English words that indicate valid queries
        self.common_words = {
            # Shopping intent words
            "show", "find", "get", "need", "want", "looking", "search", "buy", "purchase",
            # Product categories
            "dress", "shirt", "pant", "shoe", "jacket", "coat", "top", "bottom", "wear",
            "clothing", "clothes", "outfit", "apparel", "fashion", "garment",
            # Colors
            "red", "blue", "green", "black", "white", "yellow", "orange", "pink", "purple",
            "brown", "grey", "gray", "navy", "beige", "cream", "gold", "silver",
            # Occasions
            "casual", "formal", "party", "office", "beach", "wedding", "sport", "gym",
            # Styles
            "vintage", "modern", "classic", "trendy", "elegant", "comfy", "comfortable",
            "stylish", "fashionable", "chic", "casual", "relaxed",
            # Sizes
            "small", "medium", "large", "xl", "xxl", "size",
            # Materials
            "cotton", "silk", "leather", "denim", "wool", "polyester", "fabric",
            # Gender
            "men", "women", "male", "female", "unisex", "boy", "girl", "kids",
            # Actions
            "recommend", "suggest", "help", "advice", "tips", "ideas",
            # Common modifiers
            "new", "latest", "best", "cheap", "affordable", "expensive", "quality",
            # Price related
            "price", "budget", "cost", "under", "below", "around", "approximately",
        }
        
        # Patterns that indicate garbage input
        self.garbage_patterns = [
            r'^[0-9]+$',  # Only numbers
            r'^[!@#$%^&*()_+=\-\[\]{};:"\',.<>/?\\|`~]+$',  # Only special characters
        ]
        
        # Common valid short queries that should NOT be rejected
        self.valid_short_queries = {
            "hi", "hey", "hello", "bye", "thanks", "ok", "yes", "no",
            "xl", "xxl", "xs", "s", "m", "l",  # sizes
        }
    
    def classify_scope(self, text: str) -> str:
        """Classify query scope into fashion, conversation, non_fashion or garbage."""
        if not text or not text.strip():
            return "garbage"

        text_clean = text.strip().lower()
        tokens = re.findall(r"[a-zA-Z]+", text_clean)
        if not tokens:
            return "garbage"

        token_set = set(tokens)
        has_fashion = bool(token_set.intersection(self.fashion_words))
        has_conversation = bool(token_set.intersection(self.conversation_words))
        has_non_fashion_cue = bool(token_set.intersection(self.non_fashion_cues))

        if has_fashion:
            return "fashion"
        if has_non_fashion_cue and not has_conversation:
            return "non_fashion"
        if has_conversation and len(tokens) <= 8:
            return "conversation"

        # Multi-word natural sentence without domain cues is likely out-of-domain.
        if len(tokens) >= 3:
            return "non_fashion"
        return "garbage"

    def is_valid_query(self, text: str) -> Tuple[bool, str]:
        """
        Check if query is valid or garbage.
        
        Returns:
            (is_valid: bool, reason: str)
        """
        if not text or not text.strip():
            return False, "Empty query"
        
        text_clean = text.strip().lower()
        
        # 0. Allow common valid short queries immediately
        if text_clean in self.valid_short_queries:
            return True, "Valid common query"
        
        # 1. Check minimum length (at least 1 character - be more lenient)
        if len(text_clean) < 1:
            return False, "Query too short"
        
        # 2. Check for garbage patterns (only very obvious garbage)
        for pattern in self.garbage_patterns:
            if re.match(pattern, text_clean):
                return False, "Appears to be random characters"
        
        # 3. Check for excessive repeated characters (e.g., "aaaaaaa")
        # Make this more lenient - allow up to 6 repeated chars
        if re.search(r'(.)\1{6,}', text_clean):
            return False, "Excessive repeated characters"

        # 4. Scope check keeps non-fashion and random text out of catalog search.
        scope = self.classify_scope(text_clean)
        if scope == "fashion" or scope == "conversation":
            return True, "Valid query"
        if scope == "non_fashion":
            return False, "Query not related to fashion"
        return False, "No recognizable shopping terms found"
        
        return True, "Valid query"
    
    def get_validation_message(self, reason: str) -> str:
        """Get user-friendly message for invalid queries."""
        messages = {
            "Empty query": "Please tell me what you're looking for!",
            "Query too short": "Could you be more specific? Try: 'red dresses' or 'casual shoes'",
            "Appears to be random characters": "I didn't understand that. Try asking for specific products like 'blue shirts' or 'formal wear'",
            "No vowels found - likely not a real word": "That doesn't look like a valid search. Try: 'comfortable clothes' or 'stylish jackets'",
            "Excessive repeated characters": "Please enter a proper search query. Example: 'black pants under 3000'",
            "No recognizable shopping terms found": "I'm not sure what you're looking for. Could you describe the product? Like 'casual outfits' or 'sports wear'",
            "Query not related to fashion": "I can help with fashion, styling, products, cart, and orders. Please ask a fashion-related question like 'show me white shirts' or 'suggest an office outfit'.",
        }
        
        return messages.get(reason, "I didn't understand that. Please describe what product you're looking for!")


# Global instance
_validator = None


def get_intent_validator() -> IntentQualityValidator:
    """Get or create the global intent validator."""
    global _validator
    if _validator is None:
        _validator = IntentQualityValidator()
    return _validator
