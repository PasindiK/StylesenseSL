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
from src.services.agentic_ai.agents.query_structuring_agent import get_query_structuring_agent
from src.services.agentic_ai.agents.conversation_memory import get_conversation_memory
from src.users.user_agent import UserAgent
from src.utils.nl_parser import parse_intent
from src.utils.intent_validator import get_intent_validator
from src.clients.gemini_client import (
    generate_styling_advice_with_gemini,
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
        self.query_structurer = get_query_structuring_agent()
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
        Classify user intent using model-first classifier with LLM fallback.
        
        Returns:
            {
                "intent": str,
                "confidence": float,
                "reasoning": str,
                "method": "distilbert_calibrated" | "distilbert_ambiguous" | "llm_fallback" | "default",
                "action": "accept" | "fallback_low_confidence" | "ask_clarification"
            }
        """

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
        source = classification.get("source", "distilbert" if not classification.get("fallback") else "rules")
        
        # Log classification result
        logger.info(f"[ORCHESTRATOR] Zero-shot classification: {classification['intent']} "
                   f"(confidence: {classification['confidence']:.2f}, "
                   f"method: {source})")
        
        # Return classification with metadata
        return {
            "intent": classification["intent"],
            "confidence": classification["confidence"],
            "reasoning": classification["reasoning"],
            "method": source,
            "action": classification.get("action", "accept"),
            "second_intent": classification.get("second_intent"),
            "second_confidence": classification.get("second_confidence"),
            "score_margin": classification.get("score_margin"),
            "clarification": {
                "candidates": classification.get("candidates", []),
                "score_margin": classification.get("score_margin"),
                "confidence_threshold": classification.get("confidence_threshold"),
                "ambiguity_margin": classification.get("ambiguity_margin"),
            },
            "model_hint": classification.get("model_hint"),
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
        """Handle small talk without calling external LLM services."""
        fallback_responses = [
            f"I'm doing great, thanks for asking! How can I help you find the perfect fashion items today, {user_name or 'friend'}?",
            f"Doing awesome! What brings you here today? I'd love to help you discover something amazing!",
            f"I'm here and ready to help. Whether you're looking for casual wear, formal outfits, or something special, I've got you covered.",
            f"Having a great day, {user_name or 'friend'}! What kind of fashion are you in the mood for?",
        ]
        import random
        message = random.choice(fallback_responses) if user_id else fallback_responses[0]
        
        return {
            "intent": "small_talk",
            "reply": message,
            "message": message,
            "llm_used": None,
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "small_talk", "agent": "orchestrator"},
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
    
    def handle_clarification_request(self, text: Optional[str] = None,
                                     classification: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle vague/unclear queries."""

        clarification = (classification or {}).get("clarification", {}) if classification else {}
        candidates = clarification.get("candidates") or []

        if candidates:
            first = candidates[0]
            second = candidates[1] if len(candidates) > 1 else None
            if second:
                message = (
                    "I might have misunderstood your request. "
                    f"Did you mean '{first.get('intent')}' or '{second.get('intent')}'? "
                    "Please pick one so I can continue accurately."
                )
            else:
                message = "I might have misunderstood your request. Please confirm what you want me to do next."
        else:
            message = "I'd love to help! Could you be more specific? For example:\n• 'Show me red dresses under 5000'\n• 'Casual wear for the beach'\n• 'Black formal shoes'"

        clar_payload = {
            "type": "intent_disambiguation",
            "question": "Please clarify your intent so I can route your request correctly.",
            "original_query": text,
            "candidates": candidates,
            "score_margin": clarification.get("score_margin"),
            "confidence_threshold": clarification.get("confidence_threshold"),
            "ambiguity_margin": clarification.get("ambiguity_margin"),
            "reasoning": (classification or {}).get("reasoning"),
        }

        return {
            "intent": "clarification_request",
            "reply": message,
            "message": message,
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "clarification": clar_payload,
            "explanations": {
                "intent_type": "clarification_request",
                "agent": "orchestrator",
                "reason": (classification or {}).get("reasoning"),
            },
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
            structured_query = self.query_structurer.predict(text)

            # Merge predicted budget into parser intent if parser missed it.
            budget_to_price = {
                "low": 3000,
                "mid": 7000,
                "high": 15000,
            }
            if intent.get("max_price") is None and structured_query.get("budget") in budget_to_price:
                intent["max_price"] = budget_to_price[structured_query.get("budget")]

            logger.info(f"[ORCHESTRATOR] Parsed intent: {intent}")
            logger.info(f"[ORCHESTRATOR] Query structuring: {structured_query}")
            
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
                message = (
                    f"{message}\n\n"
                    "If you want styling tips for these picks, reply: yes styling tips"
                )
                selected_products = (ranked.get("best_matches", []) + ranked.get("new_suggestions", []))[:3]
                product_names = [
                    str(p.get("name") or p.get("product_name") or p.get("title") or "")
                    for p in selected_products
                    if isinstance(p, dict)
                ]
                explanation_text = "These were selected because they align with your requested style and your recent preference patterns."

                if user_id:
                    self.memory.set_styling_tips_offer(
                        user_id,
                        True,
                        recommendation_context={
                            "query": text,
                            "product_names": product_names,
                            "intent": intent,
                        },
                    )
                
                return {
                    "intent": "product_search",
                    "reply": message,
                    "message": message,
                    "products": product_names,
                    "explanation": explanation_text,
                    "best_matches": ranked.get("best_matches", []),
                    "new_suggestions": ranked.get("new_suggestions", []),
                    "explanations": {
                        **ranked.get("explanations", {}),
                        "structured_query": structured_query,
                    },
                    "user_profile_used": self.user.get_preferences(user_id),
                    "results": ranked.get("results", response["results"]),
                    "filters": {
                        **response.get("filters", {}),
                        "style": structured_query.get("style"),
                        "event": structured_query.get("event"),
                        "budget_band": structured_query.get("budget"),
                    },
                    "suggestions": response.get("suggestions", []),
                    "explainability": response.get("explainability", ""),
                    "outfit_explanation": "",
                    "llm_used": None,
                    "agent": "catalog_agent+personalization_agent"
                }
            else:
                # No personalization (no user_id or no results)
                top_products = response.get("results", [])[:3]
                base_message = response.get("message", response.get("reply", ""))
                if top_products:
                    base_message = (
                        f"{base_message}\n\n"
                        "If you want styling tips for these picks, reply: yes styling tips"
                    )
                product_names = [
                    str(p.get("name") or p.get("product_name") or p.get("title") or "")
                    for p in top_products
                    if isinstance(p, dict)
                ]
                explanation_text = "These were selected because they align with your requested style and your recent preference patterns."

                if user_id and top_products:
                    self.memory.set_styling_tips_offer(
                        user_id,
                        True,
                        recommendation_context={
                            "query": text,
                            "product_names": product_names,
                            "intent": intent,
                        },
                    )
                return {
                    "intent": "product_search",
                    "reply": base_message,
                    "message": base_message,
                    "products": product_names,
                    "explanation": explanation_text,
                    "best_matches": [],
                    "new_suggestions": [],
                    "explanations": {"structured_query": structured_query},
                    "user_profile_used": {},
                    "results": response.get("results", []),
                    "filters": {
                        **response.get("filters", {}),
                        "style": structured_query.get("style"),
                        "event": structured_query.get("event"),
                        "budget_band": structured_query.get("budget"),
                    },
                    "suggestions": response.get("suggestions", []),
                    "explainability": response.get("explainability", ""),
                    "outfit_explanation": "",
                    "llm_used": None,
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
    
    def handle_styling_advice(
        self,
        text: str,
        user_name: Optional[str],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle styling advice - uses LLM for advice."""
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

            user_profile = self.user.get_preferences(user_id) if user_id else {}
            recent_ctx = self.memory.get_last_recommendation_context(user_id) if user_id else {}
            personalization_context = {
                "preferred_style": user_profile.get("preferred_style") or user_profile.get("style"),
                "favorite_colors": user_profile.get("favorite_colors") or user_profile.get("colors"),
                "size": user_profile.get("size"),
                "budget": user_profile.get("budget") or user_profile.get("preferred_budget"),
                "recent_recommended_items": recent_ctx.get("product_names") or [],
            }
            
            # Generate advice using the configured LLM client
            advice = generate_styling_advice_with_gemini(
                user_name or "there",
                text,
                fashion_topic,
                personalization_context=personalization_context,
            )
            
            return {
                "intent": "styling_advice",
                "reply": advice,
                "message": advice,
                "llm_used": "groq_styling_advice",
                "filters": {},
                "suggestions": [],
                "best_matches": [],
                "new_suggestions": [],
                "explanations": {"intent_type": "styling_advice", "topic": fashion_topic, "agent": "groq"},
                "user_profile_used": user_profile,
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
        # Handle explicit opt-in styling tips after recommendations.
        if user_id and self.memory.should_generate_styling_tips(user_id, text):
            ctx = self.memory.get_last_recommendation_context(user_id)
            names = ctx.get("product_names") or []
            if names:
                styling_prompt = (
                    "Give short styling tips for these fashion items: "
                    + ", ".join([str(n) for n in names[:3]])
                )
            else:
                styling_prompt = "Give short styling tips for the user's latest recommended items."
            self.memory.set_styling_tips_offer(user_id, False)
            return self.handle_styling_advice(styling_prompt, user_name, user_id)

        # STEP 1: Validate query quality (filter garbage)
        validator = get_intent_validator()
        is_valid, validation_reason = validator.is_valid_query(text)
        
        if not is_valid:
            logger.warning(f"[ORCHESTRATOR] Invalid query rejected: '{text}' - {validation_reason}")
            error_message = validator.get_validation_message(validation_reason)
            invalid_intent = "non_fashion_query" if validation_reason == "Query not related to fashion" else "invalid_query"
            return {
                "intent": invalid_intent,
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
        action = classification.get("action", "accept")
        
        logger.info(f"[ORCHESTRATOR] Intent: {intent_type} | Confidence: {confidence:.2f} | Method: {method}")

        if action == "ask_clarification":
            logger.info("[ORCHESTRATOR] Ambiguous intent detected, requesting user clarification")
            return self.handle_clarification_request(text=text, classification=classification)
        
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
            return self.handle_clarification_request(text=text, classification=classification)
        
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
            return self.handle_styling_advice(text, user_name, user_id)
        
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
