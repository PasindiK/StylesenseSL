#!/usr/bin/env python
"""
Auto-trigger medallion pipeline based on drift decisions.
- AUTO_ACCEPT → Immediately approve and run pipeline
- REQUIRES_APPROVAL → Wait for manual approval before running pipeline
- Tracks processed datasets to avoid duplicates
"""
import os
import json
from pathlib import Path
from datetime import datetime

# Processing state file - tracks which datasets have been processed
PROCESSING_STATE_FILE = "medallions/gold/ml_decision_engine/processing_state.json"


def get_processing_state():
    """Load processing state tracker"""
    try:
        if os.path.exists(PROCESSING_STATE_FILE):
            with open(PROCESSING_STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"processed_datasets": {}, "last_run": None}


def save_processing_state(state):
    """Save processing state tracker"""
    os.makedirs(os.path.dirname(PROCESSING_STATE_FILE), exist_ok=True)
    with open(PROCESSING_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def mark_dataset_processed(table_name, status, decision):
    """Mark a dataset as processed"""
    state = get_processing_state()
    state["processed_datasets"][table_name] = {
        "status": status,  # "auto_approved", "approved", "rejected", "error"
        "decision": decision,  # RL policy decision (AUTO_ACCEPT, REQUIRES_APPROVAL, etc)
        "timestamp": datetime.utcnow().isoformat()
    }
    state["last_run"] = datetime.utcnow().isoformat()
    save_processing_state(state)


def is_dataset_processed(table_name):
    """Check if dataset has already been processed"""
    state = get_processing_state()
    return table_name in state.get("processed_datasets", {})


def get_processing_history(table_name):
    """Get processing history for a dataset"""
    state = get_processing_state()
    return state.get("processed_datasets", {}).get(table_name, None)


if __name__ == "__main__":
    print("Pipeline auto-trigger module loaded")
    print(f"Processing state file: {PROCESSING_STATE_FILE}")
    
    # Example usage
    state = get_processing_state()
    print(f"Total processed datasets: {len(state.get('processed_datasets', {}))}")
    print(f"Last run: {state.get('last_run', 'Never')}")
