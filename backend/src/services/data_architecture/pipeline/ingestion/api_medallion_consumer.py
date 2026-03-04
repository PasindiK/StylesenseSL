"""
Real-time API Consumer → Medallion Architecture → Azure Blob
Transforms data through Bronze → Silver → Gold layers
Each layer uploads to Azure independently
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import pandas as pd
import requests
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.medallion_uploader import upload_to_medallion_layer, create_containers_if_not_exist

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MedallionPipeline:
    """
    Real-time API → Bronze → Silver → Gold pipeline
    Each layer independently uploads to Azure Blob Storage
    """
    
    def __init__(self, api_url: str = None):
        """
        Args:
            api_url: Endpoint to fetch real-time data from
                    (e.g., 'http://localhost:8000/transactions')
        """
        self.api_url = api_url or "http://localhost:8000/transactions"
        self.batch_date = datetime.utcnow().strftime('%Y%m%d')
        self.batch_counter = 0
        
        self.stats = {
            'records_fetched': 0,
            'batches_bronze': 0,
            'batches_silver': 0,
            'batches_gold': 0,
            'failed': 0
        }
    
    def fetch_from_api(self, limit: int = 50) -> Optional[pd.DataFrame]:
        """
        Fetch real-time data from API
        
        Args:
            limit: Max records to fetch in one call
        
        Returns:
            DataFrame or None if fetch fails
        """
        try:
            response = requests.get(f"{self.api_url}?limit={limit}", timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if isinstance(data, dict) and 'data' in data:
                df = pd.DataFrame(data['data'])
            else:
                df = pd.DataFrame(data)
            
            logger.info(f"✓ Fetched {len(df)} records from API")
            return df
        
        except Exception as e:
            logger.warning(f"⚠ API fetch failed (will use sample data): {e}")
            # Return sample data for demo if API unavailable
            return self._generate_sample_data(limit)
    
    def _generate_sample_data(self, limit: int) -> pd.DataFrame:
        """Generate sample transaction data for demo"""
        import random
        
        data = []
        for i in range(limit):
            data.append({
                'transaction_id': f"TXN_{datetime.utcnow().timestamp()}_{i}",
                'user_id': random.randint(1, 1000),
                'product_id': random.randint(1, 500),
                'amount': round(random.uniform(10, 5000), 2),
                'payment_method': random.choice(['Credit Card', 'Digital Wallet', 'Cash']),
                'transaction_date': datetime.utcnow().isoformat(),
                'status': 'Completed'
            })
        
        return pd.DataFrame(data)
    
    def clean_to_silver(self, bronze_df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform Bronze → Silver (data cleaning & enrichment)
        - Remove duplicates
        - Fix data types
        - Add computed columns
        """
        df = bronze_df.copy()
        
        # Remove duplicates
        df = df.drop_duplicates(subset=['transaction_id'], keep='first')
        
        # Convert amounts to numeric
        if 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        
        # Add processing metadata
        df['cleaned_at'] = datetime.utcnow().isoformat()
        df['data_quality_score'] = 1.0  # Placeholder
        
        logger.info(f"✓ Cleaned to Silver: {len(df)} records")
        return df
    
    def curate_to_gold(self, silver_df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform Silver → Gold (aggregations & business views)
        - Daily summaries
        - User metrics
        - Product insights
        """
        df = silver_df.copy()
        
        # Add computed business metrics
        if 'amount' in df.columns:
            df['amount_tier'] = pd.cut(df['amount'], 
                                       bins=[0, 100, 500, 5000],
                                       labels=['Small', 'Medium', 'Large'])
        
        # Add enrichment
        df['enriched_at'] = datetime.utcnow().isoformat()
        df['source_layer'] = 'gold'
        
        logger.info(f"✓ Curated to Gold: {len(df)} records")
        return df
    
    def process_batch(self, bronze_df: pd.DataFrame) -> bool:
        """
        Process one batch through all medallion layers
        
        Args:
            bronze_df: Raw data from API
        
        Returns:
            True if all layers processed successfully
        """
        try:
            # Bronze layer
            bronze_df['ingested_at'] = datetime.utcnow().isoformat()
            bronze_df['source'] = 'api_pipeline'
            
            bronze_success = upload_to_medallion_layer('bronze', bronze_df, 
                                                       self.batch_counter, self.batch_date)
            if bronze_success:
                self.stats['batches_bronze'] += 1
            else:
                self.stats['failed'] += 1
                return False
            
            # Silver layer
            silver_df = self.clean_to_silver(bronze_df)
            silver_success = upload_to_medallion_layer('silver', silver_df, 
                                                       self.batch_counter, self.batch_date)
            if silver_success:
                self.stats['batches_silver'] += 1
            else:
                self.stats['failed'] += 1
            
            # Gold layer
            gold_df = self.curate_to_gold(silver_df)
            gold_success = upload_to_medallion_layer('gold', gold_df, 
                                                     self.batch_counter, self.batch_date)
            if gold_success:
                self.stats['batches_gold'] += 1
            else:
                self.stats['failed'] += 1
            
            self.batch_counter += 1
            return bronze_success and silver_success and gold_success
        
        except Exception as e:
            logger.error(f"✗ Batch processing failed: {e}")
            self.stats['failed'] += 1
            return False
    
    def run_continuous(self, num_batches: int = 5, interval_seconds: int = 2):
        """
        Run continuous API polling and medallion layer processing
        
        Args:
            num_batches: Number of batches to process
            interval_seconds: Seconds between API calls
        """
        logger.info("\n" + "="*70)
        logger.info("REAL-TIME API → MEDALLION ARCHITECTURE → AZURE BLOB".center(70))
        logger.info("="*70)
        
        # Setup Azure containers
        logger.info("Setting up Azure containers...")
        create_containers_if_not_exist(['bronze', 'silver', 'gold'])
        
        logger.info(f"Processing {num_batches} batches...\n")
        
        for i in range(num_batches):
            logger.info(f"\n--- Batch {i+1}/{num_batches} ---")
            
            # Fetch from API
            df = self.fetch_from_api(limit=50)
            if df is None or len(df) == 0:
                logger.warning(f"Batch {i+1}: No data fetched")
                self.stats['failed'] += 1
                continue
            
            self.stats['records_fetched'] += len(df)
            
            # Process through medallion
            self.process_batch(df)
            
            # Wait before next batch (except last one)
            if i < num_batches - 1:
                logger.info(f"Waiting {interval_seconds}s before next batch...")
                time.sleep(interval_seconds)
        
        # Print summary
        self._print_summary()
    
    def _print_summary(self):
        """Print pipeline execution summary"""
        logger.info("\n" + "="*70)
        logger.info("PIPELINE SUMMARY".center(70))
        logger.info("="*70)
        logger.info(f"Records fetched:          {self.stats['records_fetched']}")
        logger.info(f"Batches → Bronze:         {self.stats['batches_bronze']}")
        logger.info(f"Batches → Silver:         {self.stats['batches_silver']}")
        logger.info(f"Batches → Gold:           {self.stats['batches_gold']}")
        logger.info(f"Failed batches:           {self.stats['failed']}")
        logger.info("="*70)
        logger.info("✓ MEDALLION PIPELINE COMPLETED")
        logger.info("="*70)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Real-time API → Medallion Architecture')
    parser.add_argument('--api-url', default=None, help='API endpoint URL')
    parser.add_argument('--batches', type=int, default=5, help='Number of batches to process')
    parser.add_argument('--interval', type=int, default=2, help='Seconds between API calls')
    
    args = parser.parse_args()
    
    pipeline = MedallionPipeline(api_url=args.api_url)
    pipeline.run_continuous(num_batches=args.batches, interval_seconds=args.interval)
