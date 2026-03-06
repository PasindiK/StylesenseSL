from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import json
import shutil

# Load environment variables from .env file
from dotenv import load_dotenv
import os

# Load .env file
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Verify OpenAI API key is loaded
openai_key = os.getenv("OPENAI_API_KEY")
if openai_key:
    print(f"✅ OpenAI API key loaded: {openai_key[:20]}...")
else:
    print("⚠️ OpenAI API key not found in environment")

from src.ingestion.data_loader import DataLoader
from src.services.agentic_ai.agents.catalog_agent import CatalogAgent
from src.api.orchestrator import Orchestrator
from src.users.user_agent import UserAgent
from src.users.catalog_personalization import CatalogPersonalizer
from src.services.agentic_ai.agents.personalization_agent import PersonalizationAgent
from src.utils.nl_parser import parse_intent
from src.clients.gemini_client import dynamic_small_talk, parse_query_with_gemini, generate_styling_advice_with_gemini, clarify_ambiguous_query
from src.services.agentic_ai.agents.order_agent import OrderAgent

app = FastAPI(title="CatalogAgent API")

# Enable CORS for frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (can restrict to specific domains in production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# initialize loader and agent at import time (simple for local dev)
ROOT = Path(__file__).resolve().parent.parent.parent
DATA_RAW = ROOT / "data" / "raw"

loader = DataLoader()
products_path = DATA_RAW / "final_products.csv"
shops_path = DATA_RAW / "shops_dataset.csv"

if products_path.exists():
    loader.load_products(str(products_path))
else:
    # try relative fallback to simple filename
    try:
        loader.load_products('final_products.csv')
    except Exception:
        pass

if shops_path.exists():
    try:
        loader.load_shops(str(shops_path))
    except Exception:
        pass

agent = CatalogAgent(loader=loader)

# Initialize user intelligence
user_agent = UserAgent()
personalizer = CatalogPersonalizer(user_agent)
personalization_agent = PersonalizationAgent(user_agent)
order_agent = OrderAgent(loader=loader)  # Pass loader for shop info lookup (updated)

# Initialize the orchestrator with all agents
orchestrator = Orchestrator(
    catalog_agent=agent,
    order_agent=order_agent,
    user_agent=user_agent,
    personalization_agent=personalization_agent
)

# Build URL-to-product mapping from dataset
def _build_url_mapping():
    """Create a mapping of product URLs to product data for quick lookup."""
    url_to_product = {}
    if loader.products is not None and not loader.products.empty:
        try:
            for _, row in loader.products.iterrows():
                url = row.get('product_url')
                if url and pd.notna(url):
                    # Convert row to dict, keeping all product info
                    product_dict = row.to_dict()
                    url_to_product[str(url)] = product_dict
            print(f"[INFO] Built URL mapping with {len(url_to_product)} products")
        except Exception as e:
            print(f"[WARN] Failed to build URL mapping: {e}")
    return url_to_product

url_to_product_map = _build_url_mapping()


def _get_user_id(request: Request, user_id_param: Optional[str] = None) -> Optional[str]:
    """Extract user_id from X-User-Id header or user_id query param."""
    if user_id_param:
        return user_id_param
    return request.headers.get("X-User-Id")


def _get_user_name(user_id: Optional[str]) -> Optional[str]:
    """Get user display name from user_id, stripping professional titles."""
    if not user_id:
        return None
    try:
        users_path = ROOT / "data" / "raw" / "users_dataset.csv"
        if users_path.exists():
            df = pd.read_csv(users_path)
            # Convert user_id column to string for comparison
            df["user_id"] = df["user_id"].astype(str)
            row = df[df["user_id"] == str(user_id)]
            if not row.empty:
                name = row.iloc[0].get("name")
                if pd.notna(name) and isinstance(name, str) and name:
                    # Strip common professional titles/suffixes
                    titles_to_remove = [
                        " DDS", " MD", " PhD", " Dr.", " Dr", 
                        " DVM", " DO", " JD", " Esq", " Esq.",
                        " MBA", " MS", " MA", " BSc", " MSc",
                        " Jr.", " Jr", " Sr.", " Sr", " III", " II", " IV"
                    ]
                    clean_name = name
                    for title in titles_to_remove:
                        # Case-insensitive replacement at the end of name
                        if clean_name.endswith(title):
                            clean_name = clean_name[:-len(title)]
                        # Also check uppercase variants
                        elif clean_name.endswith(title.upper()):
                            clean_name = clean_name[:-len(title)]
                    return clean_name.strip()
    except Exception as e:
        print(f"Error getting user name: {e}")
    return None


def _classify_intent(text: str) -> str:
    """Classify intent into: greeting | farewell | small_talk | feedback_positive | feedback_negative | product_search | styling_advice | clarification_request | order_request"""
    text_lower = text.lower().strip()
    
    # Greeting patterns
    greeting_patterns = [
        "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
        "what's up", "whats up", "sup", "howdy", "greetings", "hi there", "hey there"
    ]
    if any(text_lower.startswith(pattern) or text_lower == pattern for pattern in greeting_patterns):
        if len(text.split()) <= 3 and not any(word in text_lower for word in ["show", "find", "want", "need", "looking"]):
            return "greeting"
    
    # Farewell patterns
    farewell_patterns = [
        "bye", "goodbye", "see you", "take care", "thanks", "thank you", "cheers", "later", "gtg", "gotta go"
    ]
    if any(pattern in text_lower for pattern in farewell_patterns):
        if len(text.split()) <= 5:
            return "farewell"
    
    # Feedback - Positive
    positive_patterns = [
        "i like", "love it", "love this", "perfect", "great", "awesome", "excellent", "amazing",
        "exactly what", "just what", "this is good", "looks good", "that's nice"
    ]
    if any(pattern in text_lower for pattern in positive_patterns):
        return "feedback_positive"
    
    # Feedback - Negative
    negative_patterns = [
        "i don't like", "not what", "don't want", "no", "nope", "not interested",
        "something else", "different", "other options", "not my style", "too expensive", "too cheap"
    ]
    if any(pattern in text_lower for pattern in negative_patterns):
        return "feedback_negative"
    
    # Cart/Order patterns
    cart_patterns = [
        "add to cart", "add this", "cart", "shopping cart", "show cart", "view cart", "my cart",
        "clear cart", "remove from cart"
    ]
    if any(pattern in text_lower for pattern in cart_patterns):
        if "show" in text_lower or "view" in text_lower or "my" in text_lower or "what" in text_lower:
            return "view_cart"
        elif "clear" in text_lower or "empty" in text_lower:
            return "clear_cart"
        else:
            return "add_to_cart"
    
    # Order/Purchase request
    order_patterns = [
        "order this", "buy this", "purchase", "i'll take", "checkout", "i want to buy"
    ]
    if any(pattern in text_lower for pattern in order_patterns):
        return "order_request"
    
    # Clarification needed (vague queries)
    if len(text.split()) <= 2 and not any(word in text_lower for word in ["show", "find", "get", "shirt", "pants", "shoes"]):
        vague_patterns = ["maybe", "idk", "i don't know", "not sure", "anything", "whatever"]
        if any(pattern in text_lower for pattern in vague_patterns):
            return "clarification_request"
    
    # Small talk
    small_talk_patterns = [
        "how are you", "what's new", "whats new", "how's it going", "hows it going",
        "you good", "are you", "weather", "how's your day"
    ]
    if any(pattern in text_lower for pattern in small_talk_patterns):
        return "small_talk"
    
    # Styling advice patterns
    styling_patterns = [
        "how to", "how do i", "how should i", "how can i",
        "style", "styling", "match", "pair", "goes with",
        "tips", "advice", "outfit ideas", "fashion tips"
    ]
    if any(pattern in text_lower for pattern in styling_patterns):
        # If it's asking for products specifically, treat as product search
        if not any(word in text_lower for word in ["show me", "find", "get me", "i want", "i need", "looking for"]):
            return "styling_advice"
    
    # Default to product_search for anything else
    return "product_search"


def _generate_styling_advice(text: str, user_name: str) -> str:
    """Generate fashion styling advice using Gemini API for dynamic, personalized responses"""
    # Extract fashion topic from query
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
    
    # Use Gemini to generate dynamic, personalized styling advice
    return generate_styling_advice_with_gemini(user_name, text, fashion_topic)


def _is_general_question(text: str) -> Optional[str]:
    """Check if query is a general question (not product-related). Returns response if matched."""
    t = text.lower().strip()
    
    # Hours/timing questions
    if any(x in t for x in ["open hour", "opening hour", "when open", "what time", "business hour", "store hour"]):
        return "Our partner shops have different operating hours. Most are open from 9 AM to 8 PM daily. For specific shop hours, please visit the shop's product page or contact them directly."
    
    # Location questions
    if any(x in t for x in ["where are you", "location", "address", "find you"]):
        return "I'm StylesenseSL, your AI fashion shopping assistant! I help you discover products from various shops across Sri Lanka. Each product card shows the shop location."
    
    # About/help
    if any(x in t for x in ["who are you", "what are you", "what can you", "how do you work"]):
        return "I'm StylesenseSL, your personal fashion shopping assistant! I help you find the perfect clothes by understanding your style preferences. Just tell me what you're looking for – like 'black t-shirts under 5000' or 'casual wear for the beach' – and I'll find the best matches for you!"
    
    return None


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/search")
def search(request: Request, q: str, limit: Optional[int] = 10, user_id: Optional[str] = None):
    try:
        uid = _get_user_id(request, user_id)
        user_name = _get_user_name(uid)
        candidates = agent.search_by_text(q, limit=limit)
        # log interaction
        if uid:
            user_agent.record_interaction(uid, "search", {"query": q, "limit": limit})
        # derive intent from query for better personalization
        intent = parse_intent(q)
        ranked = personalization_agent.rerank(uid, candidates, intent=intent, context={"query": q})
        # Generate natural conversational message
        message = personalization_agent.generate_chat_message(
            uid,
            intent,
            ranked.get("best_matches", []),
            ranked.get("new_suggestions", []),
            user_name
        )
        return {
            "message": message,
            "best_matches": ranked.get("best_matches", []),
            "new_suggestions": ranked.get("new_suggestions", []),
            "explanations": ranked.get("explanations", {}),
            "user_profile_used": user_agent.get_preferences(uid) if uid else {},
            # Keep legacy fields for UI backward compatibility
            "products": ranked.get("results", candidates),
            "personalization_score": None,
            "why": None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/products/{product_id}")
def get_product(request: Request, product_id: int, user_id: Optional[str] = None):
    try:
        p = agent.get_product_by_id(product_id)
        if not p:
            raise HTTPException(status_code=404, detail="Product not found")
        # log view interaction
        uid = _get_user_id(request, user_id)
        if uid:
            user_agent.record_interaction(uid, "view", {"product_id": product_id, "category": p.get("category")})
        return p
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/products/{product_id}/similar")
def get_similar_products(product_id: str, limit: int = 5):
    """Get products similar to the given product using vector search.
    
    Args:
        product_id: The product ID to find similar items for
        limit: Maximum number of similar products to return (default: 5)
    
    Returns:
        JSON with similar_products array and method used
    """
    try:
        # Check if vector search is available
        if hasattr(agent, 'vector_search') and agent.vector_search and agent.vector_search.enabled:
            try:
                similar = agent.vector_search.get_similar_products(str(product_id), top_k=limit)
                
                # Enrich with full product details
                products = []
                for match in similar:
                    # Try to get product
                    pid_str = str(match['product_id'])
                    df = loader.products
                    row = df[df['product_id'].astype(str) == pid_str]
                    if not row.empty:
                        product = row.iloc[0].to_dict()
                        product['similarity_score'] = match['similarity_score']
                        product['_search_method'] = 'vector'
                        
                        # Add shop info
                        shop = loader.get_shop(product.get('shop_id'))
                        if shop:
                            product['_shop_name'] = shop.get('shop_name')
                            product['_shop_location'] = shop.get('location')
                        
                        products.append(product)
                
                return {
                    "similar_products": products,
                    "method": "vector_search",
                    "count": len(products)
                }
            except Exception as e:
                print(f"[WARN] Vector search failed for similar products: {e}")
                import traceback
                traceback.print_exc()
        
        # Fallback: find products in same category
        product = agent.get_product_by_id(str(product_id))
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        category = product.get('category')
        color = product.get('color')
        
        # Find similar by category and color
        similar = agent.find_by_filters(category=category, color=color)
        # Exclude the original product
        similar = [p for p in similar if str(p.get('product_id')) != str(product_id)]
        
        return {
            "similar_products": similar[:limit],
            "method": "category_filter_fallback",
            "count": len(similar[:limit])
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to get similar products: {e}")
        import traceback
        traceback.print_exc()
        return {"similar_products": [], "method": "error", "error": str(e)}


@app.get("/api/shops/{shop_id}")
def get_shop(shop_id: str):
    s = loader.get_shop(shop_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return s


@app.get("/api/users")
def list_users():
    """Return a simple list of users for the frontend dropdown.

    Reads users from data/raw/users_dataset.csv if available; falls back to demo ids.
    """
    try:
        users_path = ROOT / "data" / "raw" / "users_dataset.csv"
        if users_path.exists():
            df = pd.read_csv(users_path)
            out = []
            for _, row in df.iterrows():
                uid = row.get("user_id")
                if pd.isna(uid):
                    continue
                uid = str(uid)
                name = row.get("name")
                out.append({"id": uid, "name": name if (isinstance(name, str) and name) else uid})
            return {"users": out[:500]}
    except Exception:
        pass
    return {"users": [{"id": "alice", "name": "alice"}, {"id": "bob", "name": "bob"}]}


@app.post("/api/answer")
def answer(request: Request, payload: dict, user_id: Optional[str] = None):
    """
    Main chat endpoint - uses orchestrator to route to appropriate agents.
    
    The orchestrator handles:
    - Intent classification
    - Agent routing (Catalog, Order, User, Personalization)
    - Response formatting
    
    Returns structured JSON with: {intent, reply, message, products, filters, etc.}
    """
    try:
        text = payload.get("text")
        if not text:
            return {
                "intent": "error",
                "reply": "Please tell me what you're looking for!",
                "message": "Please tell me what you're looking for!",
                "filters": {},
                "suggestions": [],
                "best_matches": [],
                "new_suggestions": [],
            }

        uid = _get_user_id(request, user_id)
        user_name = _get_user_name(uid)
        
        print(f"[DEBUG] User: {user_name or uid or 'anonymous'}, Query: '{text}'")
        
        # Use orchestrator to process the query
        response = orchestrator.process_query(text, user_id=uid, user_name=user_name)
        
        # Log interaction for product searches
        if response.get("intent") == "product_search" and uid:
            user_agent.record_interaction(uid, "search", {"query": text})
        
        # Handle special case: add_to_cart needs URL extraction (done here for now)
        if response.get("intent") == "add_to_cart" and response.get("needs_url_extraction"):
            import re
            url_pattern = r'https?://[^\s]+'
            urls = re.findall(url_pattern, text)
            
            if not urls:
                cart_msg = "📦 To add items to your cart, please share a product link!\n\nExample:\n**add to cart: https://www.daraz.lk/products/...**"
                return {
                    "intent": "add_to_cart",
                    "reply": cart_msg,
                    "message": cart_msg,
                    "filters": {},
                    "suggestions": [],
                    "best_matches": [],
                    "new_suggestions": [],
                    "results": [],
                }
            
            product_url = urls[0]
            quantity = 1
            qty_match = re.search(r'(\d+)\s*(?:x|times|pieces?|qty|quantity)', text.lower())
            if qty_match:
                quantity = int(qty_match.group(1))
            
            # Add to cart via OrderAgent
            result = order_agent.add_product(product_url, quantity)
            
            if not result.get("success"):
                error_msg = f"❌ Sorry, I couldn't add that product to your cart.\n\n**Error:** {result.get('error', 'Unknown error')}"
                return {
                    "intent": "add_to_cart",
                    "reply": error_msg,
                    "message": error_msg,
                    "error": result.get("error"),
                    "filters": {},
                    "suggestions": [],
                    "best_matches": [],
                    "new_suggestions": [],
                    "results": [],
                }
            
            product = result["product"]
            success_msg = f"✅ **Added to cart!**\n\n**{product['name']}**\n🏪 {product['shop']}\n💵 {product['currency']} {product['price']:.2f}\n"
            success_msg += f"📦 Quantity: {product['quantity']}\n\n*Cart now has {result['cart_total_items']} item(s)*"
            
            return {
                "intent": "add_to_cart",
                "reply": success_msg,
                "message": success_msg,
                "product": product,
                "cart_total": result['cart_total_items'],
                "filters": {},
                "suggestions": [],
                "best_matches": [],
                "new_suggestions": [],
                "results": [],
                "agent": "order_agent"
            }
        
        # Return orchestrator response
        return response
        
    except Exception as e:
        print(f"[ERROR] Exception in answer endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "intent": "error",
            "reply": "Sorry, I encountered an error processing your request.",
            "message": "Sorry, I encountered an error processing your request.",
            "filters": {},
            "suggestions": [],
            "best_matches": [],
            "new_suggestions": [],
            "error": str(e)
        }
    
    # Handle greeting intent
    if intent_type == "greeting":
        greeting_msg = f"Hi {user_name or 'there'}! 👋 How are you doing today?"
        return {
            "intent": "greeting",
            "reply": greeting_msg,
            "filters": {},
            "suggestions": [],
            "explainability": "User greeted me, so I respond with a friendly greeting only.",
            "message": greeting_msg,
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "greeting"},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle farewell intent
    if intent_type == "farewell":
        farewell_msg = f"Take care, {user_name or 'there'}! 👋 Feel free to come back anytime you need fashion help!"
        return {
            "intent": "farewell",
            "reply": farewell_msg,
            "filters": {},
            "suggestions": [],
            "explainability": "User is saying goodbye, responding with friendly farewell.",
            "message": farewell_msg,
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "farewell"},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle small talk intent - DYNAMIC using Gemini (with timeout)
    if intent_type == "small_talk":
        try:
            # Get last product viewed and recent interaction from user profile
            user_prefs = user_agent.get_preferences(uid) if uid else None
            last_product = user_prefs.get("last_product_viewed") if user_prefs else None
            recent_interaction = user_prefs.get("last_interaction_type") if user_prefs else None
            
            print(f"[DEBUG] Generating dynamic small talk for {user_name}")
            # Generate dynamic small talk using Gemini (should be fast with fallback)
            small_talk_msg = dynamic_small_talk(
                user_name=user_name,
                last_product=last_product,
                recent_interaction=recent_interaction
            )
            print(f"[DEBUG] Small talk generated: {small_talk_msg[:50]}...")
        except Exception as e:
            print(f"[ERROR] Error generating dynamic small talk: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to static message if Gemini fails
            small_talk_msg = f"I'm doing great, thanks for asking! 😊 I'm here to help you find amazing fashion. What are you looking for today?"
        
        return {
            "intent": "small_talk",
            "reply": small_talk_msg,
            "filters": {},
            "suggestions": [],
            "explainability": "User engaged in small talk, responding warmly with context-aware message.",
            "message": small_talk_msg,
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "small_talk"},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle positive feedback intent
    if intent_type == "feedback_positive":
        positive_msg = f"Awesome! 🎉 I'm so glad you like it! Would you like to see more similar items, or shall I help you with something else?"
        return {
            "intent": "feedback_positive",
            "reply": positive_msg,
            "filters": {},
            "suggestions": [],
            "explainability": "User expressed satisfaction, acknowledging positive feedback and offering continued assistance.",
            "message": positive_msg,
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "feedback_positive"},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle negative feedback intent
    if intent_type == "feedback_negative":
        negative_msg = f"Got it! 👍 Could you tell me what you'd like to change — style, color, price range, or category?"
        return {
            "intent": "feedback_negative",
            "reply": negative_msg,
            "filters": {},
            "suggestions": [],
            "explainability": "User disliked previous suggestions, so I ask for preference adjustments instead of repeating products.",
            "message": negative_msg,
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "feedback_negative"},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle view_cart intent
    if intent_type == "view_cart":
        cart_summary = order_agent.get_cart_summary()
        
        if cart_summary["total_items"] == 0:
            cart_msg = "🛒 Your cart is empty! Share a product link to add items. Example:\n\nadd to cart: https://www.daraz.lk/products/..."
            return {
                "intent": "view_cart",
                "reply": cart_msg,
                "message": cart_msg,
                "cart": cart_summary,
                "filters": {},
                "suggestions": [],
                "explainability": "User requested to view cart, but cart is empty.",
                "best_matches": [],
                "new_suggestions": [],
                "explanations": {"intent_type": "view_cart", "cart_empty": True},
                "user_profile_used": {},
                "results": [],
            }
        
        # Format cart display
        cart_items = cart_summary["items"]
        shops = cart_summary["by_shop"]
        
        cart_display = f"🛍️ **Your Shopping Cart** ({cart_summary['total_items']} items)\n\n"
        
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
        
        return {
            "intent": "view_cart",
            "reply": cart_display,
            "message": cart_display,
            "cart": cart_summary,
            "filters": {},
            "suggestions": [],
            "explainability": f"User requested cart view. {cart_summary['total_items']} items across {len(shops)} shop(s). Grand total: LKR {cart_summary['grand_total']:.2f}",
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "view_cart", "cart_summary": cart_summary},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle clear_cart intent
    if intent_type == "clear_cart":
        order_agent.cart = []
        clear_msg = "🗑️ Cart cleared! Your shopping cart is now empty."
        return {
            "intent": "clear_cart",
            "reply": clear_msg,
            "message": clear_msg,
            "filters": {},
            "suggestions": [],
            "explainability": "User requested to clear cart, all items removed.",
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "clear_cart"},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle add_to_cart intent
    if intent_type == "add_to_cart":
        # Extract URL from text using regex
        import re
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, text)
        
        if not urls:
            cart_msg = "📦 To add items to your cart, please share a product link!\n\nExample:\n**add to cart: https://www.daraz.lk/products/...**\n\nSupported shops: Daraz, Amazon, eBay, AliExpress, ikman.lk"
            return {
                "intent": "add_to_cart",
                "reply": cart_msg,
                "message": cart_msg,
                "filters": {},
                "suggestions": [],
                "explainability": "User wants to add to cart but didn't provide a product URL.",
                "best_matches": [],
                "new_suggestions": [],
                "explanations": {"intent_type": "add_to_cart", "no_url": True},
                "user_profile_used": {},
                "results": [],
            }
        
        product_url = urls[0]
        
        # Extract quantity if mentioned
        quantity = 1
        qty_match = re.search(r'(\d+)\s*(?:x|times|pieces?|qty|quantity)', text.lower())
        if qty_match:
            quantity = int(qty_match.group(1))
        
        # Add product to cart
        result = order_agent.add_product(product_url, quantity)
        
        if not result.get("success"):
            error_msg = f"❌ Sorry, I couldn't add that product to your cart.\n\n**Error:** {result.get('error', 'Unknown error')}\n\nPlease check the URL and try again."
            return {
                "intent": "add_to_cart",
                "reply": error_msg,
                "message": error_msg,
                "error": result.get("error"),
                "filters": {},
                "suggestions": [],
                "explainability": f"Failed to add product to cart: {result.get('error')}",
                "best_matches": [],
                "new_suggestions": [],
                "explanations": {"intent_type": "add_to_cart", "error": result.get("error")},
                "user_profile_used": {},
                "results": [],
            }
        
        # Success - show product added
        product = result["product"]
        success_msg = f"✅ **Added to cart!**\n\n"
        success_msg += f"**{product['name']}**\n"
        success_msg += f"🏪 {product['shop']}\n"
        success_msg += f"💵 {product['currency']} {product['price']:.2f}\n"
        success_msg += f"📦 Quantity: {product['quantity']}\n"
        if product.get('availability'):
            success_msg += f"✓ {product['availability']}\n"
        success_msg += f"\n*Cart now has {result['cart_total_items']} item(s)*\n\n"
        success_msg += "Type **'show cart'** to view your full cart!"
        
        return {
            "intent": "add_to_cart",
            "reply": success_msg,
            "message": success_msg,
            "product": product,
            "cart_total": result['cart_total_items'],
            "filters": {},
            "suggestions": [],
            "explainability": f"Successfully added {product['name']} from {product['shop']} to cart. Quantity: {product['quantity']}",
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "add_to_cart", "product_added": product},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle order request intent
    if intent_type == "order_request":
        order_msg = f"Great choice! 🛒 To complete your order, please click the product link to visit the shop's website. I don't process payments directly, but I'm here to help you find what you need!"
        return {
            "intent": "order_request",
            "reply": order_msg,
            "filters": {},
            "suggestions": [],
            "explainability": "User wants to order, providing instructions to complete purchase through shop website.",
            "message": order_msg,
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "order_request"},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle clarification request intent
    if intent_type == "clarification_request":
        clarification_msg = clarify_ambiguous_query(text, user_name)
        return {
            "intent": "clarification_request",
            "reply": clarification_msg,
            "filters": {},
            "suggestions": [],
            "explainability": "User query is vague, politely asking for color, budget, size, or category details.",
            "message": clarification_msg,
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "clarification_request"},
            "user_profile_used": {},
            "results": [],
        }
    
    # Check for general questions (hours/location/about)
    general_response = _is_general_question(text)
    if general_response:
        return {
            "intent": "small_talk",
            "reply": general_response,
            "filters": {},
            "suggestions": [],
            "explainability": "User asked a general question about the service, providing helpful information.",
            "message": general_response,
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"is_general_question": True},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle styling_advice intent
    if intent_type == "styling_advice":
        advice_msg = _generate_styling_advice(text, user_name)
        return {
            "intent": "styling_advice",
            "reply": advice_msg,
            "filters": {},
            "suggestions": [],
            "explainability": "User asked for styling advice, so I give general fashion tips without pushing products.",
            "message": advice_msg,
            "best_matches": [],
            "new_suggestions": [],
            "explanations": {"intent_type": "styling_advice"},
            "user_profile_used": {},
            "results": [],
        }
    
    # Handle product_search intent
    if uid:
        user_agent.record_interaction(uid, "search", {"query": text})

    # prefer an agent-level implementation if available
    if hasattr(agent, "answer_question"):
        try:
            print(f"[DEBUG] Calling agent.answer_question for: '{text}'")
            results = agent.answer_question(text)
            print(f"[DEBUG] Results received: {len(results.get('results', []))} products")
            
            # debug log returned intent and fallbacks (if present)
            try:
                log_text = f"/answer called by {uid or 'anonymous'}: intent={results.get('intent')} fallbacks={results.get('fallbacks')} result_count={len(results.get('results', []))}"
                print(log_text)
            except Exception:
                pass
            # rerank results using PersonalizationAgent
            ranked = personalization_agent.rerank(uid, results.get("results", []), intent=results.get("intent"), context={"query": text})
            
            # Extract filters from parsed intent
            parsed_intent = results.get("intent", {})
            filters = {
                "category": parsed_intent.get("category"),
                "color": parsed_intent.get("color"),
                "shop": parsed_intent.get("shop_name"),
                "budget": parsed_intent.get("max_price"),
            }
            
            # Check if we have any matches
            best_matches = ranked.get("best_matches", [])
            new_suggestions = ranked.get("new_suggestions", [])
            
            # If no matches found, ask for clarification using Gemini
            if not best_matches and not new_suggestions:
                no_match_msg = clarify_ambiguous_query(text, user_name)
                no_match_msg_intro = f"I couldn't find items matching '{text}'. " + no_match_msg
                return {
                    "intent": "product_search_no_match",
                    "reply": no_match_msg_intro,
                    "message": no_match_msg_intro,
                    "filters": filters,
                    "suggestions": [],
                    "explainability": "No products matched the query. Asking user for more specific criteria.",
                    "best_matches": [],
                    "new_suggestions": [],
                    "explanations": parsed_intent,
                    "user_profile_used": user_agent.get_preferences(uid) if uid else {},
                    "results": [],
                }
            
            # Generate natural conversational message with user name
            msg = personalization_agent.generate_chat_message(
                uid,
                results.get("intent"),
                best_matches,
                new_suggestions,
                user_name
            )
            
            print(f"[DEBUG] Generated message: '{msg[:100]}...'")
            
            # Format suggestions with detailed product info
            all_products = best_matches + new_suggestions
            suggestions = []
            for p in all_products[:6]:  # Top 6 products
                suggestions.append({
                    "name": p.get("product_name", p.get("name", "Unknown")),
                    "shop": p.get("_shop_name", p.get("shop", "Unknown")),
                    "sizes": p.get("size_range", "N/A"),
                    "price": f"LKR {p.get('price', 0):,.0f}",
                    "link": p.get("product_url", "#"),
                    "personalization_score": round(p.get("_personalization_score", 0), 2) if p.get("_personalization_score") else None,
                })
            
            explainability = f"These products match the requested filters: {', '.join([f'{k}={v}' for k, v in filters.items() if v])}. Personalized based on your style preferences."
            
            response_data = {
                "intent": "product_search",
                "reply": msg,
                "filters": filters,
                "suggestions": suggestions,
                "explainability": explainability,
                "message": msg,
                "best_matches": ranked.get("best_matches", []),
                "new_suggestions": ranked.get("new_suggestions", []),
                "explanations": {"fallbacks": results.get("fallbacks", []), **ranked.get("explanations", {})},
                "user_profile_used": user_agent.get_preferences(uid) if uid else {},
                # Keep legacy key for UI product grid
                "results": ranked.get("results", []),
            }
            print(f"[DEBUG] Returning response with message: {bool(response_data.get('message'))}")
            return response_data
        except Exception as e:
            print(f"[ERROR] Exception in answer_question: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Return friendly error message instead of raising exception
            error_msg = f"Hey, {user_name or 'there'}! I'm having trouble searching for that right now. Could you try rephrasing? For example: 'show me black t-shirts' or 'joggers under 5000'."
            return {
                "intent": "error",
                "reply": error_msg,
                "message": error_msg,
                "filters": {},
                "suggestions": [],
                "explainability": f"Error occurred: {str(e)}",
                "best_matches": [],
                "new_suggestions": [],
                "explanations": {"error": str(e)},
                "user_profile_used": {},
                "results": [],
            }
    
    # If agent doesn't have answer_question, return fallback message
    print(f"[DEBUG] Agent does not have answer_question method")
    fallback_msg = f"Hey, {user_name or 'there'}! I'm still learning to understand that query. Could you try being more specific? For example: 'show me black t-shirts' or 'joggers under 5000'."
    return {
        "intent": "clarification_request",
        "reply": fallback_msg,
        "message": fallback_msg,
        "filters": {},
        "suggestions": [],
        "explainability": "Query format not recognized, asking for clarification.",
        "best_matches": [],
        "new_suggestions": [],
        "explanations": {},
        "user_profile_used": {},
        "results": [],
    }

    res = {"text": text, "matches": []}
    m_price = re.search(r"under\s+([0-9,]+)", text, flags=re.IGNORECASE)
    shop = None
    m_shop = re.search(r"from\s+([A-Za-z0-9 &]+)", text, flags=re.IGNORECASE)
    if m_shop:
        shop = m_shop.group(1).strip()
    max_price = None
    if m_price:
        max_price = int(m_price.group(1).replace(",", ""))

    # find any known tags by scanning a small set from loader
    tags = []
    try:
        if hasattr(loader, 'products'):
            # collect unique tags from sample of products
            all_tags = []
            for t in loader.products.get('style_tags', [])[:200]:
                if isinstance(t, list):
                    all_tags.extend(t)
            all_tags = set([x.lower() for x in all_tags if isinstance(x, str)])
            for token in text.lower().split():
                if token in all_tags:
                    tags.append(token)
    except Exception:
        pass

    # perform a filter search using available pieces
    try:
        results = agent.find_by_filters(tag=(tags[0] if tags else None), max_price=max_price, category=None)
        if shop:
            # filter by shop name match
            results = [p for p in results if loader.get_shop(str(p.get('shop_id')))
                       and shop.lower() in loader.get_shop(str(p.get('shop_id'))).get('shop_name', '').lower()]
    except Exception:
        results = []

    # personalize results if user known
    if uid:
        results = personalizer.personalize_results(uid, results)

    res['matches'] = results
    return res


# ============================================
# ORDER AGENT ENDPOINTS
# ============================================

@app.post("/api/cart/add")
async def add_to_cart(request: Request):
    """Add product from URL to virtual cart.
    
    Supports two methods:
    1. URL from dataset (fast lookup via URL mapping)
    2. Real-world URL (slower, requires web scraping)
    
    Request body:
    {
        "url": "https://elements.com/product/1630",
        "quantity": 2,
        "size": "M"
    }
    """
    try:
        body = await request.json()
        url = body.get("url")
        quantity = body.get("quantity", 1)
        size = body.get("size")  # Optional selected size
        
        if not url:
            raise HTTPException(status_code=400, detail="Product URL is required")
        
        # First, check if URL exists in our product mapping (fast lookup)
        product_data = url_to_product_map.get(str(url))
        
        if product_data:
            # Found in dataset - add directly without scraping
            result = order_agent.add_product_direct(product_data, quantity, size)
            
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Failed to add product"),
                    "url": url
                }
            
            return {
                "success": True,
                "message": "Product added to cart (from dataset)",
                "product": result["product"],
                "cart_total_items": result["cart_total_items"]
            }
        else:
            # URL not in dataset, try to scrape from web
            result = order_agent.add_product(url, quantity, size)
            
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Failed to add product"),
                    "url": url
                }
            
            return {
                "success": True,
                "message": "Product added to cart",
                "product": result["product"],
                "cart_total_items": result["cart_total_items"]
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cart")
async def get_cart():
    """Get current cart summary with all items grouped by shop."""
    try:
        summary = order_agent.get_cart_summary()
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/cart/clear")
async def clear_cart():
    """Clear all items from cart."""
    try:
        order_agent.clear_cart()
        return {"success": True, "message": "Cart cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/cart/item/{index}")
async def remove_cart_item(index: int):
    """Remove specific item from cart by index."""
    try:
        success = order_agent.remove_item(index)
        if success:
            return {"success": True, "message": "Item removed"}
        else:
            raise HTTPException(status_code=404, detail="Item not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/cart/item/{index}")
async def update_cart_item(index: int, request: Request):
    """Update quantity of cart item.
    
    Request body:
    {
        "quantity": 3
    }
    """
    try:
        body = await request.json()
        quantity = body.get("quantity", 1)
        
        success = order_agent.update_quantity(index, quantity)
        if success:
            return {"success": True, "message": "Quantity updated"}
        else:
            raise HTTPException(status_code=404, detail="Item not found or invalid quantity")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _data_fabric_root() -> Path:
    return ROOT / "src" / "services" / "data_fabric"


def _load_data_fabric_catalog():
    from src.services.data_fabric.src.metadata.catalog import MetadataCatalog

    return MetadataCatalog()


def _read_table_for_dataset(catalog, dataset_name: str) -> pd.DataFrame:
    asset = catalog.get_asset(dataset_name)
    file_path = None
    if asset is not None:
        file_path = asset.location
        if not file_path:
            file_path = asset.metadata.properties.get("file_path") if asset.metadata.properties else None

    # Skip virtual outputs when source file does not exist.
    if file_path and str(file_path).startswith("virtual://"):
        file_path = None

    candidate_paths: List[Path] = []
    if file_path:
        candidate_paths.append(Path(file_path))

    raw_path = ROOT / "data" / "raw" / f"{dataset_name}.csv"
    candidate_paths.append(raw_path)

    for path in candidate_paths:
        if not path.exists() or not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(path)
        if suffix in {".tsv", ".txt"}:
            return pd.read_csv(path, sep="\t")
        if suffix in {".xls", ".xlsx"}:
            return pd.read_excel(path)
        if suffix == ".json":
            return pd.read_json(path)
        if suffix == ".parquet":
            return pd.read_parquet(path)

    raise FileNotFoundError(f"Dataset file not found for '{dataset_name}'")


def _normalize_relationship(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "relationship_key": str(record.get("relationship_key", "")),
        "left_dataset": str(record.get("left_dataset", "")),
        "right_dataset": str(record.get("right_dataset", "")),
        "left_column": str(record.get("left_column", "")),
        "right_column": str(record.get("right_column", "")),
        "confidence": float(record.get("confidence", 0.0)),
        "decision": str(record.get("decision", "weak")),
        "cardinality": str(record.get("cardinality", "unknown")),
        "model_version": str(record.get("model_version", "unknown")),
        "feature_vector_version": str(record.get("feature_vector_version", "unknown")),
        "feature_vector": record.get("feature_vector", {}),
        "counterpart_dataset": record.get("counterpart_dataset"),
        "is_unstable": bool(record.get("is_unstable", False)),
        "drift_score": float(record.get("drift_score", 0.0)),
        "join_usage_count": int(record.get("join_usage_count", 0)),
        "last_scored_at": record.get("last_scored_at"),
        "last_used_at": record.get("last_used_at"),
        "history_points": len(list(record.get("history", []))),
    }


def _relationship_signals(relationship: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    feature_vector = dict(relationship.get("feature_vector", {}))

    def pick(keys: List[str]) -> Dict[str, Any]:
        return {k: feature_vector[k] for k in keys if k in feature_vector}

    structural = {
        "name_similarity": relationship.get("name_similarity", feature_vector.get("name_similarity", 0.0)),
        "type_score": relationship.get("type_score", feature_vector.get("type_score", 0.0)),
        "cardinality": relationship.get("cardinality", "unknown"),
        **pick(["left_dtype", "right_dtype", "uniqueness_ratio_left", "uniqueness_ratio_right"]),
    }
    statistical = {
        "overlap_ratio": relationship.get("overlap_ratio", feature_vector.get("overlap_ratio", 0.0)),
        **pick(["numeric_range_similarity", "value_intersection_count", "null_ratio_left", "null_ratio_right"]),
    }
    behavioral = {
        **pick([
            "convertibility_score",
            "join_usage_count",
            "relationship_stability",
            "behavioral_score",
        ])
    }

    return {
        "structural": structural,
        "statistical": statistical,
        "behavioral": behavioral,
    }


@app.get("/api/data-fabric/overview")
async def data_fabric_overview():
    """Return Data Fabric dashboard overview from live metadata catalog."""
    catalog = _load_data_fabric_catalog()
    assets = catalog.list_assets(asset_type="table")

    datasets: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []
    seen_relationship_keys = set()

    for asset in assets:
        md = asset.metadata
        datasets.append(
            {
                "dataset_name": asset.name,
                "row_count": int(md.row_count),
                "column_count": int(md.column_count),
                "domain": str(md.domain),
                "quality_score": float(md.quality_score),
                "updated_at": md.updated_at.isoformat(),
                "usage_count": int(md.usage_count),
                "location": asset.location,
            }
        )

        for rel in catalog.get_inferred_relationships(asset.name):
            key = str(rel.get("relationship_key", ""))
            if not key or key in seen_relationship_keys:
                continue
            seen_relationship_keys.add(key)
            relationships.append(_normalize_relationship(rel))

    relationships.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)

    decision_counts = {"strong": 0, "probable": 0, "weak": 0}
    unstable_count = 0
    for rel in relationships:
        decision = str(rel.get("decision", "weak")).lower()
        if decision in decision_counts:
            decision_counts[decision] += 1
        if rel.get("is_unstable"):
            unstable_count += 1

    metrics_path = _data_fabric_root() / "models" / "relationship_metrics_v1.json"
    metrics: Dict[str, Any] = {}
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            metrics = {}

    model_info = {
        "model_mode": "ensemble",
        "model_version": "unknown",
        "feature_vector_version": "unknown",
    }
    if relationships:
        model_info["model_version"] = str(relationships[0].get("model_version", "unknown"))
        model_info["feature_vector_version"] = str(
            relationships[0].get("feature_vector_version", "unknown")
        )

    return {
        "kpis": {
            "dataset_count": len(datasets),
            "relationship_count": len(relationships),
            "strong_count": decision_counts["strong"],
            "probable_count": decision_counts["probable"],
            "weak_count": decision_counts["weak"],
            "unstable_count": unstable_count,
        },
        "model": model_info,
        "datasets": sorted(datasets, key=lambda item: item["dataset_name"]),
        "relationships": relationships,
        "metrics": metrics,
        "last_refreshed": pd.Timestamp.utcnow().isoformat(),
    }


@app.get("/api/data-fabric/join-options")
async def data_fabric_join_options(left_dataset: str, right_dataset: str):
    """Return ranked relationship suggestions and intervention mode for a pair."""
    catalog = _load_data_fabric_catalog()
    records = catalog.get_inferred_relationships(left_dataset)

    suggestions = [
        _normalize_relationship(r)
        for r in records
        if {str(r.get("left_dataset", "")), str(r.get("right_dataset", ""))}
        == {left_dataset, right_dataset}
    ]
    suggestions.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)

    non_weak = [s for s in suggestions if str(s.get("decision", "weak")).lower() != "weak"]
    if not suggestions:
        mode = "no_relationship"
    elif len(non_weak) > 1:
        mode = "manual_required_multiple"
    elif len(non_weak) == 1:
        mode = "auto_ready"
    else:
        mode = "manual_required_weak"

    return {
        "left_dataset": left_dataset,
        "right_dataset": right_dataset,
        "mode": mode,
        "suggestions": suggestions,
    }


@app.post("/api/data-fabric/join-execute")
async def data_fabric_join_execute(request: Request):
    """Execute autonomous join with optional manual relationship selection."""
    from src.services.data_fabric.src.integration import (
        AutonomousIntegrationAgent,
        ManualInterventionRequired,
        VirtualIntegrationLayer,
    )

    body = await request.json()
    left_dataset = str(body.get("left_dataset", "")).strip()
    right_dataset = str(body.get("right_dataset", "")).strip()
    selected_relationship_key = body.get("selected_relationship_key")
    allow_weak_relationship = bool(body.get("allow_weak_relationship", False))
    how = str(body.get("how", "inner"))

    if not left_dataset or not right_dataset:
        raise HTTPException(status_code=400, detail="left_dataset and right_dataset are required")

    catalog = _load_data_fabric_catalog()
    try:
        datasets = {
            left_dataset: _read_table_for_dataset(catalog, left_dataset),
            right_dataset: _read_table_for_dataset(catalog, right_dataset),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    layer = VirtualIntegrationLayer(metadata_catalog=catalog)

    try:
        joined_df, relationship = layer.join_on_demand(
            datasets=datasets,
            left_dataset=left_dataset,
            right_dataset=right_dataset,
            how=how,
            selected_relationship_key=str(selected_relationship_key) if selected_relationship_key else None,
            allow_weak_relationship=allow_weak_relationship,
        )
    except ManualInterventionRequired as exc:
        return {
            "success": False,
            "manual_intervention_required": True,
            "reason": str(exc),
            "suggestions": [s.to_dict() for s in exc.suggestions],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    relationship_key = (
        f"{relationship.left_dataset}:{relationship.left_column}->"
        f"{relationship.right_dataset}:{relationship.right_column}"
    )
    agent = AutonomousIntegrationAgent(metadata_catalog=catalog)
    usage_updates = agent.log_join_usage(
        left_dataset=left_dataset,
        right_dataset=right_dataset,
        relationship_key=relationship_key,
    )

    preview_limit = int(body.get("preview_limit", 25))
    preview = joined_df.head(max(1, min(preview_limit, 200))).to_dict(orient="records")

    return {
        "success": True,
        "manual_intervention_required": False,
        "relationship": relationship.to_dict(),
        "row_count": int(len(joined_df)),
        "columns": joined_df.columns.tolist(),
        "preview": preview,
        "usage_updates": usage_updates,
    }


@app.get("/api/data-fabric/lineage")
async def data_fabric_lineage():
    """Return node/edge lineage graph built from metadata catalog."""
    catalog = _load_data_fabric_catalog()
    assets = catalog.list_assets(asset_type="table")

    nodes = [
        {
            "id": asset.name,
            "label": asset.name,
            "domain": str(asset.metadata.domain),
            "quality_score": float(asset.metadata.quality_score),
        }
        for asset in assets
    ]

    edges_set = set()
    edges: List[Dict[str, str]] = []
    for asset in assets:
        dataset_info = catalog.get_dataset(asset.name) or {}
        downstream = dataset_info.get("downstream_datasets", [])
        for child in downstream:
            key = (asset.name, child)
            if key in edges_set:
                continue
            edges_set.add(key)
            edges.append({"source": asset.name, "target": child})

    return {
        "nodes": sorted(nodes, key=lambda n: n["id"]),
        "edges": sorted(edges, key=lambda e: (e["source"], e["target"])),
    }


@app.get("/api/data-fabric/logs")
async def data_fabric_logs(limit: int = 200):
    """Return operational logs synthesized from relationship metadata history."""
    catalog = _load_data_fabric_catalog()
    events: List[Dict[str, Any]] = []
    seen = set()

    for asset in catalog.list_assets(asset_type="table"):
        dataset_name = asset.name
        for rel in catalog.get_inferred_relationships(dataset_name):
            key = str(rel.get("relationship_key", ""))
            if not key or key in seen:
                continue
            seen.add(key)

            history = list(rel.get("history", []))
            for item in history:
                events.append(
                    {
                        "timestamp": item.get("timestamp"),
                        "event": "relationship_scored",
                        "dataset_pair": f"{rel.get('left_dataset')}:{rel.get('right_dataset')}",
                        "relationship_key": key,
                        "confidence": float(item.get("confidence", 0.0)),
                        "decision": str(item.get("decision", "weak")),
                    }
                )

            if rel.get("is_unstable"):
                events.append(
                    {
                        "timestamp": rel.get("last_scored_at"),
                        "event": "relationship_unstable",
                        "dataset_pair": f"{rel.get('left_dataset')}:{rel.get('right_dataset')}",
                        "relationship_key": key,
                        "confidence": float(rel.get("confidence", 0.0)),
                        "decision": str(rel.get("decision", "weak")),
                        "drift_score": float(rel.get("drift_score", 0.0)),
                    }
                )

    events.sort(key=lambda e: str(e.get("timestamp", "")), reverse=True)
    return {"events": events[: max(1, min(int(limit), 1000))]}


@app.post("/api/data-fabric/intake")
async def data_fabric_intake(request: Request):
    """Process newly arrived file, infer relationships, and auto-join when safe."""
    body = await request.json()
    file_path_raw = str(body.get("file_path", "")).strip()
    dataset_name = str(body.get("dataset_name", "")).strip() or None
    auto_join_if_single = bool(body.get("auto_join_if_single", True))
    how = str(body.get("how", "inner"))

    if not file_path_raw:
        raise HTTPException(status_code=400, detail="file_path is required")

    file_path = Path(file_path_raw)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path_raw}")

    return _run_data_fabric_intake(
        file_path=file_path,
        dataset_name=dataset_name,
        auto_join_if_single=auto_join_if_single,
        how=how,
    )


@app.post("/api/data-fabric/intake-upload")
async def data_fabric_intake_upload(
    file: UploadFile = File(...),
    dataset_name: Optional[str] = Form(default=None),
    auto_join_if_single: bool = Form(default=True),
    how: str = Form(default="inner"),
):
    """Process uploaded file for Data Fabric intake workflow (drag/drop or file picker)."""
    upload_dir = ROOT / "data" / "raw" / "intake_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    original = Path(file.filename or "uploaded_file.csv")
    safe_name = f"{uuid4().hex}_{original.name}"
    saved_path = upload_dir / safe_name

    with saved_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    return _run_data_fabric_intake(
        file_path=saved_path,
        dataset_name=(dataset_name or "").strip() or original.stem,
        auto_join_if_single=auto_join_if_single,
        how=how,
    )


def _run_data_fabric_intake(
    file_path: Path,
    dataset_name: Optional[str],
    auto_join_if_single: bool,
    how: str,
) -> Dict[str, Any]:
    """Shared intake execution for path-based and upload-based workflows."""
    from src.services.data_fabric.src.ingestion.folder_scanner import FolderScanner
    from src.services.data_fabric.src.integration import AutonomousIntegrationAgent, VirtualIntegrationLayer

    intake_dataset_name = dataset_name or file_path.stem
    catalog = _load_data_fabric_catalog()
    scanner = FolderScanner(str(file_path.parent))

    df_new = scanner.load_data_file(
        file_path,
        enable_preprocessing=True,
        normalize_columns=True,
        normalize_dates=True,
        normalize_numeric=True,
        dataset_name=intake_dataset_name,
        metadata_catalog=catalog,
        metadata_registry=None,
        producer_pipeline="integration.autonomous_intake",
    )
    if df_new is None:
        raise HTTPException(status_code=400, detail="Failed to parse input data file")

    metadata = scanner.create_metadata(df_new, file_path)
    catalog.upsert_dataset(
        dataset_name=intake_dataset_name,
        domain=metadata.detected_domain,
        schema=metadata.data_types,
        row_count=metadata.row_count,
        producer_pipeline="integration.autonomous_intake",
        validation_status="warning",
        quality_score=0.0,
        description=f"Intake dataset from {file_path.name}",
        owner="integration",
        source_system=metadata.file_type,
        location=str(file_path),
        tags=[metadata.detected_domain, "intake"],
        properties={
            "file_path": str(file_path),
            "loaded_at": metadata.loaded_at.isoformat(),
            "last_updated": pd.Timestamp.utcnow().isoformat(),
            "producer_pipeline": "integration.autonomous_intake",
        },
    )

    datasets: Dict[str, pd.DataFrame] = {intake_dataset_name: df_new}
    for asset in catalog.list_assets(asset_type="table"):
        if asset.name == intake_dataset_name:
            continue
        try:
            datasets[asset.name] = _read_table_for_dataset(catalog, asset.name)
        except Exception:
            continue

    if len(datasets) < 2:
        return {
            "status": "ingested_only",
            "dataset_name": intake_dataset_name,
            "message": "File ingested, but no other datasets were available for relationship discovery yet.",
        }

    layer = VirtualIntegrationLayer(metadata_catalog=catalog)
    inferred = layer.infer_relationships(datasets=datasets, register_results=True)
    candidate_relationships = [
        rel.to_dict()
        for rel in inferred
        if rel.left_dataset == intake_dataset_name or rel.right_dataset == intake_dataset_name
    ]
    candidate_relationships.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)

    good_matches = [
        rel
        for rel in candidate_relationships
        if str(rel.get("decision", "weak")).lower() in {"strong", "probable"}
    ]
    bad_matches = [
        rel
        for rel in candidate_relationships
        if str(rel.get("decision", "weak")).lower() == "weak"
    ]

    suggestions = [
        {
            **_normalize_relationship(rel),
            "signals": _relationship_signals(rel),
            "explanation": (
                f"{rel.get('left_column')} -> {rel.get('right_column')} scored {float(rel.get('confidence', 0.0)):.3f} "
                f"({str(rel.get('decision', 'weak')).upper()})"
            ),
        }
        for rel in good_matches + bad_matches
    ]

    agent = AutonomousIntegrationAgent(metadata_catalog=catalog)
    behavioral_updates = agent.update_behavioral_features()
    drift_flags = agent.detect_and_flag_confidence_drift(threshold=0.20)

    if auto_join_if_single and len(good_matches) == 1:
        selected = good_matches[0]
        left_dataset = str(selected.get("left_dataset"))
        right_dataset = str(selected.get("right_dataset"))
        relationship_key = (
            f"{left_dataset}:{selected.get('left_column')}->{right_dataset}:{selected.get('right_column')}"
        )

        join_df, used_relationship = layer.join_on_demand(
            datasets=datasets,
            left_dataset=left_dataset,
            right_dataset=right_dataset,
            selected_relationship_key=relationship_key,
            allow_weak_relationship=False,
            how=how,
            output_dataset=f"{left_dataset}_{right_dataset}_joined",
            producer_pipeline="integration.autonomous_intake",
        )

        usage_updates = agent.log_join_usage(
            left_dataset=left_dataset,
            right_dataset=right_dataset,
            relationship_key=relationship_key,
        )

        return {
            "status": "auto_joined",
            "dataset_name": intake_dataset_name,
            "good_match_count": len(good_matches),
            "bad_match_count": len(bad_matches),
            "selected_relationship": used_relationship.to_dict(),
            "selected_signals": _relationship_signals(used_relationship.to_dict()),
            "why_joined": (
                f"Exactly one good match was found: {used_relationship.left_column} -> {used_relationship.right_column} "
                f"with confidence {used_relationship.confidence:.3f} ({used_relationship.decision.upper()})."
            ),
            "join_preview": join_df.head(25).to_dict(orient="records"),
            "join_rows": int(len(join_df)),
            "suggestions": suggestions,
            "agent_updates": {
                "usage_updates": usage_updates,
                "behavioral_updates": behavioral_updates,
                "drift_flags": drift_flags,
            },
        }

    mode = "manual_required_multiple_or_bad"
    if len(good_matches) == 0:
        mode = "manual_required_no_good_match"
    elif len(good_matches) > 1:
        mode = "manual_required_multiple_good_matches"

    return {
        "status": mode,
        "dataset_name": intake_dataset_name,
        "good_match_count": len(good_matches),
        "bad_match_count": len(bad_matches),
        "suggestions": suggestions,
        "why_not_auto_joined": (
            "Manual intervention required because there are multiple good matches or no reliable good match."
        ),
        "agent_updates": {
            "behavioral_updates": behavioral_updates,
            "drift_flags": drift_flags,
        },
    }
