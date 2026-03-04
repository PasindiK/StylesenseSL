# scripts/s05_gold_embeddings.py
import os
import pandas as pd
from datetime import datetime
from sentence_transformers import SentenceTransformer
import pyarrow as pa
import pyarrow.parquet as pq

GOLD_DIR = "gold/curated"
EMBEDDING_FILE = os.path.join(GOLD_DIR, "product_embeddings_gold.parquet")
os.makedirs(GOLD_DIR, exist_ok=True)

def generate_product_embeddings():
    print("\nGenerating Product Embeddings...")

    # Load curated search index from GOLD
    search_index_path = os.path.join(GOLD_DIR, "search_index_gold.csv")
    if not os.path.exists(search_index_path):
        raise FileNotFoundError(f"Search index not found: {search_index_path}")
    
    df = pd.read_csv(search_index_path)

    # Combine product text fields for embeddings
    df["text"] = (
        df["name"].astype(str) + " " +
        df["category"].astype(str) + " " +
        df["color"].astype(str) + " " +
        df["fabric"].astype(str) + " " +
        df["semantic_tags"].astype(str)
    )

    # Load sentence transformer model
    print("  Loading embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Generate embeddings
    print("  Generating embeddings...")
    embeddings = model.encode(df["text"].tolist(), convert_to_numpy=True)

    # Prepare PyArrow table
    print("  Saving embeddings to Parquet...")
    table = pa.table({
        "product_id": df["product_id"].tolist(),
        "embedding": embeddings.tolist(),
        "_curated_at": [datetime.now().isoformat()] * len(df),
        "_dataset_type": ["product_embeddings"] * len(df)
    })

    pq.write_table(table, EMBEDDING_FILE)

    print(f"Saved: {EMBEDDING_FILE}")
    print(f"Total Embeddings: {len(df)}")

    return EMBEDDING_FILE

# ------------------------
# --- Main Execution ---
# ------------------------
if __name__ == "__main__":
    print("\n" + "="*70)
    print("GOLD VECTOR EMBEDDINGS")
    print("="*70)

    generate_product_embeddings()

    print("\n" + "="*70)
    print("EMBEDDING GENERATION COMPLETE")
    print("="*70 + "\n")
