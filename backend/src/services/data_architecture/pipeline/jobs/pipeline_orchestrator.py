"""
Pipeline Orchestrator
Coordinates end-to-end data pipeline execution:
- Ingestion (Kafka → Bronze)
- Tier optimization
- Stakeholder view generation
- Governance reporting
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.ingestion.kafka_config import KafkaConfig, DataCategorizationConfig
from pipeline.ingestion.kafka_producer import POSDataProducer
from pipeline.ingestion.kafka_consumer import LakehouseConsumer
from storage.tier_manager import AdaptiveStorageManager
from pipeline.governance.data_categorization import DataCategorizationManager
from pipeline.governance.governance_manager import GovernanceManager


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    Orchestrates complete data pipeline execution
    """
    
    def __init__(self):
        """Initialize pipeline orchestrator"""
        self.kafka_config = KafkaConfig.from_yaml()
        self.categorization_config = DataCategorizationConfig.from_yaml()
        self.storage_manager = AdaptiveStorageManager()
        self.categorization_manager = DataCategorizationManager(self.categorization_config)
        self.governance_manager = GovernanceManager()
        
        self.stats = {
            'ingestion': {},
            'tier_optimization': {},
            'view_generation': {},
            'governance': {}
        }
        
        logger.info("PipelineOrchestrator initialized")
    
    def run_ingestion_job(self, max_messages: Optional[int] = None) -> Dict[str, Any]:
        """
        Run data ingestion job (Kafka → Bronze)
        
        Args:
            max_messages: Maximum messages to ingest
        
        Returns:
            Job statistics
        """
        logger.info("=" * 70)
        logger.info("STARTING INGESTION JOB")
        logger.info("=" * 70)
        
        try:
            consumer = LakehouseConsumer(self.kafka_config, self.categorization_config)
            
            if not consumer.connect():
                logger.error("Failed to connect to Kafka")
                return {'status': 'failed', 'error': 'Connection failed'}
            
            consumer.process_messages(max_messages=max_messages)
            stats = consumer.get_stats()
            
            # Log in governance
            self.governance_manager.log_event(
                'pipeline_job',
                {
                    'job_type': 'ingestion',
                    'messages_ingested': stats['messages_processed'],
                    'batches_stored': stats['batches_stored']
                }
            )
            
            self.stats['ingestion'] = stats
            
            logger.info("INGESTION JOB COMPLETED")
            return {'status': 'success', 'stats': stats}
        
        except Exception as e:
            logger.error(f"Ingestion job failed: {str(e)}")
            return {'status': 'failed', 'error': str(e)}
    
    def run_tier_optimization_job(self) -> Dict[str, Any]:
        """
        Run storage tier optimization job
        
        Returns:
            Job statistics
        """
        logger.info("=" * 70)
        logger.info("STARTING TIER OPTIMIZATION JOB")
        logger.info("=" * 70)
        
        try:
            # Optimize storage tiers
            movements = self.storage_manager.optimize_tiers()
            stats = self.storage_manager.get_tier_statistics()
            
            # Log movements
            for movement in movements:
                self.governance_manager.log_tier_movement(
                    movement['file'],
                    movement['from_tier'],
                    movement['to_tier'],
                    movement['reason']
                )
            
            self.stats['tier_optimization'] = {
                'movements': len(movements),
                'tier_stats': stats
            }
            
            logger.info(f"Tier optimization complete: {len(movements)} movements")
            logger.info("TIER OPTIMIZATION JOB COMPLETED")
            return {'status': 'success', 'movements': len(movements), 'stats': stats}
        
        except Exception as e:
            logger.error(f"Tier optimization job failed: {str(e)}")
            return {'status': 'failed', 'error': str(e)}
    
    def run_stakeholder_views_job(self, source_dir: str = 'medallions/bronze/raw',
                                  output_dir: str = 'medallions/gold/stakeholder_views') -> Dict[str, Any]:
        """
        Run stakeholder view generation job
        
        Args:
            source_dir: Source data directory
            output_dir: Output directory for views
        
        Returns:
            Job statistics
        """
        logger.info("=" * 70)
        logger.info("STARTING STAKEHOLDER VIEWS JOB")
        logger.info("=" * 70)
        
        try:
            source_path = Path(source_dir)
            
            # Load data from bronze layer
            if not source_path.exists():
                logger.warning(f"Source directory not found: {source_path}")
                return {'status': 'failed', 'error': 'Source directory not found'}
            
            # Load parquet files
            parquet_files = list(source_path.glob('*.parquet'))
            if not parquet_files:
                logger.warning(f"No parquet files found in {source_path}")
                return {'status': 'no_data', 'message': 'No data to process'}
            
            # Combine all parquet files
            dfs = [pd.read_parquet(f) for f in parquet_files]
            if not dfs:
                return {'status': 'no_data', 'message': 'Failed to load data'}
            
            combined_df = pd.concat(dfs, ignore_index=True)
            logger.info(f"Loaded {len(combined_df)} records from {len(parquet_files)} files")
            
            # Generate views for all stakeholders
            views = self.categorization_manager.generate_stakeholder_views(combined_df, output_dir)
            
            # Log in governance
            self.governance_manager.log_event(
                'pipeline_job',
                {
                    'job_type': 'stakeholder_views',
                    'views_generated': len(views),
                    'records_processed': len(combined_df)
                }
            )
            
            self.stats['view_generation'] = {
                'views_generated': len(views),
                'records_processed': len(combined_df)
            }
            
            logger.info(f"Generated {len(views)} stakeholder views")
            logger.info("STAKEHOLDER VIEWS JOB COMPLETED")
            return {'status': 'success', 'views_generated': len(views)}
        
        except Exception as e:
            logger.error(f"Stakeholder views job failed: {str(e)}")
            return {'status': 'failed', 'error': str(e)}
    
    def run_governance_job(self) -> Dict[str, Any]:
        """
        Run governance reporting job
        
        Returns:
            Job statistics
        """
        logger.info("=" * 70)
        logger.info("STARTING GOVERNANCE JOB")
        logger.info("=" * 70)
        
        try:
            # Generate reports
            compliance_report = self.governance_manager.generate_compliance_report(
                f"reports/governance/compliance_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            )
            
            access_report = self.governance_manager.generate_access_report()
            
            # Export logs
            self.governance_manager.export_audit_logs()
            self.governance_manager.export_lineage()
            
            self.stats['governance'] = {
                'compliance_report_generated': True,
                'access_report_generated': True,
                'audit_events': len(self.governance_manager.events)
            }
            
            logger.info("Governance reports generated")
            logger.info("GOVERNANCE JOB COMPLETED")
            return {
                'status': 'success',
                'compliance_summary': {
                    'compliant': compliance_report.get('compliant', 0),
                    'non_compliant': compliance_report.get('non_compliant', 0),
                    'under_review': compliance_report.get('under_review', 0)
                },
                'audit_events': len(self.governance_manager.events)
            }
        
        except Exception as e:
            logger.error(f"Governance job failed: {str(e)}")
            return {'status': 'failed', 'error': str(e)}
    
    def run_full_pipeline(self, max_messages: Optional[int] = None) -> Dict[str, Any]:
        """
        Run complete end-to-end pipeline
        
        Args:
            max_messages: Max messages for ingestion
        
        Returns:
            Overall pipeline statistics
        """
        logger.info("\n")
        logger.info("╔" + "=" * 68 + "╗")
        logger.info("║" + " " * 68 + "║")
        logger.info("║" + "LAKEHOUSE PIPELINE - FULL EXECUTION".center(68) + "║")
        logger.info("║" + " " * 68 + "║")
        logger.info("╚" + "=" * 68 + "╝")
        logger.info("\n")
        
        start_time = datetime.utcnow()
        results = {}
        
        # Run jobs in sequence
        results['ingestion'] = self.run_ingestion_job(max_messages)
        if results['ingestion']['status'] != 'success':
            logger.warning("Ingestion failed, skipping remaining jobs")
            return results
        
        results['tier_optimization'] = self.run_tier_optimization_job()
        results['stakeholder_views'] = self.run_stakeholder_views_job()
        results['governance'] = self.run_governance_job()
        
        # Summary
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("\n")
        logger.info("=" * 70)
        logger.info("PIPELINE EXECUTION SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Start time:  {start_time.isoformat()}")
        logger.info(f"End time:    {end_time.isoformat()}")
        logger.info(f"Duration:    {duration:.1f} seconds")
        logger.info(f"\nJobs:")
        for job_name, result in results.items():
            status = result.get('status', 'unknown').upper()
            logger.info(f"  {job_name:20} - {status}")
        logger.info("=" * 70 + "\n")
        
        return {
            'status': 'success',
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration,
            'job_results': results
        }
    
    def print_statistics(self):
        """Print pipeline statistics"""
        print("\n" + "=" * 70)
        print("PIPELINE STATISTICS")
        print("=" * 70)
        
        for category, stats in self.stats.items():
            print(f"\n{category.upper()}:")
            if isinstance(stats, dict):
                for key, value in stats.items():
                    if isinstance(value, (int, float)):
                        print(f"  {key:30} {value:,}")
                    else:
                        print(f"  {key:30} {value}")
        
        print("=" * 70 + "\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Lakehouse Pipeline Orchestrator')
    parser.add_argument('--job', choices=['full', 'ingestion', 'tier_optimization', 
                                         'stakeholder_views', 'governance'],
                       default='full', help='Job to run')
    parser.add_argument('--max-messages', type=int, default=None,
                       help='Max messages for ingestion job')
    
    args = parser.parse_args()
    
    try:
        orchestrator = PipelineOrchestrator()
        
        if args.job == 'full':
            result = orchestrator.run_full_pipeline(args.max_messages)
        elif args.job == 'ingestion':
            result = orchestrator.run_ingestion_job(args.max_messages)
        elif args.job == 'tier_optimization':
            result = orchestrator.run_tier_optimization_job()
        elif args.job == 'stakeholder_views':
            result = orchestrator.run_stakeholder_views_job()
        elif args.job == 'governance':
            result = orchestrator.run_governance_job()
        
        orchestrator.print_statistics()
        
        # Exit with appropriate code
        sys.exit(0 if result.get('status') == 'success' else 1)
    
    except Exception as e:
        logger.error(f"Pipeline execution failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
