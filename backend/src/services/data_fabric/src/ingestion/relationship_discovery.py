"""
Dynamic relationship discovery module.

Auto-detects foreign key relationships between datasets by analyzing column names,
values, and cardinality patterns. Works without explicit configuration.
"""

import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set
import re


@dataclass
class Relationship:
    """Represents a discovered foreign key relationship."""
    child_dataset: str
    child_column: str
    parent_dataset: str
    parent_column: str
    confidence: float  # 0.0 to 1.0
    reasoning: str


class RelationshipDiscovery:
    """
    Auto-detect foreign key relationships between datasets.
    
    Analyzes:
    - Column name patterns (user_id -> users dataset)
    - Column value overlap (does child column exist in parent?)
    - Cardinality ratios (FK should have lower cardinality than PK)
    - Naming conventions (product_id, user_id, shop_id, etc.)
    """
    
    # Patterns for extracting entity type from column names
    # e.g., "user_id" -> "user", "product_fk" -> "product"
    ENTITY_EXTRACTION_PATTERNS = [
        (r'^(\w+?)_id$', 'id'),
        (r'^(\w+?)_fk$', 'fk'),
        (r'^(\w+?)_key$', 'key'),
    ]
    
    @staticmethod
    def discover_relationships(
        datasets: Dict[str, pd.DataFrame],
        pk_mapping: Optional[Dict[str, List[str]]] = None
    ) -> List[Relationship]:
        """
        Discover foreign key relationships across all datasets.
        
        Args:
            datasets: Dict mapping dataset names to DataFrames
            pk_mapping: Optional explicit PK mapping {dataset: [pk_columns]}
                       If not provided, uses cardinality heuristics
        
        Returns:
            List of discovered Relationship objects
        """
        relationships = []
        
        # For each dataset, look for FK columns
        for child_dataset, child_df in datasets.items():
            for child_col in child_df.columns:
                # Skip likely primary keys
                if RelationshipDiscovery._is_likely_pk(child_col, child_df):
                    continue
                
                # Check if this column could be a FK
                if not RelationshipDiscovery._looks_like_fk(child_col):
                    continue
                
                # Try to find matching parent
                parent_match = RelationshipDiscovery._find_parent_dataset(
                    child_col, child_dataset, child_df, datasets, pk_mapping
                )
                
                if parent_match:
                    parent_dataset, parent_col, confidence, reasoning = parent_match
                    relationships.append(
                        Relationship(
                            child_dataset=child_dataset,
                            child_column=child_col,
                            parent_dataset=parent_dataset,
                            parent_column=parent_col,
                            confidence=confidence,
                            reasoning=reasoning
                        )
                    )
        
        return relationships
    
    @staticmethod
    def _looks_like_fk(col_name: str) -> bool:
        """Check if column name suggests it's a foreign key."""
        fk_patterns = [
            r'_id$',
            r'_fk$',
            r'_key$',
            r'^fk_',
        ]
        return any(re.search(pattern, col_name, re.IGNORECASE) for pattern in fk_patterns)
    
    @staticmethod
    def _is_likely_pk(col_name: str, df: pd.DataFrame) -> bool:
        """Check if column looks like a primary key (high cardinality, unique, no nulls)."""
        if df[col_name].isnull().any():
            return False
        cardinality = df[col_name].nunique()
        is_unique = cardinality == len(df)
        return is_unique
    
    @staticmethod
    def _extract_entity_type(col_name: str) -> Optional[str]:
        """Extract entity type from column name.
        
        Examples:
            user_id -> user
            product_fk -> product
            shop_key -> shop
        """
        for pattern, suffix_type in RelationshipDiscovery.ENTITY_EXTRACTION_PATTERNS:
            match = re.search(pattern, col_name, re.IGNORECASE)
            if match:
                return match.group(1).lower()
        return None
    
    @staticmethod
    def _find_parent_dataset(
        fk_col: str,
        child_dataset: str,
        child_df: pd.DataFrame,
        all_datasets: Dict[str, pd.DataFrame],
        pk_mapping: Optional[Dict] = None
    ) -> Optional[Tuple[str, str, float, str]]:
        """
        Find the parent dataset and column for a foreign key.
        
        Returns: (parent_dataset, parent_column, confidence, reasoning)
        """
        # Extract entity type from FK column name
        entity_type = RelationshipDiscovery._extract_entity_type(fk_col)
        if not entity_type:
            return None
        
        candidates = []
        
        # Look for a dataset with matching entity type in name
        for parent_dataset, parent_df in all_datasets.items():
            if parent_dataset == child_dataset:
                continue
            
            # Check if parent dataset name matches entity type
            dataset_name_match = entity_type in parent_dataset.lower()
            
            # Find potential PK column in parent
            for parent_col in parent_df.columns:
                if not RelationshipDiscovery._could_be_matching_pk(parent_col, entity_type):
                    continue
                
                # Check if values match (child values exist in parent)
                value_match, overlap_pct = RelationshipDiscovery._check_value_overlap(
                    child_df[fk_col], parent_df[parent_col]
                )
                
                if value_match:
                    # Calculate confidence
                    confidence = 0.5  # base confidence
                    if dataset_name_match:
                        confidence += 0.3  # boost if dataset name matches
                    confidence += min(overlap_pct / 100 * 0.2, 0.2)  # boost based on overlap %
                    
                    candidates.append(
                        (parent_dataset, parent_col, confidence, 
                         f"Entity match: {entity_type}, Dataset: {parent_dataset}, "
                         f"Overlap: {overlap_pct:.1f}%")
                    )
        
        # Return best candidate
        if candidates:
            candidates.sort(key=lambda x: x[2], reverse=True)
            return candidates[0]
        
        return None
    
    @staticmethod
    def _could_be_matching_pk(parent_col: str, entity_type: str) -> bool:
        """Check if a column in parent dataset could be the matching PK."""
        # Should be a primary key column for the entity
        pk_candidates = [
            f"{entity_type}_id",
            f"{entity_type}_pk",
            f"{entity_type}_key",
            "id",
        ]
        return parent_col.lower() in [x.lower() for x in pk_candidates]
    
    @staticmethod
    def _check_value_overlap(
        child_series: pd.Series, 
        parent_series: pd.Series
    ) -> Tuple[bool, float]:
        """
        Check if child column values exist in parent column.
        
        Returns: (has_overlap, percentage_overlap)
        """
        # Remove nulls
        child_values = set(child_series.dropna().unique())
        parent_values = set(parent_series.dropna().unique())
        
        if len(child_values) == 0:
            return False, 0.0
        
        # Check overlap
        overlap = child_values.intersection(parent_values)
        overlap_pct = len(overlap) / len(child_values) * 100
        
        # Consider it a match if >70% overlap (to account for missing data)
        return overlap_pct >= 70, overlap_pct
    
    @staticmethod
    def print_relationships_report(relationships: List[Relationship]) -> str:
        """Generate a human-readable relationships report."""
        report = [
            f"\n{'='*100}",
            f"DISCOVERED RELATIONSHIPS",
            f"{'='*100}",
        ]
        
        if not relationships:
            report.append("No relationships discovered.")
        else:
            report.append(f"{'Child Dataset':<35} {'Child Column':<20} {'Parent Dataset':<35} {'Parent Column':<20} {'Conf':<6}")
            report.append(f"{'-'*100}")
            
            for rel in sorted(relationships, key=lambda x: x.confidence, reverse=True):
                report.append(
                    f"{rel.child_dataset:<35} {rel.child_column:<20} "
                    f"{rel.parent_dataset:<35} {rel.parent_column:<20} {rel.confidence:.2f}"
                )
                report.append(f"  -> {rel.reasoning}")
        
        report.append(f"{'='*100}\n")
        return "\n".join(report)
