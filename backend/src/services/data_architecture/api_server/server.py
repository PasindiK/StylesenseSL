"""
Flask API Server for Lakehouse Dashboard
Provides REST endpoints to serve backend data to the frontend
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import os
import glob
from datetime import datetime
from typing import Dict, Any, List

app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend

# Base paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
METADATA_DIR = os.path.join(BASE_DIR, "pipeline", "metadata")
DRIFT_EVENTS_DIR = os.path.join(METADATA_DIR, "drift_events")
DRIFT_ACTIONS_DIR = os.path.join(METADATA_DIR, "drift_actions")
DQ_RESULTS_DIR = os.path.join(METADATA_DIR, "dq_results")
QUARANTINE_DIR = os.path.join(BASE_DIR, "medallions", "bronze", "quarantine")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
GOLD_DIR = os.path.join(BASE_DIR, "medallions", "gold")


def load_json_file(filepath: str) -> Dict[str, Any]:
    """Load a JSON file safely"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return {}


def load_drift_events(limit: int = None) -> List[Dict[str, Any]]:
    """Load drift events from metadata/drift_events/, deduplicated by table (latest only)"""
    events = []
    pattern = os.path.join(DRIFT_EVENTS_DIR, "*.json")
    
    # Load all events
    all_events = []
    for filepath in sorted(glob.glob(pattern), reverse=True):
        data = load_json_file(filepath)
        if data:
            data["file"] = os.path.basename(filepath)
            all_events.append(data)
    
    # Deduplicate by table - keep only the latest event per table
    seen_tables = set()
    for evt in all_events:
        table = evt.get("table")
        if table and table not in seen_tables:
            events.append(evt)
            seen_tables.add(table)
    
    if limit:
        events = events[:limit]
    
    return events


def load_drift_actions(limit: int = None) -> List[Dict[str, Any]]:
    """Load drift actions from metadata/drift_actions/"""
    actions = []
    pattern = os.path.join(DRIFT_ACTIONS_DIR, "*.json")
    
    for filepath in sorted(glob.glob(pattern), reverse=True):
        data = load_json_file(filepath)
        if data:
            data["file"] = os.path.basename(filepath)
            actions.append(data)
    
    if limit:
        actions = actions[:limit]
    
    return actions


def calculate_live_metrics(drift_events: List[Dict], drift_actions: List[Dict]) -> Dict[str, Any]:
    """Calculate live metrics from drift events and actions"""
    # Get list of quarantined table names from actual files in quarantine folder
    quarantined_tables = set()
    quarantined = 0
    if os.path.exists(QUARANTINE_DIR):
        for date_folder in os.listdir(QUARANTINE_DIR):
            date_path = os.path.join(QUARANTINE_DIR, date_folder)
            if os.path.isdir(date_path):
                for filename in os.listdir(date_path):
                    if filename.endswith('.csv'):
                        quarantined += 1
                        # Extract table name from filename (e.g., "users_raw.csv" -> "users")
                        table_name = filename.replace('_raw.csv', '').replace('.csv', '')
                        quarantined_tables.add(table_name)
    
    # Count events that need human review (REQUIRES/QUARANTINED decision OR actually quarantined)
    pending_approvals = sum(
        1 for evt in drift_events 
        if ((("REQUIRES" in evt.get("decision", "").upper() or 
              "QUARANTINED" in evt.get("decision", "").upper()) 
             and not evt.get("approved", False))
            or evt.get("table", "") in quarantined_tables)
    )
    
    # Count truly auto-resolved (AUTO decisions that are NOT quarantined and approved ones)
    auto_resolved = sum(
        1 for evt in drift_events 
        if ((("AUTO" in evt.get("decision", "").upper() 
              and "REQUIRES" not in evt.get("decision", "").upper()) 
             or evt.get("approved", False))
            and evt.get("table", "") not in quarantined_tables)
    )
    
    # Total drifts = all unique drift events
    total_drifts = len(drift_events)
    
    pipeline_status = "Running" if pending_approvals == 0 else "Paused"
    
    return {
        "total_drifts": total_drifts,
        "auto_resolved": auto_resolved,
        "pending_approvals": pending_approvals,
        "quarantined": quarantined,
        "pipeline_status": pipeline_status
    }


def load_dataset_previews() -> Dict[str, Any]:
    """Load CSV previews from various layers"""
    import csv
    import pandas as pd
    
    previews = {}
    
    # Define layers and their paths
    layers = {
        "data": os.path.join(BASE_DIR, "data"),
        "bronze": os.path.join(BASE_DIR, "medallions", "bronze", "raw"),
        "silver_cleaned": os.path.join(BASE_DIR, "medallions", "silver", "cleaned"),
        "silver_enriched": os.path.join(BASE_DIR, "medallions", "silver", "enriched"),
        "gold": os.path.join(BASE_DIR, "medallions", "gold", "curated")
    }
    
    for layer_name, layer_path in layers.items():
        if not os.path.exists(layer_path):
            continue
            
        for filename in os.listdir(layer_path):
            if not filename.endswith('.csv'):
                continue
                
            filepath = os.path.join(layer_path, filename)
            dataset_key = f"{layer_name}/{filename}"
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    columns = reader.fieldnames or []
                    preview = []
                    rows_total = 0
                    
                    for i, row in enumerate(reader):
                        if i < 10:  # First 10 rows
                            preview.append(row)
                        rows_total += 1
                        if i >= 100:  # Don't read entire file
                            break
                    
                    previews[dataset_key] = {
                        "layer": layer_name,
                        "file": filename,
                        "rows_total": rows_total,
                        "columns": columns,
                        "preview": preview
                    }
            except Exception as e:
                print(f"Error loading {filepath}: {e}")
    
    return previews


def get_actual_datasets_by_layer() -> Dict[str, List[str]]:
    """Scan filesystem and return actual datasets grouped by layer"""
    layers = {
        "Raw Data": os.path.join(BASE_DIR, "data"),
        "Bronze": os.path.join(BASE_DIR, "medallions", "bronze", "raw"),
        "Silver (Cleaned)": os.path.join(BASE_DIR, "medallions", "silver", "cleaned"),
        "Silver (Enriched)": os.path.join(BASE_DIR, "medallions", "silver", "enriched"),
        "Gold": os.path.join(BASE_DIR, "medallions", "gold", "curated")
    }
    
    result = {}
    
    for layer_name, layer_path in layers.items():
        datasets = []
        if os.path.exists(layer_path):
            for filename in os.listdir(layer_path):
                if filename.endswith('.csv'):
                    # Remove extensions and format name
                    dataset_name = filename.replace('_dataset.csv', '').replace('_raw.csv', '').replace('.csv', '')
                    if dataset_name:  # Only add non-empty names
                        datasets.append(dataset_name)
        result[layer_name] = sorted(datasets)
    
    return result


def load_quarantine_details() -> List[Dict[str, Any]]:
    """Load quarantine file details - returns unique datasets with latest date only"""
    import csv
    
    # Dictionary to track latest quarantine for each dataset
    quarantine_dict = {}
    
    if not os.path.exists(QUARANTINE_DIR):
        return []
    
    for date_folder in sorted(os.listdir(QUARANTINE_DIR), reverse=True):
        date_path = os.path.join(QUARANTINE_DIR, date_folder)
        if not os.path.isdir(date_path):
            continue
        
        for filename in os.listdir(date_path):
            if not filename.endswith('.csv'):
                continue
            
            filepath = os.path.join(date_path, filename)
            dataset_name = filename.replace('_raw.csv', '').replace('.csv', '')
            
            # Only add if we haven't seen this dataset yet (we're iterating newest first)
            if dataset_name in quarantine_dict:
                continue
            
            # Try to read CSV preview
            columns = []
            preview = []
            rows_preview = 0
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    columns = reader.fieldnames or []
                    for i, row in enumerate(reader):
                        if i < 5:  # First 5 rows
                            preview.append(row)
                        rows_preview += 1
                        if i >= 100:  # Don't read entire file
                            break
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
                columns = []
                preview = []
                rows_preview = 0
            
            quarantine_dict[dataset_name] = {
                "dataset": dataset_name,
                "filename": filename,
                "quarantine_date": date_folder,
                "quarantine_path": filepath,
                "status": "quarantined",
                "reason": ["Schema drift detected", "Pending review"],
                "rows_preview": rows_preview,
                "columns": columns,
                "preview": preview
            }
    
    return list(quarantine_dict.values())


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "lakehouse-api"
    })


@app.route('/api/dashboard-data', methods=['GET'])
def get_dashboard_data():
    """
    Main endpoint: Returns complete dashboard data
    GET /api/dashboard-data
    """
    try:
        # Load all data sources
        drift_events = load_drift_events(limit=20)
        drift_actions = load_drift_actions(limit=20)
        quarantine_details = load_quarantine_details()
        
        # Build pending approvals list - include items requiring approval OR quarantined datasets
        pending_approvals = []
        
        # Add drift events that need approval (check both requires_approval field and decision field)
        for evt in drift_events:
            decision = evt.get("decision", "").upper()
            needs_approval = (evt.get("requires_approval", False) or 
                            "REQUIRES" in decision or 
                            "QUARANTINED" in decision)
            is_not_resolved = not evt.get("approved", False) and not evt.get("rejected", False)
            
            if needs_approval and is_not_resolved:
                # Add counts field from diff if not present
                if "counts" not in evt and "diff" in evt:
                    diff = evt.get("diff", {})
                    evt["counts"] = {
                        "new": len(diff.get("new_columns", [])),
                        "missing": len(diff.get("missing_columns", [])),
                        "dtype": len(diff.get("dtype_changes", [])),
                        "renames": len(diff.get("renames", []))
                    }
                # Set risk level if not present
                if "risk_level" not in evt:
                    counts = evt.get("counts", {})
                    total_changes = sum([counts.get("new", 0), counts.get("missing", 0), 
                                       counts.get("dtype", 0), counts.get("renames", 0)])
                    if total_changes > 10 or counts.get("missing", 0) > 0 or "QUARANTINED" in decision:
                        evt["risk_level"] = "high"
                    elif total_changes > 5:
                        evt["risk_level"] = "medium"
                    else:
                        evt["risk_level"] = "low"
                
                pending_approvals.append(evt)
        
        # Add quarantined datasets as pending approvals (they need review)
        for quarantine_item in quarantine_details:
            # Create a drift event structure for quarantined items
            pending_approvals.append({
                "table": quarantine_item["dataset"],
                "file": f"quarantine_{quarantine_item['dataset']}_{quarantine_item['quarantine_date']}.json",
                "timestamp": quarantine_item["quarantine_date"],
                "decision": "QUARANTINED",
                "requires_approval": True,
                "risk_level": "high",
                "source_file": quarantine_item["filename"],
                "diff": {
                    "new_columns": [],
                    "missing_columns": [],
                    "dtype_changes": []
                },
                "counts": {
                    "new": 0,
                    "missing": 0,
                    "dtype": 0
                }
            })
        
        # Calculate metrics AFTER building pending_approvals list
        live_metrics = calculate_live_metrics(drift_events, drift_actions)
        # Override with actual counts
        live_metrics["pending_approvals"] = len(pending_approvals)
        live_metrics["quarantined"] = len(quarantine_details)  # Use unique count
        live_metrics["pipeline_status"] = "Paused" if len(pending_approvals) > 0 else "Running"
        
        # Build decisions timeline from drift events (since drift_actions might be empty)
        decisions_timeline = []
        for evt in drift_events:
            approval_status = "Auto"
            if evt.get("approved"):
                approval_status = "Approved"
            elif evt.get("rejected"):
                approval_status = "Rejected"
            elif evt.get("requires_approval"):
                approval_status = "Pending"
            
            decisions_timeline.append({
                "timestamp": evt.get("timestamp", ""),
                "table": evt.get("table", ""),
                "drift_type": "schema",
                "action": evt.get("decision", ""),
                "approval_status": approval_status,
                "policy_confidence": evt.get("confidence", 0.85),
                "counts": {
                    "new": len(evt.get("diff", {}).get("new_columns", [])),
                    "missing": len(evt.get("diff", {}).get("missing_columns", [])),
                    "dtype": len(evt.get("diff", {}).get("dtype_changes", [])),
                    "renames": len(evt.get("diff", {}).get("renames", []))
                },
                "risk_level": evt.get("risk_level", "low")
            })
        
        # Build detailed metrics lists
        total_drifts_list = []
        auto_resolved_list = []
        pending_approvals_list = []
        
        for evt in drift_events:
            # Calculate counts from diff structure
            diff = evt.get("diff", {})
            counts = {
                "new": len(diff.get("new_columns", [])),
                "missing": len(diff.get("missing_columns", [])),
                "dtype": len(diff.get("dtype_changes", [])),
                "renames": len(diff.get("renames", []))
            }
            
            item = {
                "timestamp": evt.get("timestamp", ""),
                "table": evt.get("table", ""),
                "drift_type": "schema",
                "action": evt.get("decision", ""),
                "approval_status": "Pending" if evt.get("requires_approval") and not evt.get("approved") else "Auto",
                "policy_confidence": evt.get("confidence", 0.85),
                "counts": counts,
                "risk_level": evt.get("risk_level", "low")
            }
            
            total_drifts_list.append(item)
            
            if evt.get("requires_approval", False) and not evt.get("approved", False):
                pending_approvals_list.append(item)
            else:
                auto_resolved_list.append(item)
        
        # Build notifications
        notifications = []
        for evt in pending_approvals:
            notifications.append({
                "timestamp": evt.get("timestamp", ""),
                "table": evt.get("table", ""),
                "reason": f"Schema drift detected: {evt.get('counts', {}).get('new', 0)} new cols, {evt.get('counts', {}).get('missing', 0)} missing",
                "type": "approval",
                "risk_level": evt.get("risk_level", "medium")
            })
        
        # Build action distribution from drift events (not drift_actions since it's empty)
        action_counts = {}
        for evt in drift_events:
            action_type = evt.get("decision", "UNKNOWN")
            if action_type not in action_counts:
                action_counts[action_type] = {"count": 0, "automated": 0, "human_reviewed": 0}
            action_counts[action_type]["count"] += 1
            if evt.get("requires_approval"):
                action_counts[action_type]["human_reviewed"] += 1
            else:
                action_counts[action_type]["automated"] += 1
        
        action_distribution = [
            {"action": k, "count": v["count"], "automated": v["automated"], "human_reviewed": v["human_reviewed"]}
            for k, v in action_counts.items()
        ]
        
        # Feature importance (mock data for now)
        feature_importance = [
            {
                "action": "AUTO_ADD_COLUMNS",
                "features": [
                    {"name": "new_columns_count", "weight": 0.35},
                    {"name": "risk_score", "weight": 0.28},
                    {"name": "table_criticality", "weight": 0.22},
                    {"name": "historical_stability", "weight": 0.15}
                ]
            },
            {
                "action": "REQUIRES_REVIEW",
                "features": [
                    {"name": "dtype_changes", "weight": 0.40},
                    {"name": "missing_columns", "weight": 0.30},
                    {"name": "risk_score", "weight": 0.20},
                    {"name": "table_criticality", "weight": 0.10}
                ]
            }
        ]
        
        # Architecture status with ACTUAL datasets in each stage
        actual_datasets = get_actual_datasets_by_layer()
        
        architecture = {
            "stages": [
                {
                    "name": layer_name,
                    "status": "active",
                    "datasets": datasets
                }
                for layer_name, datasets in actual_datasets.items()
            ],
            "drift_gate_note": "Schema Drift Gate: Active between Bronze → Silver"
        }
        
        # CSV previews (load from actual files)
        csv_previews = load_dataset_previews()
        
        # Build response
        response = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "live_metrics": live_metrics,
            "detailed_metrics": {
                "total_drifts_list": total_drifts_list,
                "auto_resolved_list": auto_resolved_list,
                "pending_approvals_list": pending_approvals_list,
                "quarantined_list": quarantine_details
            },
            "notifications": notifications,
            "drift_events": drift_events,
            "latest_decision": decisions_timeline[0] if decisions_timeline else None,
            "decisions_timeline": decisions_timeline,
            "action_distribution": action_distribution,
            "feature_importance": feature_importance,
            "architecture": architecture,
            "pending_approvals": pending_approvals,
            "quarantine_details": quarantine_details,
            "csv_previews": csv_previews
        }
        
        return jsonify(response)
    
    except Exception as e:
        return jsonify({
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }), 500


@app.route('/api/drift-events', methods=['GET'])
def get_drift_events():
    """
    Get drift events with optional filtering
    GET /api/drift-events?limit=10&table=products
    """
    try:
        limit = request.args.get('limit', type=int)
        table = request.args.get('table', type=str)
        
        events = load_drift_events(limit=limit)
        
        # Filter by table if specified
        if table:
            events = [evt for evt in events if evt.get("table") == table]
        
        return jsonify({
            "count": len(events),
            "events": events
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    """
    Get live metrics only
    GET /api/metrics
    """
    try:
        drift_events = load_drift_events()
        drift_actions = load_drift_actions()
        metrics = calculate_live_metrics(drift_events, drift_actions)
        
        return jsonify(metrics)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/quarantine', methods=['GET'])
def get_quarantine():
    """
    Get quarantined files
    GET /api/quarantine
    """
    try:
        quarantine_items = load_quarantine_details()
        
        return jsonify({
            "count": len(quarantine_items),
            "quarantined_files": quarantine_items
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/approve-drift', methods=['POST'])
def approve_drift():
    """
    Approve a pending drift event
    POST /api/approve-drift
    Body: {"table": "products", "event_id": "drift_products_20260105_123456.json"}
    """
    try:
        data = request.get_json()
        table = data.get('table')
        event_id = data.get('event_id')
        
        if not table or not event_id:
            return jsonify({"error": "Missing table or event_id"}), 400
        
        # Find and update the event file
        event_path = os.path.join(DRIFT_EVENTS_DIR, event_id)
        
        if not os.path.exists(event_path):
            return jsonify({"error": "Event not found"}), 404
        
        # Load, update, and save
        event_data = load_json_file(event_path)
        event_data["approved"] = True
        event_data["approved_at"] = datetime.utcnow().isoformat() + "Z"
        event_data["approved_by"] = "user"  # Could add authentication
        
        with open(event_path, 'w', encoding='utf-8') as f:
            json.dump(event_data, f, indent=2)
        
        return jsonify({
            "status": "approved",
            "table": table,
            "event_id": event_id,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/reject-drift', methods=['POST'])
def reject_drift():
    """
    Reject a pending drift event
    POST /api/reject-drift
    Body: {"table": "products", "event_id": "drift_products_20260105_123456.json"}
    """
    try:
        data = request.get_json()
        table = data.get('table')
        event_id = data.get('event_id')
        
        if not table or not event_id:
            return jsonify({"error": "Missing table or event_id"}), 400
        
        event_path = os.path.join(DRIFT_EVENTS_DIR, event_id)
        
        if not os.path.exists(event_path):
            return jsonify({"error": "Event not found"}), 404
        
        event_data = load_json_file(event_path)
        event_data["rejected"] = True
        event_data["rejected_at"] = datetime.utcnow().isoformat() + "Z"
        event_data["rejected_by"] = "user"
        
        with open(event_path, 'w', encoding='utf-8') as f:
            json.dump(event_data, f, indent=2)
        
        return jsonify({
            "status": "rejected",
            "table": table,
            "event_id": event_id,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print(" Lakehouse API Server Starting...")
    print("=" * 60)
    print(f" Base Directory: {BASE_DIR}")
    print(f" Drift Events: {DRIFT_EVENTS_DIR}")
    print(f"  Quarantine: {QUARANTINE_DIR}")
    print("=" * 60)
    print(" API Endpoints:")
    print("   GET  /api/health")
    print("   GET  /api/dashboard-data")
    print("   GET  /api/drift-events")
    print("   GET  /api/metrics")
    print("   GET  /api/quarantine")
    print("   POST /api/approve-drift")
    print("   POST /api/reject-drift")
    print("=" * 60)
    print(" Server running at: http://localhost:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
