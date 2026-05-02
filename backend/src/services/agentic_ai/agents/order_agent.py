"""
Order Agent - Manages shopping cart from real-world product links.

This agent:
- Scrapes product details from e-commerce URLs
- Builds a virtual shopping cart
- Calculates totals and groups by shop
- Provides cart summary and instructions
"""
import logging
import json
import re
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, urljoin, parse_qsl, parse_qs, urlencode
import requests
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None
try:
    import extruct
except Exception:
    extruct = None
try:
    from w3lib.html import get_base_url
except Exception:
    get_base_url = None
from src.services.agentic_ai.kg.client import Neo4jKGClient
from src.services.agentic_ai.agents.robust_product_automation import RobustProductAutomation

logger = logging.getLogger(__name__)


class OrderAgent:
    """Virtual shopping cart manager for real-world product links."""
    
    def __init__(self, loader=None):
        self.cart_items: List[Dict[str, Any]] = []
        self.loader = loader  # Optional DataLoader for shop info lookup
        self.kg_client = Neo4jKGClient()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
        }
        self._fallback_user_agents = [
            self.headers['User-Agent'],
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        ]
        self.robust_scraper = RobustProductAutomation()
    
    def add_product(
        self,
        url: str,
        quantity: int = 1,
        size: Optional[str] = None,
        color: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add product from URL to cart.
        
        Args:
            url: Real-world product URL
            quantity: Number of items to add
            size: Optional selected size
            
        Returns:
            Product details and success status
        """
        try:
            logger.info(f"Fetching product from: {url}")
            product_info = self._scrape_product(url)
            
            if not product_info:
                return {
                    'success': False,
                    'error': 'Could not extract product information from URL',
                    'url': url
                }
            
            # Add to cart
            cart_item = {
                **product_info,
                'quantity': quantity,
                'url': url,
                'selected_size': size,
                'selected_color': color,
                'subtotal': product_info.get('price', 0) * quantity,
                'estimated_delivery': self._get_estimated_delivery(product_info.get('shop', 'Unknown'))
            }
            
            self.cart_items.append(cart_item)

            if user_id:
                self.kg_client.execute_write(
                    """
                    MERGE (u:User {user_id: toString($user_id)})
                    MATCH (p:Product {product_url: $product_url})
                    MERGE (u)-[r:ADDED_TO_CART]->(p)
                    SET r.count = coalesce(r.count, 0) + $quantity,
                        r.ts = datetime()
                    """,
                    {"user_id": user_id, "product_url": url, "quantity": int(quantity)},
                )
            
            return {
                'success': True,
                'product': cart_item,
                'cart_total_items': len(self.cart_items)
            }
            
        except Exception as e:
            logger.error(f"Error adding product: {e}")
            return {
                'success': False,
                'error': str(e),
                'url': url
            }
    
    def add_product_direct(
        self,
        product_data: Dict[str, Any],
        quantity: int = 1,
        size: Optional[str] = None,
        color: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add product directly from dataset (no web scraping needed).
        
        Args:
            product_data: Complete product information from dataset
            quantity: Number of items to add
            size: Optional selected size
            
        Returns:
            Product details and success status
        """
        try:
            logger.info(f"Adding product from dataset: {product_data.get('name', 'Unknown')}")
            
            # Look up shop info from loader if available
            shop_id = product_data.get('shop_id', '')
            shop_name = 'Unknown Shop'
            shop_domain = 'unknown.com'
            
            if self.loader and shop_id:
                try:
                    shop_info = self.loader.get_shop(shop_id)
                    if shop_info:
                        shop_name = shop_info.get('shop_name', shop_name)
                        shop_domain = shop_info.get('domain', shop_domain)
                except Exception as e:
                    logger.warning(f"Could not get shop info for {shop_id}: {e}")
            
            product_id = product_data.get('product_id', '')
            product_url = product_data.get('product_url', '')
            
            # Check if this exact item (same product, same size) already exists in cart
            for existing_item in self.cart_items:
                if (existing_item.get('product_id') == product_id and 
                    existing_item.get('selected_size') == size and
                    existing_item.get('selected_color') == color):
                    # Item already exists - just increase quantity
                    price = float(product_data.get('price_LKR', 0))
                    existing_item['quantity'] += quantity
                    existing_item['subtotal'] = existing_item['quantity'] * price
                    logger.info(f"Increased quantity of existing item to {existing_item['quantity']}")
                    return {
                        'success': True,
                        'product': existing_item,
                        'cart_total_items': len(self.cart_items),
                        'updated': True
                    }
            
            # Item doesn't exist - add new item
            # Normalize product data from CSV
            price = float(product_data.get('price_LKR', 0))
            cart_item = {
                'product_id': product_id,
                'name': product_data.get('name', 'Unknown Product'),
                'category': product_data.get('category', product_data.get('normalized_category', '')),
                'color': product_data.get('color', ''),
                'price_LKR': price,
                'price': price,  # Alias for compatibility
                'currency': 'LKR',
                'shop_id': shop_id,
                'shop': shop_name,  # Required for cart summary
                'domain': shop_domain,  # Required for cart summary
                'fabric': product_data.get('fabric', ''),
                'size_range': product_data.get('size_range', ''),
                'selected_size': size,  # User-selected size
                'selected_color': color,  # User-selected color
                'style_tags': product_data.get('style_tags', ''),
                'product_url': product_url,
                'quantity': quantity,
                'url': product_url,
                'subtotal': price * quantity,
                'estimated_delivery': self._get_estimated_delivery(shop_name)  # Add estimated delivery
            }
            
            self.cart_items.append(cart_item)

            if user_id:
                self.kg_client.execute_write(
                    """
                    MERGE (u:User {user_id: toString($user_id)})
                    MATCH (p:Product {product_id: toString($product_id)})
                    MERGE (u)-[r:ADDED_TO_CART]->(p)
                    SET r.count = coalesce(r.count, 0) + $quantity,
                        r.ts = datetime()
                    """,
                    {
                        "user_id": user_id,
                        "product_id": str(product_id),
                        "quantity": int(quantity),
                    },
                )
            
            return {
                'success': True,
                'product': cart_item,
                'cart_total_items': len(self.cart_items)
            }
            
        except Exception as e:
            logger.error(f"Error adding product directly: {e}")
            return {
                'success': False,
                'error': str(e),
                'product_data': product_data
            }
    
    def _scrape_product(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape product details from URL using ordered extractors.

        Extraction order:
        1) Shopify product JSON endpoint (`/products/<handle>.js`) when URL matches.
        2) JSON-LD Product schema using extruct.
        3) BeautifulSoup selector fallback with junk-text filtering.
        4) Optional Playwright-rendered HTML retry for JS-heavy pages.
        """
        try:
            domain = urlparse(url).netloc.lower()
            shop_name = self._extract_shop_name(domain)

            # Primary path: robust Playwright-first scraping engine.
            try:
                robust_result = self.robust_scraper.scrape_product(url)
                if isinstance(robust_result, dict) and (robust_result.get('name') or robust_result.get('title')):
                    # Keep legacy fields and inferred action links aligned.
                    robust_result.setdefault('shop', shop_name)
                    robust_result.setdefault('seller', shop_name)
                    robust_result.setdefault('shipping_fee', None)
                    robust_result.setdefault('shipping_availability', 'Unknown')
                    robust_result.setdefault('stock_count', None)
                    robust_result.setdefault('shop_location', 'Online Shop')
                    robust_result.setdefault('shop_hours', '24/7 Online (Check seller page)')
                    if BeautifulSoup is not None:
                        html_for_links = self._fetch_page_html_with_playwright(url) or self._fetch_page_html(url)
                        if html_for_links:
                            soup_for_links = BeautifulSoup(html_for_links, 'html.parser')
                            robust_result.update(self._extract_action_links(soup_for_links, url))
                            robust_result['shipping_availability'] = self._extract_shipping_availability(soup_for_links)
                            extracted_fee = self._extract_shipping_fee(soup_for_links, str(robust_result.get('currency') or 'LKR'))
                            if extracted_fee is not None:
                                robust_result['shipping_fee'] = extracted_fee

                    # If product page lacks shipping details, try checkout page best-effort extraction.
                    if (
                        str(robust_result.get('shipping_availability') or '').strip().lower() in {'', 'unknown'}
                        and robust_result.get('checkout_url')
                    ):
                        checkout_shipping = self._extract_shipping_from_checkout_url(
                            str(robust_result.get('checkout_url')),
                            str(robust_result.get('currency') or 'LKR'),
                        )
                        robust_result['shipping_availability'] = checkout_shipping.get('shipping_availability') or 'Unknown'
                        if checkout_shipping.get('shipping_fee') is not None:
                            robust_result['shipping_fee'] = checkout_shipping.get('shipping_fee')
                    robust_result = self._enrich_shopify_cart_links(url, robust_result)
                    robust_result = self._apply_ordered_size_extraction(url, robust_result, html_for_sizes=html_for_links)
                    return self._enrich_product_variants_with_rendered_html(url, robust_result)
            except Exception as robust_err:
                logger.warning(f"Robust scraper failed for {url}: {robust_err}. Falling back to legacy extractors.")

            shopify_product = self._extract_shopify_product(url, shop_name, domain)
            if shopify_product:
                return self._apply_ordered_size_extraction(url, shopify_product)

            html = self._fetch_page_html(url)
            if not html:
                html = self._fetch_page_html_with_playwright(url)
            if not html:
                return None

            soup = BeautifulSoup(html, 'html.parser') if BeautifulSoup is not None else None

            jsonld_product = self._extract_jsonld_product(html, url, shop_name, domain)
            if jsonld_product:
                if soup is not None:
                    jsonld_product.update(self._extract_action_links(soup, url))
                    jsonld_product['shipping_availability'] = self._extract_shipping_availability(soup)
                    extracted_fee = self._extract_shipping_fee(soup, str(jsonld_product.get('currency') or 'LKR'))
                    if extracted_fee is not None:
                        jsonld_product['shipping_fee'] = extracted_fee

                    # Prefer truly available options from rendered page controls.
                    rendered_sizes = self._filter_junk_values(self._extract_available_sizes(soup))
                    rendered_colors = self._filter_junk_values(self._extract_available_colors(soup))
                    if rendered_sizes:
                        jsonld_product['available_sizes'] = rendered_sizes
                    if rendered_colors:
                        jsonld_product['available_colors'] = rendered_colors
                    jsonld_product['variants'] = {
                        'sizes': jsonld_product.get('available_sizes') or [],
                        'colors': jsonld_product.get('available_colors') or [],
                    }

                if (
                    str(jsonld_product.get('shipping_availability') or '').strip().lower() in {'', 'unknown'}
                    and jsonld_product.get('checkout_url')
                ):
                    checkout_shipping = self._extract_shipping_from_checkout_url(
                        str(jsonld_product.get('checkout_url')),
                        str(jsonld_product.get('currency') or 'LKR'),
                    )
                    jsonld_product['shipping_availability'] = checkout_shipping.get('shipping_availability') or 'Unknown'
                    if checkout_shipping.get('shipping_fee') is not None:
                        jsonld_product['shipping_fee'] = checkout_shipping.get('shipping_fee')
                jsonld_product = self._enrich_shopify_cart_links(url, jsonld_product)
                jsonld_product['variants'] = {
                    'sizes': jsonld_product.get('available_sizes') or [],
                    'colors': jsonld_product.get('available_colors') or [],
                }
                jsonld_product = self._apply_ordered_size_extraction(url, jsonld_product, html_for_sizes=html, soup_for_sizes=soup)
                return self._enrich_product_variants_with_rendered_html(url, jsonld_product)

            if soup is None:
                logger.warning("BeautifulSoup not installed. Selector fallback unavailable for URL scraping.")
                return None

            soup_product = self._extract_soup_fallback_product(soup, url, shop_name, domain)
            soup_product = self._enrich_shopify_cart_links(url, soup_product)
            soup_product = self._apply_ordered_size_extraction(url, soup_product, html_for_sizes=html, soup_for_sizes=soup)
            return self._enrich_product_variants_with_rendered_html(url, soup_product)

        except requests.RequestException as e:
            logger.error(f"Network error fetching {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing product from {url}: {e}")
            return None

    def _extract_shopify_product(self, url: str, shop_name: str, domain: str) -> Optional[Dict[str, Any]]:
        """Try Shopify product JSON endpoint first when URL matches Shopify product path."""
        if not re.search(r"/products/[^/?#]+", url, flags=re.I):
            return None

        parsed = urlparse(url)
        handle_match = re.search(r"/products/([^/?#.]+)", parsed.path, flags=re.I)
        if not handle_match:
            return None

        handle = handle_match.group(1)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        json_url = f"{base_url}/products/{handle}.js"

        try:
            response = requests.get(json_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None

        variants = payload.get('variants') or []
        options = payload.get('options') or []
        available_variants = [v for v in variants if isinstance(v, dict) and bool(v.get('available', True))]
        candidate_variant = available_variants[0] if available_variants else (variants[0] if variants else {})

        size_values: List[str] = []
        color_values: List[str] = []

        for option in options:
            if not isinstance(option, dict):
                continue
            name = str(option.get('name') or '').strip().lower()
            values = [str(v).strip() for v in (option.get('values') or []) if str(v).strip()]
            if 'size' in name:
                size_values.extend(values)
            if 'color' in name or 'colour' in name:
                color_values.extend(values)

        option_name_by_index: Dict[int, str] = {}
        for idx, option in enumerate(options, start=1):
            if isinstance(option, dict):
                option_name_by_index[idx] = str(option.get('name') or '').strip().lower()

        variants_for_options = available_variants if available_variants else variants
        for variant in variants_for_options:
            if not isinstance(variant, dict):
                continue
            for idx, key in enumerate(['option1', 'option2', 'option3'], start=1):
                value = str(variant.get(key) or '').strip()
                if not value:
                    continue

                option_name = option_name_by_index.get(idx, '')
                if 'size' in option_name or self._looks_like_size(value):
                    size_values.append(value)
                if (
                    'color' in option_name
                    or 'colour' in option_name
                    or re.search(r'\b(red|blue|green|black|white|pink|yellow|brown|gray|grey|orange|purple|gold|silver)\b', value, flags=re.I)
                ):
                    color_values.append(value)

        deduped_sizes = self._filter_junk_values(self._dedupe_preserve_case(size_values))
        deduped_colors = self._filter_junk_values(self._dedupe_preserve_case(color_values))

        raw_price = candidate_variant.get('price') or payload.get('price')
        price = self._safe_float(raw_price)
        # Shopify .js commonly returns price in minor units (e.g., cents) as int or digit string.
        raw_price_str = str(raw_price or '').strip()
        if isinstance(raw_price, int) and raw_price > 100000:
            price = float(raw_price) / 100.0
        elif raw_price_str.isdigit() and '.' not in raw_price_str and int(raw_price_str) > 100000:
            price = float(raw_price_str) / 100.0

        if not deduped_colors:
            # Some products are fixed-color and expose only size variants. Infer a single color
            # from product title/body text when an explicit color option is absent.
            text_blob = ' '.join(
                [
                    str(payload.get('title') or ''),
                    str(payload.get('body_html') or ''),
                ]
            )
            color_tokens = re.findall(
                r'\b(red|blue|green|black|white|pink|yellow|brown|gray|grey|orange|purple|gold|silver|beige|navy)\b',
                text_blob,
                flags=re.I,
            )
            if color_tokens:
                deduped_colors = self._filter_junk_values(self._dedupe_preserve_case([token.title() for token in color_tokens]))

        image_value = payload.get('image')
        image_url = None
        if isinstance(image_value, dict):
            image_url = image_value.get('src')
        elif isinstance(image_value, str):
            image_url = image_value
        if not image_url:
            images = payload.get('images') or []
            if isinstance(images, list) and images:
                image_url = str(images[0])

        stock_count = 0
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            qty = variant.get('inventory_quantity')
            if isinstance(qty, int) and qty > 0:
                stock_count += qty

        availability = 'In Stock' if available_variants else 'Out of Stock'
        selected_variant_id = candidate_variant.get('id') if isinstance(candidate_variant, dict) else None
        add_to_cart_url = f"{base_url}/cart/add?id={selected_variant_id}" if selected_variant_id else None

        html_hint = ''
        currency = str(payload.get('currency') or '').strip().upper()
        if not currency:
            currency = self._default_currency_for_domain(domain)

            # Try to infer currency from storefront HTML when Shopify JSON omits it.
            # This keeps price display consistent for stores priced in LKR on .com domains.
            try:
                html_hint = self._fetch_page_html(url) or ''
            except Exception:
                html_hint = ''

        if not html_hint:
            try:
                html_hint = self._fetch_page_html(url) or ''
            except Exception:
                html_hint = ''

            if re.search(r'\bLKR\b|\bRs\.?\b|\brupees\b', html_hint, flags=re.I):
                currency = 'LKR'
            elif re.search(r'\bUSD\b|\bdollars?\b', html_hint, flags=re.I):
                currency = 'USD'

            # Practical fallback: apparel prices in the thousands are usually local currency,
            # not USD, when no explicit currency code is available.
            if currency == 'USD' and price >= 1000:
                currency = 'LKR'

        shipping_availability = 'Unknown'
        shipping_fee: Optional[float] = None
        if BeautifulSoup is not None:
            try:
                soup_hint = BeautifulSoup(html_hint, 'html.parser') if html_hint else None
                if soup_hint is not None:
                    shipping_availability = self._extract_shipping_availability(soup_hint)
                    shipping_fee = self._extract_shipping_fee(soup_hint, currency)
            except Exception:
                pass

        if shipping_availability.lower() == 'unknown':
            checkout_probe = self._extract_shipping_from_checkout_url(f"{base_url}/checkout", currency)
            shipping_availability = checkout_probe.get('shipping_availability') or shipping_availability
            if shipping_fee is None:
                shipping_fee = checkout_probe.get('shipping_fee')

        return {
            'shop': shop_name,
            'seller': str(payload.get('vendor') or shop_name),
            'domain': domain,
            'name': str(payload.get('title') or 'Unknown Product').strip(),
            'title': str(payload.get('title') or 'Unknown Product').strip(),
            'price': price,
            'currency': currency,
            'image': image_url,
            'availability': availability,
            'shipping_availability': shipping_availability,
            'shipping_fee': shipping_fee,
            'description': self._clean_candidate_text(str(payload.get('body_html') or '')),
            'available_sizes': deduped_sizes,
            'available_colors': deduped_colors,
            'stock_count': stock_count if stock_count > 0 else None,
            'shop_location': 'Online Shop',
            'shop_hours': '24/7 Online (Check seller page)',
            'add_to_cart_url': add_to_cart_url,
            'buy_now_url': f"{base_url}/checkout",
            'checkout_url': f"{base_url}/checkout",
            'url': f"{base_url}/products/{handle}",
            'variants': {
                'sizes': deduped_sizes,
                'colors': deduped_colors,
                'shopify_variant_map': self._build_shopify_variant_map(options, variants),
            },
        }

    def _build_shopify_variant_map(self, options: List[Dict[str, Any]], variants: List[Dict[str, Any]]) -> Dict[str, int]:
        """Build a normalized option-combination -> variant id map for Shopify products."""
        option_name_by_index: Dict[int, str] = {}
        for idx, option in enumerate(options, start=1):
            if isinstance(option, dict):
                option_name_by_index[idx] = str(option.get('name') or '').strip().lower()

        def normalize_token(value: Any) -> str:
            return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())

        variant_map: Dict[str, int] = {}
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            variant_id = variant.get('id')
            if not isinstance(variant_id, int):
                continue

            parts: List[str] = []
            for idx, key in enumerate(['option1', 'option2', 'option3'], start=1):
                raw = str(variant.get(key) or '').strip()
                if not raw:
                    continue
                option_name = option_name_by_index.get(idx, f'option{idx}')
                normalized_value = normalize_token(raw)
                if not normalized_value:
                    continue
                parts.append(f'{option_name}:{normalized_value}')

            if parts:
                variant_map['|'.join(parts)] = variant_id

        return variant_map

    def _enrich_shopify_cart_links(self, url: str, product: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure Shopify products always include a deterministic add-to-cart URL and variant map."""
        if not isinstance(product, dict):
            return product
        if not re.search(r"/products/[^/?#]+", str(url), flags=re.I):
            return product

        parsed = urlparse(url)
        handle_match = re.search(r"/products/([^/?#.]+)", parsed.path, flags=re.I)
        if not handle_match:
            return product

        handle = handle_match.group(1)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        json_url = f"{base_url}/products/{handle}.js"

        try:
            response = requests.get(json_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return product

        variants = payload.get('variants') or []
        options = payload.get('options') or []
        available_variants = [v for v in variants if isinstance(v, dict) and bool(v.get('available', True))]
        candidate_variant = available_variants[0] if available_variants else (variants[0] if variants else None)
        candidate_variant_id = candidate_variant.get('id') if isinstance(candidate_variant, dict) else None

        variant_map = self._build_shopify_variant_map(
            [opt for opt in options if isinstance(opt, dict)],
            [v for v in variants if isinstance(v, dict)],
        )

        existing_variants = product.get('variants') if isinstance(product.get('variants'), dict) else {}
        product['variants'] = {
            **existing_variants,
            'shopify_variant_map': variant_map,
        }

        if isinstance(candidate_variant_id, int):
            product['add_to_cart_url'] = f"{base_url}/cart/{candidate_variant_id}:1"

        product.setdefault('checkout_url', f"{base_url}/checkout")
        product.setdefault('buy_now_url', f"{base_url}/checkout")
        return product

    def _extract_jsonld_product(self, html: str, url: str, shop_name: str, domain: str) -> Optional[Dict[str, Any]]:
        """Try JSON-LD Product extraction using extruct first, then script fallback."""
        product_node: Optional[Dict[str, Any]] = None

        if extruct is not None and get_base_url is not None:
            try:
                metadata = extruct.extract(html, base_url=get_base_url(html, url), syntaxes=['json-ld'], uniform=True)
                candidates = metadata.get('json-ld') or []
                product_node = self._find_product_node(candidates)
            except Exception:
                product_node = None

        if product_node is None and BeautifulSoup is not None:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                for script in soup.find_all('script', {'type': re.compile(r'application/ld\+json', re.I)}):
                    raw = script.string or script.get_text(' ', strip=True)
                    if not raw:
                        continue
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        continue
                    product_node = self._find_product_node(parsed)
                    if product_node is not None:
                        break
            except Exception:
                product_node = None

        if not isinstance(product_node, dict):
            return None

        offers = product_node.get('offers')
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if not isinstance(offers, dict):
            offers = {}

        name = self._clean_candidate_text(str(product_node.get('name') or ''))
        if not name:
            return None

        price = self._safe_float(offers.get('price'))
        currency = str(offers.get('priceCurrency') or self._default_currency_for_domain(domain)).upper()

        raw_availability = str(offers.get('availability') or '').lower()
        availability = 'Unknown'
        if 'instock' in raw_availability:
            availability = 'In Stock'
        elif 'outofstock' in raw_availability:
            availability = 'Out of Stock'

        image = product_node.get('image')
        image_url = None
        if isinstance(image, list) and image:
            image_url = str(image[0])
        elif isinstance(image, dict):
            image_url = str(image.get('url') or '')
        elif isinstance(image, str):
            image_url = image

        seller = shop_name
        brand = product_node.get('brand')
        if isinstance(brand, dict) and brand.get('name'):
            seller = str(brand.get('name'))
        elif isinstance(offers.get('seller'), dict) and offers.get('seller', {}).get('name'):
            seller = str(offers.get('seller', {}).get('name'))

        size_values: List[str] = []
        color_values: List[str] = []
        additional_props = product_node.get('additionalProperty') or []
        if isinstance(additional_props, dict):
            additional_props = [additional_props]
        for prop in additional_props:
            if not isinstance(prop, dict):
                continue
            prop_name = str(prop.get('name') or '').lower()
            prop_value = str(prop.get('value') or '').strip()
            if not prop_value:
                continue
            if 'size' in prop_name:
                size_values.extend([v.strip() for v in re.split(r'[,/|]', prop_value) if v.strip()])
            if 'color' in prop_name or 'colour' in prop_name:
                color_values.extend([v.strip() for v in re.split(r'[,/|]', prop_value) if v.strip()])

        raw_color = str(product_node.get('color') or '').strip()
        if raw_color:
            color_values.extend([v.strip() for v in re.split(r'[,/|]', raw_color) if v.strip()])

        raw_size = product_node.get('size')
        if isinstance(raw_size, list):
            for item in raw_size:
                size_values.extend([v.strip() for v in re.split(r'[,/|]', str(item)) if v.strip()])
        elif raw_size is not None:
            size_values.extend([v.strip() for v in re.split(r'[,/|]', str(raw_size)) if v.strip()])

        deduped_sizes = self._filter_junk_values(self._dedupe_preserve_case(size_values))
        deduped_colors = self._filter_junk_values(self._dedupe_preserve_case(color_values))

        return {
            'shop': shop_name,
            'seller': seller,
            'domain': domain,
            'name': name,
            'title': name,
            'price': price,
            'currency': currency,
            'image': image_url,
            'availability': availability,
            'shipping_availability': 'Unknown',
            'shipping_fee': None,
            'description': self._clean_candidate_text(str(product_node.get('description') or '')),
            'available_sizes': deduped_sizes,
            'available_colors': deduped_colors,
            'stock_count': None,
            'shop_location': 'Online Shop',
            'shop_hours': '24/7 Online (Check seller page)',
            'add_to_cart_url': None,
            'buy_now_url': offers.get('url') or product_node.get('url'),
            'checkout_url': offers.get('url') or product_node.get('url'),
            'url': str(product_node.get('url') or url),
            'variants': {
                'sizes': deduped_sizes,
                'colors': deduped_colors,
            },
        }

    def _extract_soup_fallback_product(self, soup: BeautifulSoup, url: str, shop_name: str, domain: str) -> Dict[str, Any]:
        """BeautifulSoup fallback extraction with junk text filtering."""
        name = self._clean_candidate_text(self._extract_name(soup, domain))
        if not name:
            name = 'Unknown Product'

        description = self._clean_candidate_text(self._extract_description(soup))
        sizes = self._filter_junk_values(self._extract_available_sizes(soup))
        colors = self._filter_junk_values(self._extract_available_colors(soup))

        currency = self._extract_currency(soup, domain)
        product = {
            'shop': shop_name,
            'seller': shop_name,
            'domain': domain,
            'name': name,
            'title': name,
            'price': self._extract_price(soup, domain),
            'currency': currency,
            'image': self._extract_image(soup, domain),
            'availability': self._extract_availability(soup),
            'shipping_availability': self._extract_shipping_availability(soup),
            'shipping_fee': self._extract_shipping_fee(soup, currency),
            'description': description,
            'available_sizes': sizes,
            'available_colors': colors,
            'stock_count': self._extract_stock_count(soup),
            'shop_location': self._extract_shop_location(soup, domain),
            'shop_hours': self._extract_shop_hours(soup),
        }

        product.update(self._extract_action_links(soup, url))
        product['variants'] = {
            'sizes': sizes,
            'colors': colors,
        }
        return product

    def _apply_ordered_size_extraction(
        self,
        url: str,
        product: Optional[Dict[str, Any]],
        html_for_sizes: Optional[str] = None,
        soup_for_sizes: Optional[BeautifulSoup] = None,
    ) -> Optional[Dict[str, Any]]:
        """Ensure available sizes are extracted using a stable fallback order.

        Order:
        1) JSON product API
        2) JSON-LD
        3) HTML selectors (including rendered fallback)
        """
        if not isinstance(product, dict):
            return product

        sizes = self._extract_available_sizes_ordered(url, html_for_sizes=html_for_sizes, soup_for_sizes=soup_for_sizes)
        colors = self._extract_available_colors_ordered(url, html_for_colors=html_for_sizes, soup_for_colors=soup_for_sizes)

        if sizes:
            product['available_sizes'] = sizes
        if colors:
            product['available_colors'] = colors

        if not sizes and not colors:
            return product

        variants = product.get('variants') if isinstance(product.get('variants'), dict) else {}
        product['variants'] = {
            'sizes': sizes or variants.get('sizes') or product.get('available_sizes') or [],
            'colors': colors or variants.get('colors') or product.get('available_colors') or [],
            **({k: v for k, v in variants.items() if k not in {'sizes', 'colors'}} if isinstance(variants, dict) else {}),
        }
        return product

    def _extract_available_sizes_ordered(
        self,
        url: str,
        html_for_sizes: Optional[str] = None,
        soup_for_sizes: Optional[BeautifulSoup] = None,
    ) -> List[str]:
        """Extract available sizes by trying data sources in strict order."""
        # 1) Product JSON API (best for availability-aware variants)
        api_sizes = self._extract_available_sizes_from_shopify_api(url)
        if api_sizes:
            return api_sizes

        html = html_for_sizes
        if not html:
            html = self._fetch_page_html(url)

        # 2) Structured data (JSON-LD)
        jsonld_sizes = self._extract_available_sizes_from_jsonld(url, html)
        if jsonld_sizes:
            return jsonld_sizes

        # 3) HTML selector extraction (with disabled/sold-out filtering)
        soup = soup_for_sizes
        if soup is None and html and BeautifulSoup is not None:
            try:
                soup = BeautifulSoup(html, 'html.parser')
            except Exception:
                soup = None

        if soup is not None:
            html_sizes = self._dedupe_size_tokens(self._extract_available_sizes(soup))
            if html_sizes:
                return html_sizes

        rendered_html = self._fetch_page_html_with_playwright(url)
        if rendered_html and BeautifulSoup is not None:
            try:
                rendered_soup = BeautifulSoup(rendered_html, 'html.parser')
                rendered_sizes = self._dedupe_size_tokens(self._extract_available_sizes(rendered_soup))
                if rendered_sizes:
                    return rendered_sizes
            except Exception:
                return []

        return []

    def _extract_available_sizes_from_shopify_api(self, url: str) -> List[str]:
        """Extract only available sizes from Shopify product JSON API."""
        if not re.search(r"/products/[^/?#]+", url, flags=re.I):
            return []

        parsed = urlparse(url)
        handle_match = re.search(r"/products/([^/?#.]+)", parsed.path, flags=re.I)
        if not handle_match:
            return []

        handle = handle_match.group(1)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        json_url = f"{base_url}/products/{handle}.js"

        try:
            response = requests.get(json_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        variants = payload.get('variants') or []
        options = payload.get('options') or []
        available_variants = [v for v in variants if isinstance(v, dict) and bool(v.get('available', False))]
        if not available_variants:
            return []

        option_name_by_index: Dict[int, str] = {}
        for idx, option in enumerate(options, start=1):
            if isinstance(option, dict):
                option_name_by_index[idx] = str(option.get('name') or '').strip().lower()

        size_values: List[str] = []
        for variant in available_variants:
            if not isinstance(variant, dict):
                continue
            for idx, key in enumerate(['option1', 'option2', 'option3'], start=1):
                raw = str(variant.get(key) or '').strip()
                if not raw:
                    continue
                option_name = option_name_by_index.get(idx, '')
                if 'size' in option_name or self._looks_like_size(raw):
                    if not self._is_invalid_size_label(raw):
                        size_values.append(self._normalize_size_token(raw))

        return self._dedupe_size_tokens(size_values)

    def _extract_available_sizes_from_jsonld(self, url: str, html: Optional[str]) -> List[str]:
        """Extract available sizes from JSON-LD Product data."""
        if not html:
            return []

        domain = urlparse(url).netloc.lower()
        shop_name = self._extract_shop_name(domain)
        product = self._extract_jsonld_product(html, url, shop_name, domain)
        if not isinstance(product, dict):
            return []

        raw_sizes = product.get('available_sizes') or []
        cleaned = [self._normalize_size_token(str(size)) for size in raw_sizes if not self._is_invalid_size_label(str(size))]
        return self._dedupe_size_tokens(cleaned)

    def _extract_available_colors_ordered(
        self,
        url: str,
        html_for_colors: Optional[str] = None,
        soup_for_colors: Optional[BeautifulSoup] = None,
    ) -> List[str]:
        """Extract available colors by trying data sources in strict order."""
        api_colors = self._extract_available_colors_from_shopify_api(url)
        if api_colors:
            return api_colors

        html = html_for_colors
        if not html:
            html = self._fetch_page_html(url)

        jsonld_colors = self._extract_available_colors_from_jsonld(url, html)
        if jsonld_colors:
            return jsonld_colors

        soup = soup_for_colors
        if soup is None and html and BeautifulSoup is not None:
            try:
                soup = BeautifulSoup(html, 'html.parser')
            except Exception:
                soup = None

        if soup is not None:
            html_colors = self._dedupe_preserve_case(self._extract_available_colors(soup))
            if html_colors:
                return html_colors

        rendered_html = self._fetch_page_html_with_playwright(url)
        if rendered_html and BeautifulSoup is not None:
            try:
                rendered_soup = BeautifulSoup(rendered_html, 'html.parser')
                rendered_colors = self._dedupe_preserve_case(self._extract_available_colors(rendered_soup))
                if rendered_colors:
                    return rendered_colors
            except Exception:
                return []

        return []

    def _extract_available_colors_from_shopify_api(self, url: str) -> List[str]:
        """Extract only available colors from Shopify product JSON API."""
        if not re.search(r"/products/[^/?#]+", url, flags=re.I):
            return []

        parsed = urlparse(url)
        handle_match = re.search(r"/products/([^/?#.]+)", parsed.path, flags=re.I)
        if not handle_match:
            return []

        handle = handle_match.group(1)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        json_url = f"{base_url}/products/{handle}.js"

        try:
            response = requests.get(json_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        variants = payload.get('variants') or []
        options = payload.get('options') or []
        available_variants = [v for v in variants if isinstance(v, dict) and bool(v.get('available', False))]
        if not available_variants:
            return []

        option_name_by_index: Dict[int, str] = {}
        for idx, option in enumerate(options, start=1):
            if isinstance(option, dict):
                option_name_by_index[idx] = str(option.get('name') or '').strip().lower()

        color_values: List[str] = []
        for variant in available_variants:
            if not isinstance(variant, dict):
                continue
            for idx, key in enumerate(['option1', 'option2', 'option3'], start=1):
                raw = str(variant.get(key) or '').strip()
                if not raw:
                    continue
                option_name = option_name_by_index.get(idx, '')
                if 'color' in option_name or 'colour' in option_name or self._looks_like_color(raw):
                    if not self._is_invalid_color_label(raw):
                        color_values.append(raw)

        return self._dedupe_preserve_case(color_values)

    def _extract_available_colors_from_jsonld(self, url: str, html: Optional[str]) -> List[str]:
        """Extract available colors from JSON-LD Product data."""
        if not html:
            return []

        domain = urlparse(url).netloc.lower()
        shop_name = self._extract_shop_name(domain)
        product = self._extract_jsonld_product(html, url, shop_name, domain)
        if not isinstance(product, dict):
            return []

        raw_colors = product.get('available_colors') or []
        cleaned = [str(color).strip() for color in raw_colors if not self._is_invalid_color_label(str(color))]
        return self._dedupe_preserve_case(cleaned)

    def _extract_shipping_fee(self, soup: BeautifulSoup, currency: str) -> Optional[float]:
        """Best-effort shipping fee extraction from shipping/delivery blocks."""
        selectors = [
            '.shipping',
            '.delivery',
            '[class*="shipping"]',
            '[class*="delivery"]',
            '[data-shipping]',
            '[data-delivery]',
        ]
        snippets: List[str] = []
        for selector in selectors:
            for elem in soup.select(selector):
                txt = elem.get_text(' ', strip=True)
                if txt:
                    snippets.append(txt)

        haystack = ' '.join(snippets)
        if not haystack:
            return None
        if re.search(r'free\s+shipping|shipping\s+free', haystack, flags=re.I):
            return 0.0

        money_patterns = [
            r'(?:LKR|Rs\.?|රු)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
            r'([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:LKR|Rs\.?|රු)',
            r'\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
            r'€\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
            r'£\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
        ]

        for pattern in money_patterns:
            match = re.search(pattern, haystack, flags=re.I)
            if not match:
                continue
            try:
                amount = float(match.group(1).replace(',', ''))
            except Exception:
                continue

            if amount < 0:
                continue
            return amount

        return None

    def _fetch_page_html_with_playwright(self, url: str) -> Optional[str]:
        """Optional JS-render fallback for heavily dynamic product pages."""
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=45000)
                page.wait_for_timeout(1200)
                html = page.content()
                context.close()
                browser.close()
                return html
        except Exception:
            return None

    def _find_product_node(self, node: Any) -> Optional[Dict[str, Any]]:
        """Recursively find schema.org Product node in JSON-LD payload."""
        if isinstance(node, dict):
            node_type = node.get('@type')
            if isinstance(node_type, list):
                types = [str(t).lower() for t in node_type]
            else:
                types = [str(node_type).lower()] if node_type else []
            if 'product' in types:
                return node
            for key in ['@graph', 'itemListElement', 'mainEntity', 'subjectOf', 'hasVariant', 'isVariantOf']:
                if key in node:
                    found = self._find_product_node(node.get(key))
                    if found is not None:
                        return found
            for value in node.values():
                found = self._find_product_node(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = self._find_product_node(item)
                if found is not None:
                    return found
        return None

    def _clean_candidate_text(self, value: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', str(value or ''))
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            return ''
        lower = text.lower()
        junk_tokens = ['privacy', 'terms', 'contact', 'search', 'blog', 'shipping']
        if any(token in lower for token in junk_tokens):
            return ''
        return text

    def _filter_junk_values(self, values: List[str]) -> List[str]:
        cleaned: List[str] = []
        for value in values:
            token = self._clean_candidate_text(str(value))
            if token:
                cleaned.append(token)
        return self._dedupe_preserve_case(cleaned)

    def _dedupe_preserve_case(self, values: List[str]) -> List[str]:
        seen = set()
        deduped: List[str] = []
        for value in values:
            cleaned = str(value).strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped

    def _safe_float(self, raw_value: Any) -> float:
        try:
            cleaned = re.sub(r'[^0-9.]', '', str(raw_value or ''))
            return float(cleaned) if cleaned else 0.0
        except Exception:
            return 0.0

    def _default_currency_for_domain(self, domain: str) -> str:
        lower_domain = str(domain or '').lower()
        if '.lk' in lower_domain:
            return 'LKR'
        return 'LKR'

    def automate_checkout_prefill(self, product: Dict[str, Any], order: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
        """Use Playwright to prefill checkout fields, without submitting payment."""
        checkout_url = self._resolve_checkout_url(product, order)
        prefilled_checkout_url = self.build_prefilled_checkout_url(str(checkout_url or ''), order, profile)
        if not checkout_url:
            return {
                'success': False,
                'checkout_url': None,
                'message': 'No checkout URL found for this product.',
                'filled_fields': [],
            }

        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return {
                'success': True,
                'checkout_url': prefilled_checkout_url or checkout_url,
                'message': 'Using URL-based checkout prefill parameters. Playwright is not installed, so browser form field automation is skipped.',
                'filled_fields': ['prefill_url_params'],
            }

        filled_fields: List[str] = []

        def fill_first(page: Any, selectors: List[str], value: Optional[str], field_name: str) -> None:
            if not value or str(value).strip() in {'', 'N/A'}:
                return
            text = str(value).strip()
            for selector in selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible(timeout=500):
                        try:
                            locator.fill(text, timeout=1000)
                            filled_fields.append(field_name)
                            return
                        except Exception:
                            continue
                except Exception:
                    continue

        def fill_first_in_frames(page: Any, selectors: List[str], value: Optional[str], field_name: str) -> None:
            if not value or str(value).strip() in {'', 'N/A'}:
                return
            text = str(value).strip()
            for frame in page.frames:
                frame_url = str(getattr(frame, 'url', '') or '').lower()
                if not frame_url:
                    continue
                if 'checkout' not in frame_url and 'shopify' not in frame_url:
                    continue
                for selector in selectors:
                    try:
                        locator = frame.locator(selector).first
                        if locator.count() > 0 and locator.is_visible(timeout=500):
                            try:
                                locator.fill(text, timeout=1000)
                                filled_fields.append(field_name)
                                return
                            except Exception:
                                continue
                    except Exception:
                        continue

        def select_first(page: Any, selectors: List[str], value: Optional[str], field_name: str) -> None:
            if not value or str(value).strip() in {'', 'N/A'}:
                return
            text = str(value).strip()
            for selector in selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible(timeout=500):
                        try:
                            locator.select_option(label=text, timeout=1000)
                            filled_fields.append(field_name)
                            return
                        except Exception:
                            try:
                                locator.select_option(value=text, timeout=1000)
                                filled_fields.append(field_name)
                                return
                            except Exception:
                                continue
                except Exception:
                    continue

        def canonical(value: Optional[str]) -> str:
            return re.sub(r'[^a-z0-9]', '', str(value or '').lower())

        def click_option_like(page: Any, value: Optional[str], field_name: str) -> None:
            if not value or str(value).strip() in {'', 'N/A'}:
                return

            target = str(value).strip()
            target_key = canonical(target)
            if not target_key:
                return

            candidate_selectors = [
                f'button:has-text("{target}")',
                f'label:has-text("{target}")',
                f'[role="option"]:has-text("{target}")',
                f'[role="radio"]:has-text("{target}")',
                f'[aria-label*="{target}" i]',
                f'[data-size*="{target}" i]',
                f'[data-value*="{target}" i]',
                f'input[type="radio"][value*="{target}" i]',
                f'option[value*="{target}" i]',
            ]

            for selector in candidate_selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.count() == 0:
                        continue
                    try:
                        locator.scroll_into_view_if_needed(timeout=500)
                    except Exception:
                        pass
                    if locator.is_visible(timeout=600):
                        try:
                            locator.click(timeout=1000, force=True)
                            filled_fields.append(field_name)
                            return
                        except Exception:
                            pass

                        # Some radios must be checked directly.
                        try:
                            locator.check(timeout=1000, force=True)
                            filled_fields.append(field_name)
                            return
                        except Exception:
                            continue
                except Exception:
                    continue

            # Fallback: iterate likely option controls and fuzzy-match displayed text/value.
            for selector in ['button', 'label', '[role="option"]', '[role="radio"]', 'option', 'input[type="radio"]']:
                try:
                    options = page.locator(selector)
                    count = min(options.count(), 120)
                    for idx in range(count):
                        option = options.nth(idx)
                        option_text = ''
                        for getter in (lambda: option.inner_text(timeout=200), lambda: option.get_attribute('value'), lambda: option.get_attribute('aria-label'), lambda: option.get_attribute('data-size'), lambda: option.get_attribute('data-value')):
                            try:
                                raw = getter()
                                if raw:
                                    option_text = str(raw)
                                    break
                            except Exception:
                                continue
                        if canonical(option_text) != target_key:
                            continue
                        try:
                            if option.is_visible(timeout=400):
                                option.click(timeout=1000, force=True)
                                filled_fields.append(field_name)
                                return
                        except Exception:
                            try:
                                option.check(timeout=1000, force=True)
                                filled_fields.append(field_name)
                                return
                            except Exception:
                                continue
                except Exception:
                    continue

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.goto(str(prefilled_checkout_url or checkout_url), wait_until='domcontentloaded', timeout=45000)

                fill_first(page, ['input[name*="name" i]', 'input[id*="name" i]', 'input[name="checkout[shipping_address][first_name]"]'], profile.get('name'), 'name')
                fill_first(page, ['input[type="email"]', 'input[name*="email" i]', 'input[name="checkout[email]"]'], profile.get('email'), 'email')
                fill_first(page, ['input[type="tel"]', 'input[name*="phone" i]', 'input[name*="mobile" i]', 'input[name="checkout[shipping_address][phone]"]'], profile.get('phone'), 'phone')
                fill_first(page, ['textarea[name*="address" i]', 'input[name*="address" i]', 'input[id*="address" i]', 'input[name="checkout[shipping_address][address1]"]'], profile.get('shipping_address'), 'shipping_address')

                fill_first_in_frames(page, ['input[name*="name" i]', 'input[id*="name" i]', 'input[name="checkout[shipping_address][first_name]"]'], profile.get('name'), 'name_iframe')
                fill_first_in_frames(page, ['input[type="email"]', 'input[name*="email" i]', 'input[name="checkout[email]"]'], profile.get('email'), 'email_iframe')
                fill_first_in_frames(page, ['input[type="tel"]', 'input[name*="phone" i]', 'input[name*="mobile" i]', 'input[name="checkout[shipping_address][phone]"]'], profile.get('phone'), 'phone_iframe')
                fill_first_in_frames(page, ['textarea[name*="address" i]', 'input[name*="address" i]', 'input[id*="address" i]', 'input[name="checkout[shipping_address][address1]"]'], profile.get('shipping_address'), 'shipping_address_iframe')

                fill_first(page, ['input[name*="quantity" i]', 'input[id*="quantity" i]'], str(order.get('quantity') or ''), 'quantity')
                select_first(page, ['select[name*="size" i]', 'select[id*="size" i]'], order.get('variant'), 'size')
                select_first(page, ['select[name*="color" i]', 'select[id*="color" i]'], order.get('color'), 'color')
                click_option_like(page, order.get('variant'), 'size')
                click_option_like(page, order.get('color'), 'color')

                detected_shipping_fee = self._extract_checkout_shipping_fee(page, product.get('currency') or 'LKR')

                # Best effort only; no submit and no payment automation.
                context.close()
                browser.close()

            return {
                'success': True,
                'checkout_url': prefilled_checkout_url or checkout_url,
                'message': 'Generated checkout URL with prefill params and applied best-effort browser automation for detected fields. Please review before payment.',
                'filled_fields': ['prefill_url_params', *filled_fields],
                'shipping_fee': detected_shipping_fee,
            }
        except Exception as e:
            return {
                'success': True,
                'checkout_url': prefilled_checkout_url or checkout_url,
                'message': f'URL-based prefill generated. Browser automation failed: {e}',
                'filled_fields': ['prefill_url_params', *filled_fields],
                'shipping_fee': None,
            }

    def build_prefilled_checkout_url(self, checkout_url: str, order: Dict[str, Any], profile: Dict[str, Any]) -> str:
        """Build checkout URL with common prefill params used by many shops (including Shopify)."""
        if not checkout_url:
            return checkout_url

        try:
            parsed = urlparse(checkout_url)
            existing_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
            params = dict(existing_params)

            raw_name = str(profile.get('name') or '').strip()
            first_name = raw_name
            last_name = ''
            if ' ' in raw_name:
                first_name, last_name = raw_name.split(' ', 1)

            email = str(profile.get('email') or '').strip()
            phone = str(profile.get('phone') or '').strip()
            address = str(profile.get('shipping_address') or '').strip()
            quantity = order.get('quantity')
            variant = str(order.get('variant') or '').strip()
            color = str(order.get('color') or '').strip()

            if email:
                params['email'] = email
                params['checkout[email]'] = email
            if phone:
                params['phone'] = phone
                params['checkout[phone]'] = phone
            if raw_name:
                params['name'] = raw_name
                params['checkout[shipping_address][first_name]'] = first_name
                params['checkout[shipping_address][last_name]'] = last_name
            if address:
                params['address'] = address
                params['address1'] = address
                params['shipping_address'] = address
                params['checkout[shipping_address][address1]'] = address
            if quantity:
                params['quantity'] = str(quantity)
                params['qty'] = str(quantity)
            if variant and variant != 'N/A':
                params['size'] = variant
                params['option'] = variant
                params['checkout[attributes][size]'] = variant
            if color and color != 'N/A':
                params['color'] = color
                params['colour'] = color
                params['checkout[attributes][color]'] = color

            encoded = urlencode(params, doseq=True)
            return parsed._replace(query=encoded).geturl()
        except Exception:
            return checkout_url

    def _resolve_checkout_url(self, product: Dict[str, Any], order: Dict[str, Any]) -> Optional[str]:
        """Resolve the best checkout URL, including Shopify product-page fallbacks."""
        explicit = (
            product.get('checkout_url')
            or product.get('buy_now_url')
            or product.get('add_to_cart_url')
        )
        if explicit:
            return str(explicit)

        raw_url = str(product.get('url') or '').strip()
        if not raw_url:
            return None

        parsed = urlparse(raw_url)
        base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ''
        if not base:
            return raw_url

        # Shopify fallback: build a cart->checkout URL using variant id when available.
        is_shopify_product = '/products/' in parsed.path.lower()
        if is_shopify_product:
            query = parse_qs(parsed.query)
            variant_values = query.get('variant') or []
            variant_id = ''
            if variant_values:
                candidate = str(variant_values[0]).strip()
                if candidate.isdigit():
                    variant_id = candidate

            qty = int(order.get('quantity') or 1)
            qty = max(1, min(20, qty))
            if variant_id:
                return f"{base}/cart/{variant_id}:{qty}?checkout"
            return f"{base}/checkout"

        return raw_url

    def _extract_checkout_shipping_fee(self, page: Any, currency: str) -> Optional[float]:
        """Best-effort shipping fee extraction from checkout page after prefill."""
        try:
            page.wait_for_timeout(1200)
            html = page.content()
            if not html or BeautifulSoup is None:
                return None

            soup = BeautifulSoup(html, 'html.parser')
            # Try specific checkout/shipping method selectors first.
            shipping_snippets: List[str] = []
            selectors = [
                '[data-shipping-method]',
                '[class*="shipping-method"]',
                '[name*="shipping" i] + label',
                '[class*="shipping"]',
                '[data-testid*="shipping" i]',
            ]
            for selector in selectors:
                for node in soup.select(selector):
                    txt = node.get_text(' ', strip=True)
                    if txt:
                        shipping_snippets.append(txt)

            haystack = ' '.join(shipping_snippets) if shipping_snippets else soup.get_text(' ', strip=True)
            if not haystack:
                return None
            if re.search(r'free\s+shipping|shipping\s+free', haystack, flags=re.I):
                return 0.0

            patterns = [
                r'(?:LKR|Rs\.?|රු)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
                r'([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:LKR|Rs\.?|රු)',
                r'\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
                r'€\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
                r'£\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
            ]
            for pattern in patterns:
                match = re.search(pattern, haystack, flags=re.I)
                if not match:
                    continue
                amount = float(match.group(1).replace(',', ''))
                if amount < 0:
                    continue
                return amount
        except Exception:
            return None
        return None

    def _extract_shipping_from_checkout_url(self, checkout_url: str, currency: str) -> Dict[str, Any]:
        """Best-effort extraction of shipping availability/fee from checkout page HTML."""
        if not checkout_url or BeautifulSoup is None:
            return {'shipping_availability': 'Unknown', 'shipping_fee': None}

        html = self._fetch_page_html_with_playwright(checkout_url) or self._fetch_page_html(checkout_url)
        if not html:
            return {'shipping_availability': 'Unknown', 'shipping_fee': None}

        try:
            soup = BeautifulSoup(html, 'html.parser')
            availability = self._extract_shipping_availability(soup)
            fee = self._extract_shipping_fee(soup, currency)
            return {
                'shipping_availability': availability,
                'shipping_fee': fee,
            }
        except Exception:
            return {'shipping_availability': 'Unknown', 'shipping_fee': None}

    def _enrich_product_variants_with_rendered_html(self, url: str, product: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Fill missing size/color options by parsing rendered HTML for JS-heavy storefronts."""
        if not isinstance(product, dict):
            return product

        current_sizes = product.get('available_sizes') or []
        current_colors = product.get('available_colors') or []
        current_variant_map = product.get('variants') if isinstance(product.get('variants'), dict) else {}
        variant_sizes = current_variant_map.get('sizes') if isinstance(current_variant_map, dict) else []
        variant_colors = current_variant_map.get('colors') if isinstance(current_variant_map, dict) else []

        needs_sizes = not current_sizes and not variant_sizes
        needs_colors = not current_colors and not variant_colors
        if not (needs_sizes or needs_colors):
            return product

        rendered_html = self._fetch_page_html_with_playwright(url)
        if not rendered_html or BeautifulSoup is None:
            return product

        try:
            soup = BeautifulSoup(rendered_html, 'html.parser')
            dynamic_sizes = self._filter_junk_values(self._extract_available_sizes(soup)) if needs_sizes else []
            dynamic_colors = self._filter_junk_values(self._extract_available_colors(soup)) if needs_colors else []

            merged_sizes = self._dedupe_preserve_case([*current_sizes, *variant_sizes, *dynamic_sizes]) if needs_sizes else self._dedupe_preserve_case([*current_sizes, *variant_sizes])
            merged_colors = self._dedupe_preserve_case([*current_colors, *variant_colors, *dynamic_colors]) if needs_colors else self._dedupe_preserve_case([*current_colors, *variant_colors])

            if merged_sizes:
                product['available_sizes'] = merged_sizes
            if merged_colors:
                product['available_colors'] = merged_colors

            existing_variants = product.get('variants') if isinstance(product.get('variants'), dict) else {}
            product['variants'] = {
                'sizes': merged_sizes,
                'colors': merged_colors,
                **({k: v for k, v in existing_variants.items() if k not in {'sizes', 'colors'}} if isinstance(existing_variants, dict) else {}),
            }

            if not product.get('add_to_cart_url') or not product.get('buy_now_url') or not product.get('checkout_url'):
                product.update(self._extract_action_links(soup, url))
        except Exception:
            return product

        return product

    def _fetch_page_html(self, url: str) -> Optional[str]:
        """Fetch page HTML with lightweight retries for unstable sites."""
        session = requests.Session()
        attempts = len(self._fallback_user_agents)

        for idx, agent in enumerate(self._fallback_user_agents):
            headers = dict(self.headers)
            headers['User-Agent'] = agent
            try:
                response = session.get(url, headers=headers, timeout=15, allow_redirects=True)
                response.raise_for_status()
                if response.text and len(response.text) > 200:
                    return response.text
            except requests.RequestException as err:
                logger.warning(f"Fetch attempt {idx + 1}/{attempts} failed for {url}: {err}")
                if idx < attempts - 1:
                    time.sleep(0.5 * (idx + 1))

        return None

    def _extract_action_links(self, soup: BeautifulSoup, url: str) -> Dict[str, Optional[str]]:
        """Extract likely cart/checkout action URLs from product page anchors/buttons."""
        try:
            hrefs = []
            for a_tag in soup.find_all('a', href=True):
                hrefs.append(str(a_tag.get('href') or '').strip())
            for btn in soup.find_all(['button']):
                data_href = btn.get('data-href') or btn.get('formaction') or ''
                if data_href:
                    hrefs.append(str(data_href).strip())

            resolved = [urljoin(url, h) for h in hrefs if h]

            def first_match(patterns: List[str]) -> Optional[str]:
                for link in resolved:
                    low = link.lower()
                    if any(p in low for p in patterns):
                        return link
                return None

            add_to_cart = first_match(['add-to-cart', 'add_to_cart', 'cart/add', '/cart?add', '/cart/add'])
            buy_now = first_match(['buy-now', 'buy_now', 'checkout', 'express-checkout'])
            checkout = first_match(['/checkout', 'checkout'])

            return {
                'add_to_cart_url': add_to_cart,
                'buy_now_url': buy_now,
                'checkout_url': checkout,
            }
        except Exception:
            return {
                'add_to_cart_url': None,
                'buy_now_url': None,
                'checkout_url': None,
            }
    
    def _extract_shop_name(self, domain: str) -> str:
        """Extract shop name from domain."""
        # Common patterns
        if 'daraz' in domain:
            return 'Daraz'
        elif 'amazon' in domain:
            return 'Amazon'
        elif 'ebay' in domain:
            return 'eBay'
        elif 'aliexpress' in domain:
            return 'AliExpress'
        elif 'ikman' in domain:
            return 'ikman.lk'
        else:
            # Extract from domain
            parts = domain.replace('www.', '').split('.')
            return parts[0].capitalize()
    
    def _extract_name(self, soup: BeautifulSoup, domain: str) -> str:
        """Extract product name from page."""
        # Try common selectors for different platforms
        selectors = [
            # Daraz selectors
            'h1.pdp-mod-product-badge-title',
            'h1.product-title',
            
            # Amazon selectors
            'h1#title',
            'span#productTitle',
            
            # Generic/Open Graph
            'h1[itemprop="name"]',
            'meta[property="og:title"]',
            
            # Generic fallbacks
            '.product-name',
            '[data-product-name]',
            'h1',
        ]
        
        for selector in selectors:
            if selector.startswith('meta'):
                elem = soup.find('meta', {'property': 'og:title'})
                if elem and elem.get('content'):
                    return elem['content'].strip()
            else:
                elem = soup.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 2:
                        return text
        
        # Fallback to title tag
        title = soup.find('title')
        if title:
            text = title.get_text(strip=True)
            # Clean up common patterns
            text = re.sub(r'\s*[-|]\s*.*', '', text)  # Remove after dash/pipe
            if len(text) > 2:
                return text
        
        return 'Unknown Product'
    
    def _extract_price(self, soup: BeautifulSoup, domain: str) -> float:
        """Extract product price from HTML."""
        # Try common price selectors
        selectors = [
            # Daraz selectors
            '.pdp-price__current',
            '.pdp-price',
            
            # Amazon selectors
            'span.a-price-whole',
            'span.a-price',
            '.a-price-whole',
            
            # Generic selectors
            '[itemprop="price"]',
            '.price',
            '.product-price',
            '.current-price',
            '[data-price]',
            '.product-pricing',
        ]
        
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                price_text = elem.get_text(strip=True)
                price = self._parse_price(price_text)
                if price and price > 0:
                    return price
        
        # Search in meta tags
        meta_price = soup.find('meta', {'property': 'product:price:amount'})
        if meta_price and meta_price.get('content'):
            try:
                return float(meta_price['content'])
            except:
                pass
        
        # Search in all text for currency patterns (e.g., "Rs. 2,500" or "$29.99")
        page_text = soup.get_text()
        # Look for patterns like "Rs. 2500", "$29.99", "LKR 5000"
        price_patterns = [
            r'Rs\.?\s*[\d,]+(?:\.\d{2})?',
            r'LKR\s*[\d,]+(?:\.\d{2})?',
            r'\$\s*[\d,]+(?:\.\d{2})?',
            r'USD\s*[\d,]+(?:\.\d{2})?',
            r'EUR\s*[\d,]+(?:\.\d{2})?',
            r'£\s*[\d,]+(?:\.\d{2})?',
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, page_text)
            if match:
                price = self._parse_price(match.group())
                if price and price > 0:
                    return price
        
        logger.warning(f"Could not extract price from page, defaulting to 0")
        return 0.0
    
    def _parse_price(self, text: str) -> Optional[float]:
        """Parse price from text string."""
        # Remove common currency symbols and text
        cleaned = re.sub(r'[^\d.,]', '', text)
        cleaned = cleaned.replace(',', '')
        
        try:
            return float(cleaned)
        except:
            return None
    
    def _extract_currency(self, soup: BeautifulSoup, domain: str) -> str:
        """Extract currency from page."""
        # Priority 1: Meta tag (most reliable)
        meta_currency = soup.find('meta', {'property': 'product:price:currency'})
        if meta_currency and meta_currency.get('content'):
            return meta_currency['content']
        
        # Priority 2: Search page text for currency indicators
        page_text = soup.get_text().lower()
        
        if 'lkr' in page_text or 'rupees' in page_text or 'rs.' in page_text:
            return 'LKR'
        elif 'usd' in page_text or 'dollar' in page_text or '$' in page_text:
            return 'USD'
        elif 'eur' in page_text or 'euro' in page_text or '€' in page_text:
            return 'EUR'
        elif 'gbp' in page_text or 'pound' in page_text or '£' in page_text:
            return 'GBP'
        
        # Priority 3: Domain-based defaults
        if 'daraz.lk' in domain or 'ikman.lk' in domain:
            return 'LKR'
        elif 'amazon' in domain:
            return 'USD'
        elif 'amazon.eu' in domain or '.de' in domain or '.uk' in domain:
            return 'EUR'
        
        return 'LKR'
    
    def _extract_image(self, soup: BeautifulSoup, domain: str) -> Optional[str]:
        """Extract product image URL."""
        # Priority 1: Open Graph image (most reliable)
        og_image = soup.find('meta', {'property': 'og:image'})
        if og_image and og_image.get('content'):
            img_url = og_image['content']
            if img_url.startswith('http'):
                return img_url
        
        # Priority 2: Schema.org image
        schema_image = soup.find('meta', {'itemprop': 'image'})
        if schema_image and schema_image.get('content'):
            img_url = schema_image['content']
            if img_url.startswith('http'):
                return img_url
        
        # Priority 3: Site-specific selectors (main product image)
        selectors = [
            # Daraz main image
            'img.pdp-mod-product-image-gallery-item[data-src]',
            'img.pdp-mod-product-image-gallery-item',
            
            # Amazon main image
            'img#landingImage',
            'img#imageBlkFront',
            
            # Generic product image
            'img[alt*="product"]',
            'img[alt*="Product"]',
            '.product-image img',
            '.product-photo img',
            '[itemprop="image"] img',
            '.main-image img',
            
            # Fallback: any img in main content area
            'img[class*="product"]',
            'img[class*="main"]',
        ]
        
        for selector in selectors:
            img_elem = soup.select_one(selector)
            if img_elem:
                # Try data-src first (lazy loading)
                if img_elem.get('data-src'):
                    img_url = img_elem['data-src']
                    if img_url and img_url.startswith('http'):
                        return img_url
                
                # Try src attribute
                if img_elem.get('src'):
                    img_url = img_elem['src']
                    # Convert relative URLs to absolute
                    if img_url.startswith('http'):
                        return img_url
                    elif img_url.startswith('/'):
                        # Construct absolute URL
                        return f"https://{domain}{img_url}"
                    elif img_url.startswith('//'):
                        # Protocol-relative URL
                        return f"https:{img_url}"
        
        logger.warning(f"Could not extract image from page")
        return None
    
    def _extract_availability(self, soup: BeautifulSoup) -> str:
        """Extract stock availability without over-triggering on unrelated page text."""
        avail_meta = soup.find('meta', {'itemprop': 'availability'})
        if avail_meta:
            content = str(avail_meta.get('content') or '').lower()
            if 'instock' in content:
                return 'In Stock'
            if 'outofstock' in content:
                return 'Out of Stock'

        selector_candidates = [
            '[itemprop="availability"]',
            '.availability',
            '.stock',
            '.stock-status',
            '[class*="stock"]',
            '[class*="availability"]',
            '[data-stock-status]',
        ]

        in_stock_hits = 0
        out_of_stock_hits = 0

        for selector in selector_candidates:
            for elem in soup.select(selector):
                txt = elem.get_text(' ', strip=True).lower()
                if not txt:
                    continue
                if re.search(r'\b(in stock|available|ready to ship|ships in)\b', txt):
                    in_stock_hits += 1
                if re.search(r'\b(out of stock|sold out|unavailable|not available)\b', txt):
                    out_of_stock_hits += 1

        if in_stock_hits and not out_of_stock_hits:
            return 'In Stock'
        if out_of_stock_hits and not in_stock_hits:
            return 'Out of Stock'

        buy_cta = soup.select_one('button[name*="add" i], button[class*="add" i], button[id*="add" i]')
        if buy_cta and not buy_cta.has_attr('disabled'):
            return 'In Stock'

        return 'Unknown'

    def _extract_shipping_availability(self, soup: BeautifulSoup) -> str:
        """Extract shipping-related availability separately from stock status."""
        selectors = [
            '.shipping',
            '.delivery',
            '[class*="shipping"]',
            '[class*="delivery"]',
            '[data-shipping]',
            '[data-delivery]',
        ]
        snippets: List[str] = []
        for selector in selectors:
            for elem in soup.select(selector):
                txt = elem.get_text(' ', strip=True)
                if txt:
                    snippets.append(txt)

        text = ' '.join(snippets).lower()
        if not text:
            return 'Unknown'
        if re.search(r'\b(not available|cannot be shipped|does not ship)\b', text):
            return 'Unavailable for selected address'
        if re.search(r'\b(free shipping|shipping free|free delivery)\b', text):
            return 'Free Shipping'
        if re.search(r'\b(ships|delivery|delivers|available for shipping)\b', text):
            return 'Shipping available'
        return 'Unknown'
    
    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract product description."""
        # Try meta description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            desc = meta_desc['content']
            return desc[:200] + '...' if len(desc) > 200 else desc
        
        return ''
    
    def _extract_available_sizes(self, soup: BeautifulSoup) -> List[str]:
        """Extract available sizes for clothing/products.

        Keeps only selectable/in-stock values and removes placeholders such as
        "Choose an option", "Select size", and sold-out labels.
        """
        sizes = []
        
        try:
            # Try to find size selector elements
            size_selectors = [
                'select[name*="size"] option',  # Select with options
                'button[data-size]',            # Size buttons
                'input[type="radio"][data-size]',  # Radio buttons
                '.size-option',                 # Generic class
                '[data-size]',                  # Generic data attr
                '[aria-label*="size" i]',
                '[class*="size" i] li',
            ]
            
            for selector in size_selectors:
                elements = soup.select(selector)
                for elem in elements:
                    size = (
                        elem.get_text(strip=True)
                        or elem.get('data-size', '')
                        or elem.get('value', '')
                        or elem.get('aria-label', '')
                    )
                    if not size:
                        continue

                    if self._is_element_unavailable(elem):
                        continue

                    normalized_size = re.sub(r'\s+', ' ', str(size)).strip()
                    normalized_size = self._normalize_size_token(normalized_size)
                    if self._is_invalid_size_label(normalized_size):
                        continue
                    if self._looks_like_size(normalized_size):
                        sizes.append(normalized_size)

            # Remove duplicates while preserving order
            seen = set()
            unique_sizes = []
            for size in sizes:
                key = self._normalize_size_token(size).upper()
                if key not in seen:
                    seen.add(key)
                    unique_sizes.append(self._normalize_size_token(size))

            if unique_sizes:
                return unique_sizes[:12]

            # Fallback 1: parse embedded JSON for size-like fields.
            json_sizes = self._extract_sizes_from_embedded_json(soup)
            if json_sizes:
                return json_sizes[:12]

            # Fallback 2: parse visible text around size labels.
            text_sizes = self._extract_sizes_from_text(soup.get_text(' ', strip=True))
            if text_sizes:
                return text_sizes[:12]

            return []

        except Exception as e:
            logger.warning(f"Could not extract sizes: {e}")
            return []

    def _extract_available_colors(self, soup: BeautifulSoup) -> List[str]:
        """Extract available colors while excluding disabled variants."""
        colors: List[str] = []
        selectors = [
            'select[name*="color" i] option',
            'button[data-color]',
            'button[aria-label*="color" i]',
            '[data-color]',
            '.color-option',
            '[class*="color"]',
        ]

        try:
            for selector in selectors:
                for elem in soup.select(selector):
                    raw_color = (
                        elem.get('data-color', '')
                        or elem.get('value', '')
                        or elem.get('aria-label', '')
                        or elem.get_text(' ', strip=True)
                    )
                    color = re.sub(r'\s+', ' ', str(raw_color)).strip()
                    if not color:
                        continue
                    if len(color) > 30:
                        continue

                    class_text = ' '.join(elem.get('class', [])).lower()
                    txt = elem.get_text(' ', strip=True).lower()
                    if elem.has_attr('disabled') or 'disabled' in class_text or 'out of stock' in txt:
                        continue

                    if color.lower() in {'select', 'choose color', 'color'}:
                        continue
                    if not self._looks_like_color(color):
                        continue
                    colors.append(color)

            seen: set[str] = set()
            unique_colors: List[str] = []
            for color in colors:
                key = color.lower()
                if key not in seen:
                    seen.add(key)
                    unique_colors.append(color)

            return unique_colors[:12]
        except Exception as e:
            logger.warning(f"Could not extract colors: {e}")
            return []

    def _normalize_size_token(self, raw_size: str) -> str:
        token = re.sub(r'\s+', '', str(raw_size or '')).upper()
        if token in {'FREE', 'FREESIZE', 'ONE', 'ONESIZE'}:
            return 'FREE SIZE'
        # Normalize variants like XXL, 2XL, XXXL.
        if re.fullmatch(r'[2-5]?X{0,3}L', token):
            if token.startswith(('2', '3', '4', '5')):
                return token
            x_count = token.count('X')
            if x_count >= 2:
                return f'{x_count}XL'
            return token
        if token in {'XS', 'S', 'M', 'L'}:
            return token
        return str(raw_size).strip()

    def _looks_like_size(self, raw_value: str) -> bool:
        """Heuristic classifier to identify plausible size tokens."""
        normalized = self._normalize_size_token(raw_value)
        token = re.sub(r'\s+', '', normalized).upper()
        if not token:
            return False

        known_tokens = {
            'XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL',
            '2XL', '3XL', '4XL', '5XL', 'FREESIZE', 'ONESIZE',
            'SMALL', 'MEDIUM', 'LARGE',
        }
        if token in known_tokens:
            return True

        # Common e-commerce prefixed sizes, e.g. UK-08-S, US-4-XS, EU-40-L.
        if re.fullmatch(r'[A-Z]{1,5}-[0-9]{1,3}-(XXS|XS|S|M|L|XL|XXL|XXXL|2XL|3XL|4XL|5XL)', token):
            return True

        compact = re.sub(r'[^A-Z0-9]', '', token)
        if re.fullmatch(r'[A-Z]{1,5}[0-9]{1,3}(XXS|XS|S|M|L|XL|XXL|XXXL|2XL|3XL|4XL|5XL)', compact):
            return True

        if re.fullmatch(r'[0-9]{1,3}', token):
            return True
        if re.fullmatch(r'[0-9]{1,3}[A-Z]', token):
            return True
        if re.fullmatch(r'[0-9]{1,3}-[0-9]{1,3}', token):
            return True
        if re.fullmatch(r'W[0-9]{1,3}L[0-9]{1,3}', token):
            return True

        return False

    def _looks_like_color(self, raw_value: str) -> bool:
        """Heuristic classifier for color values to avoid menu/footer text noise."""
        value = re.sub(r'\s+', ' ', str(raw_value or '')).strip().lower()
        if not value:
            return False

        if len(value) > 25:
            return False
        if re.search(r'privacy|terms|policy|search|contact|faq|blog|shipping|refund|about', value, flags=re.I):
            return False

        known_colors = {
            'red', 'blue', 'green', 'black', 'white', 'pink', 'yellow', 'brown',
            'gray', 'grey', 'orange', 'purple', 'gold', 'silver', 'beige', 'navy',
            'maroon', 'olive', 'cream', 'khaki', 'mustard', 'teal',
            'multi', 'multicolor', 'multi-color',
        }
        if value in known_colors:
            return True

        tokens = re.split(r'[\s\-/]+', value)
        tokens = [t for t in tokens if t]
        if not tokens:
            return False

        # Allow descriptor + base color patterns, e.g. "light blue", "off white".
        descriptors = {
            'light', 'dark', 'deep', 'sky', 'baby', 'off', 'ash', 'royal',
            'charcoal', 'pastel', 'dusty', 'metallic',
        }
        if len(tokens) == 1:
            return tokens[0] in known_colors
        if len(tokens) == 2:
            return (tokens[0] in descriptors and tokens[1] in known_colors) or all(t in known_colors for t in tokens)

        return False

    def _extract_sizes_from_embedded_json(self, soup: BeautifulSoup) -> List[str]:
        """Extract size options from inline JSON blobs used by modern storefronts."""
        results: List[str] = []
        candidate_keys = {'size', 'sizes', 'available_sizes', 'availablesizes', 'sizeoptions'}

        def collect(obj: Any, parent_key: str = '') -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    key_norm = re.sub(r'[^a-z_]', '', str(key).lower())
                    next_parent = key_norm or parent_key
                    if key_norm in candidate_keys:
                        self._append_size_candidates(value, results)
                    collect(value, next_parent)
            elif isinstance(obj, list):
                for item in obj:
                    collect(item, parent_key)
            elif isinstance(obj, str):
                if parent_key in candidate_keys:
                    self._append_size_candidates(obj, results)

        for script in soup.find_all('script'):
            raw = script.string or script.get_text(' ', strip=True)
            if not raw:
                continue
            raw = raw.strip()
            parsed_any = False

            if raw.startswith('{') or raw.startswith('['):
                try:
                    parsed = json.loads(raw)
                    collect(parsed)
                    parsed_any = True
                except Exception:
                    parsed_any = False

            if not parsed_any:
                # Handle wrappers such as `window.__STATE__ = {...};`
                wrapped_json_matches = re.findall(r'=\s*(\{.*?\}|\[.*?\])\s*;?\s*$', raw, flags=re.S)
                for candidate_json in wrapped_json_matches:
                    try:
                        parsed = json.loads(candidate_json)
                        collect(parsed)
                    except Exception:
                        continue

                self._append_sizes_from_script_text(raw, results)

        return self._dedupe_size_tokens(results)

    def _append_sizes_from_script_text(self, raw_script: str, sink: List[str]) -> None:
        """Best-effort extraction for size arrays embedded in non-JSON script blocks."""
        if not raw_script:
            return

        array_pattern = re.compile(
            r'(?i)(?:"|\')?(?:size|sizes|available_sizes|sizeoptions)(?:"|\')?\s*:\s*\[([^\]]{1,500})\]'
        )
        for array_match in array_pattern.finditer(raw_script):
            values_blob = array_match.group(1)
            for token in re.findall(r'"([^"\\]{1,30})"|\'([^\'\\]{1,30})\'', values_blob):
                value = token[0] or token[1]
                if value:
                    self._append_size_candidates(value, sink)

        option_values_pattern = re.compile(
            r'(?is)(?:"|\')name(?:"|\')\s*:\s*(?:"|\')size(?:"|\').{0,240}?(?:"|\')values(?:"|\')\s*:\s*\[([^\]]{1,500})\]'
        )
        for option_match in option_values_pattern.finditer(raw_script):
            values_blob = option_match.group(1)
            for token in re.findall(r'"([^"\\]{1,30})"|\'([^\'\\]{1,30})\'', values_blob):
                value = token[0] or token[1]
                if value:
                    self._append_size_candidates(value, sink)

    def _extract_sizes_from_text(self, page_text: str) -> List[str]:
        """Extract size tokens from free text when no structured selectors are found."""
        text = str(page_text or '')
        if not text:
            return []

        results: List[str] = []
        pattern = re.compile(r'(?:size|sizes)\s*[:\-]\s*([A-Za-z0-9\s,/|.-]{2,80})', re.I)
        for match in pattern.finditer(text):
            chunk = match.group(1)
            self._append_size_candidates(chunk, results)

        # Also scan for standalone known size tokens.
        token_pattern = re.compile(r'\b(?:XS|S|M|L|XL|XXL|XXXL|2XL|3XL|4XL|5XL|FREE\s*SIZE|ONE\s*SIZE)\b', re.I)
        for match in token_pattern.finditer(text):
            self._append_size_candidates(match.group(0), results)

        return self._dedupe_size_tokens(results)

    def _append_size_candidates(self, raw_value: Any, sink: List[str]) -> None:
        """Normalize and append size candidates from mixed scalar/list values."""
        if raw_value is None:
            return
        if isinstance(raw_value, list):
            for item in raw_value:
                self._append_size_candidates(item, sink)
            return
        value = str(raw_value).strip()
        if not value:
            return
        parts = re.split(r'[,/|]', value)
        for part in parts:
            token = self._normalize_size_token(part.strip())
            if not token:
                continue
            if self._is_invalid_size_label(token):
                continue
            if not self._looks_like_size(token):
                continue
            if len(token) > 20:
                continue
            if re.search(r'privacy|terms|contact|search|blog|shipping', token, flags=re.I):
                continue
            sink.append(token)

    def _dedupe_size_tokens(self, values: List[str]) -> List[str]:
        seen = set()
        deduped: List[str] = []
        for value in values:
            normalized = self._normalize_size_token(value)
            key = normalized.upper()
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped

    def _is_invalid_size_label(self, raw_value: str) -> bool:
        """Identify placeholder or unavailable labels that should never be returned as sizes."""
        value = re.sub(r'\s+', ' ', str(raw_value or '')).strip().lower()
        if not value:
            return True

        invalid_exact = {
            'select',
            'choose',
            'size',
            'sizes',
            'select size',
            'select a size',
            'choose size',
            'choose a size',
            'choose an option',
            'select an option',
            'pick a size',
            'n/a',
            'na',
            'none',
        }
        if value in invalid_exact:
            return True

        if re.search(r'\b(out of stock|sold out|unavailable|not available|sold-out|oos)\b', value):
            return True

        return False

    def _is_invalid_color_label(self, raw_value: str) -> bool:
        """Identify placeholder/unavailable labels that should not be returned as colors."""
        value = re.sub(r'\s+', ' ', str(raw_value or '')).strip().lower()
        if not value:
            return True

        invalid_exact = {
            'select',
            'choose',
            'color',
            'colour',
            'colors',
            'colours',
            'select color',
            'select colour',
            'select an option',
            'choose an option',
            'n/a',
            'na',
            'none',
        }
        if value in invalid_exact:
            return True

        if re.search(r'\b(out of stock|sold out|unavailable|not available|sold-out|oos)\b', value):
            return True

        return False

    def _is_element_unavailable(self, elem: Any) -> bool:
        """Check variant option node for disabled/unavailable markers."""
        if elem is None:
            return True

        text = str(elem.get_text(' ', strip=True) or '').lower()
        class_text = ' '.join(elem.get('class', [])).lower()
        parent_class_text = ' '.join((elem.parent.get('class', []) if getattr(elem, 'parent', None) else [])).lower()

        aria_disabled = str(elem.get('aria-disabled', '')).strip().lower()
        disabled_attr = elem.has_attr('disabled')
        disabled_by_aria = aria_disabled in {'true', '1', 'yes'}
        unavailable_data = str(elem.get('data-available', '')).strip().lower() in {'false', '0', 'no'}

        unavailable_markers = [
            'disabled',
            'unavailable',
            'sold-out',
            'soldout',
            'out-of-stock',
            'oos',
        ]
        class_unavailable = any(marker in class_text for marker in unavailable_markers)
        parent_class_unavailable = any(marker in parent_class_text for marker in unavailable_markers)
        text_unavailable = bool(re.search(r'\b(out of stock|sold out|unavailable|not available|sold-out)\b', text))

        return bool(
            disabled_attr
            or disabled_by_aria
            or unavailable_data
            or class_unavailable
            or parent_class_unavailable
            or text_unavailable
        )

    def _extract_stock_count(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract numeric stock count when explicitly available on page."""
        text = soup.get_text(' ', strip=True)
        patterns = [
            r'only\s+(\d+)\s+left',
            r'in stock\s*\(?\s*(\d+)\s*\)?',
            r'(\d+)\s+items?\s+left',
            r'stock\s*[:\-]\s*(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    continue
        return None
    
    def _extract_shop_location(self, soup: BeautifulSoup, domain: str) -> str:
        """Extract shop location/address."""
        try:
            # Try common location patterns
            location_selectors = [
                'meta[property="business:contact_data:street_address"]',
                '[itemprop="streetAddress"]',
                '.shop-location',
                '.store-address',
                '.address',
            ]
            
            for selector in location_selectors:
                if selector.startswith('meta'):
                    elem = soup.find('meta', {'property': 'business:contact_data:street_address'})
                    if elem and elem.get('content'):
                        return elem['content']
                else:
                    elem = soup.select_one(selector)
                    if elem:
                        text = elem.get_text(strip=True)
                        if text:
                            return text
            
            # Default based on shop
            if 'daraz' in domain:
                return 'Sri Lanka (Daraz.lk)'
            elif 'amazon' in domain:
                return 'International (Amazon)'
            elif 'ebay' in domain:
                return 'International (eBay)'
            
            return 'Online Shop'
            
        except Exception as e:
            logger.warning(f"Could not extract location: {e}")
            return 'Online Shop'
    
    def _extract_shop_hours(self, soup: BeautifulSoup) -> str:
        """Extract shop/seller opening hours."""
        try:
            # Try common hours patterns
            hours_selectors = [
                'meta[property="business:contact_data:phone_number"]',
                '[itemprop="openingHoursSpecification"]',
                '.shop-hours',
                '.store-hours',
                '.business-hours',
                '[data-hours]',
            ]
            
            for selector in hours_selectors:
                if selector.startswith('meta'):
                    elem = soup.find('meta', {'property': 'business:contact_data:phone_number'})
                    if elem and elem.get('content'):
                        return elem['content']
                else:
                    elem = soup.select_one(selector)
                    if elem:
                        text = elem.get_text(strip=True)
                        if text and len(text) > 2:
                            return text
            
            # Generic fallback
            return '24/7 Online (Check seller page)'
            
        except Exception as e:
            logger.warning(f"Could not extract hours: {e}")
            return '24/7 Online'
    
    
    def get_cart_summary(self) -> Dict[str, Any]:
        """Get shopping cart summary grouped by shop.
        
        Returns:
            Cart summary with totals and shop groupings
        """
        if not self.cart_items:
            return {
                'total_items': 0,
                'total_products': 0,
                'items': [],
                'by_shop': {},
                'grand_total': 0,
                'checkout_instructions': ''
            }
        
        # Group by shop
        shops = {}
        
        for item in self.cart_items:
            shop = item['shop']
            shop_id = item.get('shop_id', item['domain'])  # Use shop_id as the key
            domain = item['domain']
            currency = item.get('currency', 'LKR')
            
            if shop_id not in shops:
                shops[shop_id] = {
                    'shop_name': shop,
                    'shop_id': shop_id,
                    'domain': domain,
                    'items': [],
                    'subtotal': 0,
                    'currency': currency,
                    'item_count': 0
                }
            
            shops[shop_id]['items'].append(item)
            shops[shop_id]['subtotal'] += item['subtotal']
            shops[shop_id]['item_count'] += item['quantity']
        
        # Calculate grand total (sum of all shop subtotals)
        grand_total = 0
        for shop_id, shop_data in shops.items():
            # Convert to LKR for grand total if needed
            if shop_data['currency'] == 'USD':
                grand_total += shop_data['subtotal'] * 330  # Approx USD to LKR
            elif shop_data['currency'] == 'EUR':
                grand_total += shop_data['subtotal'] * 360  # Approx EUR to LKR
            else:  # LKR or unknown
                grand_total += shop_data['subtotal']
        
        return {
            'total_items': len(self.cart_items),
            'total_products': sum(item['quantity'] for item in self.cart_items),
            'items': self.cart_items,
            'by_shop': shops,
            'grand_total': grand_total,
            'checkout_instructions': self._generate_instructions(shops)
        }
    
    def _generate_instructions(self, shops: Dict[str, Any]) -> List[str]:
        """Generate step-by-step instructions for manual checkout."""
        instructions = []
        
        for idx, (shop_name, shop_data) in enumerate(shops.items(), 1):
            instructions.append(f"{idx}. Open {shop_name} ({shop_data['domain']})")
            
            for item in shop_data['items']:
                instructions.append(
                    f"   - Add '{item['name']}' × {item['quantity']} to cart"
                )
                instructions.append(f"     Link: {item['url']}")
            
            instructions.append(f"   - Proceed to checkout (Subtotal: {shop_data['currency']} {shop_data['subtotal']:.2f})")
            instructions.append("")
        
        return instructions
    
    def _get_estimated_delivery(self, shop_name: str) -> str:
        """Get estimated delivery based on shop.
        
        Args:
            shop_name: Name of the shop
            
        Returns:
            Estimated delivery string (e.g., "3-5 business days")
        """
        # Default delivery estimates by shop (you can customize these)
        delivery_estimates = {
            'Daraz': '2-3 business days',
            'Vogue Street': '3-5 business days',
            'TrendZ': '3-7 business days',
            'Arena': '4-6 business days',
            'Elements': '5-7 business days',
        }
        
        # Check if shop name exists in estimates
        for shop_key, estimate in delivery_estimates.items():
            if shop_key.lower() in shop_name.lower():
                return estimate
        
        # Default to 5-7 business days
        return '5-7 business days'
    
    def clear_cart(self):
        """Clear all items from cart."""
        self.cart_items = []
        logger.info("Cart cleared")
    
    def remove_item(self, index: int) -> bool:
        """Remove item from cart by index.
        
        Args:
            index: Cart item index (0-based)
            
        Returns:
            True if removed successfully
        """
        try:
            if 0 <= index < len(self.cart_items):
                removed = self.cart_items.pop(index)
                logger.info(f"Removed item: {removed['name']}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing item: {e}")
            return False
    
    def update_quantity(self, index: int, quantity: int) -> bool:
        """Update quantity of cart item.
        
        Args:
            index: Cart item index (0-based)
            quantity: New quantity
            
        Returns:
            True if updated successfully
        """
        try:
            if 0 <= index < len(self.cart_items) and quantity > 0:
                item = self.cart_items[index]
                item['quantity'] = quantity
                item['subtotal'] = item['price'] * quantity
                logger.info(f"Updated {item['name']} quantity to {quantity}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating quantity: {e}")
            return False
