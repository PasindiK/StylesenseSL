import os
from scripts.logger import setup_logger

logger = setup_logger(__name__)

def create_layer_structure():
    """Create Bronze, Silver, Gold layer folders"""
    
    layers = {
        'bronze': ['raw'],
        'silver': ['cleaned', 'enriched'],
        'gold': ['curated', 'analytics']
    }
    
    print("\n" + "="*70)
    print("CREATING MEDALLION ARCHITECTURE LAYER STRUCTURE")
    print("="*70 + "\n")
    
    for layer, sublayers in layers.items():
        for sublayer in sublayers:
            folder_path = os.path.join(layer, sublayer)
            
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                print(f"Created: {folder_path}/")
                logger.info(f"Created directory: {folder_path}")
            else:
                print(f"Already exists: {folder_path}/")
                logger.info(f"Directory already exists: {folder_path}")
    
    print("\n" + "="*70)
    print("LAYER STRUCTURE CREATED SUCCESSFULLY")
    print("="*70)
    print("""
    Your data will flow through:
    
    raw_data.csv
        ↓ (Bronze Layer - Raw Storage)
    bronze/raw/
        ↓ (Script: 02_bronze_to_silver_cleanse.py)
    silver/cleaned/ + silver/enriched/
        ↓ (Silver Layer - Clean & Transform)
        ↓ (Script: 03_silver_to_gold_curate.py)
    gold/curated/ + gold/analytics/
        ↓ (Gold Layer - Business Ready)
        ↓ (Ready for dashboards, analytics, reporting)
    """)
    print("="*70 + "\n")

if __name__ == "__main__":
    create_layer_structure()
