"""
Zero-Shot Intent Classifier Agent

Uses OpenAI API for semantic intent understanding with confidence scores.
This replaces rule-based pattern matching for intelligent routing.

Intent Categories:
- product_search: Looking for products to buy
- styling_advice: How to style/wear/match items
- small_talk: Casual conversation, greetings, "how are you"
- greeting: Initial hello/hi
- farewell: Goodbye, thanks
- feedback: User reactions (positive/negative)
- cart_action: Add/view/clear cart (caught by rules first)
- clarification: Vague/unclear queries
"""
import logging
from typing import Dict, Any, Optional
import os
import json

logger = logging.getLogger(__name__)

# Check if OpenAI is available
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_AVAILABLE = bool(OPENAI_API_KEY)

if OPENAI_AVAILABLE:
    try:
        from openai import OpenAI
        logger.info("✅ OpenAI SDK loaded - zero-shot classification enabled")
    except ImportError:
        OPENAI_AVAILABLE = False
        logger.warning("⚠️ OpenAI SDK not available - install: pip install openai")
else:
    logger.warning("⚠️ OPENAI_API_KEY not found - using fallback rules")


class IntentClassifierAgent:
    """Zero-shot intent classifier using OpenAI API for semantic understanding."""
    
    # Supported intent types with descriptions
    INTENTS = {
        "product_search": "User wants to find/browse/search for products to buy (e.g., 'show me blue dresses', 'find casual shoes')",
        "styling_advice": "User wants tips on how to style, wear, or match clothing items (e.g., 'how should I style denim', 'outfit tips')",
        "small_talk": "Casual conversation, asking how the assistant is, general chat (e.g., 'how are you', 'what's new', 'how's your day')",
        "greeting": "Initial greeting or hello (e.g., 'hi', 'hello', 'hey there', 'good morning')",
        "farewell": "Goodbye or thank you message (e.g., 'bye', 'thanks', 'see you later')",
        "feedback_positive": "User likes/loves the recommendations (e.g., 'I love this', 'perfect', 'amazing')",
        "feedback_negative": "User dislikes or wants something different (e.g., 'not my style', 'show me something else')",
        "clarification": "Vague or unclear query needing more details (e.g., 'idk', 'maybe', 'anything')",
    }
    
    def __init__(self):
        """Initialize intent classifier."""
        self.enabled = OPENAI_AVAILABLE
        if self.enabled:
            from openai import OpenAI
            self.client = OpenAI(api_key=OPENAI_API_KEY)
            logger.info("🧠 Zero-shot intent classifier initialized with OpenAI GPT-3.5-turbo")
        else:
            self.client = None
            logger.warning("⚠️ Intent classifier disabled - OpenAI API not available. Falling back to rules.")
    
    def classify_intent(self, query: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Classify user intent using zero-shot learning with OpenAI.
        
        Args:
            query: User's natural language query
            user_context: Optional context (user_name, last_interaction, etc.)
        
        Returns:
            {
                "intent": str,  # Primary intent type
                "confidence": float,  # 0.0-1.0
                "reasoning": str,  # Why this intent was chosen
                "fallback": bool  # True if using rule-based fallback
            }
        """
        if not self.enabled:
            return self._fallback_classify(query)
        
        try:
            # Build zero-shot prompt
            prompt = self._build_classification_prompt(query, user_context)
            
            # Call OpenAI API
            response = self._call_openai_api(prompt)
            
            # Parse response
            result = self._parse_openai_response(response, query)
            result["fallback"] = False
            
            logger.info(f"[INTENT-CLASSIFIER] Query: '{query}' → Intent: {result['intent']} "
                       f"(confidence: {result['confidence']:.2f}) [OpenAI]")
            return result
            
        except Exception as e:
            logger.warning(f"[INTENT-CLASSIFIER] OpenAI classification failed: {e}, using fallback")
            return self._fallback_classify(query)
    
    def _build_classification_prompt(self, query: str, user_context: Optional[Dict[str, Any]] = None) -> str:
        """Build zero-shot classification prompt for Gemini."""
        
        # Build intent options
        intent_list = "\n".join([f"- {name}: {desc}" for name, desc in self.INTENTS.items()])
        
        # Add user context if available
        context_str = ""
        if user_context:
            user_name = user_context.get("user_name")
            last_interaction = user_context.get("last_interaction")
            if user_name:
                context_str += f"\nUser name: {user_name}"
            if last_interaction:
                context_str += f"\nLast interaction: {last_interaction}"
        
        prompt = f"""You are an intent classifier for a fashion e-commerce chatbot. 

AVAILABLE INTENTS:
{intent_list}

USER QUERY: "{query}"{context_str}

TASK: Classify the intent of this query. Respond in this EXACT format:
INTENT: <intent_name>
CONFIDENCE: <0.0-1.0>
REASONING: <brief explanation>

Example:
INTENT: product_search
CONFIDENCE: 0.85
REASONING: User is asking to find specific products (blue dresses)

Now classify the query above:"""
        
        return prompt
    
    def _call_openai_api(self, prompt: str) -> Dict[str, Any]:
        """Call OpenAI API for zero-shot classification using official SDK."""
        try:
            logger.info("🔗 [OPENAI-API-CALL] Sending request to GPT-3.5-turbo...")
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an intent classifier for a fashion e-commerce chatbot. Respond in the exact format requested."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=150
            )
            
            # Extract the text content
            text = response.choices[0].message.content.strip()
            logger.info("✅ [OPENAI-API-SUCCESS] Received response from OpenAI")
            return {"content": text}
            
        except Exception as e:
            logger.error(f"❌ [OPENAI-API-FAILED] OpenAI API call failed: {e}")
            raise
    
    def _parse_openai_response(self, response: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Parse OpenAI API response into structured intent result."""
        try:
            # Extract text from OpenAI response
            text = response.get('content', '').strip()
            
            # Parse structured response
            lines = text.strip().split('\n')
            intent = "product_search"  # default
            confidence = 0.5
            reasoning = "Unable to parse response"
            
            for line in lines:
                line = line.strip()
                if line.startswith("INTENT:"):
                    intent_raw = line.replace("INTENT:", "").strip().lower()
                    # Match to valid intent
                    if intent_raw in self.INTENTS:
                        intent = intent_raw
                    else:
                        # Try fuzzy match
                        for valid_intent in self.INTENTS.keys():
                            if valid_intent in intent_raw or intent_raw in valid_intent:
                                intent = valid_intent
                                break
                
                elif line.startswith("CONFIDENCE:"):
                    try:
                        confidence = float(line.replace("CONFIDENCE:", "").strip())
                        confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
                    except ValueError:
                        confidence = 0.5
                
                elif line.startswith("REASONING:"):
                    reasoning = line.replace("REASONING:", "").strip()
            
            return {
                "intent": intent,
                "confidence": confidence,
                "reasoning": reasoning
            }
            
        except Exception as e:
            logger.error(f"Failed to parse Gemini response: {e}")
            return {
                "intent": "product_search",
                "confidence": 0.3,
                "reasoning": f"Parse error: {str(e)}"
            }
    
    def _fallback_classify(self, query: str) -> Dict[str, Any]:
        """
        Simple rule-based fallback when OpenAI is unavailable.
        Uses basic pattern matching (keep this minimal).
        Enhanced to detect context-aware queries like "add first one to cart".
        """
        text_lower = query.lower().strip()
        
        # RULE 0: Cart actions (HIGH PRIORITY - ordinal + cart)
        # Detects: "add first one to cart", "add the second one", "buy first item"
        ordinal_patterns = ['first', 'second', 'third', 'fourth', 'fifth', '1st', '2nd', '3rd']
        cart_keywords = ['add', 'buy', 'purchase', 'cart']
        
        if any(ord_p in text_lower for ord_p in ordinal_patterns):
            if any(cart_kw in text_lower for cart_kw in cart_keywords):
                return {
                    "intent": "add_to_cart",
                    "confidence": 0.95,
                    "reasoning": "Pattern match: ordinal + cart keyword (context-aware)",
                    "fallback": True
                }
        
        # RULE 1: Greetings (short and clear)
        if any(text_lower.startswith(p) or text_lower == p for p in ["hi", "hello", "hey", "good morning"]):
            if len(query.split()) <= 3:
                return {
                    "intent": "greeting",
                    "confidence": 0.9,
                    "reasoning": "Pattern match: greeting keyword",
                    "fallback": True
                }
        
        # RULE 2: Farewells
        if any(p in text_lower for p in ["bye", "goodbye", "thanks", "thank you"]):
            if len(query.split()) <= 5:
                return {
                    "intent": "farewell",
                    "confidence": 0.85,
                    "reasoning": "Pattern match: farewell keyword",
                    "fallback": True
                }
        
        # RULE 3: Small talk patterns
        if any(p in text_lower for p in ["how are you", "how's it going", "what's new"]):
            return {
                "intent": "small_talk",
                "confidence": 0.8,
                "reasoning": "Pattern match: small talk phrase",
                "fallback": True
            }
        
        # RULE 4: Styling advice (minimal patterns)
        if any(p in text_lower for p in ["how to style", "how should i", "styling tips", "outfit tips"]):
            if not any(w in text_lower for w in ["show", "find", "get me"]):
                return {
                    "intent": "styling_advice",
                    "confidence": 0.75,
                    "reasoning": "Pattern match: styling question",
                    "fallback": True
                }
        
        # RULE 5: Feedback
        if any(p in text_lower for p in ["love it", "perfect", "amazing", "awesome"]):
            return {
                "intent": "feedback_positive",
                "confidence": 0.8,
                "reasoning": "Pattern match: positive feedback",
                "fallback": True
            }
        
        if any(p in text_lower for p in ["don't like", "not my style", "something else"]):
            return {
                "intent": "feedback_negative",
                "confidence": 0.8,
                "reasoning": "Pattern match: negative feedback",
                "fallback": True
            }
        
        # RULE 6: Clarification needed
        if len(query.split()) <= 2 and any(p in text_lower for p in ["idk", "maybe", "whatever"]):
            return {
                "intent": "clarification",
                "confidence": 0.85,
                "reasoning": "Pattern match: vague query",
                "fallback": True
            }
        
        # DEFAULT: Product search (most common)
        return {
            "intent": "product_search",
            "confidence": 0.6,
            "reasoning": "Default fallback - assume product search",
            "fallback": True
        }


# Singleton instance
_intent_classifier = None

def get_intent_classifier() -> IntentClassifierAgent:
    """Get singleton instance of intent classifier."""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifierAgent()
    return _intent_classifier
