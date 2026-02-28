"""
Simple data loader utility to read products and provide filter functions.
"""
from pathlib import Path
import pandas as pd
import json
import os
from typing import List

from src.utils import synonyms

# Support both local and Docker environments
BASE_DIR = Path(os.getenv("DATA_DIR", "/app/data" if os.path.exists("/app/data") else "data"))
RAW_DIR = BASE_DIR / "raw"


class DataLoader:
    def __init__(self):
        self.products = None
        self.shops = None

    def _parse_style_tags(self, x) -> List[str]:
        try:
            if pd.isna(x):
                return []
            if isinstance(x, str) and x.strip().startswith('['):
                return json.loads(x)
            if isinstance(x, str):
                if ',' in x:
                    items = [t.strip() for t in x.split(',') if t.strip()]
                    return items
                if '|' in x:
                    return [t.strip() for t in x.split('|') if t.strip()]
                if ';' in x:
                    return [t.strip() for t in x.split(';') if t.strip()]
                return [x.strip()]
            return list(x)
        except Exception:
            return []

    def _normalize_value(self, val: str, synonyms_map: dict) -> str:
        if not isinstance(val, str) or not val:
            return val
        v = val.strip().lower()
        # direct canonical match
        for canon, opts in synonyms_map.items():
            if v == canon:
                return canon
            if v in [o.lower() for o in opts]:
                return canon
        return v

    def load_products(self, filename="final_products.csv"):
        path = RAW_DIR / filename
        df = pd.read_csv(path)

        # ensure shop_id is string for joins
        if 'shop_id' in df.columns:
            df['shop_id'] = df['shop_id'].astype(str)

        # normalize price column: many CSVs use price_LKR
        if 'price' not in df.columns and 'price_LKR' in df.columns:
            df['price'] = pd.to_numeric(df['price_LKR'], errors='coerce')
        else:
            if 'price' in df.columns:
                df['price'] = pd.to_numeric(df['price'], errors='coerce')

        # coerce popularity_score to float if present
        if 'popularity_score' in df.columns:
            df['popularity_score'] = pd.to_numeric(df['popularity_score'], errors='coerce')

        # parse style_tags into list
        if 'style_tags' in df.columns:
            df['style_tags'] = df['style_tags'].apply(self._parse_style_tags)
        else:
            df['style_tags'] = [[] for _ in range(len(df))]

        # normalized fields: category, color, fabric, style_tags (canonicalized)
        def norm_category(x):
            return self._normalize_value(x or '', synonyms.category_synonyms) if x else ''

        def norm_color(x):
            return self._normalize_value(x or '', synonyms.color_synonyms) if x else ''

        def norm_fabric(x):
            return self._normalize_value(x or '', synonyms.fabric_synonyms) if x else ''

        df['normalized_category'] = df['category'].apply(norm_category) if 'category' in df.columns else ''
        df['normalized_color'] = df['color'].apply(norm_color) if 'color' in df.columns else ''
        df['normalized_fabric'] = df['fabric'].apply(norm_fabric) if 'fabric' in df.columns else ''

        # normalize tags using style_synonyms
        def norm_tags(tag_list):
            out = []
            for t in tag_list or []:
                if not isinstance(t, str):
                    continue
                tt = t.strip().lower()
                replaced = False
                for canon, opts in synonyms.style_synonyms.items():
                    if tt == canon or tt in [o.lower() for o in opts]:
                        out.append(canon)
                        replaced = True
                        break
                if not replaced:
                    out.append(tt)
            return list(dict.fromkeys(out))

        df['normalized_style_tags'] = df['style_tags'].apply(norm_tags)

        # ensure price_LKR exists and is integer where possible
        if 'price_LKR' in df.columns:
            df['price_LKR'] = pd.to_numeric(df['price_LKR'], errors='coerce').astype('Int64')
        else:
            # fallback: copy from price if present
            df['price_LKR'] = pd.to_numeric(df['price'], errors='coerce').astype('Int64')

        # embedding placeholder
        df['embedding_vector'] = None

        self.products = df
        return df

    def load_shops(self, filename="shops_dataset.csv"):
        path = RAW_DIR / filename
        if not path.exists():
            return None
        df = pd.read_csv(path)
        if 'shop_id' in df.columns:
            df['shop_id'] = df['shop_id'].astype(str)
        self.shops = df
        return df

    def get_shops(self):
        """Get all shops dataframe."""
        if getattr(self, 'shops', None) is None:
            self.load_shops()
        return self.shops
    
    def get_shop(self, shop_id):
        if getattr(self, 'shops', None) is None:
            self.load_shops()
        if self.shops is None:
            return None
        sid = str(shop_id)
        row = self.shops[self.shops['shop_id'] == sid]
        if row.empty:
            return None
        return row.iloc[0].to_dict()

    def filter_products(self, category=None, color=None, max_price=None, tag=None, fabric=None):
        if self.products is None:
            raise RuntimeError("Products not loaded. Call load_products() first.")
        df = self.products
        # prefer normalized columns if available
        if category:
            # compare against normalized_category
            if 'normalized_category' in df.columns:
                df = df[df['normalized_category'].fillna('').str.lower() == str(category).lower()]
            else:
                df = df[df['category'].fillna('').str.lower() == str(category).lower()]
        if color:
            if 'normalized_color' in df.columns:
                df = df[df['normalized_color'].fillna('').str.lower() == str(color).lower()]
            else:
                df = df[df['color'].fillna('').str.lower() == str(color).lower()]
        if max_price:
            df = df[pd.to_numeric(df['price'], errors='coerce') <= max_price]
        if fabric:
            if 'normalized_fabric' in df.columns:
                df = df[df['normalized_fabric'].fillna('').str.lower() == str(fabric).lower()]
            else:
                df = df[df['fabric'].fillna('').str.lower() == str(fabric).lower()]
        if tag:
            # match against normalized_style_tags if present
            if 'normalized_style_tags' in df.columns:
                df = df[df['normalized_style_tags'].apply(lambda tags: str(tag).lower() in [t.lower() for t in tags])]
            else:
                df = df[df['style_tags'].apply(lambda tags: str(tag).lower() in [t.lower() for t in (tags or [])])]
        return df.copy()


if __name__ == '__main__':
    dl = DataLoader()
    print(dl.load_products().head())
