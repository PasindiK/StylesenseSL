"""
Sample ingestion script to load CSVs into Postgres using SQLAlchemy.
Configure the DATABASE_URL environment variable before running.
"""
import os
from sqlalchemy import create_engine
import pandas as pd
from pathlib import Path

RAW_DIR = Path("C:/TEST_RP/data/raw")
DATABASE_URL = os.environ.get('DATABASE_URL')  # e.g. postgresql://user:pass@localhost:5432/db
if not DATABASE_URL:
    raise SystemExit("Please set DATABASE_URL environment variable before running.")

engine = create_engine(DATABASE_URL)

for csv_file in RAW_DIR.glob('*.csv'):
    table_name = csv_file.stem.lower()
    print(f"Loading {csv_file} -> {table_name}")
    df = pd.read_csv(csv_file)
    # Basic type coercion could be added here
    df.to_sql(table_name, engine, if_exists='replace', index=False)

print("Ingestion complete.")
