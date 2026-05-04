"""
Baseline-Driven Semantic Drift Detection with Self-Healing Data Ingestion.

Compares approved baseline semantics and **reference numeric snapshots** to each upload,
detects **interpretation drift** (embedding-only meaning + optional encoding transforms),
applies safe self-healing, and persists outcomes in ChromaDB.

Decisions: APPEND | SELF_HEAL | HUMAN_REVIEW | QUARANTINE — tuned via
`interpretation_calibration.json` (not scattered magic numbers in code).
"""

__all__: list[str] = []
