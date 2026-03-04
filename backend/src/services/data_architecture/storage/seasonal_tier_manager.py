"""
Seasonal Storage Tier Management for Sri Lankan Fashion Retail
Manages medallion layers based on business seasons, not just time
"""
import os
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
from azure.storage.blob import BlobServiceClient, StandardBlobTier

logger = logging.getLogger(__name__)


class BusinessSeason(Enum):
    """Sri Lankan business seasons for fashion retail"""
    FESTIVE_SEASON = "festive"           # Peak demand (Holidays, Poya)
    MONSOON_SEASON = "monsoon"           # Moderate demand (Weather impacts)
    DRY_SEASON = "dry"                   # Lower demand (Off-season)
    HISTORICAL_ARCHIVE = "historical"    # Yearly previous data


class SeasonalTierManager:
    """
    Manages storage tiers based on Sri Lankan business seasons
    Links medallion layers to seasonal demand patterns
    """
    
    def __init__(self, azure_connection_string: str):
        self.conn_str = azure_connection_string
        self.client = BlobServiceClient.from_connection_string(azure_connection_string)
        
        # Define seasonal calendar for Sri Lanka
        self.season_calendar = {
            # Month (1-12) → Season
            1: BusinessSeason.FESTIVE_SEASON,      # New Year
            2: BusinessSeason.DRY_SEASON,          # Post-monsoon
            3: BusinessSeason.DRY_SEASON,          # Dry season
            4: BusinessSeason.FESTIVE_SEASON,      # Sinhala & Tamil New Year
            5: BusinessSeason.MONSOON_SEASON,      # Southwest monsoon begins
            6: BusinessSeason.MONSOON_SEASON,      # Monsoon peak
            7: BusinessSeason.MONSOON_SEASON,      # Monsoon
            8: BusinessSeason.MONSOON_SEASON,      # Monsoon
            9: BusinessSeason.MONSOON_SEASON,      # End of monsoon
            10: BusinessSeason.DRY_SEASON,         # Post-monsoon
            11: BusinessSeason.DRY_SEASON,         # Dry season begins
            12: BusinessSeason.FESTIVE_SEASON,     # Christmas & New Year
        }
        
        # Poya (full moon) dates & special holidays (approximate)
        self.festive_dates = {
            (1, 14): "Thai Pongal",
            (2, 5): "Independence Day",
            (4, 13): "Sinhala & Tamil New Year",
            (5, 1): "Labour Day",
            (8, 15): "Assumption Day",
            (10, 31): "Deepavali",
            (12, 25): "Christmas",
        }
        
        # Tier pricing & latency
        self.tier_config = {
            StandardBlobTier.HOT: {
                "cost": "$$$$",
                "latency_ms": 50,
                "use_case": "Real-time dashboards, AI predictions",
                "description": "Peak season - high-frequency access"
            },
            StandardBlobTier.COOL: {
                "cost": "$$$",
                "latency_ms": 500,
                "use_case": "Weekly reports, moderate analysis",
                "description": "Off-season or monsoon - moderate access"
            },
            StandardBlobTier.ARCHIVE: {
                "cost": "$",
                "latency_ms": 5000,
                "use_case": "Historical trends, year-over-year comparison",
                "description": "Historical data from previous seasons"
            }
        }
    
    def get_current_season(self) -> Tuple[BusinessSeason, str]:
        """
        Determine current business season
        
        Returns:
            (Season enum, Description)
        """
        now = datetime.now()
        month = now.month
        
        # Check for special festive dates
        if (now.month, now.day) in self.festive_dates:
            holiday = self.festive_dates[(now.month, now.day)]
            return BusinessSeason.FESTIVE_SEASON, f"Festive: {holiday}"
        
        # Default seasonal assignment
        season = self.season_calendar.get(month, BusinessSeason.DRY_SEASON)
        return season, f"{season.value.title()} Season (Month {month})"
    
    def get_tier_for_season(self, season: BusinessSeason) -> Tuple[StandardBlobTier, str]:
        """
        Get Azure storage tier based on business season
        
        Returns:
            (Tier, Business Logic)
        """
        tier_map = {
            BusinessSeason.FESTIVE_SEASON: (
                StandardBlobTier.HOT,
                "Peak demand: Real-time dashboards, inventory, AI predictions"
            ),
            BusinessSeason.MONSOON_SEASON: (
                StandardBlobTier.COOL,
                "Monsoon impact: Moderate access, weekly analysis"
            ),
            BusinessSeason.DRY_SEASON: (
                StandardBlobTier.COOL,
                "Off-season: Archive preparation, slower dashboards"
            ),
            BusinessSeason.HISTORICAL_ARCHIVE: (
                StandardBlobTier.ARCHIVE,
                "Historical: Year-over-year trends, ML training data"
            ),
        }
        return tier_map.get(season, (StandardBlobTier.COOL, "Default"))
    
    def get_medallion_tier_strategy(self, layer: str, season: BusinessSeason) -> Dict:
        """
        Get optimal tier strategy for medallion layer based on season
        
        Args:
            layer: 'bronze', 'silver', or 'gold'
            season: Current business season
        
        Returns:
            Dictionary with tier, retention, lifecycle policies
        """
        strategies = {
            'bronze': {
                BusinessSeason.FESTIVE_SEASON: {
                    'tier': StandardBlobTier.HOT,
                    'retention_days': 7,
                    'reason': 'Keep raw ingestion data hot during peak season for validation'
                },
                BusinessSeason.MONSOON_SEASON: {
                    'tier': StandardBlobTier.COOL,
                    'retention_days': 14,
                    'reason': 'Move to cool after validation during monsoon'
                },
                BusinessSeason.DRY_SEASON: {
                    'tier': StandardBlobTier.COOL,
                    'retention_days': 14,
                    'reason': 'Standard retention off-season'
                },
                BusinessSeason.HISTORICAL_ARCHIVE: {
                    'tier': StandardBlobTier.ARCHIVE,
                    'retention_days': 365,
                    'reason': 'Archive raw data from previous seasons'
                }
            },
            'silver': {
                BusinessSeason.FESTIVE_SEASON: {
                    'tier': StandardBlobTier.COOL,
                    'retention_days': 30,
                    'reason': 'Cleaned data available for reference, keep cool'
                },
                BusinessSeason.MONSOON_SEASON: {
                    'tier': StandardBlobTier.COOL,
                    'retention_days': 45,
                    'reason': 'Extended reference during slower periods'
                },
                BusinessSeason.DRY_SEASON: {
                    'tier': StandardBlobTier.COOL,
                    'retention_days': 60,
                    'reason': 'Available for off-season analysis'
                },
                BusinessSeason.HISTORICAL_ARCHIVE: {
                    'tier': StandardBlobTier.ARCHIVE,
                    'retention_days': 730,
                    'reason': 'Keep cleaned data for trend analysis'
                }
            },
            'gold': {
                BusinessSeason.FESTIVE_SEASON: {
                    'tier': StandardBlobTier.HOT,
                    'retention_days': 90,
                    'reason': 'Curated data HOT for dashboards, AI, real-time decisions'
                },
                BusinessSeason.MONSOON_SEASON: {
                    'tier': StandardBlobTier.COOL,
                    'retention_days': 120,
                    'reason': 'Slower access during monsoon, can cool'
                },
                BusinessSeason.DRY_SEASON: {
                    'tier': StandardBlobTier.COOL,
                    'retention_days': 90,
                    'reason': 'Off-season analytics'
                },
                BusinessSeason.HISTORICAL_ARCHIVE: {
                    'tier': StandardBlobTier.ARCHIVE,
                    'retention_days': 1825,
                    'reason': 'Keep curated gold data permanently for AI model training'
                }
            }
        }
        
        return strategies.get(layer, {}).get(season, {
            'tier': StandardBlobTier.COOL,
            'retention_days': 90,
            'reason': 'Default strategy'
        })
    
    def set_tier_for_layer(self, container: str, layer: str, 
                          season: Optional[BusinessSeason] = None) -> bool:
        """
        Set storage tier for all blobs in a medallion layer
        
        Args:
            container: Azure container name (bronze, silver, gold)
            layer: Layer name for logging
            season: Business season (if None, use current)
        
        Returns:
            True if successful
        """
        if season is None:
            season, _ = self.get_current_season()
        
        strategy = self.get_medallion_tier_strategy(layer, season)
        tier = strategy['tier']
        
        try:
            container_client = self.client.get_container_client(container)
            
            for blob in container_client.list_blobs():
                blob_client = self.client.get_blob_client(container, blob.name)
                blob_client.set_standard_blob_tier(tier)
                logger.info(
                    f"✓ Set {layer}/{blob.name} to {tier.value} "
                    f"({strategy['reason']})"
                )
            
            logger.info(f"✓ All {layer} blobs set to {tier.value} tier")
            return True
        
        except Exception as e:
            logger.error(f"✗ Failed to set tier for {layer}: {str(e)}")
            return False
    
    def print_current_strategy(self):
        """Print current seasonal tier strategy"""
        season, season_desc = self.get_current_season()
        
        print("\n" + "="*70)
        print("SEASONAL TIER STRATEGY - SRI LANKAN FASHION RETAIL".center(70))
        print("="*70)
        
        print(f"\n📅 Current Season: {season_desc}")
        
        for layer in ['bronze', 'silver', 'gold']:
            strategy = self.get_medallion_tier_strategy(layer, season)
            tier = strategy['tier']
            
            print(f"\n{layer.upper()} Layer:")
            print(f"  Tier: {tier.value.upper()}")
            print(f"  Retention: {strategy['retention_days']} days")
            print(f"  Reason: {strategy['reason']}")
            print(f"  Cost: {self.tier_config[tier]['cost']}")
            print(f"  Latency: {self.tier_config[tier]['latency_ms']}ms")
        
        print("\n" + "="*70 + "\n")


# Example usage
if __name__ == '__main__':
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    if not conn_str:
        print("Error: AZURE_STORAGE_CONNECTION_STRING not set")
        exit(1)
    
    manager = SeasonalTierManager(conn_str)
    manager.print_current_strategy()
    
    # Set tiers for all layers based on current season
    for layer, container in [('bronze', 'bronze'), ('silver', 'silver'), ('gold', 'gold')]:
        manager.set_tier_for_layer(container, layer)
