"""Size-level stock manager for product recommendations and cart operations."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


class StockManager:
    """Manages size stock for products keyed by product URL."""

    def __init__(self, stock_file_path: Path, inventory_file_path: Optional[Path] = None):
        self.stock_file_path = Path(stock_file_path)
        self.inventory_file_path = (
            Path(inventory_file_path)
            if inventory_file_path is not None
            else self.stock_file_path.with_name("mock_products_inventory.json")
        )
        self._lock = Lock()
        self._stock_by_url: Dict[str, Dict[str, int]] = {}
        self._inventory_by_url: Dict[str, Dict[str, Any]] = {}
        self._load()
        self._load_inventory()

    def _load(self) -> None:
        if not self.stock_file_path.exists():
            self._stock_by_url = {}
            return
        try:
            payload = json.loads(self.stock_file_path.read_text(encoding="utf-8"))
            self._stock_by_url = self._normalize_stock_map(payload)
        except Exception:
            self._stock_by_url = {}

    @staticmethod
    def _size_scale() -> List[str]:
        return ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "4XL", "5XL"]

    @classmethod
    def _canonical_size(cls, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        normalized = raw.upper().replace(" ", "")
        known = set(cls._size_scale())
        if normalized in known:
            return normalized
        if normalized in {"ONESIZE", "FREE SIZE", "FREESIZE"}:
            return "One Size"
        return raw

    @classmethod
    def _expand_size_label(cls, value: str) -> List[str]:
        text = str(value or "").strip()
        if not text:
            return []

        separators = ["-", " to ", "/", "–", "—"]
        for sep in separators:
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                if len(parts) != 2:
                    break
                start = cls._canonical_size(parts[0])
                end = cls._canonical_size(parts[1])
                scale = cls._size_scale()
                if start in scale and end in scale:
                    i1 = scale.index(start)
                    i2 = scale.index(end)
                    if i1 <= i2:
                        return scale[i1 : i2 + 1]
                    return scale[i2 : i1 + 1]
                break

        return [cls._canonical_size(text)]

    @staticmethod
    def _normalize_stock_map(payload: Any) -> Dict[str, Dict[str, int]]:
        if not isinstance(payload, dict):
            return {}
        normalized: Dict[str, Dict[str, int]] = {}
        for url, size_map in payload.items():
            if not isinstance(url, str) or not isinstance(size_map, dict):
                continue
            cleaned: Dict[str, int] = {}
            for size, count in size_map.items():
                try:
                    n = int(count)
                except Exception:
                    continue
                if not isinstance(size, str) or not size.strip():
                    continue
                for expanded in StockManager._expand_size_label(size):
                    if not expanded:
                        continue
                    cleaned[expanded] = max(cleaned.get(expanded, 0), max(0, n))
            if cleaned:
                normalized[url] = cleaned
        return normalized

    @staticmethod
    def _size_list_to_map(raw_sizes: Any) -> Dict[str, int]:
        mapped: Dict[str, int] = {}
        if not isinstance(raw_sizes, list):
            return mapped
        for item in raw_sizes:
            if not isinstance(item, dict):
                continue
            size = str(item.get("size") or "").strip()
            if not size:
                continue
            try:
                stock = int(item.get("stock", 0))
            except Exception:
                stock = 0
            for expanded in StockManager._expand_size_label(size):
                if not expanded:
                    continue
                mapped[expanded] = max(mapped.get(expanded, 0), max(0, stock))
        return mapped

    def _load_inventory(self) -> None:
        if not self.inventory_file_path.exists():
            self._inventory_by_url = {}
            return
        try:
            payload = json.loads(self.inventory_file_path.read_text(encoding="utf-8"))
        except Exception:
            self._inventory_by_url = {}
            return

        inventory_by_url: Dict[str, Dict[str, Any]] = {}
        inventory_changed = False
        if not isinstance(payload, list):
            self._inventory_by_url = {}
            return

        for record in payload:
            if not isinstance(record, dict):
                continue
            url = str(record.get("product_url") or "").strip()
            if not url:
                continue
            size_stock = self._size_list_to_map(record.get("sizes"))
            if size_stock:
                normalized_sizes = [
                    {"size": size, "stock": int(stock)}
                    for size, stock in sorted(size_stock.items())
                ]
                record_copy = dict(record)
                if record_copy.get("sizes") != normalized_sizes:
                    inventory_changed = True
                record_copy["sizes"] = normalized_sizes
                inventory_by_url[url] = record_copy
                self._stock_by_url[url] = size_stock

        self._inventory_by_url = inventory_by_url
        if inventory_by_url:
            self._persist()
            if inventory_changed:
                self._persist_inventory()

    def _persist(self) -> None:
        self.stock_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.stock_file_path.write_text(
            json.dumps(self._stock_by_url, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _persist_inventory(self) -> None:
        self.inventory_file_path.parent.mkdir(parents=True, exist_ok=True)
        records = [
            self._inventory_by_url[url]
            for url in sorted(self._inventory_by_url.keys())
        ]
        self.inventory_file_path.write_text(
            json.dumps(records, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _sync_inventory_sizes(self, product_url: str) -> None:
        record = self._inventory_by_url.get(product_url)
        if not isinstance(record, dict):
            return
        size_map = self._stock_by_url.get(product_url, {})
        record["sizes"] = [
            {"size": size, "stock": int(stock)}
            for size, stock in sorted(size_map.items())
        ]

    @staticmethod
    def _parse_sizes_from_product(product: Dict[str, Any]) -> List[str]:
        raw = product.get("size_range")
        if isinstance(raw, str) and raw.strip():
            sizes: List[str] = []
            for item in [s.strip() for s in raw.split(",") if s and s.strip()]:
                sizes.extend(StockManager._expand_size_label(item))
            return list(dict.fromkeys([s for s in sizes if s]))
        raw_sizes = product.get("available_sizes")
        if isinstance(raw_sizes, list):
            sizes: List[str] = []
            for item in raw_sizes:
                sizes.extend(StockManager._expand_size_label(str(item).strip()))
            return list(dict.fromkeys([s for s in sizes if s]))
        return []

    @staticmethod
    def _seed_count(url: str, size: str) -> int:
        # Deterministic pseudo stock count in [0, 8] without random module.
        return abs(hash(f"{url}|{size}")) % 9

    @staticmethod
    def _extract_brand_from_url(product_url: str) -> str:
        netloc = urlparse(product_url).netloc.lower()
        if netloc.startswith("www2."):
            netloc = netloc[5:]
        elif netloc.startswith("www."):
            netloc = netloc[4:]
        head = netloc.split(".")[0] if netloc else ""
        return head.upper() if head else "UNKNOWN"

    @staticmethod
    def _pick_event(style_tags: List[str], category: str) -> str:
        lower_tags = [t.lower() for t in style_tags]
        event_priorities = [
            "office wear",
            "business casual",
            "party wear",
            "beach wear",
            "festival",
            "travel friendly",
            "formal",
            "sporty",
            "streetwear",
        ]
        for event in event_priorities:
            if event in lower_tags:
                return event.title()
        return category.title() if category else "Casual"

    @staticmethod
    def _split_style_tags(product: Dict[str, Any]) -> List[str]:
        raw = product.get("style_tags")
        if isinstance(raw, list):
            return [str(t).strip() for t in raw if str(t).strip()]
        if isinstance(raw, str) and raw.strip():
            return [t.strip() for t in raw.split(",") if t.strip()]
        return []

    def _build_inventory_record(self, product: Dict[str, Any], size_map: Dict[str, int]) -> Dict[str, Any]:
        product_url = str(product.get("product_url") or "").strip()
        style_tags = self._split_style_tags(product)
        style_value = style_tags[0] if style_tags else str(product.get("category") or "Casual").title()
        category = str(product.get("category") or "").strip()
        return {
            "id": str(product.get("product_id") or "").strip(),
            "name": str(product.get("name") or "").strip(),
            "brand": self._extract_brand_from_url(product_url),
            "category": category,
            "color": str(product.get("color") or "").strip(),
            "price": float(product.get("price") or product.get("price_LKR") or 0.0),
            "style": style_value,
            "event": self._pick_event(style_tags, category),
            "product_url": product_url,
            "sizes": [
                {"size": size, "stock": int(stock)}
                for size, stock in sorted(size_map.items())
            ],
        }

    def ensure_seed_from_products(self, products: List[Dict[str, Any]]) -> None:
        # Backward-compatible wrapper for older call sites.
        self.ensure_inventory_from_products(products)

    def ensure_inventory_from_products(self, products: List[Dict[str, Any]]) -> None:
        stock_changed = False
        inventory_changed = False
        with self._lock:
            for product in products:
                if not isinstance(product, dict):
                    continue
                url = str(product.get("product_url") or "").strip()
                if not url:
                    continue
                sizes = self._parse_sizes_from_product(product)
                if not sizes:
                    continue
                if url not in self._stock_by_url:
                    self._stock_by_url[url] = {}
                for size in sizes:
                    if size not in self._stock_by_url[url]:
                        self._stock_by_url[url][size] = self._seed_count(url, size)
                        stock_changed = True

                desired_record = self._build_inventory_record(product, self._stock_by_url[url])
                current_record = self._inventory_by_url.get(url)
                if current_record != desired_record:
                    self._inventory_by_url[url] = desired_record
                    inventory_changed = True

            if stock_changed:
                self._persist()
            if inventory_changed:
                self._persist_inventory()

    def get_stock_map(self, product_url: str) -> Dict[str, int]:
        with self._lock:
            return dict(self._stock_by_url.get(str(product_url), {}))

    def get_available_sizes(self, product_url: str) -> List[str]:
        with self._lock:
            size_map = self._stock_by_url.get(str(product_url), {})
            return [size for size, count in size_map.items() if int(count) > 0]

    def get_size_stock(self, product_url: str, size: str) -> int:
        with self._lock:
            return int(self._stock_by_url.get(str(product_url), {}).get(str(size), 0))

    def reserve_size(self, product_url: str, size: str, quantity: int = 1) -> bool:
        qty = max(1, int(quantity))
        with self._lock:
            url_key = str(product_url)
            size_key = str(size)
            current = int(self._stock_by_url.get(url_key, {}).get(size_key, 0))
            if current < qty:
                return False
            self._stock_by_url[url_key][size_key] = current - qty
            self._sync_inventory_sizes(url_key)
            self._persist()
            self._persist_inventory()
            return True

    def release_size(self, product_url: str, size: str, quantity: int = 1) -> None:
        qty = max(1, int(quantity))
        with self._lock:
            url_key = str(product_url)
            size_key = str(size)
            if url_key not in self._stock_by_url:
                self._stock_by_url[url_key] = {}
            current = int(self._stock_by_url[url_key].get(size_key, 0))
            self._stock_by_url[url_key][size_key] = current + qty
            self._sync_inventory_sizes(url_key)
            self._persist()
            self._persist_inventory()

    def enrich_product(self, product: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(product, dict):
            return product
        url = str(product.get("product_url") or "").strip()
        if not url:
            return product
        stock_map = self.get_stock_map(url)
        if not stock_map:
            return product
        enriched = dict(product)
        enriched["size_stock"] = stock_map
        enriched["available_sizes"] = [s for s, c in stock_map.items() if int(c) > 0]
        return enriched

    def enrich_response_products(self, response: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(response, dict):
            return response
        updated = dict(response)
        for key in ("best_matches", "new_suggestions", "results"):
            values = updated.get(key)
            if isinstance(values, list):
                updated[key] = [self.enrich_product(p) if isinstance(p, dict) else p for p in values]
        return updated


def build_seed_products_from_loader(loader: Any) -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = []
    try:
        df = getattr(loader, "products", None)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                products.append(row.to_dict())
    except Exception:
        return []
    return products
