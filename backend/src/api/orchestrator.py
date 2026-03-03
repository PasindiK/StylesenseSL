"""
Orchestrator Agent - Routes user queries to appropriate agents based on intent.

This orchestrator acts as the central coordinator, analyzing user queries and
delegating tasks to specialized agents (Catalog, Order, User, Personalization).
"""
import logging
from typing import Dict, Any, Optional, List

from src.services.agentic_ai.agents.catalog_agent import CatalogAgent
from src.services.agentic_ai.agents.order_agent import OrderAgent
from src.services.agentic_ai.agents.personalization_agent import PersonalizationAgent
from src.services.agentic_ai.agents.intent_classifier_agent import get_intent_classifier
from src.services.agentic_ai.agents.conversation_memory import get_conversation_memory
from src.users.user_agent import UserAgent
from src.utils.nl_parser import parse_intent
from src.utils.intent_validator import get_intent_validator
from src.clients.gemini_client import (
    dynamic_small_talk,
    generate_styling_advice_with_gemini
)

logger = logging.getLogger(__name__)


class Orchestrator:
    """Central orchestrator that routes queries to appropriate agents."""
    
    def __init__(self, catalog_agent: CatalogAgent, order_agent: OrderAgent, 
                 user_agent: UserAgent, personalization_agent: PersonalizationAgent):
        self.catalog = catalog_agent
        self.order = order_agent
        self.user = user_agent
        self.personalization = personalization_agent
        self.intent_classifier = get_intent_classifier()
        self.memory = get_conversation_memory()  # Add conversation memory
        
        logger.info("[ORCHESTRATOR] Initialized with all agents + zero-shot intent classifier + conversation memory")
    
    def detect_multi_task(self, text: str) -> List[Dict[str, Any]]:
        """
        Detect if query contains multiple tasks that should be executed sequentially.
        
        Examples:
        - "show me red dresses and add the first one to cart"
        - "find casual shoes then clear my cart"
        - "show t-shirts and add first 2 to cart"
        
        Returns list of tasks in execution order: [{"type": "search", "text": ...}, {"type": "add_to_cart", ...}]
        """
        text_lower = text.lower().strip()
        tasks = []
        
        # Check for compound patterns
        compound_patterns = [
            (r'(.*?)\s+(?:and|then)\s+(?:add|put).*?(?:first|1st|top)\s+(?:one|item|product).*?(?:to\s+)?cart', 
             'search_and_add_first'),
            (r'(.*?)\s+(?:and|then)\s+(?:add|put).*?(?:first|top)\s+(\d+).*?(?:to\s+)?cart', 
             'search_and_add_multiple'),
            (r'(.*?)\s+(?:and|then)\s+(?:clear|empty)\s+(?:my\s+)?cart',
             'search_and_clear_cart'),
        ]
        
        import re
        for pattern, task_type in compound_patterns:
            match = re.search(pattern, text_lower)
            if match:
                if task_type == 'search_and_add_first':
                    # Extract search query
                    search_text = match.group(1).strip()
                    tasks.append({"type": "search", "text": search_text})
                    tasks.append({"type": "add_to_cart", "index": 0, "count": 1})
                    return tasks
                    
                elif task_type == 'search_and_add_multiple':
                    search_text = match.group(1).strip()
                    count = int(match.group(2))
                    tasks.append({"type": "search", "text": search_text})
                    tasks.append({"type": "add_to_cart", "index": 0, "count": min(count, 5)})  # Max 5
                    return tasks
                    
                elif task_type == 'search_and_clear_cart':
                    search_text = match.group(1).strip()
                    tasks.append({"type": "clear_cart"})
                    tasks.append({"type": "search", "text": search_text})
                    return tasks
        
        # No multi-task detected
        return []
    
    def execute_multi_task(self, tasks: List[Dict[str, Any]], user_id: Optional[str], 
                          user_name: Optional[str]) -> Dict[str, Any]:
        """Execute multiple tasks sequentially and combine results."""
        results = []
        final_response = None
        search_results = []
        
        for i, task in enumerate(tasks):
            task_type = task.get("type")
            
            if task_type == "search":
                # Execute search
                search_response = self.handle_product_search(task.get("text"), user_id, user_name)
                # Get products from best_matches, new_suggestions, or results
                search_results = (
                    search_response.get("best_matches", []) + 
                    search_response.get("new_suggestions", []) +
                    search_response.get("results", [])
                )
                final_response = search_response
                results.append(f"✅ Found {len(search_results)} products")
                
            elif task_type == "add_to_cart":
                # Add products to cart
                count = task.get("count", 1)
                index = task.get("index", 0)
                
                if not search_results:
                    results.append("❌ No products found to add")
                    continue
                
                added_count = 0
                for idx in range(index, min(index + count, len(search_results))):
                    if idx < len(search_results):
                        product = search_results[idx]
                        try:
                            # Use add_product_direct with full product data
                            response = self.order.add_product_direct(product)
                            if response.get('success'):
                                added_count += 1
                                logger.info(f"[MULTI-TASK] Added product to cart: {product.get('name', 'Unknown')}")
                            else:
                                logger.warning(f"[MULTI-TASK] Failed to add product: {response.get('error')}")
                        except Exception as e:
                            logger.error(f"Failed to add product: {e}")
                
                if added_count > 0:
                    results.append(f"✅ Added {added_count} item(s) to cart")
                else:
                    results.append("❌ Could not add items to cart")
                    
            elif task_type == "clear_cart":
                self.order.clear_cart()
                results.append("✅ Cart cleared")
        
        # Combine results into final message
        if final_response:
            task_summary = " → ".join(results)
            original_msg = final_response.get("reply", "")
            final_response["reply"] = f"{task_summary}\\n\\n{original_msg}"
            final_response["message"] = final_response["reply"]
            final_response["intent"] = "multi_task"  # Ensure intent is set
            final_response["multi_task"] = True
            final_response["task_results"] = results
            final_response["cart"] = self.order.get_cart_summary()
            
        return final_response or {
            "intent": "multi_task",
            "reply": " → ".join(results),
            "message": " → ".join(results),
            "task_results": results,
            "cart": self.order.get_cart_summary(),
            "results": search_results,
        }
    
    def classify_intent(self, text: str, user_id: Optional[str] = None, 
                       user_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Classify user intent using zero-shot learning + rule guards.
        
        LAYER 1: Rule-based guards (for critical actions only)
        LAYER 2: Zero-shot semantic classifier (Gemini API)
        
        Returns:
            {
                "intent": str,
                "confidence": float,
                "reasoning": str,
                "method": "guard" | "zero_shot" | "fallback"
            }
        """
        text_lower = text.lower().strip()
        
        # ===== LAYER 1: RULE GUARDS (CRITICAL ACTIONS ONLY) =====
        
        # GUARD 1: Cart operations (must be explicit)
        cart_patterns = [
            "add to cart", "add this", "shopping cart", "show cart", 
            "view cart", "my cart", "clear cart", "remove from cart"
        ]
        if any(p in text_lower for p in cart_patterns):
            if "show" in text_lower or "view" in text_lower or "my" in text_lower or "what" in text_lower:
                return {
                    "intent": "view_cart",
                    "confidence": 1.0,
                    "reasoning": "Explicit cart view command",
                    "method": "guard"
                }
            elif "clear" in text_lower or "empty" in text_lower:
                return {
                    "intent": "clear_cart",
                    "confidence": 1.0,
                    "reasoning": "Explicit cart clear command",
                    "method": "guard"
                }
            else:
                return {
                    "intent": "add_to_cart",
                    "confidence": 1.0,
                    "reasoning": "Explicit add to cart command",
                    "method": "guard"
                }
        
        # GUARD 2: Order/Checkout (must be explicit)
        if any(p in text_lower for p in ["checkout", "order this", "buy this", "purchase"]):
            return {
                "intent": "order_request",
                "confidence": 1.0,
                "reasoning": "Explicit order/checkout command",
                "method": "guard"
            }
        
        # ===== LAYER 2: ZERO-SHOT SEMANTIC CLASSIFIER =====
        
        # Build user context for better classification
        user_context = {}
        if user_name:
            user_context["user_name"] = user_name
        if user_id:
            try:
                prefs = self.user.get_preferences(user_id)
                user_context["last_interaction"] = prefs.get("last_interaction_type")
            except Exception:
                pass
        
        # Call zero-shot classifier
        classification = self.intent_classifier.classify_intent(text, user_context)
        
        # Log classification result
        logger.info(f"[ORCHESTRATOR] Zero-shot classification: {classification['intent']} "
                   f"(confidence: {classification['confidence']:.2f}, "
                   f"method: {'fallback' if classification.get('fallback') else 'zero_shot'})")
        
        # Return classification with metadata
        return {
            "intent": classification["intent"],
            "confidence": classification["confidence"],
            "reasoning": classification["reasoning"],
            "method": "zero_shot" if not classification.get("fallback") else "fallback"
        }
    
    def handle_greeting(self, user_name: Optional[str]) -> Dict[str, Any]:
        """Handle greeting intent - direct response."""
        message = f"Hi {user_name or 'there'}! 👋 How are you doing today?"
        return {
            "intent": "greeting",
            "reply": message,
            "message": message,
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "greeting", "agent": "orchestrator"},
            "user_profile_used": {},
            "results": [],
        }
    
    def handle_farewell(self, user_name: Optional[str]) -> Dict[str, Any]:
        """Handle farewell intent - direct response."""
        message = f"Take care, {user_name or 'there'}! 👋 Feel free to come back anytime you need fashion help!"
        return {
            "intent": "farewell",
            "reply": message,
            "message": message,
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "farewell", "agent": "orchestrator"},
            "user_profile_used": {},
            "results": [],
        }
    
    def handle_small_talk(self, user_id: Optional[str], user_name: Optional[str]) -> Dict[str, Any]:
        """Handle small talk - uses Gemini for dynamic responses with smart fallback."""
        try:
            user_prefs = self.user.get_preferences(user_id) if user_id else None
            last_product = user_prefs.get("last_product_viewed") if user_prefs else None
            recent_interaction = user_prefs.get("last_interaction_type") if user_prefs else None
            
            message = dynamic_small_talk(
                user_name=user_name,
                last_product=last_product,
                recent_interaction=recent_interaction
            )
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Small talk generation failed: {e}, using fallback")
            # Smart fallback responses
            fallback_responses = [
                f"I'm doing great, thanks for asking! 😊 How can I help you find the perfect fashion items today, {user_name or 'friend'}?",
                f"Doing awesome! 🙌 What brings you here today? I'd love to help you discover something amazing!",
                f"I'm here and ready to help! 💪 Whether you're looking for casual wear, formal outfits, or something special, I've got you covered.",
                f"Having a great day, {user_name or 'friend'}! ✨ What kind of fashion are you in the mood for?",
            ]
            # Use first response by default, or random if user_id available
            import random
            message = random.choice(fallback_responses) if user_id else fallback_responses[0]
        
        return {
            "intent": "small_talk",
            "reply": message,
            "message": message,
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "small_talk", "agent": "orchestrator+gemini"},
            "user_profile_used": {},
            "results": [],
        }
    
    def handle_feedback_positive(self) -> Dict[str, Any]:
        """Handle positive feedback."""
        message = "Awesome! 🎉 I'm so glad you like it! Would you like to see more similar items, or shall I help you with something else?"
        return {
            "intent": "feedback_positive",
            "reply": message,
            "message": message,
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "feedback_positive", "agent": "orchestrator"},
            "user_profile_used": {},
            "results": [],
        }
    
    def handle_feedback_negative(self) -> Dict[str, Any]:
        """Handle negative feedback."""
        message = "Got it! 👍 Could you tell me what you'd like to change — style, color, price range, or category?"
        return {
            "intent": "feedback_negative",
            "reply": message,
            "message": message,
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "feedback_negative", "agent": "orchestrator"},
            "user_profile_used": {},
            "results": [],
        }
    
    def handle_clarification_request(self) -> Dict[str, Any]:
        """Handle vague/unclear queries."""
        message = "I'd love to help! Could you be more specific? For example:\n• 'Show me red dresses under 5000'\n• 'Casual wear for the beach'\n• 'Black formal shoes'"
        return {
            "intent": "clarification_request",
            "reply": message,
            "message": message,
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "clarification_request", "agent": "orchestrator"},
            "user_profile_used": {},
            "results": [],
        }
    
    def handle_view_cart(self) -> Dict[str, Any]:
        """Handle view cart - routes to OrderAgent."""
        cart_summary = self.order.get_cart_summary()
        
        if cart_summary["total_items"] == 0:
            message = "🛒 Your cart is empty! Share a product link to add items. Example:\n\nadd to cart: https://www.daraz.lk/products/..."
            return {
                "intent": "view_cart",
                "reply": message,
                "message": message,
                "cart": cart_summary,
                "filters": {},
                "suggestions": [],
                "best_matches": [],
                "new_suggestions": [],
                "explanations": {"intent_type": "view_cart", "cart_empty": True, "agent": "order_agent"},
                "user_profile_used": {},
                "results": [],
            }
        
        # Format cart display
        cart_display = self._format_cart_display(cart_summary)
        
        return {
            "intent": "view_cart",
            "reply": cart_display,
            "message": cart_display,
            "cart": cart_summary,
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {
                "intent_type": "view_cart",
                "cart_summary": cart_summary,
                "agent": "order_agent"
            },
            "user_profile_used": {},
            "results": [],
        }
    
    def handle_clear_cart(self) -> Dict[str, Any]:
        """Handle clear cart - routes to OrderAgent."""
        self.order.clear_cart()
        message = "🗑️ Your cart has been cleared successfully!"
        
        return {
            "intent": "clear_cart",
            "reply": message,
            "message": message,
            "cart": self.order.get_cart_summary(),
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "clear_cart", "agent": "order_agent"},
            "user_profile_used": {},
            "results": [],
        }
    
    def handle_product_search(self, text: str, user_id: Optional[str], 
                            user_name: Optional[str]) -> Dict[str, Any]:
        """
        Handle product search - routes to CatalogAgent + PersonalizationAgent.
        This is the main search flow with personalization.
        """
        try:
            logger.info(f"[ORCHESTRATOR] Routing product search to CatalogAgent: '{text}'")
            
            # MEMORY TRACKING: Add query to conversation history
            if user_id:
                self.memory.add_query(user_id, text)
            
            # Parse intent using NL parser
            intent = parse_intent(text)
            logger.info(f"[ORCHESTRATOR] Parsed intent: {intent}")
            
            # Call CatalogAgent
            response = self.catalog.answer_question(text, user_id=user_id)
            logger.info(f"[ORCHESTRATOR] CatalogAgent returned {len(response.get('results', []))} products")
            
            # MEMORY TRACKING: Cache the search results
            all_results = response.get("results", [])
            if user_id:
                self.memory.add_results(user_id, all_results, query=text)
            
            # Apply personalization if we have results
            if response.get("results") and user_id:
                logger.info(f"[ORCHESTRATOR] Applying personalization for user {user_id}")
                ranked = self.personalization.rerank(
                    user_id,
                    response["results"],
                    intent=intent,
                    context={"query": text}
                )
                
                # Generate personalized message
                message = self.personalization.generate_chat_message(
                    user_id,
                    intent,
                    ranked.get("best_matches", []),
                    ranked.get("new_suggestions", []),
                    user_name
                )
                
                return {
                    "intent": "product_search",
                    "reply": message,
                    "message": message,
                    "best_matches": ranked.get("best_matches", []),
                    "new_suggestions": ranked.get("new_suggestions", []),
                    "explanations": ranked.get("explanations", {}),
                    "user_profile_used": self.user.get_preferences(user_id),
                    "results": ranked.get("results", response["results"]),
                    "filters": response.get("filters", {}),
                    "suggestions": response.get("suggestions", []),
                    "explainability": response.get("explainability", ""),
                    "agent": "catalog_agent+personalization_agent"
                }
            else:
                # No personalization (no user_id or no results)
                return {
                    "intent": "product_search",
                    "reply": response.get("message", response.get("reply", "")),
                    "message": response.get("message", response.get("reply", "")),
                    "best_matches": [],
                    "new_suggestions": [],
                    "explanations": {},
                    "user_profile_used": {},
                    "results": response.get("results", []),
                    "filters": response.get("filters", {}),
                    "suggestions": response.get("suggestions", []),
                    "explainability": response.get("explainability", ""),
                    "agent": "catalog_agent"
                }
                
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Product search failed: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "intent": "error",
                "reply": "Sorry, I encountered an error searching for products. Please try again!",
                "message": "Sorry, I encountered an error searching for products. Please try again!",
                "filters": {},
                "suggestions": [],
                "best_matches": [],
                "new_suggestions": [],
                "results": [],
                "error": str(e),
                "agent": "orchestrator"
            }
    
    def handle_styling_advice(self, text: str, user_name: Optional[str]) -> Dict[str, Any]:
        """Handle styling advice - uses Gemini for advice."""
        try:
            # Extract fashion topic
            text_lower = text.lower()
            fashion_topics = {
                "jogger": "joggers and casual wear",
                "sweatpant": "sweatpants and casual wear",
                "t-shirt": "t-shirts and casual tops",
                "tee": "t-shirts and casual tops",
                "shirt": "shirts",
                "formal": "formal clothing",
                "office": "office wear",
                "casual": "casual styling",
                "jacket": "jackets and layering",
                "shoe": "footwear",
                "sneaker": "sneakers",
            }
            
            fashion_topic = None
            for keyword, topic in fashion_topics.items():
                if keyword in text_lower:
                    fashion_topic = topic
                    break
            
            # Generate advice using Gemini
            advice = generate_styling_advice_with_gemini(user_name, text, fashion_topic)
            
            return {
                "intent": "styling_advice",
                "reply": advice,
                "message": advice,
                "filters": {},
                "suggestions": [],
                "best_matches": [],
                "new_suggestions": [],
                "explanations": {"intent_type": "styling_advice", "topic": fashion_topic, "agent": "gemini"},
                "user_profile_used": {},
                "results": [],
            }
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Styling advice generation failed: {e}")
            fallback = f"Great question! For {text}, I'd suggest looking at our collection and experimenting with different styles. What specific products are you interested in?"
            return {
                "intent": "styling_advice",
                "reply": fallback,
                "message": fallback,
                "filters": {},
                "suggestions": [],
                "best_matches": [],
                "new_suggestions": [],
                "results": [],
                "agent": "orchestrator"
            }
    
    def process_query(self, text: str, user_id: Optional[str] = None, 
                     user_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Main entry point - processes user query and routes to appropriate handler.
        
        Args:
            text: User query
            user_id: Optional user ID for personalization
            user_name: Optional user name for personalized messages
            
        Returns:
            Structured response with intent, message, products, etc.
        """
        # STEP 1: Validate query quality (filter garbage)
        validator = get_intent_validator()
        is_valid, validation_reason = validator.is_valid_query(text)
        
        if not is_valid:
            logger.warning(f"[ORCHESTRATOR] Invalid query rejected: '{text}' - {validation_reason}")
            error_message = validator.get_validation_message(validation_reason)
            return {
                "intent": "invalid_query",
                "reply": error_message,
                "message": error_message,
                "filters": {},
                "suggestions": [],
                "best_matches": [],
                "new_suggestions": [],
                "results": [],
                "explanations": {
                    "validation_failed": True,
                    "reason": validation_reason
                },
                "agent": "orchestrator_validator"
            }
        
        # STEP 1.5: Check for multi-task queries
        multi_tasks = self.detect_multi_task(text)
        if multi_tasks:
            logger.info(f"[ORCHESTRATOR] Multi-task detected: {len(multi_tasks)} tasks")
            return self.execute_multi_task(multi_tasks, user_id, user_name)
        
        # STEP 2: Classify intent using zero-shot classifier
        classification = self.classify_intent(text, user_id, user_name)
        intent_type = classification["intent"]
        confidence = classification.get("confidence", 0.0)
        method = classification.get("method", "unknown")
        
        logger.info(f"[ORCHESTRATOR] Intent: {intent_type} | Confidence: {confidence:.2f} | Method: {method}")
        
        # STEP 3: Route to appropriate handler
        if intent_type == "greeting":
            return self.handle_greeting(user_name)
        
        elif intent_type == "farewell":
            return self.handle_farewell(user_name)
        
        elif intent_type == "small_talk":
            return self.handle_small_talk(user_id, user_name)
        
        elif intent_type == "feedback_positive":
            return self.handle_feedback_positive()
        
        elif intent_type == "feedback_negative":
            return self.handle_feedback_negative()
        
        elif intent_type == "clarification":
            return self.handle_clarification_request()
        
        elif intent_type == "view_cart":
            return self.handle_view_cart()
        
        elif intent_type == "clear_cart":
            return self.handle_clear_cart()
        
        elif intent_type == "add_to_cart":
            # For add_to_cart, we need URL extraction - keeping this in app.py for now
            # as it requires more complex text parsing and URL detection
            return {
                "intent": "add_to_cart",
                "reply": "Please share the product URL you'd like to add. Example:\n\nadd to cart: https://www.daraz.lk/products/...",
                "message": "Please share the product URL you'd like to add.",
                "agent": "orchestrator",
                "needs_url_extraction": True
            }
        
        elif intent_type == "styling_advice":
            return self.handle_styling_advice(text, user_name)
        
        elif intent_type == "product_search":
            return self.handle_product_search(text, user_id, user_name)
        
        else:
            # Fallback - treat as product search
            logger.warning(f"[ORCHESTRATOR] Unknown intent '{intent_type}', defaulting to product_search")
            return self.handle_product_search(text, user_id, user_name)
    
    def _format_cart_display(self, cart_summary: Dict[str, Any]) -> str:
        """Format cart summary into readable text."""
        cart_display = f"🛍️ **Your Shopping Cart** ({cart_summary['total_items']} items)\n\n"
        
        shops = cart_summary["by_shop"]
        for shop_id, shop_data in shops.items():
            cart_display += f"### 🏪 {shop_data['shop_name']}\n\n"
            
            for item in shop_data['items']:
                cart_display += f"**{item['name']}**\n"
                cart_display += f"- Quantity: {item['quantity']}\n"
                cart_display += f"- Price: {item['currency']} {item['price']:.2f} each\n"
                cart_display += f"- Subtotal: {item['currency']} {item['subtotal']:.2f}\n\n"
            
            cart_display += f"**Shop Subtotal:** {shop_data['currency']} {shop_data['subtotal']:.2f}\n"
            cart_display += f"**Delivery:** {shop_data['currency']} {shop_data['delivery_charge']:.2f}\n"
            cart_display += f"**Shop Total:** {shop_data['currency']} {shop_data['total_with_delivery']:.2f}\n\n"
            cart_display += "---\n\n"
        
        cart_display += f"### 💰 Grand Total: LKR {cart_summary['grand_total']:.2f}\n\n"
        cart_display += "*Note: Different currencies converted to LKR at current rates*\n\n"
        cart_display += cart_summary["checkout_instructions"]
        
        return cart_display
