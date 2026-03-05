"""
Kafka Producer for POS Data
Simulates POS systems sending transaction data to Kafka
"""
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from pathlib import Path
import pandas as pd
from kafka import KafkaProducer
from kafka.errors import KafkaError

from pipeline.ingestion.kafka_config import KafkaConfig


logger = logging.getLogger(__name__)


class POSDataProducer:
    """
    Kafka producer for point-of-sale transaction data
    Sends transaction records to Kafka topic with delivery confirmation
    """
    
    def __init__(self, kafka_config: KafkaConfig = None):
        """
        Initialize POS data producer
        
        Args:
            kafka_config: KafkaConfig instance (default: loads from YAML)
        """
        if kafka_config is None:
            kafka_config = KafkaConfig.from_yaml()
        
        self.kafka_config = kafka_config
        self.producer = None
        self.stats = {
            'messages_sent': 0,
            'messages_failed': 0,
            'bytes_sent': 0
        }
        
        logger.info(f"POSDataProducer initialized for brokers: {kafka_config.bootstrap_servers}")
    
    def connect(self) -> bool:
        """
        Connect to Kafka broker
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            config = self.kafka_config.get_producer_config()
            config['value_serializer'] = lambda v: json.dumps(v).encode('utf-8')
            
            self.producer = KafkaProducer(**config)
            logger.info(f"Connected to Kafka brokers: {self.kafka_config.bootstrap_servers}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from Kafka"""
        if self.producer:
            self.producer.flush()
            self.producer.close()
            logger.info("Kafka producer disconnected")
    
    def send_transaction(self, transaction: Dict[str, Any], 
                        callback: Optional[Callable] = None) -> bool:
        """
        Send a single transaction to Kafka
        
        Args:
            transaction: Transaction dictionary
            callback: Optional callback function for delivery confirmation
        
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.producer:
            logger.error("Producer not connected. Call connect() first.")
            return False
        
        try:
            # Add metadata
            enriched_transaction = {
                **transaction,
                'kafka_timestamp': datetime.utcnow().isoformat(),
                'source': 'pos_system'
            }
            
            # Send to Kafka
            future = self.producer.send(
                self.kafka_config.pos_topic,
                value=enriched_transaction
            )
            
            # Add delivery callback
            future.add_errback(self._error_callback)
            if callback:
                future.add_callback(callback)
            
            # Update stats
            self.stats['messages_sent'] += 1
            self.stats['bytes_sent'] += len(json.dumps(enriched_transaction))
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to send transaction: {str(e)}")
            self.stats['messages_failed'] += 1
            return False
    
    def send_batch(self, transactions: list, batch_size: int = 100) -> Dict[str, int]:
        """
        Send multiple transactions to Kafka
        
        Args:
            transactions: List of transaction dictionaries
            batch_size: Records per batch (for buffering)
        
        Returns:
            Dictionary with success/failure counts
        """
        if not self.producer:
            logger.error("Producer not connected. Call connect() first.")
            return {'sent': 0, 'failed': 0}
        
        results = {'sent': 0, 'failed': 0}
        
        for i, transaction in enumerate(transactions):
            if self.send_transaction(transaction):
                results['sent'] += 1
            else:
                results['failed'] += 1
            
            # Flush periodically
            if (i + 1) % batch_size == 0:
                self.producer.flush()
                logger.debug(f"Flushed batch at record {i + 1}")
        
        # Final flush
        self.producer.flush()
        logger.info(f"Batch complete: {results['sent']} sent, {results['failed']} failed")
        
        return results
    
    def send_dataframe(self, df: pd.DataFrame, batch_size: int = 100) -> Dict[str, int]:
        """
        Send DataFrame records to Kafka
        
        Args:
            df: Pandas DataFrame with transaction data
            batch_size: Records per batch
        
        Returns:
            Dictionary with success/failure counts
        """
        if df.empty:
            logger.warning("DataFrame is empty")
            return {'sent': 0, 'failed': 0}
        
        logger.info(f"Sending {len(df)} records from DataFrame")
        
        transactions = df.to_dict('records')
        return self.send_batch(transactions, batch_size)
    
    def send_from_csv(self, csv_path: str, batch_size: int = 100) -> Dict[str, int]:
        """
        Send records from CSV file to Kafka
        
        Args:
            csv_path: Path to CSV file
            batch_size: Records per batch
        
        Returns:
            Dictionary with success/failure counts
        """
        try:
            df = pd.read_csv(csv_path)
            logger.info(f"Loaded {len(df)} records from {csv_path}")
            return self.send_dataframe(df, batch_size)
        except Exception as e:
            logger.error(f"Failed to read CSV file: {str(e)}")
            return {'sent': 0, 'failed': 0}
    
    def send_confirmation(self, batch_id: str, record_count: int, 
                         source: str = "lakehouse_ingestion") -> bool:
        """
        Send confirmation message for successful ingestion
        
        Args:
            batch_id: Unique batch identifier
            record_count: Number of records in batch
            source: Source of confirmation
        
        Returns:
            True if sent successfully
        """
        if not self.producer:
            logger.error("Producer not connected")
            return False
        
        try:
            confirmation = {
                'batch_id': batch_id,
                'record_count': record_count,
                'source': source,
                'timestamp': datetime.utcnow().isoformat(),
                'status': 'success'
            }
            
            future = self.producer.send(
                self.kafka_config.confirmation_topic,
                value=confirmation
            )
            
            future.get(timeout=10)
            logger.info(f"Confirmation sent for batch {batch_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to send confirmation: {str(e)}")
            return False
    
    def _error_callback(self, exc):
        """Callback for delivery errors"""
        self.stats['messages_failed'] += 1
        logger.error(f"Kafka delivery error: {str(exc)}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get producer statistics"""
        return self.stats.copy()
    
    def print_stats(self):
        """Print producer statistics"""
        stats = self.get_stats()
        print(f"\n{'='*50}")
        print("Producer Statistics:")
        print(f"{'='*50}")
        print(f"Messages sent:     {stats['messages_sent']:,}")
        print(f"Messages failed:   {stats['messages_failed']:,}")
        print(f"Bytes sent:        {stats['bytes_sent']:,}")
        if stats['messages_sent'] > 0:
            success_rate = (stats['messages_sent'] / (stats['messages_sent'] + stats['messages_failed'])) * 100
            print(f"Success rate:      {success_rate:.1f}%")
        print(f"{'='*50}\n")
