"""
Data Categorization & Stakeholder Access Management
Filters and categorizes data based on stakeholder type and geographic scope
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum
import pandas as pd

from pipeline.ingestion.kafka_config import DataCategorizationConfig


logger = logging.getLogger(__name__)


class StakeholderType(Enum):
    """Supported stakeholder types"""
    FABRIC_COMPONENT_MEMBER = "fabric_component_member"
    ISLAND_WIDE_ANALYST = "island_wide_analyst"
    REGIONAL_MANAGER = "regional_manager"
    EXECUTIVE = "executive"
    ML_ENGINEER = "ml_engineer"


class DataCategorizationManager:
    """
    Manages data categorization and filtering for different stakeholders
    Ensures appropriate access control based on role and geography
    """
    
    def __init__(self, categorization_config: DataCategorizationConfig = None):
        """
        Initialize categorization manager
        
        Args:
            categorization_config: DataCategorizationConfig instance
        """
        if categorization_config is None:
            categorization_config = DataCategorizationConfig.from_yaml()
        
        self.config = categorization_config
        self.access_log = []
        
        logger.info(f"DataCategorizationManager initialized with {len(self.config.get_stakeholder_types())} stakeholder types")
    
    def get_stakeholder_view(self, df: pd.DataFrame, stakeholder_type: str,
                            region: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Get filtered view of data for stakeholder
        
        Args:
            df: Source DataFrame
            stakeholder_type: Type of stakeholder
            region: Region filter (for regional stakeholders)
        
        Returns:
            Filtered DataFrame or None if validation fails
        """
        # Validate stakeholder type
        if stakeholder_type not in self.config.get_stakeholder_types():
            logger.warning(f"Unknown stakeholder type: {stakeholder_type}")
            return None
        
        # Apply filters
        filtered_df = df.copy()
        
        # 1. Apply row-level filtering (geography)
        filtered_df = self._apply_row_level_security(filtered_df, stakeholder_type, region)
        
        # 2. Apply column-level filtering (PII, sensitive data)
        filtered_df = self._apply_column_level_security(filtered_df, stakeholder_type)
        
        # 3. Apply category filtering
        filtered_df = self._apply_category_filtering(filtered_df, stakeholder_type)
        
        # Log access
        self._log_access(stakeholder_type, region, len(filtered_df), 'success')
        
        logger.info(f"Generated view for {stakeholder_type}: {len(filtered_df)} rows, {len(filtered_df.columns)} columns")
        
        return filtered_df
    
    def _apply_row_level_security(self, df: pd.DataFrame, stakeholder_type: str,
                                  region: Optional[str] = None) -> pd.DataFrame:
        """
        Apply row-level filtering based on geography
        
        Args:
            df: Source DataFrame
            stakeholder_type: Type of stakeholder
            region: Region filter
        
        Returns:
            Filtered DataFrame
        """
        if df.empty:
            return df
        
        scope = self.config.get_geographic_scope(stakeholder_type)
        if not scope:
            return df
        
        scope_type = scope.get('type', 'all_regions')
        
        # Island-wide analysts get all regions
        if scope_type == 'all_regions' or scope.get('regions') == 'all':
            return df
        
        # Regional filtering
        if scope_type == 'specific_regions':
            allowed_regions = scope.get('regions', [])
            if 'province' in df.columns:
                return df[df['province'].isin(allowed_regions)]
        
        elif scope_type == 'assigned_region':
            if region and 'province' in df.columns:
                return df[df['province'] == region]
        
        return df
    
    def _apply_column_level_security(self, df: pd.DataFrame, 
                                     stakeholder_type: str) -> pd.DataFrame:
        """
        Remove sensitive columns for stakeholder
        
        Args:
            df: Source DataFrame
            stakeholder_type: Type of stakeholder
        
        Returns:
            DataFrame with sensitive columns removed
        """
        if df.empty:
            return df
        
        excluded_columns = self.config.get_excluded_columns(stakeholder_type)
        
        # Remove excluded columns that exist in DataFrame
        columns_to_drop = [col for col in excluded_columns if col in df.columns]
        
        if columns_to_drop:
            df = df.drop(columns=columns_to_drop)
            logger.debug(f"Removed columns for {stakeholder_type}: {columns_to_drop}")
        
        return df
    
    def _apply_category_filtering(self, df: pd.DataFrame, 
                                  stakeholder_type: str) -> pd.DataFrame:
        """
        Filter data categories based on stakeholder access rules
        
        Args:
            df: Source DataFrame
            stakeholder_type: Type of stakeholder
        
        Returns:
            Filtered DataFrame
        """
        allowed_categories = self.config.get_allowed_categories(stakeholder_type)
        
        if not allowed_categories:
            return df
        
        # If DataFrame has 'category' column, filter it
        if 'category' in df.columns:
            return df[df['category'].isin(allowed_categories)]
        
        return df
    
    def _log_access(self, stakeholder_type: str, region: Optional[str],
                   record_count: int, status: str):
        """
        Log data access for audit trail
        
        Args:
            stakeholder_type: Type of stakeholder
            region: Region (if applicable)
            record_count: Number of records accessed
            status: Access status (success/denied)
        """
        from datetime import datetime
        
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'stakeholder_type': stakeholder_type,
            'region': region,
            'record_count': record_count,
            'status': status
        }
        
        self.access_log.append(log_entry)
        logger.debug(f"Access logged: {stakeholder_type} - {record_count} records - {status}")
    
    def generate_stakeholder_views(self, source_df: pd.DataFrame,
                                  output_dir: str = None) -> Dict[str, Path]:
        """
        Generate views for all stakeholder types
        
        Args:
            source_df: Source data to filter
            output_dir: Output directory for views (default: gold/stakeholder_views)
        
        Returns:
            Dictionary mapping stakeholder type to output file path
        """
        output_dir = Path(output_dir or 'gold/stakeholder_views')
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {}
        
        for stakeholder_type in self.config.get_stakeholder_types():
            try:
                # Get stakeholder config
                config = self.config.get_stakeholder_config(stakeholder_type)
                if not config:
                    continue
                
                # For regional stakeholders, create views for each region
                scope = config.get('geographic_scope', {})
                
                if scope.get('type') == 'specific_regions':
                    regions = scope.get('regions', [])
                    for region in regions:
                        view_df = self.get_stakeholder_view(source_df, stakeholder_type, region)
                        if view_df is not None:
                            filename = f"{stakeholder_type}_{region.lower().replace(' ', '_')}.parquet"
                            output_path = output_dir / filename
                            view_df.to_parquet(output_path, index=False, compression='snappy')
                            results[f"{stakeholder_type}_{region}"] = output_path
                
                else:
                    # Island-wide views
                    view_df = self.get_stakeholder_view(source_df, stakeholder_type)
                    if view_df is not None:
                        filename = f"{stakeholder_type}.parquet"
                        output_path = output_dir / filename
                        view_df.to_parquet(output_path, index=False, compression='snappy')
                        results[stakeholder_type] = output_path
                
                logger.info(f"Generated views for {stakeholder_type}")
            
            except Exception as e:
                logger.error(f"Failed to generate view for {stakeholder_type}: {str(e)}")
        
        logger.info(f"Generated {len(results)} stakeholder views")
        return results
    
    def validate_access(self, stakeholder_type: str, data_category: str,
                       region: Optional[str] = None) -> bool:
        """
        Validate if stakeholder has access to data
        
        Args:
            stakeholder_type: Type of stakeholder
            data_category: Data category to access
            region: Region (if applicable)
        
        Returns:
            True if access allowed, False otherwise
        """
        # Check if stakeholder type exists
        if stakeholder_type not in self.config.get_stakeholder_types():
            logger.warning(f"Unknown stakeholder type: {stakeholder_type}")
            self._log_access(stakeholder_type, region, 0, 'denied - unknown type')
            return False
        
        # Check allowed categories
        allowed_categories = self.config.get_allowed_categories(stakeholder_type)
        if data_category not in allowed_categories:
            logger.warning(f"{stakeholder_type} not allowed for category {data_category}")
            self._log_access(stakeholder_type, region, 0, f'denied - {data_category}')
            return False
        
        # Check region access
        scope = self.config.get_geographic_scope(stakeholder_type)
        if scope and scope.get('type') == 'specific_regions':
            allowed_regions = scope.get('regions', [])
            if region and region not in allowed_regions:
                logger.warning(f"{stakeholder_type} not allowed for region {region}")
                self._log_access(stakeholder_type, region, 0, 'denied - region')
                return False
        
        return True
    
    def get_stakeholder_info(self, stakeholder_type: str) -> Optional[Dict[str, Any]]:
        """
        Get information about stakeholder type
        
        Args:
            stakeholder_type: Type of stakeholder
        
        Returns:
            Stakeholder configuration dictionary
        """
        return self.config.get_stakeholder_config(stakeholder_type)
    
    def get_access_log(self) -> List[Dict[str, Any]]:
        """Get access audit log"""
        return self.access_log.copy()
