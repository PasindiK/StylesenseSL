"""
Order Agent - Manages shopping cart from real-world product links.

This agent:
- Scrapes product details from e-commerce URLs
- Builds a virtual shopping cart
- Calculates totals and groups by shop
- Provides cart summary and instructions
"""
import logging
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import requests
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None
from src.services.agentic_ai.kg.client import Neo4jKGClient

logger = logging.getLogger(__name__)


class OrderAgent:
    """Virtual shopping cart manager for real-world product links."""
    
    def __init__(self, loader=None):
        self.cart_items: List[Dict[str, Any]] = []
        self.loader = loader  # Optional DataLoader for shop info lookup
        self.kg_client = Neo4jKGClient()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def add_product(self, url: str, quantity: int = 1, size: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
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
    
    def add_product_direct(self, product_data: Dict[str, Any], quantity: int = 1, size: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
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
                    existing_item.get('selected_size') == size):
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
        """Scrape product details from URL.
        
        Args:
            url: Product URL
            
        Returns:
            Product information dict or None
        """
        try:
            if BeautifulSoup is None:
                logger.warning("BeautifulSoup not installed. URL scraping disabled for add_product().")
                return None

            # Detect shop from URL
            domain = urlparse(url).netloc.lower()
            shop_name = self._extract_shop_name(domain)
            
            # Fetch page
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract product details based on common patterns
            product = {
                'shop': shop_name,
                'domain': domain,
                'name': self._extract_name(soup, domain),
                'price': self._extract_price(soup, domain),
                'currency': self._extract_currency(soup, domain),
                'image': self._extract_image(soup, domain),
                'availability': self._extract_availability(soup),
                'description': self._extract_description(soup),
                'available_sizes': self._extract_available_sizes(soup),
                'shop_location': self._extract_shop_location(soup, domain),
                'shop_hours': self._extract_shop_hours(soup)
            }
            
            return product
            
        except requests.RequestException as e:
            logger.error(f"Network error fetching {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing product from {url}: {e}")
            return None
    
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
        elif 'amazon' in domain or '.com' in domain:
            return 'USD'
        elif 'amazon.eu' in domain or '.de' in domain or '.uk' in domain:
            return 'EUR'
        
        return 'USD'
    
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
        """Extract stock availability."""
        # Check for out of stock indicators
        out_of_stock_texts = ['out of stock', 'sold out', 'unavailable']
        
        text = soup.get_text().lower()
        for phrase in out_of_stock_texts:
            if phrase in text:
                return 'Out of Stock'
        
        # Check availability schema
        avail = soup.find('meta', {'itemprop': 'availability'})
        if avail:
            content = avail.get('content', '').lower()
            if 'instock' in content:
                return 'In Stock'
            elif 'outofstock' in content:
                return 'Out of Stock'
        
        return 'Available'
    
    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract product description."""
        # Try meta description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            desc = meta_desc['content']
            return desc[:200] + '...' if len(desc) > 200 else desc
        
        return ''
    
    def _extract_available_sizes(self, soup: BeautifulSoup) -> List[str]:
        """Extract available sizes for clothing/products."""
        sizes = []
        
        try:
            # Try to find size selector elements
            size_selectors = [
                'select[name*="size"] option',  # Select with options
                'button[data-size]',            # Size buttons
                'input[type="radio"][data-size]',  # Radio buttons
                '.size-option',                 # Generic class
                '[data-size]',                  # Generic data attr
            ]
            
            for selector in size_selectors:
                elements = soup.select(selector)
                for elem in elements:
                    size = elem.get_text(strip=True) or elem.get('data-size', '')
                    if size and size.lower() not in ['select', 'choose']:
                        sizes.append(size)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_sizes = []
            for size in sizes:
                if size not in seen:
                    seen.add(size)
                    unique_sizes.append(size)
            
            return unique_sizes[:10] if unique_sizes else []
            
        except Exception as e:
            logger.warning(f"Could not extract sizes: {e}")
            return []
    
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
