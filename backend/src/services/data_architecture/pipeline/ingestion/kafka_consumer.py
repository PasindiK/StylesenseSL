"""
Kafka Consumer for Lakehouse Ingestion
Ingests POS data from Kafka and stores in bronze layer with confirmation
"""
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd
from kafka import KafkaConsumer
from kafka.errors import KafkaError

from pipeline.ingestion.kafka_config import KafkaConfig, DataCategorizationConfig
from storage.azure_blob import upload_file_to_azure_blob, get_azure_connection_string
from storage.medallion_blob_layout import blob_metadata_for_medallion_upload


logger = logging.getLogger(__name__)


class LakehouseConsumer:
    """
    Kafka consumer for ingesting POS data into lakehouse bronze layer
    Implements publisher-subscriber confirmation pattern
    """
    
    def __init__(self, kafka_config: KafkaConfig = None, 
                 categorization_config: DataCategorizationConfig = None,
                 bronze_path: str = None):
        """
        Initialize lakehouse consumer
        
        Args:
            kafka_config: KafkaConfig instance
            categorization_config: DataCategorizationConfig instance
            bronze_path: Path to bronze layer (default: medallions/bronze/raw)
        """
        if kafka_config is None:
            kafka_config = KafkaConfig.from_yaml()
        if categorization_config is None:
            categorization_config = DataCategorizationConfig.from_yaml()
        
        self.kafka_config = kafka_config
        self.categorization_config = categorization_config
        self.bronze_path = Path(bronze_path or 'medallions/bronze/raw')
        self.bronze_path.mkdir(parents=True, exist_ok=True)
        
        self.consumer = None
        self.producer = None  # For sending confirmations
        self.stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'messages_failed': 0,
            'confirmations_sent': 0,
            'batches_stored': 0
        }
        
        logger.info(f"LakehouseConsumer initialized: bronze_path={self.bronze_path}")
    
    def connect(self) -> bool:
        """
        Connect to Kafka consumer
        
        Returns:
            True if connection successful
        """
        try:
            config = self.kafka_config.get_consumer_config()
            
            self.consumer = KafkaConsumer(
                self.kafka_config.pos_topic,
                **config
            )
            
            logger.info(f"Connected to Kafka topic: {self.kafka_config.pos_topic}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from Kafka"""
        if self.consumer:
            self.consumer.close()
            logger.info("Kafka consumer disconnected")
    
    def process_messages(self, max_messages: Optional[int] = None, 
                        batch_size: int = 100):
        """
        Process messages from Kafka topic
        
        Args:
            max_messages: Maximum messages to process (None = infinite)
            batch_size: Records per batch for storage
        """
        if not self.consumer:
            if not self.connect():
                logger.error("Failed to connect consumer")
                return
        
        if not self.consumer:
            logger.error("Consumer not initialized")
            return
        
        batch = []
        batch_id = 0
        messages_processed = 0
        
        try:
            for message in self.consumer:
                try:
                    # Parse message
                    if isinstance(message.value, str):
                        transaction = json.loads(message.value)
                    else:
                        transaction = message.value
                    
                    # Add metadata
                    transaction['received_timestamp'] = datetime.utcnow().isoformat()
                    transaction['offset'] = message.offset
                    transaction['partition'] = message.partition
                    
                    batch.append(transaction)
                    self.stats['messages_received'] += 1
                    messages_processed += 1
                    
                    # Store batch when it reaches batch_size
                    if len(batch) >= batch_size:
                        batch_id += self._store_batch(batch, batch_id)
                        batch = []
                    
                    # Check max messages
                    if max_messages and messages_processed >= max_messages:
                        break
                
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
                    self.stats['messages_failed'] += 1
            
            # Store remaining batch
            if batch:
                self._store_batch(batch, batch_id)
        
        except KeyboardInterrupt:
            logger.info("Consumer interrupted")
        
        except Exception as e:
            logger.error(f"Consumer error: {str(e)}")
        
        finally:
            self.print_stats()
    
    def _store_batch(self, batch: list, batch_id: int) -> int:
        """
        Store batch of records to bronze layer
        
        Args:
            batch: List of transaction records
            batch_id: Batch identifier
        
        Returns:
            1 if successful, 0 otherwise
        """
        try:
            # Create DataFrame
            df = pd.DataFrame(batch)
            
            # Add batch metadata
            date_str = datetime.utcnow().strftime('%Y%m%d')
            batch_filename = f"batch_{batch_id:05d}_{date_str}.parquet"
            batch_path = self.bronze_path / batch_filename
            
            # Try to store as parquet (preferred). If parquet engine missing, fallback to CSV.
            try:
                df.to_parquet(batch_path, index=False, compression='snappy')
                stored_path = batch_path
            except Exception:
                # Fallback to CSV when pyarrow/fastparquet is not available
                csv_path = batch_path.with_suffix('.csv')
                df.to_csv(csv_path, index=False)
                stored_path = csv_path

            self.stats['messages_processed'] += len(batch)
            self.stats['batches_stored'] += 1

            logger.info(f"Stored batch {batch_id} ({len(batch)} records) to {batch_path}")

            # Upload to Azure Blob Storage if AZURE_STORAGE_CONNECTION_STRING is set
            try:
                if get_azure_connection_string():
                    container = 'bronze'  # Your Azure container name
                    blob_name = f"raw/ingestion/{stored_path.name}"
                    n_rows = int(len(df))
                    upload_meta = blob_metadata_for_medallion_upload(
                        container,
                        blob_name,
                        stored_path.name,
                        "HOT",
                        record_count=n_rows,
                    )
                    uploaded = upload_file_to_azure_blob(
                        str(stored_path),
                        container,
                        blob_name,
                        metadata=upload_meta,
                    )
                    if uploaded:
                        logger.info(f"Batch {batch_id} uploaded to Azure Blob: {container}/{blob_name}")
                        self.stats['batches_uploaded_to_cloud'] = self.stats.get('batches_uploaded_to_cloud', 0) + 1
                
                # Send confirmation
                self._send_confirmation(batch_id, len(batch))
            except Exception as e:
                logger.warning(f"Cloud upload attempt failed for batch {batch_id}: {e}")
                # Still send confirmation even if upload fails
                self._send_confirmation(batch_id, len(batch))

            return 1
        
        except Exception as e:
            logger.error(f"Failed to store batch {batch_id}: {str(e)}")
            self.stats['messages_failed'] += len(batch)
            return 0
    
    def _send_confirmation(self, batch_id: int, record_count: int):
        """
        Send confirmation for successful ingestion
        
        Args:
            batch_id: Batch identifier
            record_count: Number of records in batch
        """
        try:
            from kafka import KafkaProducer
            
            if not self.producer:
                config = self.kafka_config.get_producer_config()
                config['value_serializer'] = lambda v: json.dumps(v).encode('utf-8')
                self.producer = KafkaProducer(**config)
            
            confirmation = {
                'batch_id': batch_id,
                'record_count': record_count,
                'source': 'lakehouse_consumer',
                'timestamp': datetime.utcnow().isoformat(),
                'status': 'ingested',
                'bronze_location': str(self.bronze_path)
            }
            
            future = self.producer.send(
                self.kafka_config.confirmation_topic,
                value=confirmation
            )
            
            future.get(timeout=5)
            self.stats['confirmations_sent'] += 1
            logger.debug(f"Confirmation sent for batch {batch_id}")
        
        except Exception as e:
            logger.warning(f"Failed to send confirmation: {str(e)}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get consumer statistics"""
        return self.stats.copy()
    
    def print_stats(self):
        """Print consumer statistics"""
        stats = self.get_stats()
        print(f"\n{'='*50}")
        print("Consumer Statistics:")
        print(f"{'='*50}")
        print(f"Messages received:     {stats['messages_received']:,}")
        print(f"Messages processed:    {stats['messages_processed']:,}")
        print(f"Messages failed:       {stats['messages_failed']:,}")
        print(f"Batches stored:        {stats['batches_stored']:,}")
        print(f"Confirmations sent:    {stats['confirmations_sent']:,}")
        print(f"Bronze location:       {self.bronze_path}")
        if stats['messages_received'] > 0:
            success_rate = (stats['messages_processed'] / stats['messages_received']) * 100
            print(f"Success rate:          {success_rate:.1f}%")
        print(f"{'='*50}\n")
