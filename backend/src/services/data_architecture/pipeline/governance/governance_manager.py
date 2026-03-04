"""
Data Governance Manager
Comprehensive audit logging, data lineage tracking, and compliance management
"""
import logging
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd


logger = logging.getLogger(__name__)


class GovernanceManager:
    """
    Manages data governance including:
    - Audit logging (all operations)
    - Data lineage tracking (source to output)
    - Compliance reporting
    - Access analytics
    """
    
    def __init__(self, audit_log_path: str = None):
        """
        Initialize governance manager
        
        Args:
            audit_log_path: Path to audit log directory (default: metadata/audit_logs)
        """
        self.audit_log_path = Path(audit_log_path or 'metadata/audit_logs')
        self.audit_log_path.mkdir(parents=True, exist_ok=True)
        
        self.audit_log_file = self.audit_log_path / 'audit_log.jsonl'
        self.lineage_file = self.audit_log_path / 'data_lineage.json'
        self.compliance_file = self.audit_log_path / 'compliance_status.json'
        
        self.events = []
        self.lineage = {}
        self.compliance_status = {}
        
        logger.info(f"GovernanceManager initialized: {self.audit_log_path}")
    
    def log_event(self, event_type: str, details: Dict[str, Any],
                 user: str = "system", status: str = "success") -> Dict[str, Any]:
        """
        Log a governance event
        
        Args:
            event_type: Type of event (ingestion, access, transformation, etc.)
            details: Event details dictionary
            user: User performing action
            status: Event status (success/failure)
        
        Returns:
            Event log entry
        """
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'user': user,
            'status': status,
            'details': details
        }
        
        self.events.append(event)
        
        # Append to audit log file
        self._append_to_audit_log(event)
        
        logger.info(f"Event logged: {event_type} - {status}")
        return event
    
    def log_ingestion(self, source_file: str, destination: str,
                     record_count: int, batch_id: str = None) -> Dict[str, Any]:
        """
        Log data ingestion event
        
        Args:
            source_file: Source file path
            destination: Destination path
            record_count: Number of records ingested
            batch_id: Optional batch identifier
        
        Returns:
            Event log entry
        """
        details = {
            'source_file': source_file,
            'destination': destination,
            'record_count': record_count,
            'batch_id': batch_id or f"batch_{datetime.utcnow().timestamp()}",
            'source_checksum': self._calculate_file_checksum(source_file)
        }
        
        return self.log_event('ingestion', details)
    
    def log_access(self, stakeholder_type: str, data_category: str,
                  record_count: int, region: Optional[str] = None,
                  status: str = "success") -> Dict[str, Any]:
        """
        Log data access event
        
        Args:
            stakeholder_type: Type of stakeholder
            data_category: Category of data accessed
            record_count: Number of records accessed
            region: Region filter (if applicable)
            status: Access status (success/denied)
        
        Returns:
            Event log entry
        """
        details = {
            'stakeholder_type': stakeholder_type,
            'data_category': data_category,
            'record_count': record_count,
            'region': region
        }
        
        return self.log_event('data_access', details, status=status)
    
    def log_transformation(self, source_path: str, destination_path: str,
                          transformation_type: str,
                          record_count: int) -> Dict[str, Any]:
        """
        Log data transformation event
        
        Args:
            source_path: Source data path
            destination_path: Destination data path
            transformation_type: Type of transformation
            record_count: Number of records transformed
        
        Returns:
            Event log entry
        """
        details = {
            'source': source_path,
            'destination': destination_path,
            'transformation_type': transformation_type,
            'record_count': record_count,
            'source_checksum': self._calculate_file_checksum(source_path),
            'destination_checksum': self._calculate_file_checksum(destination_path)
        }
        
        return self.log_event('transformation', details)
    
    def log_tier_movement(self, file_path: str, from_tier: str, to_tier: str,
                         reason: str) -> Dict[str, Any]:
        """
        Log storage tier movement
        
        Args:
            file_path: Path to file
            from_tier: Source tier
            to_tier: Destination tier
            reason: Reason for movement
        
        Returns:
            Event log entry
        """
        details = {
            'file': file_path,
            'from_tier': from_tier,
            'to_tier': to_tier,
            'reason': reason
        }
        
        return self.log_event('tier_movement', details)
    
    def track_lineage(self, source: str, output: str, transformation: str,
                     dataset_name: str = None) -> Dict[str, Any]:
        """
        Track data lineage from source to output
        
        Args:
            source: Source dataset/file
            output: Output dataset/file
            transformation: Transformation applied
            dataset_name: Name of dataset (for tracking)
        
        Returns:
            Lineage entry
        """
        dataset_id = dataset_name or f"dataset_{datetime.utcnow().timestamp()}"
        
        lineage_entry = {
            'dataset_id': dataset_id,
            'timestamp': datetime.utcnow().isoformat(),
            'source': source,
            'output': output,
            'transformation': transformation,
            'source_checksum': self._calculate_file_checksum(source),
            'output_checksum': self._calculate_file_checksum(output)
        }
        
        # Update lineage tracking
        if dataset_id not in self.lineage:
            self.lineage[dataset_id] = []
        self.lineage[dataset_id].append(lineage_entry)
        
        logger.info(f"Lineage tracked for {dataset_id}: {source} → {output}")
        return lineage_entry
    
    def update_compliance_status(self, dataset_name: str, status: str,
                                policy: str = None, notes: str = None) -> Dict[str, Any]:
        """
        Update compliance status for a dataset
        
        Args:
            dataset_name: Dataset name
            status: Compliance status (compliant/non-compliant/under_review)
            policy: Applicable policy
            notes: Additional notes
        
        Returns:
            Compliance entry
        """
        compliance_entry = {
            'dataset_name': dataset_name,
            'timestamp': datetime.utcnow().isoformat(),
            'status': status,
            'policy': policy,
            'notes': notes
        }
        
        self.compliance_status[dataset_name] = compliance_entry
        
        logger.info(f"Compliance status updated: {dataset_name} - {status}")
        return compliance_entry
    
    def generate_compliance_report(self, output_file: str = None) -> Dict[str, Any]:
        """
        Generate compliance report
        
        Args:
            output_file: Output file path (optional)
        
        Returns:
            Compliance report
        """
        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'total_datasets': len(self.compliance_status),
            'compliant': sum(1 for e in self.compliance_status.values() if e['status'] == 'compliant'),
            'non_compliant': sum(1 for e in self.compliance_status.values() if e['status'] == 'non-compliant'),
            'under_review': sum(1 for e in self.compliance_status.values() if e['status'] == 'under_review'),
            'datasets': self.compliance_status
        }
        
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Compliance report saved to {output_path}")
        
        return report
    
    def generate_access_report(self, start_date: Optional[datetime] = None,
                             end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate access analytics report
        
        Args:
            start_date: Report start date
            end_date: Report end date
        
        Returns:
            Access report
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.utcnow()
        
        # Filter events
        access_events = [e for e in self.events 
                        if e['event_type'] == 'data_access' and
                        start_date <= datetime.fromisoformat(e['timestamp']) <= end_date]
        
        # Generate statistics
        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'period_start': start_date.isoformat(),
            'period_end': end_date.isoformat(),
            'total_access_events': len(access_events),
            'successful_accesses': sum(1 for e in access_events if e['status'] == 'success'),
            'denied_accesses': sum(1 for e in access_events if e['status'] == 'denied'),
            'by_stakeholder': self._aggregate_by_field(access_events, 'stakeholder_type'),
            'by_category': self._aggregate_by_field(access_events, 'data_category')
        }
        
        return report
    
    def query_audit_log(self, event_type: Optional[str] = None,
                       user: Optional[str] = None,
                       status: Optional[str] = None,
                       hours_back: int = 24) -> List[Dict[str, Any]]:
        """
        Query audit log with filters
        
        Args:
            event_type: Filter by event type
            user: Filter by user
            status: Filter by status
            hours_back: Look back N hours
        
        Returns:
            List of matching events
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        results = []
        for event in self.events:
            event_time = datetime.fromisoformat(event['timestamp'])
            
            # Apply filters
            if event_time < cutoff_time:
                continue
            if event_type and event['event_type'] != event_type:
                continue
            if user and event['user'] != user:
                continue
            if status and event['status'] != status:
                continue
            
            results.append(event)
        
        return results
    
    def export_audit_logs(self, output_file: str = None) -> str:
        """
        Export all audit logs to file
        
        Args:
            output_file: Output file path
        
        Returns:
            Path to exported file
        """
        if output_file is None:
            output_file = str(self.audit_log_file)
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            for event in self.events:
                f.write(json.dumps(event, default=str) + '\n')
        
        logger.info(f"Audit logs exported to {output_path} ({len(self.events)} events)")
        return str(output_path)
    
    def export_lineage(self, output_file: str = None) -> str:
        """
        Export data lineage information
        
        Args:
            output_file: Output file path
        
        Returns:
            Path to exported file
        """
        if output_file is None:
            output_file = str(self.lineage_file)
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(self.lineage, f, indent=2, default=str)
        
        logger.info(f"Lineage exported to {output_path}")
        return str(output_path)
    
    def _append_to_audit_log(self, event: Dict[str, Any]):
        """Append event to audit log file"""
        try:
            with open(self.audit_log_file, 'a') as f:
                f.write(json.dumps(event, default=str) + '\n')
        except Exception as e:
            logger.warning(f"Failed to append to audit log: {str(e)}")
    
    def _calculate_file_checksum(self, file_path: str) -> Optional[str]:
        """Calculate SHA256 checksum of file"""
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            
            sha256_hash = hashlib.sha256()
            with open(path, 'rb') as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.warning(f"Failed to calculate checksum: {str(e)}")
            return None
    
    def _aggregate_by_field(self, events: List[Dict], field: str) -> Dict[str, int]:
        """Aggregate events by a specific field"""
        aggregation = {}
        for event in events:
            value = event.get('details', {}).get(field, 'unknown')
            aggregation[value] = aggregation.get(value, 0) + 1
        return aggregation
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get governance statistics"""
        return {
            'total_events': len(self.events),
            'event_types': self._aggregate_by_field(self.events, 'event_type'),
            'total_datasets_tracked': len(self.lineage),
            'total_datasets_monitored': len(self.compliance_status)
        }
