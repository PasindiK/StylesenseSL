"""Robust product scraping and checkout automation utilities.

This module is Playwright-first and keeps scraping resilient for dynamic pages.
It intentionally does not automate payment fields (card/cvv/tokens).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
import structlog
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_fixed

try:
    from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
except Exception:  # pragma: no cover - handled at runtime
    Page = Any
    PlaywrightTimeoutError = Exception
    sync_playwright = None

log = structlog.get_logger(__name__)


class ProductModel(BaseModel):
    title: str
    price: float
    image: Optional[str] = None
    sizes: List[str] = Field(default_factory=list)
    colors: List[str] = Field(default_factory=list)
    currency: str = "LKR"
    url: str
    availability: Optional[str] = None
    add_to_cart_url: Optional[str] = None
    buy_now_url: Optional[str] = None
    checkout_url: Optional[str] = None


class RobustProductAutomation:
    """Playwright-driven extractor with DOM/API/JSON-LD/meta fallbacks."""

    def __init__(self) -> None:
        self.ua = UserAgent()

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    def _dedupe(self, values: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for value in values:
            token = re.sub(r"\s+", " ", str(value or "")).strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
        return out

    def _parse_price(self, raw: Any) -> float:
        text = str(raw or "").strip()
        if not text:
            return 0.0

        # Normal path: parse a single numeric token with optional separators.
        cleaned = re.sub(r"[^0-9.,]", "", text)
        if cleaned.count('.') <= 1:
            try:
                return float(cleaned.replace(',', '')) if cleaned else 0.0
            except Exception:
                pass

        # Fallback for concatenated values like "5600.0031866.665600.00".
        # Pick the first plausible amount token instead of raising.
        candidates = re.findall(r"\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?", text)
        for candidate in candidates:
            normalized = candidate.replace(',', '')
            try:
                value = float(normalized)
            except Exception:
                continue
            if value > 0:
                return value

        return 0.0

    def _extract_jsonld(self, soup: BeautifulSoup) -> Dict[str, Any]:
        for script in soup.find_all("script", {"type": re.compile(r"application/ld\+json", re.I)}):
            raw = script.string or script.get_text(" ", strip=True)
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue

            def find_product(node: Any) -> Optional[Dict[str, Any]]:
                if isinstance(node, dict):
                    node_type = node.get("@type")
                    if isinstance(node_type, list):
                        types = [str(t).lower() for t in node_type]
                    else:
                        types = [str(node_type).lower()] if node_type else []
                    if "product" in types:
                        return node
                    for value in node.values():
                        found = find_product(value)
                        if found is not None:
                            return found
                elif isinstance(node, list):
                    for item in node:
                        found = find_product(item)
                        if found is not None:
                            return found
                return None

            product = find_product(payload)
            if not product:
                continue

            offers = product.get("offers")
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if not isinstance(offers, dict):
                offers = {}

            image = product.get("image")
            image_url = None
            if isinstance(image, list) and image:
                image_url = str(image[0])
            elif isinstance(image, str):
                image_url = image
            elif isinstance(image, dict):
                image_url = str(image.get("url") or "")

            raw_size = product.get("size")
            sizes: List[str] = []
            if isinstance(raw_size, list):
                sizes.extend([str(v) for v in raw_size])
            elif raw_size is not None:
                sizes.extend(re.split(r"[,/|]", str(raw_size)))

            raw_color = product.get("color")
            colors: List[str] = []
            if isinstance(raw_color, list):
                colors.extend([str(v) for v in raw_color])
            elif raw_color is not None:
                colors.extend(re.split(r"[,/|]", str(raw_color)))

            return {
                "title": str(product.get("name") or "").strip(),
                "price": self._parse_price(offers.get("price")),
                "currency": str(offers.get("priceCurrency") or "LKR").upper(),
                "image": image_url,
                "sizes": self._dedupe([s.strip() for s in sizes if str(s).strip()]),
                "colors": self._dedupe([c.strip() for c in colors if str(c).strip()]),
                "availability": str(offers.get("availability") or ""),
                "checkout_url": str(offers.get("url") or product.get("url") or "").strip() or None,
            }

        return {}

    def _extract_meta(self, soup: BeautifulSoup) -> Dict[str, Any]:
        title = ""
        title_candidates = [
            "h1",
            "[data-testid='product-title']",
            ".product-title",
            "meta[property='og:title']",
            "meta[name='twitter:title']",
        ]
        for selector in title_candidates:
            node = soup.select_one(selector)
            if not node:
                continue
            if node.name == "meta":
                title = str(node.get("content") or "").strip()
            else:
                title = node.get_text(" ", strip=True)
            if title:
                break

        price = 0.0
        for selector in [
            "[data-testid='product-price']",
            ".product-price",
            "[itemprop='price']",
            "meta[property='product:price:amount']",
            "meta[property='og:price:amount']",
        ]:
            node = soup.select_one(selector)
            if not node:
                continue
            raw = node.get("content") if node.name == "meta" else node.get_text(" ", strip=True)
            price = self._parse_price(raw)
            if price > 0:
                break

        image = None
        for selector in ["meta[property='og:image']", "img[src]", "[data-testid='product-image'] img"]:
            node = soup.select_one(selector)
            if not node:
                continue
            image = str(node.get("content") or node.get("src") or "").strip() or None
            if image:
                break

        sizes = self._extract_option_values(
            soup,
            [
                "button[data-size]",
                ".size-selector button",
                "select[name*='size' i] option",
                "[aria-label*='size' i]",
                "[data-testid*='size' i] button",
            ],
            ["data-size", "value", "aria-label"],
        )
        colors = self._extract_option_values(
            soup,
            [
                "button[data-color]",
                ".color-selector button",
                "select[name*='color' i] option",
                "[aria-label*='color' i]",
                "[data-testid*='color' i] button",
            ],
            ["data-color", "value", "aria-label"],
        )

        return {
            "title": title,
            "price": price,
            "image": image,
            "sizes": sizes,
            "colors": colors,
        }

    def _extract_option_values(self, soup: BeautifulSoup, selectors: List[str], attrs: List[str]) -> List[str]:
        values: List[str] = []
        for selector in selectors:
            for node in soup.select(selector):
                raw = ""
                for attr in attrs:
                    raw = str(node.get(attr) or "").strip()
                    if raw:
                        break
                if not raw:
                    raw = node.get_text(" ", strip=True)
                if not raw:
                    continue
                low = raw.lower()
                class_text = " ".join(node.get("class", [])).lower()
                if low in {"select", "choose", "size", "color", "colour"}:
                    continue
                if "disabled" in class_text or node.has_attr("disabled"):
                    continue
                values.append(raw)
        return self._dedupe(values)

    def _fallback_requests_html(self, url: str) -> str:
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.text

    def _extract_product_api_payload(self, responses: List[Tuple[str, str]]) -> Dict[str, Any]:
        for url, body in responses:
            if "product" not in url.lower() and "variant" not in url.lower():
                continue
            try:
                payload = json.loads(body)
            except Exception:
                continue

            if isinstance(payload, dict):
                title = str(payload.get("title") or payload.get("name") or "").strip()
                price = self._parse_price(payload.get("price") or payload.get("amount"))
                image = payload.get("image")
                if isinstance(image, dict):
                    image = image.get("url")
                sizes = payload.get("sizes") or payload.get("available_sizes") or []
                colors = payload.get("colors") or payload.get("available_colors") or []
                variants = payload.get("variants") or []
                if isinstance(variants, list):
                    for variant in variants:
                        if not isinstance(variant, dict):
                            continue
                        option = str(variant.get("option") or variant.get("size") or "").strip()
                        if option:
                            sizes.append(option)
                        color = str(variant.get("color") or "").strip()
                        if color:
                            colors.append(color)
                if title or price:
                    return {
                        "title": title,
                        "price": price,
                        "image": str(image or "").strip() or None,
                        "sizes": self._dedupe([str(v).strip() for v in sizes if str(v).strip()]),
                        "colors": self._dedupe([str(v).strip() for v in colors if str(v).strip()]),
                    }
        return {}

    def _render_with_playwright(self, url: str) -> Tuple[str, Dict[str, Any]]:
        if sync_playwright is None:
            raise RuntimeError("Playwright is not installed")

        network_json: List[Tuple[str, str]] = []
        headers = self._headers()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=headers["User-Agent"], extra_http_headers=headers)
            page = context.new_page()

            def on_response(resp: Any) -> None:
                try:
                    ctype = str(resp.headers.get("content-type") or "").lower()
                    if "json" not in ctype:
                        return
                    body = resp.text()
                    network_json.append((str(resp.url), body))
                except Exception:
                    return

            page.on("response", on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=25000)
            except PlaywrightTimeoutError:
                log.warning("networkidle_timeout", url=url)

            # Lazy-load handling
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(700)

            # Wait for common product selectors.
            selector_candidates = ["h1", "[data-testid='product-title']", ".product-title", "[itemprop='name']"]
            for selector in selector_candidates:
                try:
                    page.wait_for_selector(selector, timeout=1500)
                    break
                except Exception:
                    continue

            html = page.content()
            api_data = self._extract_product_api_payload(network_json)
            context.close()
            browser.close()
            return html, api_data

    def _to_result(self, url: str, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        title = str(data.get("title") or "").strip()
        price = float(data.get("price") or 0.0)
        sizes = self._dedupe([str(v) for v in (data.get("sizes") or [])])
        colors = self._dedupe([str(v) for v in (data.get("colors") or [])])
        currency = str(data.get("currency") or "LKR").upper()

        parsed = ProductModel(
            title=title or "Unknown Product",
            price=price,
            image=data.get("image"),
            sizes=sizes,
            colors=colors,
            currency=currency,
            url=url,
            availability=data.get("availability"),
            add_to_cart_url=data.get("add_to_cart_url"),
            buy_now_url=data.get("buy_now_url"),
            checkout_url=data.get("checkout_url"),
        )

        domain = urlparse(url).netloc
        return {
            "name": parsed.title,
            "title": parsed.title,
            "price": parsed.price,
            "image": parsed.image,
            "available_sizes": parsed.sizes,
            "available_colors": parsed.colors,
            "variants": {"sizes": parsed.sizes, "colors": parsed.colors},
            "currency": parsed.currency,
            "url": parsed.url,
            "shop": domain,
            "seller": domain,
            "domain": domain,
            "availability": parsed.availability or "Unknown",
            "shipping_availability": "Check at checkout",
            "add_to_cart_url": parsed.add_to_cart_url,
            "buy_now_url": parsed.buy_now_url,
            "checkout_url": parsed.checkout_url,
            "source": source,
        }

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def scrape_product(self, url: str) -> Dict[str, Any]:
        """Scrape product details with fallback order:
        1) API extraction from Playwright network responses
        2) Playwright DOM scraping
        3) JSON-LD extraction
        4) Meta/DOM extraction
        """
        log.info("scrape_start", url=url)

        html = ""
        api_data: Dict[str, Any] = {}

        # Prefer Playwright-rendered data first.
        try:
            html, api_data = self._render_with_playwright(url)
        except Exception as exc:
            log.warning("playwright_render_failed", url=url, error=str(exc))

        if not html:
            html = self._fallback_requests_html(url)

        soup = BeautifulSoup(html, "lxml")

        # 1) API data
        if api_data.get("title") and float(api_data.get("price") or 0.0) > 0:
            result = self._to_result(url, api_data, source="api")
            log.info("scrape_success", url=url, source="api")
            return result

        # 2) Playwright DOM/meta extraction
        dom_data = self._extract_meta(soup)

        # 3) JSON-LD
        jsonld_data = self._extract_jsonld(soup)

        # Merge, preferring stronger sources.
        merged = {
            "title": jsonld_data.get("title") or dom_data.get("title"),
            "price": jsonld_data.get("price") or dom_data.get("price"),
            "image": jsonld_data.get("image") or dom_data.get("image"),
            "sizes": self._dedupe([*(jsonld_data.get("sizes") or []), *(dom_data.get("sizes") or [])]),
            "colors": self._dedupe([*(jsonld_data.get("colors") or []), *(dom_data.get("colors") or [])]),
            "currency": jsonld_data.get("currency") or "LKR",
            "availability": jsonld_data.get("availability"),
            "checkout_url": jsonld_data.get("checkout_url"),
        }

        missing_fields: List[str] = []
        if not merged.get("title"):
            missing_fields.append("title")
        if not float(merged.get("price") or 0.0):
            missing_fields.append("price")
        if missing_fields:
            log.warning("missing_required_fields", url=url, missing=missing_fields)

        result = self._to_result(url, merged, source="dom_jsonld")
        if result.get("name") == "Unknown Product" and float(result.get("price") or 0) <= 0:
            log.warning("partial_product_data", url=url, reason="required_fields_unresolved")

        log.info("scrape_success", url=url, source=result.get("source"))
        return result

    def apply_product_selections(self, page: Page, size: Optional[str], color: Optional[str], quantity: Optional[int]) -> Dict[str, Any]:
        """Interact with size/color/quantity controls without touching payment fields."""
        filled: List[str] = []

        def click_by_text(candidates: List[str], value: Optional[str], field: str) -> None:
            if not value:
                return
            for selector in candidates:
                try:
                    node = page.locator(f"{selector}:has-text('{value}')").first
                    if node.count() > 0 and node.is_visible(timeout=500):
                        node.click(timeout=1000, force=True)
                        filled.append(field)
                        return
                except Exception:
                    continue

        click_by_text(["button", "label", "[role='option']", "[role='radio']"], size, "size")
        click_by_text(["button", "label", "[role='option']", "[role='radio']"], color, "color")

        if quantity and quantity > 0:
            for selector in ["input[name*='quantity' i]", "input[id*='quantity' i]"]:
                try:
                    qty_input = page.locator(selector).first
                    if qty_input.count() > 0 and qty_input.is_visible(timeout=500):
                        qty_input.fill(str(quantity), timeout=1000)
                        filled.append("quantity")
                        break
                except Exception:
                    continue

        return {"filled_fields": self._dedupe(filled)}

    def prefill_checkout_non_payment(self, page: Page, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Fill contact/shipping fields and skip card/cvv/payment token fields."""
        filled: List[str] = []

        def fill(selectors: List[str], value: Optional[str], field: str) -> None:
            if not value:
                return
            for selector in selectors:
                try:
                    node = page.locator(selector).first
                    if node.count() > 0 and node.is_visible(timeout=500):
                        node.fill(str(value), timeout=1000)
                        filled.append(field)
                        return
                except Exception:
                    continue

        fill(["input[name*='name' i]", "input[id*='name' i]"], profile.get("name"), "name")
        fill(["input[type='email']", "input[name*='email' i]"], profile.get("email"), "email")
        fill(["input[type='tel']", "input[name*='phone' i]"], profile.get("phone"), "phone")
        fill(["textarea[name*='address' i]", "input[name*='address' i]"], profile.get("shipping_address"), "shipping_address")

        # iframe detection for checkout forms
        for frame in page.frames:
            frame_url = str(frame.url or "").lower()
            if "checkout" not in frame_url:
                continue
            fill_in_frame = [
                ("input[type='email']", profile.get("email"), "email_iframe"),
                ("input[name*='address' i]", profile.get("shipping_address"), "shipping_address_iframe"),
            ]
            for selector, value, field in fill_in_frame:
                if not value:
                    continue
                try:
                    node = frame.locator(selector).first
                    if node.count() > 0 and node.is_visible(timeout=400):
                        node.fill(str(value), timeout=1000)
                        filled.append(field)
                except Exception:
                    continue

        return {"filled_fields": self._dedupe(filled)}
