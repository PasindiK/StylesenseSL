"""
Adaptive Storage Tier Management
Automatically moves data between hot/warm/cold tiers based on:
- Seasonal patterns (fashion industry)
- Access frequency
- Data age
- Business rules
"""
import os
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum
import pandas as pd
import yaml


class StorageTier(Enum):
    """Storage tier definitions"""
    HOT = "hot"      # Frequently accessed, current season data
    WARM = "warm"    # Moderately accessed, previous season data
    COLD = "cold"    # Rarely accessed, archived historical data


class Season(Enum):
    """Fashion industry seasons"""
    SPRING_SUMMER = "spring_summer"  # Feb-July
    FALL_WINTER = "fall_winter"      # Aug-Jan


class AdaptiveStorageManager:
    """
    Manages data movement across storage tiers based on:
    - Seasonal relevance (fashion industry cycles)
    - Access patterns
    - Data age
    - Configurable policies
    """
    
    def __init__(self, config_path: str = None):
        self.logger = logging.getLogger(__name__)
        
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'configs' / 'storage_tiers.yaml'
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Set up storage paths
        base_path = Path(self.config.get('base_path', 'storage_tiers'))
        self.hot_path = base_path / 'hot'
        self.warm_path = base_path / 'warm'
        self.cold_path = base_path / 'cold'
        
        # Create directories
        for path in [self.hot_path, self.warm_path, self.cold_path]:
            path.mkdir(parents=True, exist_ok=True)
        
        # Tier policies
        self.policies = self.config.get('tier_policies', {})
        
        # Metadata tracking
        self.metadata_path = base_path / 'metadata'
        self.metadata_path.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.metadata_path / 'file_metadata.csv'
        
        # Load or initialize metadata
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> pd.DataFrame:
        """Load file metadata tracking access patterns and locations"""
        if self.metadata_file.exists():
            return pd.read_csv(self.metadata_file)
        else:
            return pd.DataFrame(columns=[
                'file_path', 'file_name', 'current_tier', 'created_date',
                'last_accessed', 'access_count', 'file_size_mb',
                'season_tag', 'category', 'last_tier_change'
            ])
    
    def _save_metadata(self):
        """Save metadata to disk"""
        self.metadata.to_csv(self.metadata_file, index=False)
    
    def get_current_season(self) -> Season:
        """Determine current fashion season based on date"""
        current_month = datetime.now().month
        
        # Spring/Summer: Feb-July (months 2-7)
        # Fall/Winter: Aug-Jan (months 8-12, 1)
        if 2 <= current_month <= 7:
            return Season.SPRING_SUMMER
        else:
            return Season.FALL_WINTER
    
    def get_season_for_date(self, date: datetime) -> Season:
        """Get season for a specific date"""
        if 2 <= date.month <= 7:
            return Season.SPRING_SUMMER
        else:
            return Season.FALL_WINTER
    
    def determine_tier(
        self, 
        file_path: Path,
        created_date: datetime,
        last_accessed: datetime,
        access_count: int,
        season_tag: Optional[str] = None,
        category: Optional[str] = None
    ) -> StorageTier:
        """
        Determine appropriate storage tier for a file based on policies
        
        Args:
            file_path: Path to the file
            created_date: When file was created
            last_accessed: Last access timestamp
            access_count: Number of times accessed
            season_tag: Fashion season tag (spring_summer, fall_winter)
            category: Data category
            
        Returns:
            StorageTier: Recommended storage tier
        """
        current_date = datetime.now()
        days_since_creation = (current_date - created_date).days
        days_since_access = (current_date - last_accessed).days
        
        # Get tier policies
        hot_policy = self.policies.get('hot', {})
        warm_policy = self.policies.get('warm', {})
        
        # Seasonal consideration (fashion industry)
        current_season = self.get_current_season()
        is_current_season = (
            season_tag and 
            Season[season_tag.upper()] == current_season
        )
        
        # Decision logic
        # HOT tier: Current season + recently accessed + high access frequency
        if is_current_season:
            if days_since_access <= hot_policy.get('max_days_since_access', 7):
                return StorageTier.HOT
            elif days_since_access <= warm_policy.get('max_days_since_access', 30):
                return StorageTier.WARM
        
        # High access frequency keeps data hot
        if access_count >= hot_policy.get('min_access_count', 100):
            if days_since_access <= hot_policy.get('max_days_since_access', 7):
                return StorageTier.HOT
        
        # WARM tier: Previous season or moderate access
        if days_since_creation <= warm_policy.get('max_age_days', 90):
            if days_since_access <= warm_policy.get('max_days_since_access', 30):
                return StorageTier.WARM
        
        # COLD tier: Old data or rarely accessed
        return StorageTier.COLD
    
    def register_file(
        self,
        source_path: Path,
        season_tag: Optional[str] = None,
        category: Optional[str] = None
    ) -> StorageTier:
        """
        Register a new file and place it in appropriate tier
        
        Args:
            source_path: Path to source file
            season_tag: Fashion season tag
            category: Data category
            
        Returns:
            StorageTier: Tier where file was placed
        """
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {source_path}")
        
        # Determine initial tier
        created_date = datetime.fromtimestamp(source_path.stat().st_ctime)
        last_accessed = datetime.fromtimestamp(source_path.stat().st_atime)
        file_size_mb = source_path.stat().st_size / (1024 * 1024)
        
        tier = self.determine_tier(
            source_path, created_date, last_accessed, 0, season_tag, category
        )
        
        # Copy to tier
        tier_path = self._get_tier_path(tier)
        dest_path = tier_path / source_path.name
        shutil.copy2(source_path, dest_path)
        
        # Update metadata
        new_record = {
            'file_path': str(dest_path),
            'file_name': source_path.name,
            'current_tier': tier.value,
            'created_date': created_date.isoformat(),
            'last_accessed': last_accessed.isoformat(),
            'access_count': 0,
            'file_size_mb': file_size_mb,
            'season_tag': season_tag or '',
            'category': category or '',
            'last_tier_change': datetime.now().isoformat()
        }
        
        self.metadata = pd.concat([
            self.metadata, 
            pd.DataFrame([new_record])
        ], ignore_index=True)
        
        self._save_metadata()
        
        self.logger.info(
            f"Registered file {source_path.name} in {tier.value} tier"
        )
        
        return tier
    
    def _get_tier_path(self, tier: StorageTier) -> Path:
        """Get path for a storage tier"""
        if tier == StorageTier.HOT:
            return self.hot_path
        elif tier == StorageTier.WARM:
            return self.warm_path
        else:
            return self.cold_path
    
    def record_access(self, file_name: str):
        """Record file access for tracking"""
        mask = self.metadata['file_name'] == file_name
        if mask.any():
            self.metadata.loc[mask, 'last_accessed'] = datetime.now().isoformat()
            self.metadata.loc[mask, 'access_count'] += 1
            self._save_metadata()
    
    def optimize_tiers(self) -> Dict[str, int]:
        """
        Review all files and move between tiers as needed
        
        Returns:
            Dictionary with movement counts
        """
        movements = {
            'hot_to_warm': 0,
            'hot_to_cold': 0,
            'warm_to_hot': 0,
            'warm_to_cold': 0,
            'cold_to_warm': 0,
            'cold_to_hot': 0
        }
        
        self.logger.info("Starting tier optimization...")
        
        for idx, row in self.metadata.iterrows():
            try:
                file_path = Path(row['file_path'])
                if not file_path.exists():
                    self.logger.warning(f"File not found: {file_path}")
                    continue
                
                current_tier = StorageTier(row['current_tier'])
                created_date = datetime.fromisoformat(row['created_date'])
                last_accessed = datetime.fromisoformat(row['last_accessed'])
                access_count = int(row['access_count'])
                season_tag = row['season_tag'] if pd.notna(row['season_tag']) else None
                category = row['category'] if pd.notna(row['category']) else None
                
                # Determine optimal tier
                optimal_tier = self.determine_tier(
                    file_path, created_date, last_accessed,
                    access_count, season_tag, category
                )
                
                # Move if needed
                if optimal_tier != current_tier:
                    new_path = self._move_file(file_path, current_tier, optimal_tier)
                    
                    # Update metadata
                    self.metadata.at[idx, 'current_tier'] = optimal_tier.value
                    self.metadata.at[idx, 'file_path'] = str(new_path)
                    self.metadata.at[idx, 'last_tier_change'] = datetime.now().isoformat()
                    
                    # Track movement
                    movement_key = f"{current_tier.value}_to_{optimal_tier.value}"
                    movements[movement_key] = movements.get(movement_key, 0) + 1
                    
                    self.logger.info(
                        f"Moved {file_path.name} from {current_tier.value} "
                        f"to {optimal_tier.value}"
                    )
            
            except Exception as e:
                self.logger.error(f"Error processing {row.get('file_name', 'unknown')}: {e}")
                continue
        
        self._save_metadata()
        
        self.logger.info(f"Tier optimization complete: {movements}")
        return movements
    
    def _move_file(
        self, 
        file_path: Path, 
        from_tier: StorageTier, 
        to_tier: StorageTier
    ) -> Path:
        """Move file between tiers"""
        dest_path = self._get_tier_path(to_tier) / file_path.name
        shutil.move(str(file_path), str(dest_path))
        return dest_path
    
    def get_tier_statistics(self) -> Dict:
        """Get statistics about current tier distribution"""
        stats = {
            'total_files': len(self.metadata),
            'tiers': {}
        }
        
        for tier in StorageTier:
            tier_data = self.metadata[self.metadata['current_tier'] == tier.value]
            stats['tiers'][tier.value] = {
                'file_count': len(tier_data),
                'total_size_mb': tier_data['file_size_mb'].sum() if len(tier_data) > 0 else 0,
                'avg_access_count': tier_data['access_count'].mean() if len(tier_data) > 0 else 0
            }
        
        # Season distribution
        current_season = self.get_current_season()
        current_season_data = self.metadata[
            self.metadata['season_tag'] == current_season.value
        ]
        stats['current_season'] = {
            'season': current_season.value,
            'file_count': len(current_season_data)
        }
        
        return stats
    
    def cleanup_old_data(self, max_age_days: int = 365) -> int:
        """
        Archive or delete very old data from cold tier
        
        Args:
            max_age_days: Maximum age in days before archival
            
        Returns:
            Number of files archived
        """
        archived_count = 0
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        # Archive path
        archive_path = self.cold_path / 'archived'
        archive_path.mkdir(exist_ok=True)
        
        for idx, row in self.metadata.iterrows():
            if row['current_tier'] == StorageTier.COLD.value:
                created_date = datetime.fromisoformat(row['created_date'])
                
                if created_date < cutoff_date:
                    file_path = Path(row['file_path'])
                    if file_path.exists():
                        # Move to archive
                        archive_file = archive_path / file_path.name
                        shutil.move(str(file_path), str(archive_file))
                        
                        self.metadata.at[idx, 'file_path'] = str(archive_file)
                        archived_count += 1
                        
                        self.logger.info(f"Archived old file: {file_path.name}")
        
        self._save_metadata()
        return archived_count
