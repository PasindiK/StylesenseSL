"""
Initialize Tier Metadata in Azure
Creates tier-metadata container and syncs current blob tier assignments
"""
import os
import sys
from pathlib import Path

# Add storage path to sys.path
storage_path = Path(__file__).parent
sys.path.insert(0, str(storage_path))

from seasonal_tier_manager import SeasonalTierManager


def initialize_tier_metadata():
    """Initialize tier metadata in Azure"""
    
    # Get Azure connection string
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    
    if not conn_str:
        # Try loading from .env
        env_file = storage_path.parent / '.env'
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            if key.strip() == 'AZURE_STORAGE_CONNECTION_STRING':
                                conn_str = value.strip().strip('"').strip("'")
                                break
            except Exception:
                pass
    
    if not conn_str:
        print("❌ Error: AZURE_STORAGE_CONNECTION_STRING not set")
        print("\nPlease set the environment variable:")
        print("  export AZURE_STORAGE_CONNECTION_STRING='your-connection-string'")
        print("\nOr add it to backend/src/services/data_architecture/.env")
        return False
    
    print("🚀 Initializing Tier Metadata in Azure...\n")
    
    try:
        # Create manager
        manager = SeasonalTierManager(conn_str)
        
        # Print current season strategy
        print("1️⃣  Current Season Strategy:")
        print("="*70)
        season, season_desc = manager.get_current_season()
        print(f"📅 Season: {season_desc}")
        print(f"🏷️  Season Code: {season.value}")
        
        for layer in ['bronze', 'silver', 'gold']:
            strategy = manager.get_medallion_tier_strategy(layer, season)
            print(f"\n{layer.upper()}:")
            print(f"  Tier: {strategy['tier'].value.upper()}")
            print(f"  Retention: {strategy['retention_days']} days")
            print(f"  Reason: {strategy['reason']}")
        
        print("\n" + "="*70 + "\n")
        
        # Scan and sync tier assignments
        print("2️⃣  Scanning Azure Blob Storage...")
        assignments = manager.sync_tier_assignments_from_azure()
        
        print(f"\n✅ Synced Tier Assignments:")
        print(f"   Hot tier:     {len(assignments['hot'])} datasets")
        print(f"   Warm tier:    {len(assignments['warm'])} datasets")
        print(f"   Cold tier:    {len(assignments['cold'])} datasets")
        print(f"   Archive tier: {len(assignments['archive'])} datasets")
        
        if assignments['hot']:
            print(f"\n   Hot datasets: {', '.join(assignments['hot'][:5])}")
            if len(assignments['hot']) > 5:
                print(f"                 ...and {len(assignments['hot']) - 5} more")
        
        print(f"\n   Last Updated: {assignments['last_updated']}")
        print(f"   Current Season: {assignments['season']}")
        
        print("\n3️⃣  Tier-Metadata Container Created:")
        print("   ✓ current_tier_assignments.json")
        print("   ✓ history/tier_assignments_YYYYMM.jsonl")
        
        print("\n" + "="*70)
        print("🎉 Tier metadata initialized successfully!")
        print("="*70)
        
        print("\n📊 You can now:")
        print("   • View tiers in dashboard: http://localhost:5174 (Storage Tiers page)")
        print("   • Query API: http://localhost:8003/api/storage-tiers/current")
        print("   • Check Azure portal for 'tier-metadata' container")
        
        return True
    
    except Exception as e:
        print(f"\n❌ Error initializing tier metadata: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = initialize_tier_metadata()
    sys.exit(0 if success else 1)
