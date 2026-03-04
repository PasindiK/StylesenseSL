"""
Kafka Configuration Module
Handles loading and managing Kafka broker settings and data categorization rules
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml


logger = logging.getLogger(__name__)


class KafkaConfig:
    """
    Kafka broker configuration management
    Loads settings from kafka_config.yaml
    """
    
    def __init__(self, bootstrap_servers: List[str] = None, pos_topic: str = None,
                 confirmation_topic: str = None, consumer_group: str = None,
                 auto_offset_reset: str = "earliest", enable_auto_commit: bool = False,
                 max_poll_records: int = 500, session_timeout_ms: int = 30000):
        """
        Initialize Kafka configuration
        
        Args:
            bootstrap_servers: List of Kafka brokers
            pos_topic: Topic for POS data
            confirmation_topic: Topic for confirmations
            consumer_group: Consumer group name
            auto_offset_reset: Offset reset behavior
            enable_auto_commit: Auto-commit flag
            max_poll_records: Max records per poll
            session_timeout_ms: Session timeout in ms
        """
        self.bootstrap_servers = bootstrap_servers or ["localhost:9092"]
        self.pos_topic = pos_topic or "pos-transactions"
        self.confirmation_topic = confirmation_topic or "pos-confirmations"
        self.consumer_group = consumer_group or "lakehouse-ingestion"
        self.auto_offset_reset = auto_offset_reset
        self.enable_auto_commit = enable_auto_commit
        self.max_poll_records = max_poll_records
        self.session_timeout_ms = session_timeout_ms
        
        logger.info(f"KafkaConfig initialized: brokers={self.bootstrap_servers}, topic={self.pos_topic}")
    
    @classmethod
    def from_yaml(cls, config_path: str = None) -> 'KafkaConfig':
        """
        Load Kafka configuration from YAML file
        
        Args:
            config_path: Path to kafka_config.yaml (default: configs/kafka_config.yaml)
        
        Returns:
            KafkaConfig instance
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'configs' / 'kafka_config.yaml'
        
        config_path = Path(config_path)
        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return cls()
        
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        kafka_config = config_data.get('kafka', {})
        
        return cls(
            bootstrap_servers=kafka_config.get('bootstrap_servers', ["localhost:9092"]),
            pos_topic=kafka_config.get('pos_topic', 'pos-transactions'),
            confirmation_topic=kafka_config.get('confirmation_topic', 'pos-confirmations'),
            consumer_group=kafka_config.get('consumer_group', 'lakehouse-ingestion'),
            auto_offset_reset=kafka_config.get('auto_offset_reset', 'earliest'),
            enable_auto_commit=kafka_config.get('enable_auto_commit', False),
            max_poll_records=kafka_config.get('max_poll_records', 500),
            session_timeout_ms=kafka_config.get('session_timeout_ms', 30000)
        )
    
    def get_producer_config(self) -> Dict[str, Any]:
        """Get Kafka producer configuration dictionary"""
        return {
            'bootstrap_servers': self.bootstrap_servers,
            'acks': 'all',  # Wait for all replicas
            'retries': 3,
            'max_in_flight_requests_per_connection': 1,
            'request_timeout_ms': 30000,
            'linger_ms': 100,
            'batch_size': 16384
        }
    
    def get_consumer_config(self) -> Dict[str, Any]:
        """Get Kafka consumer configuration dictionary"""
        return {
            'bootstrap_servers': self.bootstrap_servers,
            'group_id': self.consumer_group,
            'auto_offset_reset': self.auto_offset_reset,
            'enable_auto_commit': self.enable_auto_commit,
            'max_poll_records': self.max_poll_records,
            'session_timeout_ms': self.session_timeout_ms,
            'value_deserializer': lambda m: m.decode('utf-8') if m else None
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'bootstrap_servers': self.bootstrap_servers,
            'pos_topic': self.pos_topic,
            'confirmation_topic': self.confirmation_topic,
            'consumer_group': self.consumer_group,
            'auto_offset_reset': self.auto_offset_reset,
            'enable_auto_commit': self.enable_auto_commit,
            'max_poll_records': self.max_poll_records,
            'session_timeout_ms': self.session_timeout_ms
        }


class DataCategorizationConfig:
    """
    Data categorization configuration management
    Loads stakeholder access rules and geographic filters from YAML
    """
    
    def __init__(self, config_data: Dict[str, Any] = None):
        """
        Initialize data categorization configuration
        
        Args:
            config_data: Configuration dictionary
        """
        self.config_data = config_data or {}
        self.geographic_regions = self.config_data.get('geographic_regions', {})
        self.stakeholder_access = self.config_data.get('stakeholder_access', {})
        self.access_validation = self.config_data.get('access_validation', {})
        self.view_generation = self.config_data.get('view_generation', {})
        self.data_categories = self.config_data.get('data_categories', {})
        self.compliance = self.config_data.get('compliance', {})
        
        logger.info(f"DataCategorizationConfig initialized: {len(self.stakeholder_access)} stakeholder types")
    
    @classmethod
    def from_yaml(cls, config_path: str = None) -> 'DataCategorizationConfig':
        """
        Load categorization configuration from YAML file
        
        Args:
            config_path: Path to data_categorization.yaml (default: configs/data_categorization.yaml)
        
        Returns:
            DataCategorizationConfig instance
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'configs' / 'data_categorization.yaml'
        
        config_path = Path(config_path)
        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}, using empty config")
            return cls({})
        
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        return cls(config_data)
    
    def get_stakeholder_types(self) -> List[str]:
        """Get list of supported stakeholder types"""
        return list(self.stakeholder_access.keys())
    
    def get_stakeholder_config(self, stakeholder_type: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for a specific stakeholder type
        
        Args:
            stakeholder_type: Name of stakeholder type
        
        Returns:
            Configuration dictionary or None if not found
        """
        return self.stakeholder_access.get(stakeholder_type)
    
    def get_allowed_categories(self, stakeholder_type: str) -> List[str]:
        """Get allowed data categories for stakeholder"""
        config = self.get_stakeholder_config(stakeholder_type)
        return config.get('allowed_categories', []) if config else []
    
    def get_geographic_scope(self, stakeholder_type: str) -> Optional[Dict[str, Any]]:
        """Get geographic scope for stakeholder"""
        config = self.get_stakeholder_config(stakeholder_type)
        return config.get('geographic_scope', {}) if config else None
    
    def get_excluded_columns(self, stakeholder_type: str) -> List[str]:
        """Get excluded columns for stakeholder (PII, sensitive data)"""
        config = self.get_stakeholder_config(stakeholder_type)
        if config:
            security = config.get('column_level_security', {})
            return security.get('excluded_columns', [])
        return []
    
    def is_pii_column(self, column_name: str) -> bool:
        """Check if column contains PII"""
        pii_columns = self.access_validation.get('pii_columns', [])
        return column_name.lower() in [c.lower() for c in pii_columns]
    
    def get_regions_by_province(self, province_name: str) -> Optional[Dict[str, Any]]:
        """Get districts and cities for a province"""
        provinces = self.geographic_regions.get('provinces', [])
        for province in provinces:
            if province.get('name') == province_name:
                return province
        return None
    
    def get_all_provinces(self) -> List[str]:
        """Get list of all provinces"""
        provinces = self.geographic_regions.get('provinces', [])
        return [p.get('name') for p in provinces]
    
    def get_view_storage_location(self, stakeholder_type: str) -> Optional[str]:
        """Get storage location for stakeholder views"""
        views_config = self.view_generation.get(stakeholder_type, {})
        return views_config.get('storage_location')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return self.config_data
