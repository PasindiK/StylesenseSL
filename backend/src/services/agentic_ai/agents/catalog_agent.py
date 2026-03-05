"""
Catalog Agent - simple rule-based agent that queries the DataLoader.

This agent provides a small, testable surface that will later be called by
the orchestration agent or an API. Methods are deterministic and operate
on the CSV-backed DataLoader for now.
"""
import logging
from typing import List, Optional
import pandas as pd

from src.ingestion.data_loader import DataLoader
from src.utils.nl_parser import parse_intent
from src.utils.deduplication_service import get_deduplication_service
from src.services.agentic_ai.kg.client import Neo4jKGClient
from src.services.agentic_ai.kg.events import KGEventWriter

# Import Gemini query parser for enhanced query understanding
try:
    from src.clients.gemini_client import parse_query_with_gemini
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# Import Vector Search Agent
try:
    from src.services.agentic_ai.agents.vector_search_agent import VectorSearchAgent
    VECTOR_SEARCH_AVAILABLE = True
except ImportError:
    VECTOR_SEARCH_AVAILABLE = False

try:
    from rapidfuzz import process, fuzz
except Exception:
    process = None
    fuzz = None

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class CatalogAgent:
    def __init__(self, loader: DataLoader = None):
        self.loader = loader or DataLoader()
        # load default products into memory
        self.loader.load_products()
        self.kg_client = Neo4jKGClient()
        self.kg_events = KGEventWriter(self.kg_client)
        
        # Initialize vector search agent
        self.vector_search = None
        if VECTOR_SEARCH_AVAILABLE:
            try:
                print("[INFO] Initializing vector search agent...")
                self.vector_search = VectorSearchAgent(use_fashion_model=True)
                if self.vector_search.enabled and self.loader.products is not None:
                    print("[INFO] Indexing products for vector search...")
                    success = self.vector_search.index_products(self.loader.products)
                    if success:
                        print("[INFO] ✅ Vector search ready! Semantic search enabled.")
                    else:
                        print("[WARN] Vector search indexing failed, using fuzzy search fallback")
                        self.vector_search = None
                else:
                    print("[WARN] Vector search not available, using fuzzy search fallback")
                    self.vector_search = None
            except Exception as e:
                print(f"[WARN] Could not initialize vector search: {e}")
                self.vector_search = None
        else:
            print("[INFO] Vector search dependencies not installed. Using fuzzy search.")
            print("[INFO] To enable: pip install chromadb sentence-transformers")

    def find_by_filters(self, category: Optional[str] = None, color: Optional[str] = None,
                        max_price: Optional[float] = None, tag: Optional[str] = None, fabric: Optional[str] = None):
        """Return list of products matching simple filters."""
        df = self.loader.filter_products(category=category, color=color, max_price=max_price, tag=tag, fabric=fabric)
        results = df.to_dict(orient='records')
        # enrich with shop info if available
        for r in results:
            shop = self.loader.get_shop(r.get('shop_id'))
            if shop:
                r['_shop_name'] = shop.get('shop_name')
                r['_shop_location'] = shop.get('location')
            else:
                r['_shop_name'] = None
                r['_shop_location'] = None
        return results

    def get_product_by_id(self, product_id: str):
        """Return a single product dict by product_id or None."""
        if self.loader.products is None:
            self.loader.load_products()
        df = self.loader.products
        row = df[df['product_id'] == product_id]
        if row.empty:
            return None
        return row.iloc[0].to_dict()

    def get_shop_info(self, shop_name: Optional[str] = None, shop_id: Optional[int] = None):
        """Get information about a specific shop or all shops."""
        try:
            shops_df = self.loader.get_shops()
            if shops_df is None or shops_df.empty:
                return None
            
            if shop_id:
                result = shops_df[shops_df['shop_id'] == shop_id]
                if not result.empty:
                    return result.iloc[0].to_dict()
            elif shop_name:
                # Case-insensitive search
                shop_lower = shop_name.lower()
                result = shops_df[shops_df['shop_name'].str.lower().str.contains(shop_lower, na=False)]
                if not result.empty:
                    return result.iloc[0].to_dict()
            else:
                # Return all active shops
                return shops_df[shops_df['is_active'] == True].to_dict(orient='records')
            
            return None
        except Exception as e:
            log.error(f"Error fetching shop info: {e}")
            return None
    
    def get_shop_hours(self, shop_name: str):
        """Get opening hours for a specific shop."""
        shop_info = self.get_shop_info(shop_name=shop_name)
        if shop_info:
            return {
                "shop_name": shop_info.get('shop_name'),
                "location": shop_info.get('location'),
                "district": shop_info.get('district'),
                "opening_time": shop_info.get('operating_hours_open'),
                "closing_time": shop_info.get('operating_hours_close'),
                "is_active": shop_info.get('is_active'),
                "phone": shop_info.get('phone_number')
            }
        return None
    
    def search_by_text(self, q: str, limit: int = 8):
        """Simple text search across name, category, color and tags.
        Returns top matches limited to prevent overwhelming results.
        Default limit is 8 to provide focused recommendations.
        """
        if not q:
            return []
        ql = q.strip().lower()
        df = self.loader.products

        def matches(row):
            if ql in str(row.get('name', '')).lower():
                return True
            if ql in str(row.get('category', '')).lower():
                return True
            if ql in str(row.get('color', '')).lower():
                return True
            tags = row.get('style_tags') or []
            for t in tags:
                if ql in str(t).lower():
                    return True
            return False

        matched = df[df.apply(matches, axis=1)]
        # if no substring matches found, attempt fuzzy matching using rapidfuzz
        if matched.empty and process is not None:
            # fuzzy match against names
            names = df['name'].fillna('').astype(str).tolist()
            name_map = {n: i for i, n in enumerate(names)}
            try:
                name_hits = process.extract(q, names, scorer=fuzz.token_sort_ratio, limit=limit)
                chosen = set([h[0] for h in name_hits if h[1] >= 75])
                if chosen:
                    idxs = [name_map[n] for n in chosen]
                    matched = df.iloc[idxs]
            except Exception:
                pass
            # if still none, fuzzy match tags
            if matched.empty:
                # collect unique tags
                all_tags = set()
                for tags in df.get('normalized_style_tags', df.get('style_tags', [])):
                    for t in (tags or []):
                        all_tags.add(str(t))
                try:
                    tag_hits = process.extract(q, list(all_tags), scorer=fuzz.token_sort_ratio, limit=10)
                    tag_chosen = [h[0] for h in tag_hits if h[1] >= 75]
                    if tag_chosen:
                        matched = df[df['normalized_style_tags'].apply(lambda tags: any(tc.lower() in [t.lower() for t in (tags or [])] for tc in tag_chosen))]
                except Exception:
                    pass
        # sort by popularity_score if available
        if 'popularity_score' in matched.columns:
            try:
                matched = matched.assign(_p=matched['popularity_score'].astype(float))
                matched = matched.sort_values('_p', ascending=False).drop(columns=['_p'])
            except Exception:
                pass
        return matched.head(limit).to_dict(orient='records')

    def recommend_similar_by_tag(self, tag: str, top_n: int = 5):
        """Return top_n products that share the given style tag, ordered by popularity."""
        if not tag:
            return []
        df = self.loader.products
        tagl = tag.lower()
        matched = df[df['style_tags'].apply(lambda tags: tagl in [t.lower() for t in (tags or [])])]
        if 'popularity_score' in matched.columns:
            try:
                matched = matched.assign(_p=matched['popularity_score'].astype(float))
                matched = matched.sort_values('_p', ascending=False).drop(columns=['_p'])
            except Exception:
                pass
        return matched.head(top_n).to_dict(orient='records')

    def _fuzzy_lookup_choices(self, choices: List[str], query: str, threshold: int = 75) -> List[str]:
        """Return list of matching choice strings whose fuzzy score >= threshold."""
        if not choices or not query or process is None:
            return []
        try:
            hits = process.extract(query, choices, scorer=fuzz.token_sort_ratio, limit=10)
            return [h[0] for h in hits if h[1] >= threshold]
        except Exception:
            return []

    def find_with_fallback(self, category: Optional[str] = None, color: Optional[str] = None,
                           max_price: Optional[float] = None, tag: Optional[str] = None,
                           fabric: Optional[str] = None):
        """Attempt strict filters first, then apply fallbacks in order until results found.

        Fallback order:
        1) remove color
        2) expand price by +20%
        3) remove fabric
        4) relax category matching (substring/fuzzy)
        """
        applied = []
        # try strict
        res = self.find_by_filters(category=category, color=color, max_price=max_price, tag=tag, fabric=fabric)
        if res:
            return {"results": res, "fallbacks": applied}

        # 1. remove color
        if color:
            applied.append('remove_color')
            res = self.find_by_filters(category=category, color=None, max_price=max_price, tag=tag, fabric=fabric)
            if res:
                return {"results": res, "fallbacks": applied}

        # 2. expand price by 20%
        if max_price:
            applied.append('expand_price_20pct')
            try:
                new_price = float(max_price) * 1.2
            except Exception:
                new_price = max_price
            res = self.find_by_filters(category=category, color=None, max_price=new_price, tag=tag, fabric=fabric)
            if res:
                return {"results": res, "fallbacks": applied}

        # 3. remove fabric constraint
        if fabric:
            applied.append('remove_fabric')
            res = self.find_by_filters(category=category, color=None, max_price=new_price if max_price else None, tag=tag, fabric=None)
            if res:
                return {"results": res, "fallbacks": applied}

        # 4. relax category: try substring or fuzzy match against available categories
        if category:
            applied.append('relax_category')
            df = self.loader.products
            cats = list(df.get('normalized_category', df.get('category', pd.Series())).fillna('').unique())
            # try substring match
            candidates = [c for c in cats if category.lower() in str(c).lower()]
            if not candidates and process is not None:
                candidates = self._fuzzy_lookup_choices([str(c) for c in cats], category, threshold=70)
            for c in candidates:
                res = self.find_by_filters(category=c, color=None, max_price=new_price if max_price else None, tag=tag, fabric=None)
                if res:
                    return {"results": res, "fallbacks": applied}

        # nothing found
        return {"results": [], "fallbacks": applied}

    # --- helper methods connecting products and shops ---
    def get_products_by_shop(self, shop_id: str):
        """Return list of products for a given shop_id (enriched)."""
        results = self.find_by_filters()
        return [p for p in results if str(p.get('shop_id')) == str(shop_id)]

    def get_shop_by_product(self, product_id: str):
        """Return shop details for a given product id."""
        prod = self.get_product_by_id(str(product_id))
        if not prod:
            return None
        return self.loader.get_shop(prod.get('shop_id'))
    
    def get_shop_info(self, shop_name: Optional[str] = None, shop_id: Optional[int] = None):
        """Get information about a specific shop or all shops."""
        try:
            shops_df = self.loader.get_shops()
            if shops_df is None or shops_df.empty:
                return None
            
            if shop_id:
                result = shops_df[shops_df['shop_id'] == shop_id]
                if not result.empty:
                    return result.iloc[0].to_dict()
            elif shop_name:
                # Case-insensitive search
                shop_lower = shop_name.lower()
                result = shops_df[shops_df['shop_name'].str.lower().str.contains(shop_lower, na=False)]
                if not result.empty:
                    return result.iloc[0].to_dict()
            else:
                # Return all active shops
                return shops_df[shops_df['is_active'] == True].to_dict(orient='records')
            
            return None
        except Exception as e:
            log.error(f"Error fetching shop info: {e}")
            return None
    
    def get_shop_hours(self, shop_name: str):
        """Get opening hours for a specific shop."""
        shop_info = self.get_shop_info(shop_name=shop_name)
        if shop_info:
            return {
                "shop_name": shop_info.get('shop_name'),
                "location": shop_info.get('location'),
                "district": shop_info.get('district'),
                "opening_time": shop_info.get('operating_hours_open'),
                "closing_time": shop_info.get('operating_hours_close'),
                "is_active": shop_info.get('is_active'),
                "phone": shop_info.get('phone_number')
            }
        return None

    def answer_question(self, text: str, user_id=None, **kwargs):
        """Parse a natural language query and return results.

        This is a thin wrapper: parse intent -> map shop name to id -> call find_by_filters.
        Returns dict with keys: intent, results, shop (if found).
        
        Args:
            text: Natural language query
            user_id: Optional user ID for personalization and deduplication
            **kwargs: Additional arguments for future extensibility
        """
        q_lower = text.lower().strip()
        
        # Check for shop information queries FIRST
        shop_keywords = ['opening', 'closing', 'hours', 'open', 'close', 'location', 
                        'where', 'phone', 'contact', 'address', 'shop']
        
        if any(keyword in q_lower for keyword in shop_keywords):
            # Try to extract shop name
            shop_name = None
            try:
                shops_df = self.loader.get_shops()
                if shops_df is not None:
                    for _, shop in shops_df.iterrows():
                        if shop['shop_name'].lower() in q_lower:
                            shop_name = shop['shop_name']
                            break
            except Exception as e:
                log.error(f"Error loading shops: {e}")
            
            # Handle shop queries
            if shop_name or any(word in q_lower for word in ['all shops', 'list shops', 'show shops']):
                if shop_name:
                    hours = self.get_shop_hours(shop_name)
                    if hours:
                        # Build message with actual line breaks, not escaped \n
                        msg = f"📍 {hours['shop_name']}\n"
                        
                        # Only show what was asked for
                        if 'location' in q_lower or 'where' in q_lower or 'address' in q_lower:
                            msg += f"Location: {hours['location']}, {hours['district']}\n"
                        
                        if 'hour' in q_lower or 'open' in q_lower or 'close' in q_lower or 'time' in q_lower:
                            msg += f"Hours: {hours['opening_time']} - {hours['closing_time']}\n"
                            msg += f"Status: {'✅ Open' if hours['is_active'] else '❌ Closed'}\n"
                        
                        if 'phone' in q_lower or 'contact' in q_lower or 'number' in q_lower:
                            msg += f"Phone: {hours['phone']}\n"
                        
                        # If no specific aspect requested, show all
                        if not any(word in q_lower for word in ['location', 'where', 'address', 'hour', 'open', 'close', 'time', 'phone', 'contact', 'number']):
                            msg = f"📍 {hours['shop_name']}\n"
                            msg += f"Location: {hours['location']}, {hours['district']}\n"
                            msg += f"Hours: {hours['opening_time']} - {hours['closing_time']}\n"
                            msg += f"Phone: {hours['phone']}\n"
                            msg += f"Status: {'✅ Open' if hours['is_active'] else '❌ Closed'}"
                        
                        return {
                            'message': msg.strip(),
                            'reply': msg.strip(),
                            'results': [],
                            'filters': {},
                            'shop_info': hours,
                            'explainability': 'Shop information query',
                            'intent': 'shop_info'
                        }
                else:
                    # List all active shops
                    shops = self.get_shop_info()
                    if shops:
                        msg = "📍 Our Shop Locations:\n\n"
                        for shop in shops[:10]:  # Limit to 10
                            msg += f"• {shop['shop_name']} - {shop['location']} ({shop['operating_hours_open']}-{shop['operating_hours_close']})\n"
                        return {
                            'message': msg.strip(),
                            'reply': msg.strip(),
                            'results': [],
                            'filters': {},
                            'shops': shops,
                            'explainability': 'Shop listing query',
                            'intent': 'shop_info'
                        }
        
        # Ensure products are loaded
        try:
            if getattr(self.loader, 'products', None) is None:
                self.loader.load_products()
        except Exception:
            pass

        # Prepare known shops/categories from dataset
        try:
            known_shops = []
            if getattr(self.loader, 'shops', None) is not None:
                known_shops = [str(x) for x in self.loader.shops.get('shop_name', []).dropna().unique().tolist()]
            known_categories = []
            if getattr(self.loader, 'products', None) is not None:
                cats = self.loader.products.get('normalized_category', self.loader.products.get('category'))
                if cats is not None:
                    known_categories = [str(x) for x in cats.dropna().unique().tolist()]
        except Exception:
            known_shops = []
            known_categories = []

        # Parse intent with Gemini first (enhanced understanding), fallback to basic parser
        gemini_parsed = None
        if GEMINI_AVAILABLE:
            try:
                print(f"[DEBUG] Using Gemini to parse query: '{text}'")
                gemini_parsed = parse_query_with_gemini(text)
                print(f"[DEBUG] Gemini parsed: category={gemini_parsed.get('category')}, color={gemini_parsed.get('color')}, budget={gemini_parsed.get('budget')}")
            except Exception as e:
                print(f"[DEBUG] Gemini parsing failed: {e}, falling back to basic parser")
                gemini_parsed = None
        
        # Use basic parser and merge with Gemini results
        try:
            intent = parse_intent(text, known_shops=known_shops, known_categories=known_categories)
            
            # Enhance with Gemini parsed data (Gemini takes priority for ambiguous fields)
            if gemini_parsed:
                if gemini_parsed.get('category') and not intent.get('category'):
                    intent['category'] = gemini_parsed.get('category')
                if gemini_parsed.get('color') and not intent.get('color'):
                    intent['color'] = gemini_parsed.get('color')
                if gemini_parsed.get('budget') and not intent.get('max_price'):
                    intent['max_price'] = gemini_parsed.get('budget')
                if gemini_parsed.get('size'):
                    intent['size'] = gemini_parsed.get('size')
                if gemini_parsed.get('style_preferences'):
                    intent['style_preferences'] = gemini_parsed.get('style_preferences')
                    
            print(f"[DEBUG] Final merged intent: {intent}")
        except Exception as e:
            print(f"[DEBUG] Intent parsing failed: {e}")
            intent = {"tag": None, "max_price": None, "shop": None, "category": None, "color": None, "raw_text": text}

            # debug log parsed intent
            try:
                log.info(f"answer_question - parsed intent: {intent}")
            except Exception:
                pass

        shop_id = None
        shop_details = None
        if intent.get('shop'):
            # try to find a matching shop by name (case-insensitive substring)
            try:
                s = self.loader.shops
                # try exact/fuzzy first
                matched = s[s['shop_name'].str.lower() == str(intent['shop']).lower()]
                if matched.empty:
                    matched = s[s['shop_name'].str.contains(str(intent['shop']), case=False, na=False)]
                if not matched.empty:
                    shop_id = str(matched.iloc[0]['shop_id'])
                    shop_details = self.loader.get_shop(shop_id)
            except Exception:
                shop_id = None

        if user_id:
            self.kg_events.record_search(user_id=user_id, query=text, intent=intent)
            if intent.get("category"):
                self.kg_events.record_user_preference(user_id, "category", str(intent.get("category")), 0.5)
            if intent.get("color"):
                self.kg_events.record_user_preference(user_id, "color", str(intent.get("color")), 0.4)

        # Try vector search first if available (semantic understanding)
        if self.vector_search and self.vector_search.enabled:
            try:
                print(f"[DEBUG] Using vector search for: '{text}'")
                vector_results = self.vector_search.search(
                    query=text,
                    top_k=8,  # Get only top 8 relevant matches - no need for excess
                    category=intent.get('category'),
                    color=intent.get('color'),
                    max_price=intent.get('max_price')
                )
                
                if vector_results:
                    # Convert vector results to product dicts
                    results = []
                    for match in vector_results:
                        # Get product using the product_id from vector search
                        pid = str(match['product_id'])
                        df = self.loader.products
                        # Try both string and numeric comparison
                        row = df[df['product_id'].astype(str) == pid]
                        if row.empty:
                            # Try without string conversion
                            try:
                                row = df[df['product_id'] == int(pid) if pid.isdigit() else pid]
                            except:
                                pass
                        
                        if not row.empty:
                            product = row.iloc[0].to_dict()
                            product['_similarity_score'] = match['similarity_score']
                            product['_search_method'] = 'vector'
                            
                            # Add shop info
                            shop = self.loader.get_shop(product.get('shop_id'))
                            if shop:
                                product['_shop_name'] = shop.get('shop_name')
                                product['_shop_location'] = shop.get('location')
                            
                            results.append(product)
                    
                    # Filter by shop if specified
                    if shop_id:
                        results = [r for r in results if str(r.get('shop_id')) == shop_id]
                    
                    print(f"[DEBUG] Vector search returned {len(results)} products after conversion")
                    
                    # Apply deduplication if user_id provided
                    if user_id:
                        dedup_service = get_deduplication_service()
                        shown_product_ids = [str(p['product_id']) for p in results]
                        new_products = dedup_service.filter_new_products(user_id, shown_product_ids)
                        
                        if new_products:
                            # Return only new products
                            results = [p for p in results if str(p['product_id']) in new_products]
                            print(f"[DEBUG] After deduplication: {len(results)} new products (filtered {len(shown_product_ids) - len(new_products)} duplicates)")
                        
                        # Track all shown products (including duplicates)
                        dedup_service.track_shown(user_id, shown_product_ids)
                    
                    if results:
                        if user_id and results:
                            for product in results[:8]:
                                pid = str(product.get("product_id") or "")
                                if not pid:
                                    continue
                                self.kg_client.execute_write(
                                    """
                                    MERGE (u:User {user_id: toString($user_id)})
                                    MATCH (p:Product {product_id: toString($product_id)})
                                    MERGE (u)-[r:VIEWED]->(p)
                                    SET r.count = coalesce(r.count, 0) + 1,
                                        r.ts = datetime()
                                    """,
                                    {"user_id": user_id, "product_id": pid},
                                )
                        return {
                            "intent": intent,
                            "shop": shop_details,
                            "results": results[:8],  # Limit to top 8 focused recommendations
                            "fallbacks": [],
                            "search_method": "vector_search"
                        }
            except Exception as e:
                print(f"[WARN] Vector search failed: {e}, falling back to fuzzy search")
                import traceback
                traceback.print_exc()
        
        # Fallback to traditional filter search
        try:
            fallback_response = self.find_with_fallback(
                category=intent.get('category'),
                color=intent.get('color'),
                max_price=intent.get('max_price'),
                tag=intent.get('tag'),
                fabric=None,
            )
            results = fallback_response.get('results', []) if isinstance(fallback_response, dict) else []
            fallbacks = fallback_response.get('fallbacks', []) if isinstance(fallback_response, dict) else []
        except Exception:
            try:
                results = self.find_by_filters(
                    category=intent.get('category'),
                    color=intent.get('color'),
                    max_price=intent.get('max_price'),
                    tag=intent.get('tag'),
                )
            except Exception:
                results = []
            fallbacks = []

        # if shop_id known, filter results by shop
        if shop_id:
            results = [r for r in results if str(r.get('shop_id')) == shop_id]
        
        # Apply deduplication if user_id provided
        if user_id and results:
            dedup_service = get_deduplication_service()
            shown_product_ids = [str(p['product_id']) for p in results]
            new_products = dedup_service.filter_new_products(user_id, shown_product_ids)
            
            if new_products:
                # Return only new products
                results = [p for p in results if str(p['product_id']) in new_products]
                print(f"[DEBUG] After deduplication: {len(results)} new products (filtered {len(shown_product_ids) - len(new_products)} duplicates)")
            
            # Track all shown products
            dedup_service.track_shown(user_id, shown_product_ids)

        # debug log fallbacks applied and number of results
        try:
            log.info(f"answer_question - fallbacks: {fallbacks}, results_count: {len(results)}")
        except Exception:
            pass

        if user_id and results:
            for product in results[:8]:
                pid = str(product.get("product_id") or "")
                if not pid:
                    continue
                self.kg_client.execute_write(
                    """
                    MERGE (u:User {user_id: toString($user_id)})
                    MATCH (p:Product {product_id: toString($product_id)})
                    MERGE (u)-[r:VIEWED]->(p)
                    SET r.count = coalesce(r.count, 0) + 1,
                        r.ts = datetime()
                    """,
                    {"user_id": user_id, "product_id": pid},
                )

        return {"intent": intent, "shop": shop_details, "results": results[:8] or [], "fallbacks": fallbacks or [], "search_method": "fuzzy_search"}


if __name__ == '__main__':
    agent = CatalogAgent()
    print('Sample search for "denim":')
    print(agent.search_by_text('denim'))
    print('\nRecommend similar (tag=casual):')
    print(agent.recommend_similar_by_tag('casual', top_n=3))
