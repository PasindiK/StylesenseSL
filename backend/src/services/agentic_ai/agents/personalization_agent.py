"""PersonalizationAgent: Rerank products using user preferences + context.

Inputs:
- user_id (from UserAgent)
- candidates (list of product dicts from CatalogAgent)
- intent (optional parsed intent dict)
- context (optional: { time_of_day, device, query })

Outputs:
- dict { results: [...], scores: [...], why: '...', intent, context }
"""
from typing import Any, Dict, List, Optional
from src.users.user_agent import UserAgent


class PersonalizationAgent:
    def __init__(self, user_agent: UserAgent):
        self.user_agent = user_agent

    def rerank(
        self,
        user_id: Optional[str],
        candidates: List[Dict[str, Any]],
        intent: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not candidates:
            return {"results": [], "scores": [], "why": "No candidates", "intent": intent or {}, "context": context or {}}

        # Compute weighted scores per spec
        prefs = self.user_agent.get_preferences(user_id) if user_id else None
        scored = []
        for c in candidates:
            intent_score = 0.0
            personalization = 0.0
            price_score = 0.0
            poprec = 0.0
            why: List[str] = []

            # IntentMatchScore (category, color, shop, occasion)
            if intent:
                if intent.get("category") and str(intent["category"]).lower() in str(c.get("category", "")).lower():
                    intent_score += 0.4
                if intent.get("color") and str(intent["color"]).lower() in str(c.get("color", "")).lower():
                    intent_score += 0.3
                    why.append(f"Matches the {intent['color']} color you asked for")
                if intent.get("shop") and intent.get("shop") and intent["shop"].lower() in str(c.get("_shop_name", c.get("shop_name", ""))).lower():
                    intent_score += 0.2
                if intent.get("occasion"):
                    tags = [str(t).lower() for t in (c.get("normalized_style_tags") or c.get("style_tags") or [])]
                    if intent["occasion"].lower() in tags:
                        intent_score += 0.1
                        why.append(f"Perfect for {intent['occasion']}")
            intent_score = min(intent_score, 1.0)

            # PersonalizationScore (user prefs)
            if prefs:
                if prefs.get("top_categories"):
                    if (c.get("category") or "").lower() in [x.lower() for x in prefs["top_categories"]]:
                        personalization += 0.4
                        why.append(f"Matches your favorite {c.get('category')} style")
                if prefs.get("top_colors"):
                    if (c.get("color") or "").lower() in [x.lower() for x in prefs["top_colors"]]:
                        personalization += 0.3
                        why.append(f"One of your preferred colors")
                if prefs.get("preferred_shops") and str(c.get("shop_id")) in prefs["preferred_shops"]:
                    personalization += 0.2
                    why.append("From a shop you love")
                if prefs.get("style_tag_frequency"):
                    tags = set(str(t).lower() for t in (c.get("normalized_style_tags") or c.get("style_tags") or []))
                    pref_tags = set(str(t).lower() for t in prefs["style_tag_frequency"].keys())
                    if tags & pref_tags:
                        personalization += 0.1
                        why.append("Matches your style preferences")
            personalization = min(personalization, 1.0)

            # PriceScore: closer to budget
            try:
                price = float(c.get("price") or c.get("price_LKR") or 0)
                budget = float(intent.get("max_price") or (prefs and prefs.get("price_range", {}).get("max")) or 0)
                if budget > 0:
                    # Normalize inverse distance: within budget gets 1.0, else decays
                    price_score = 1.0 if price <= budget else max(0.0, 1.0 - (price - budget) / max(budget, 1.0))
                    if price <= budget:
                        why.append(f"Great price - within your LKR {budget:,.0f} budget")
            except Exception:
                price_score = 0.0

            # Popularity/Recency: simple normalization of popularity_score
            try:
                pop = float(c.get("popularity_score") or 0)
                poprec = min(max(pop / 5.0, 0.0), 1.0)  # assuming 0-5 scale in dataset
                if pop >= 4.0:
                    why.append("Popular choice right now")
            except Exception:
                poprec = 0.0

            final = 0.40 * intent_score + 0.30 * personalization + 0.20 * price_score + 0.10 * poprec
            # Ensure at least one reason
            if not why:
                why = ["Recommended for you"]
            c2 = {**c, "personalization_score": round(final, 4), "_why_reasons": why}
            scored.append(c2)

        # Sort and limit to top 6
        scored.sort(key=lambda x: x.get("personalization_score", 0), reverse=True)
        top6 = scored[:6]
        
        # Split into sections: max 3 best matches + max 3 new suggestions
        best_matches_raw = top6[:3]
        new_suggestions_raw = top6[3:6]
        
        # Process best_matches: add similarity score info
        MIN_SIMILARITY_SCORE = 0.40  # 40% threshold
        best = []
        for item in best_matches_raw:
            match_item = {**item}
            # Best matches are from semantic search, not personalization
            # DO NOT show match scores here - only on new suggestions
            match_item["_show_match_score"] = False
            match_item["_match_score_percent"] = None
            
            best.append(match_item)
        
        # Add why bullets ONLY to new_suggestions
        # Apply similarity score filtering: only show scores > 40%, hide scores below 40%
        new_suggestions = []
        
        for item in new_suggestions_raw:
            # Boost scores for new_suggestions (exploration)
            boosted_item = {**item}
            boosted_item["personalization_score"] = round(item.get("personalization_score", 0.5) + 0.15, 4)
            boosted_item["why"] = item.get("_why_reasons", ["Fresh pick for you"])
            
            # Get similarity score from vector search (if available)
            similarity_score = item.get("_similarity_score", None)
            
            if similarity_score is not None:
                # Only show match score if >= 40%
                if similarity_score >= MIN_SIMILARITY_SCORE:
                    boosted_item["_show_match_score"] = True
                    boosted_item["_match_score_percent"] = round(similarity_score * 100, 1)
                else:
                    # Hide score but still show the item
                    boosted_item["_show_match_score"] = False
                    boosted_item["_match_score_percent"] = None
            else:
                # No similarity score available
                boosted_item["_show_match_score"] = False
                boosted_item["_match_score_percent"] = None
            
            new_suggestions.append(boosted_item)
        
        # Sort new_suggestions by shop match first (if shop was specified in intent)
        intent_shop = (intent.get('shop', '') or '').lower() if intent else ''
        
        def get_shop_name(item):
            return (item.get('_shop_name', '') or item.get('shop', '') or '').lower()
        
        # If shop was specified, prioritize products from that shop
        if intent_shop:
            new_suggestions.sort(key=lambda x: (
                1 if intent_shop in get_shop_name(x) else 0,  # Shop match first
                x.get('personalization_score', 0)  # Then by score
            ), reverse=True)
        else:
            # No shop specified, just sort by score
            new_suggestions.sort(key=lambda x: x.get('personalization_score', 0), reverse=True)
        
        # If new_suggestions are low (< 3), repeat items to fill the list
        MIN_SUGGESTIONS = 3
        
        if len(new_suggestions) < MIN_SUGGESTIONS:
            # First try to repeat existing new_suggestions
            if len(new_suggestions) > 0:
                idx = 0
                while len(new_suggestions) < MIN_SUGGESTIONS:
                    repeat_item = {**new_suggestions[idx % len(new_suggestions)]}
                    repeat_item["_is_repeated"] = True
                    new_suggestions.append(repeat_item)
                    idx += 1
            else:
                # No new_suggestions at all, use best matches
                if len(best) > 0:
                    idx = 0
                    while len(new_suggestions) < MIN_SUGGESTIONS and idx < len(best):
                        fallback_item = {**best[idx]}
                        fallback_item["_is_repeated"] = True
                        fallback_item["_show_match_score"] = False
                        fallback_item["why"] = ["Also recommended for you"]
                        new_suggestions.append(fallback_item)
                        idx += 1
                    
                    # If still not enough, repeat from start
                    idx = 0
                    while len(new_suggestions) < MIN_SUGGESTIONS and len(new_suggestions) > 0:
                        repeat_item = {**new_suggestions[idx % len(new_suggestions)]}
                        repeat_item["_is_repeated"] = True
                        new_suggestions.append(repeat_item)
                        idx += 1
        overall_why = {
            "personalization_applied": True if prefs else False,
            "budget": intent.get("max_price") if intent else None,
            "shop": intent.get("shop") if intent else None,
            "category": intent.get("category") if intent else None,
        }
        return {
            "results": top6,
            "best_matches": best,
            "new_suggestions": new_suggestions,
            "explanations": overall_why,
            "intent": intent or {},
            "context": context or {},
        }

    def generate_chat_message(
        self,
        user_id: Optional[str],
        intent: Optional[Dict[str, Any]],
        best_matches: List[Dict[str, Any]],
        new_suggestions: List[Dict[str, Any]],
        user_name: Optional[str] = None,
    ) -> str:
        """Generate a natural, conversational response message."""
        # Use proper greeting with name
        greeting = f"Hey, {user_name}!" if user_name else "Hey!"
        
        # Check if we have any products at all
        has_products = (best_matches and len(best_matches) > 0) or (new_suggestions and len(new_suggestions) > 0)
        
        if not has_products:
            if intent and intent.get("category"):
                return f"{greeting} I couldn't find exact matches for {intent.get('category', 'that')} right now. Could you tell me your preferred color, size, or budget?"
            return f"{greeting} I couldn't find exact matches yet. Could you tell me your preferred style, color, size, or budget?"

        prefs = self.user_agent.get_preferences(user_id) if user_id else None
        
        # Build natural intro based on intent and context
        parts = [greeting]
        
        if intent:
            cat = intent.get("category", "")
            color = intent.get("color", "")
            budget = intent.get("max_price")
            shop = intent.get("shop_name", "")
            
            # Dynamic response based on what filters are present
            if cat and color and budget:
                parts.append(f"I found some amazing {color.lower()} {cat.lower()} under LKR {budget:,.0f} that match your style perfectly.")
            elif cat and budget:
                parts.append(f"Great! Here are the best {cat.lower()} items within LKR {budget:,.0f}.")
            elif cat and color:
                parts.append(f"Perfect! These {color.lower()} {cat.lower()} items are just what you need.")
            elif cat and shop:
                parts.append(f"Here are the top {cat.lower()} items from {shop}.")
            elif cat:
                parts.append(f"I've picked the top {cat.lower()} items for you.")
            elif color:
                parts.append(f"Check out these stylish {color.lower()} pieces!")
            else:
                parts.append("I found some amazing pieces just for you.")
        else:
            parts.append("I found some amazing pieces just for you.")

        # Add personalization insight if available
        if prefs and prefs.get("top_categories") and len(best_matches) > 0:
            top_cat = prefs['top_categories'][0]
            parts.append(f"These are curated based on your love for {top_cat.lower()}.")
        elif len(best_matches) > 0:
            parts.append("These are curated based on what matches your profile best.")

        parts.append("\n\n**Here are your top picks:**")
        
        # Add suggestion section if present
        if new_suggestions and len(new_suggestions) > 0:
            parts.append("\n\n**Fresh alternatives that might surprise you:**")

        return " ".join(parts)
