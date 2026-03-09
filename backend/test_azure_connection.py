"""
Test Azure Blob Storage Connection
Run this after setting up AZURE_STORAGE_CONNECTION_STRING in .env
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_azure_connection():
    """Test if Azure connection string is configured and working"""
    
    # Try to load from .env file
    env_path = project_root / '.env'
    conn_str = None
    
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('AZURE_STORAGE_CONNECTION_STRING='):
                    conn_str = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break
    
    # Also check environment variable
    if not conn_str:
        conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    
    if not conn_str or conn_str == 'your_actual_connection_string_here':
        print("❌ ERROR: Azure Storage connection string not configured!")
        print("\n📝 Please update the AZURE_STORAGE_CONNECTION_STRING in backend/.env")
        print("   You can find it in Azure Portal > Storage Account > Access keys\n")
        return False
    
    print("✅ Found Azure connection string in configuration")
    print(f"   Account: {conn_str.split('AccountName=')[1].split(';')[0] if 'AccountName=' in conn_str else 'Unknown'}")
    
    # Try to connect
    try:
        from azure.storage.blob import BlobServiceClient
        print("\n🔄 Testing connection to Azure Blob Storage...")
        
        client = BlobServiceClient.from_connection_string(conn_str)
        
        # List containers
        containers = list(client.list_containers())
        print(f"✅ Successfully connected to Azure Blob Storage!")
        print(f"   Found {len(containers)} containers:")
        
        for container in containers:
            print(f"   - {container.name}")
            
            # List a few blobs in each container
            container_client = client.get_container_client(container.name)
            blobs = list(container_client.list_blobs())
            
            if blobs:
                print(f"     ({len(blobs)} blob(s) - showing first 5):")
                for blob in blobs[:5]:
                    size_mb = blob.size / (1024 * 1024) if blob.size else 0
                    tier = getattr(blob, 'blob_tier', 'N/A')
                    print(f"       • {blob.name} ({size_mb:.2f} MB, tier: {tier})")
            else:
                print(f"     (Empty container)")
        
        print("\n✅ Azure Blob Storage is properly configured and working!")
        print("   Your backend will now fetch real data from Azure instead of mock data.\n")
        return True
        
    except ImportError:
        print("\n❌ ERROR: Azure Storage SDK not installed")
        print("   Run: pip install azure-storage-blob azure-identity\n")
        return False
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to connect to Azure Storage")
        print(f"   {str(e)}")
        print("\n💡 Please check:")
        print("   1. Your connection string is correct")
        print("   2. Your storage account exists")
        print("   3. You have network access to Azure\n")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("  Azure Blob Storage Connection Test")
    print("=" * 70)
    print()
    
    success = test_azure_connection()
    
    sys.exit(0 if success else 1)
