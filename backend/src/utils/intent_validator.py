"""Intent Quality Validator - Filters out garbage/nonsense queries before product search."""

import re
from typing import Dict, Tuple


class IntentQualityValidator:
    """Validates if a user query is meaningful enough to search products."""
    
    def __init__(self):
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
        
        # 3. Allow any query with letters - let OpenAI classifier handle intent
        if re.search(r'[a-zA-Z]', text_clean):
            return True, "Valid query with letters"
        
        # 4. Check for excessive repeated characters (e.g., "aaaaaaa")
        # Make this more lenient - allow up to 6 repeated chars
        if re.search(r'(.)\1{6,}', text_clean):
            return False, "Excessive repeated characters"
        
        # 5. Check if contains at least one recognizable word
        words = text_clean.split()
        has_known_word = False
        
        for word in words:
            # Check exact match
            if word in self.common_words:
                has_known_word = True
                break
            
            # Check if any common word is a substring (e.g., "dresses" contains "dress")
            for common in self.common_words:
                if common in word or word in common:
                    has_known_word = True
                    break
            
            if has_known_word:
                break
        
        # If no known words but query is long enough and has vowels, give benefit of doubt
        if not has_known_word:
            if len(text_clean) >= 5 and ' ' in text_clean:
                # Multiple words that look real-ish
                return True, "Multi-word query accepted"
            else:
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
            "No recognizable shopping terms found": "I'm not sure what you're looking for. Could you describe the product? Like 'summer dresses' or 'sports shoes'",
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
