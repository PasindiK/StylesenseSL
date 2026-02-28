from pathlib import Path
import pandas as pd
from src.ingestion.data_loader import DataLoader

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "raw"


def test_load_products_and_parse_tags():
    loader = DataLoader()
    # load sample products.csv from the workspace data/raw
    loader.load_products("products.csv")
    df = loader.products
    # basic sanity checks
    assert 'product_id' in df.columns
    assert 'style_tags' in df.columns
    # parsed tags must be a list for the first row
    first_tags = df.iloc[0]['style_tags']
    assert isinstance(first_tags, list)
    # price numeric coercion: price column should exist and be numeric
    assert 'price' in df.columns
    assert pd.api.types.is_numeric_dtype(df['price'])
