"""
Medallion Architecture Demo
Shows: Bronze → Silver → Gold layers in Azure Blob Storage
"""
import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.medallion_uploader import get_azure_connection_string, create_containers_if_not_exist
from pipeline.ingestion.api_medallion_consumer import MedallionPipeline


def demo_1_azure_connection():
    """Demo 1: Verify Azure connection"""
    print("\n" + "="*70)
    print("DEMO 1: VERIFY AZURE BLOB CONNECTION".center(70))
    print("="*70)
    
    try:
        from azure.storage.blob import BlobServiceClient
        
        conn_str = get_azure_connection_string()
        if not conn_str:
            print("✗ Connection string not found in .env")
            return False
        
        client = BlobServiceClient.from_connection_string(conn_str)
        account_info = client.get_account_information()
        
        print(f"✓ Connected to Azure Storage Account")
        print(f"  SKU: {account_info['sku_name']}")
        print(f"  Account Kind: {account_info['account_kind']}")
        return True
    
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


def demo_2_list_containers_and_files():
    """Demo 2: List all medallion layer containers and files"""
    print("\n" + "="*70)
    print("DEMO 2: LIST MEDALLION LAYERS & FILES IN AZURE BLOB".center(70))
    print("="*70)
    
    try:
        from azure.storage.blob import BlobServiceClient
        
        conn_str = get_azure_connection_string()
        client = BlobServiceClient.from_connection_string(conn_str)
        
        layers = ['bronze', 'silver', 'gold']
        
        for layer in layers:
            try:
                container_client = client.get_container_client(layer)
                blobs = list(container_client.list_blobs())
                
                print(f"\n📦 {layer.upper()} Layer: {len(blobs)} files")
                
                total_size = 0
                for blob in blobs[-5:]:  # Show last 5
                    size_kb = blob.size / 1024
                    total_size += blob.size
                    print(f"   • {blob.name} ({size_kb:.1f} KB)")
                
                if len(blobs) > 5:
                    print(f"   ... and {len(blobs) - 5} more files")
                
                total_size_mb = total_size / (1024 * 1024)
                print(f"   Total size: {total_size_mb:.2f} MB")
            
            except Exception as e:
                print(f"   ✗ {layer}: {e}")
    
    except Exception as e:
        print(f"✗ Failed to list containers: {e}")


def demo_3_read_and_display_samples():
    """Demo 3: Read sample data from each layer"""
    print("\n" + "="*70)
    print("DEMO 3: SAMPLE DATA FROM EACH LAYER".center(70))
    print("="*70)
    
    try:
        from azure.storage.blob import BlobServiceClient
        import io
        
        conn_str = get_azure_connection_string()
        client = BlobServiceClient.from_connection_string(conn_str)
        
        layers = ['bronze', 'silver', 'gold']
        
        for layer in layers:
            try:
                container_client = client.get_container_client(layer)
                blobs = list(container_client.list_blobs())
                
                if not blobs:
                    print(f"\n{layer.upper()}: No data yet")
                    continue
                
                # Download latest blob
                latest_blob = blobs[-1]
                print(f"\n{layer.upper()}: Reading {latest_blob.name}")
                
                blob_client = container_client.get_blob_client(latest_blob.name)
                download_stream = blob_client.download_blob()
                
                # Read as parquet
                df = pd.read_parquet(io.BytesIO(download_stream.readall()))
                
                print(f"  Shape: {df.shape[0]} rows × {df.shape[1]} columns")
                print(f"  Columns: {', '.join(df.columns[:5].tolist())}...")
                print(f"\n  First 2 rows:")
                print(df.head(2).to_string())
            
            except Exception as e:
                print(f"  ✗ Error reading {layer}: {e}")
    
    except Exception as e:
        print(f"✗ Failed to read samples: {e}")


def demo_4_run_pipeline():
    """Demo 4: Run a live pipeline"""
    print("\n" + "="*70)
    print("DEMO 4: RUN LIVE MEDALLION PIPELINE".center(70))
    print("="*70)
    
    pipeline = MedallionPipeline()
    pipeline.run_continuous(num_batches=2, interval_seconds=1)


def demo_5_show_transformations():
    """Demo 5: Show data transformations across layers"""
    print("\n" + "="*70)
    print("DEMO 5: DATA TRANSFORMATIONS (CSV → BRONZE → SILVER → GOLD)".center(70))
    print("="*70)
    
    # Load original CSV
    csv_path = 'data/transactions_dataset.csv'
    try:
        csv_df = pd.read_csv(csv_path)
        print(f"\n📄 CSV (Original): {len(csv_df)} records")
        print(f"   Sample:")
        print(f"   {csv_df.iloc[0].to_dict()}")
    except Exception as e:
        print(f"✗ Could not read CSV: {e}")
    
    # Load from Bronze
    print(f"\n🟫 BRONZE (Raw): CSV + metadata")
    print(f"   • Added: batch_id, ingested_at, source")
    
    # Load from Silver  
    print(f"\n🟪 SILVER (Cleaned): Bronze + cleaning")
    print(f"   • Removed duplicates")
    print(f"   • Fixed data types")
    print(f"   • Added: cleaned_at, data_quality_score")
    
    # Load from Gold
    print(f"\n🟨 GOLD (Curated): Silver + business logic")
    print(f"   • Added: amount_tier (Small/Medium/Large)")
    print(f"   • Added: enriched_at, source_layer")
    print(f"   • Ready for dashboards & analytics")


def demo_6_show_azure_urls():
    """Demo 6: Show direct Azure Blob URLs for verification"""
    print("\n" + "="*70)
    print("DEMO 6: AZURE BLOB URLS FOR MANUAL VERIFICATION".center(70))
    print("="*70)
    
    try:
        from azure.storage.blob import BlobServiceClient
        
        conn_str = get_azure_connection_string()
        from urllib.parse import urlparse
        
        # Extract account name from connection string
        params = dict(param.split('=', 1) for param in conn_str.split(';') if '=' in param)
        account_name = params.get('AccountName', 'unknown')
        
        layers = ['bronze', 'silver', 'gold']
        
        print(f"\nAzure Storage Account: {account_name}")
        print(f"\nDirect URLs to access from Azure Portal:")
        
        for layer in layers:
            url = f"https://{account_name}.blob.core.windows.net/{layer}/"
            print(f"\n{layer.upper()}:")
            print(f"  {url}")
            print(f"  → View in Portal: https://portal.azure.com")
    
    except Exception as e:
        print(f"✗ Could not generate URLs: {e}")


def main():
    """Run all demos"""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " MEDALLION ARCHITECTURE DEMO - AZURE BLOB STORAGE ".center(68) + "║")
    print("╚" + "="*68 + "╝")
    
    demos = [
        ("Azure Connection", demo_1_azure_connection),
        ("List Containers & Files", demo_2_list_containers_and_files),
        ("Read Sample Data", demo_3_read_and_display_samples),
        ("Live Pipeline", demo_4_run_pipeline),
        ("Show Transformations", demo_5_show_transformations),
        ("Azure URLs", demo_6_show_azure_urls),
    ]
    
    for i, (name, demo_func) in enumerate(demos, 1):
        try:
            demo_func()
        except KeyboardInterrupt:
            print(f"\n⏸ Demo interrupted by user")
            break
        except Exception as e:
            print(f"\n✗ Demo {i} failed: {e}")
    
    print("\n" + "="*70)
    print("DEMO COMPLETE".center(70))
    print("="*70)
    print("\nNext steps:")
    print("  1. Check Azure Portal: https://portal.azure.com")
    print("  2. Navigate to Storage Account → Containers")
    print("  3. View bronze/, silver/, gold/ containers")
    print("  4. Download & inspect .parquet files")
    print("  5. Connect Power BI to gold/ layer for dashboards")
    print("\n")


if __name__ == '__main__':
    main()
