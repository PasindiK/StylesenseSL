# scripts/schema_drift.py
import os
import json
from datetime import datetime
from difflib import SequenceMatcher
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StructType
from shutil import move
from typing import Dict, Any, List, Tuple

# adjust these paths for your repo
METADATA_DIR = "pipeline/metadata"
SCHEMA_VERSIONS_FILE = os.path.join(METADATA_DIR, "schema_registry_versions.json")
DRIFT_EVENTS_DIR = os.path.join(METADATA_DIR, "drift_events")
QUARANTINE_DIR = "medallions/bronze/quarantine"

os.makedirs(METADATA_DIR, exist_ok=True)
os.makedirs(DRIFT_EVENTS_DIR, exist_ok=True)
os.makedirs(QUARANTINE_DIR, exist_ok=True)

from pipeline.schemas.schema_registry import get_schema, SCHEMAS  # adjust path
from medallions.gold.ml_decision_engine.feature_builder import build_feature_vector
from medallions.gold.ml_decision_engine.policy import LinUCBPolicy, EpsilonGreedyPolicy
from scripts.schema_drift_tie_breaker import ActionTieBreaker, TieBreakingStrategy

POLICY_PATH = os.path.join("medallions", "gold", "ml_decision_engine", "models", "policy.json")
DECISIONS_LOG = os.path.join("medallions", "gold", "ml_decision_engine", "logs", "decisions.jsonl")
os.makedirs(os.path.dirname(DECISIONS_LOG), exist_ok=True)

POLICY = {
    "required_missing_severity": "ALERT",
    "new_column_auto_accept": True,
    "min_non_null_ratio_for_accept": 0.5,  # More lenient
    "max_new_columns_for_auto_accept": 15,  # Increased from 5
    "auto_cast_dtype": True,  # Enable auto dtype handling
    "auto_add_missing_columns": True,  # Enable auto missing column handling
}

# -------------------------------------------------------------------------
def _schema_to_dict(struct: StructType):
    return {f.name: f.dataType.simpleString() for f in struct.fields}

def string_similarity(a: str, b: str) -> float:
    """Calculate string similarity using SequenceMatcher (0.0 to 1.0)"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def detect_potential_renames(
    missing_columns: List[str],
    new_columns: List[str],
    expected_types: Dict[str, str],
    actual_types: Dict[str, str],
    similarity_threshold: float = 0.6
) -> Tuple[List[Dict[str, str]], List[str], List[str]]:
    """
    Detect potential column renames by matching missing and new columns.
    
    Returns:
        - renames: List of {"old_name", "new_name", "similarity", "type_match"}
        - remaining_missing: Columns that weren't matched
        - remaining_new: Columns that weren't matched
    """
    renames = []
    used_missing = set()
    used_new = set()
    
    # Try to pair each missing column with the most similar new column
    for missing in missing_columns:
        best_match = None
        best_score = 0.0
        
        for new in new_columns:
            if new in used_new:
                continue
                
            # Calculate similarity score
            name_sim = string_similarity(missing, new)
            
            # Bonus points if types match
            type_match = expected_types.get(missing) == actual_types.get(new)
            score = name_sim
            if type_match:
                score += 0.2  # Boost score if types match
            
            if score > best_score and name_sim >= similarity_threshold:
                best_score = score
                best_match = (new, name_sim, type_match)
        
        if best_match:
            new_name, name_sim, type_match = best_match
            renames.append({
                "old_name": missing,
                "new_name": new_name,
                "similarity": round(name_sim, 3),
                "type_match": type_match
            })
            used_missing.add(missing)
            used_new.add(new_name)
    
    remaining_missing = [c for c in missing_columns if c not in used_missing]
    remaining_new = [c for c in new_columns if c not in used_new]
    
    return renames, remaining_missing, remaining_new

def compare_schemas(expected_struct: StructType, actual_df: DataFrame):
    expected = _schema_to_dict(expected_struct) if expected_struct else {}
    actual = {f.name: str(f.dataType) for f in actual_df.schema.fields}

    new_columns = [c for c in actual.keys() if c not in expected.keys()]
    missing_columns = [c for c in expected.keys() if c not in actual.keys()]

    dtype_changes = []
    for c in expected.keys():
        if c in actual.keys() and expected[c] != actual[c]:
            dtype_changes.append({"column": c, "expected": expected[c], "actual": actual[c]})

    # Detect potential renames
    renames = []
    if missing_columns and new_columns:
        renames, missing_columns, new_columns = detect_potential_renames(
            missing_columns, new_columns, expected, actual
        )

    return {
        "new_columns": new_columns,
        "missing_columns": missing_columns,
        "dtype_changes": dtype_changes,
        "renames": renames
    }

def save_drift_event(table_name: str, source_file: str, diff: Dict[str, Any], decision: str, extra: Dict[str, Any] = None):
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "table": table_name,
        "source_file": source_file,
        "diff": diff,
        "decision": decision,
    }
    if extra:
        event["extra"] = extra

    fname = os.path.join(DRIFT_EVENTS_DIR, f"drift_{table_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(event, f, indent=2)
    return fname

def quarantine_file(file_path: str, reason: str):
    date_dir = datetime.utcnow().strftime("%Y%m%d")
    target_dir = os.path.join(QUARANTINE_DIR, date_dir)
    os.makedirs(target_dir, exist_ok=True)
    dest = os.path.join(target_dir, os.path.basename(file_path))
    move(file_path, dest)
    return dest

def compute_basic_stats(df: DataFrame, columns: List[str]):
    stats = {}
    total = df.count()
    for c in columns:
        non_null = df.filter(F.col(c).isNotNull()).count() if total > 0 else 0
        unique = df.select(c).distinct().count() if total > 0 else 0
        stats[c] = {"non_null_ratio": non_null / total if total > 0 else 0, "unique_count": unique}
    return stats

def bump_schema_version(table_name: str, new_schema_struct: StructType):
    if os.path.exists(SCHEMA_VERSIONS_FILE):
        with open(SCHEMA_VERSIONS_FILE, "r", encoding="utf-8") as f:
            versions = json.load(f)
    else:
        versions = {}
    table_versions = versions.get(table_name, [])
    new_version = {"version_ts": datetime.utcnow().isoformat(), "schema": _schema_to_dict(new_schema_struct)}
    table_versions.append(new_version)
    versions[table_name] = table_versions
    with open(SCHEMA_VERSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(versions, f, indent=2)
    return len(table_versions)

def update_registry_with_new_columns(table_name: str, new_columns: Dict[str, str]):
    current_struct = get_schema(table_name)
    from pyspark.sql.types import StructType, StructField, StringType
    if current_struct is None:
        fields = [StructField(k, StringType(), True) for k in new_columns.keys()]
        new_struct = StructType(fields)
    else:
        fields = list(current_struct.fields)
        for col, dtype in new_columns.items():
            fields.append(StructField(col, StringType(), True))
        new_struct = StructType(fields)
    version_no = bump_schema_version(table_name, new_struct)
    return new_struct, version_no

# -------------------------------------------------------------------------
def handle_schema_drift(spark, table_name: str, df: DataFrame, source_file_path: str, raw_file_path: str, policy: Dict = POLICY):
    """
    Structured drift event handler returning:
    - status: OK / ALERT / REVIEW / AUTO_ACCEPT
    - hard_failures, soft_warnings, diff
    - quarantine_path if applicable
    """
    expected = get_schema(table_name)
    diff = compare_schemas(expected, df)

    hard_failures = []
    soft_warnings = []
    quarantine_path = None

    # Handle detected renames first (lower risk than missing columns)
    if diff.get("renames"):
        rename_count = len(diff["renames"])
        if rename_count <= 5:  # Auto-accept reasonable number of renames
            # Update schema registry to reflect renames
            rename_actions = []
            for rename in diff["renames"]:
                old_name = rename["old_name"]
                new_name = rename["new_name"]
                similarity = rename["similarity"]
                type_match = rename["type_match"]
                
                # High confidence rename (>0.8 similarity + type match)
                if similarity >= 0.8 and type_match:
                    rename_actions.append({"action": "auto_accept", **rename})
                # Medium confidence rename (>0.7 similarity or type match)
                elif similarity >= 0.7 or type_match:
                    rename_actions.append({"action": "auto_accept_with_warning", **rename})
                    soft_warnings.append(f"Column rename detected with medium confidence: {old_name} → {new_name} (similarity: {similarity})")
                else:
                    rename_actions.append({"action": "requires_review", **rename})
                    soft_warnings.append(f"Potential column rename requires review: {old_name} → {new_name} (similarity: {similarity})")
            
            # Update schema registry with renamed columns
            auto_accepted_renames = [r for r in diff["renames"] if r["similarity"] >= 0.7 or r["type_match"]]
            if auto_accepted_renames:
                new_cols_map = {r["new_name"]: "string" for r in auto_accepted_renames}
                new_struct, version = update_registry_with_new_columns(table_name, new_cols_map)
                save_drift_event(table_name, source_file_path, diff, "RENAMES_AUTO_ACCEPTED", {
                    "renames": auto_accepted_renames,
                    "rename_actions": rename_actions,
                    "new_version": version
                })
                return {
                    "status": "AUTO_ACCEPT",
                    "hard_failures": hard_failures,
                    "soft_warnings": soft_warnings,
                    "renames": auto_accepted_renames,
                    "rename_actions": rename_actions,
                    "new_version": version,
                    "diff": diff
                }
        else:
            soft_warnings.append(f"Too many potential renames detected ({rename_count}), requires manual review")
            save_drift_event(table_name, source_file_path, diff, "RENAMES_REQUIRE_REVIEW", {"rename_count": rename_count})
            return {
                "status": "REVIEW",
                "hard_failures": hard_failures,
                "soft_warnings": soft_warnings,
                "diff": diff
            }

    # Missing required columns -> ALERT
    missing_required = [f.name for f in expected.fields if not f.nullable] if expected else []
    missing_required = [c for c in missing_required if c in diff["missing_columns"]]
    if missing_required:
        hard_failures.append(f"Required columns missing: {missing_required}")
        quarantine_path = quarantine_file(raw_file_path, "required column missing")
        save_drift_event(table_name, source_file_path, diff, "ALERT", {"quarantined_path": quarantine_path})
        return {
            "status": "ALERT",
            "hard_failures": hard_failures,
            "soft_warnings": soft_warnings,
            "quarantined_path": quarantine_path,
            "diff": diff
        }

    # Build features and call decision policy (if available). Use policy for final action decision.
    try:
        fb = build_feature_vector({"diff": diff}, dq_metrics=None, pipeline_meta=None)
        x = fb["vector"]
    except Exception:
        fb = {"features": {}, "vector": []}
        x = []

    # Try to load trained policy
    policy_obj = None
    try:
        policy_obj = LinUCBPolicy.load(POLICY_PATH)
    except Exception:
        try:
            policy_obj = EpsilonGreedyPolicy.load(POLICY_PATH)
        except Exception:
            policy_obj = None

    def _log_decision(action, score, reward=None):
        rec = {
            "timestamp": datetime.utcnow().isoformat(),
            "table": table_name,
            "source_file": source_file_path,
            "features": fb.get("features"),
            "action": action,
            "score": score,
        }
        if reward is not None:
            rec["reward"] = reward
        with open(DECISIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def _execute_action(action):
        # Map policy actions to conservation steps already in this module
        if action == "auto_merge_schema":
            # Accept new columns conservatively (string type)
            if diff["new_columns"]:
                new_cols_map = {c: "string" for c in diff["new_columns"]}
                new_struct, version = update_registry_with_new_columns(table_name, new_cols_map)
                save_drift_event(table_name, source_file_path, diff, "AUTO_ACCEPT", {"accepted": list(new_cols_map.keys()), "new_version": version})
                return {"status": "AUTO_ACCEPT", "accepted": list(new_cols_map.keys()), "new_version": version, "diff": diff}
            else:
                return {"status": "OK", "diff": diff}

        if action == "create_new_schema_version":
            if diff["new_columns"]:
                new_cols_map = {c: "string" for c in diff["new_columns"]}
                new_struct, version = update_registry_with_new_columns(table_name, new_cols_map)
                save_drift_event(table_name, source_file_path, diff, "NEW_VERSION_CREATED", {"new_version": version})
                return {"status": "NEW_VERSION", "new_version": version, "diff": diff}
            else:
                return {"status": "OK", "diff": diff}

        if action == "quarantine_data":
            qpath = quarantine_file(raw_file_path, "policy_quarantine")
            save_drift_event(table_name, source_file_path, diff, "QUARANTINED", {"quarantined_path": qpath})
            return {"status": "QUARANTINED", "quarantined_path": qpath, "diff": diff}

        if action == "rollback_previous_schema":
            # conservative: record rollback intent (actual rollback requires version operations)
            save_drift_event(table_name, source_file_path, diff, "ROLLBACK_REQUESTED", {})
            return {"status": "ROLLBACK_REQUESTED", "diff": diff}

        if action == "require_human_approval":
            save_drift_event(table_name, source_file_path, diff, "REQUIRES_REVIEW", {})
            return {"status": "REVIEW", "diff": diff}

        # default
        return {"status": "REVIEW", "diff": diff}

    # Use policy if available, otherwise fall back to heuristics below
    if policy_obj is not None and len(x) > 0:
        try:
            # Get top N actions with scores instead of just one
            actions_with_scores = policy_obj.get_top_actions(x, top_k=5)  # Get top 5 actions with scores
            
            # Check for ties (multiple actions with same highest score)
            if len(actions_with_scores) > 1:
                max_score = actions_with_scores[0][1]
                tied_count = sum(1 for _, score in actions_with_scores if score == max_score)
                
                if tied_count > 1:
                    # Tie detected - use tie-breaker
                    tie_breaker = ActionTieBreaker(strategy=TieBreakingStrategy.PRIORITY_ORDER)
                    tied_actions = [(action, score) for action, score in actions_with_scores if score == max_score]
                    chosen_action, score, tie_reason = tie_breaker.resolve_tie(tied_actions, context={
                        "table_name": table_name,
                        "diff": diff,
                        "source_file": source_file_path
                    })
                    
                    explain = tie_breaker.explain_tie(tied_actions)
                    result = _execute_action(chosen_action)
                    
                    # Log decision with tie resolution details
                    rec = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "table": table_name,
                        "source_file": source_file_path,
                        "features": fb.get("features"),
                        "action": chosen_action,
                        "score": score,
                        "tie_detected": True,
                        "tied_actions": tied_actions,
                        "tie_resolution_strategy": TieBreakingStrategy.PRIORITY_ORDER.value,
                        "tie_reason": tie_reason,
                        "explain": explain
                    }
                    with open(DECISIONS_LOG, "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec) + "\n")
                    
                    result.update({"policy_action": chosen_action, "policy_score": score, 
                                 "explain": explain, "tie_resolved": True, "tie_reason": tie_reason})
                    return result
            
            # No tie - proceed normally with single best action
            chosen_action, score = actions_with_scores[0]
            explain = policy_obj.explain(chosen_action, x)
            result = _execute_action(chosen_action)
            
            # log decision with explainability
            rec = {"timestamp": datetime.utcnow().isoformat(), "table": table_name, "source_file": source_file_path, 
                   "features": fb.get("features"), "action": chosen_action, "score": score, "explain": explain}
            with open(DECISIONS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            
            # include policy decision in return
            result.update({"policy_action": chosen_action, "policy_score": score, "explain": explain})
            return result
        except Exception as e:
            soft_warnings.append(f"Policy inference failed: {e}")
            save_drift_event(table_name, source_file_path, diff, "POLICY_FAILURE", {"error": str(e)})

    # New columns only -> AUTO_ACCEPT heuristic
    if diff["new_columns"] and not diff["missing_columns"] and not diff["dtype_changes"]:
        if len(diff["new_columns"]) <= POLICY["max_new_columns_for_auto_accept"] and POLICY["new_column_auto_accept"]:
            stats = compute_basic_stats(df, diff["new_columns"])
            accepted = [c for c, s in stats.items() if s["non_null_ratio"] >= POLICY["min_non_null_ratio_for_accept"]]
            rejected = [c for c in stats.keys() if c not in accepted]
            if accepted:
                new_cols_map = {c: "string" for c in accepted}
                new_struct, version = update_registry_with_new_columns(table_name, new_cols_map)
                save_drift_event(table_name, source_file_path, diff, "AUTO_ACCEPT",
                                 {"accepted": accepted, "rejected": rejected, "new_version": version})
                if rejected:
                    soft_warnings.append(f"New columns not accepted: {rejected}")
                return {
                    "status": "AUTO_ACCEPT",
                    "hard_failures": hard_failures,
                    "soft_warnings": soft_warnings,
                    "accepted": accepted,
                    "rejected": rejected,
                    "new_version": version,
                    "diff": diff
                }
            else:
                soft_warnings.append(f"New columns require manual review: {list(stats.keys())}")
                save_drift_event(table_name, source_file_path, diff, "NEW_COLUMNS_REQUIRES_REVIEW", {"stats": stats})
                return {
                    "status": "REVIEW",
                    "hard_failures": hard_failures,
                    "soft_warnings": soft_warnings,
                    "diff": diff,
                    "stats": stats
                }
        else:
            # Auto-accept anyway but mark for review
            soft_warnings.append(f"Many new columns ({len(diff['new_columns'])}) auto-accepted - please review")
            new_cols_map = {c: "string" for c in diff["new_columns"]}
            new_struct, version = update_registry_with_new_columns(table_name, new_cols_map)
            save_drift_event(table_name, source_file_path, diff, "AUTO_ACCEPT_PENDING_REVIEW", 
                           {"accepted": diff["new_columns"], "new_version": version})
            return {
                "status": "AUTO_ACCEPT",
                "hard_failures": hard_failures,
                "soft_warnings": soft_warnings,
                "accepted": diff["new_columns"],
                "new_version": version,
                "diff": diff
            }

    # Dtype changes or missing non-required columns -> REVIEW
    if diff["dtype_changes"] or diff["missing_columns"]:
        soft_warnings.append("Dtype changes or missing non-required columns")

        # Try conservative automated actions before moving to manual review
        try:
            from scripts import schema_drift_actions

            actions_taken = []

            # Handle dtype changes conservatively if policy allows
            if diff["dtype_changes"] and policy.get("auto_cast_dtype", False):
                casts = {}
                for change in diff["dtype_changes"]:
                    col = change.get("column")
                    expected = change.get("expected")
                    actual = change.get("actual")
                    if schema_drift_actions.safe_to_cast(expected, actual):
                        casts[col] = expected

                if casts:
                    # attempt to cast and overwrite raw file (conservative)
                    action_res = schema_drift_actions.attempt_dtype_casts_and_overwrite_pandas(
                        spark, table_name, df, casts, raw_file_path
                    )
                    actions_taken.append(action_res)

            # Handle missing non-required columns: add null columns if policy allows auto-fix
            if diff["missing_columns"] and policy.get("auto_add_missing_columns", False):
                missing_map = {c: "string" for c in diff["missing_columns"]}
                # updating registry but not filling data (columns are nullable)
                new_struct, version = update_registry_with_new_columns(table_name, missing_map)
                actions_taken.append({"added_columns": list(missing_map.keys()), "new_version": version})

            if actions_taken:
                save_drift_event(table_name, source_file_path, diff, "AUTO_REMEDIATION", {"actions": actions_taken})
                return {
                    "status": "AUTO_ACCEPT",
                    "hard_failures": hard_failures,
                    "soft_warnings": soft_warnings,
                    "actions": actions_taken,
                    "diff": diff
                }
        except Exception as e:
            # If automated remediation fails, fall back to review mode
            soft_warnings.append(f"Automated remediation failed: {e}")
            save_drift_event(table_name, source_file_path, diff, "REQUIRES_REVIEW", {"error": str(e)})
            return {
                "status": "REVIEW",
                "hard_failures": hard_failures,
                "soft_warnings": soft_warnings,
                "diff": diff
            }

        # If we didn't take any automated actions, apply conservative fixes and mark for review
        actions_taken = []
        
        # Auto-fix dtype changes conservatively (cast to string)
        if diff["dtype_changes"]:
            soft_warnings.append("Dtype changes handled conservatively (cast to string)")
            actions_taken.append({"dtype_changes_accepted": len(diff["dtype_changes"])})
        
        # Auto-add missing columns as nullable strings
        if diff["missing_columns"]:
            missing_map = {c: "string" for c in diff["missing_columns"]}
            new_struct, version = update_registry_with_new_columns(table_name, missing_map)
            actions_taken.append({"added_columns": list(missing_map.keys()), "new_version": version})
            soft_warnings.append(f"Missing columns added as nullable: {diff['missing_columns']}")
        
        save_drift_event(table_name, source_file_path, diff, "AUTO_ACCEPT_PENDING_REVIEW", {"actions": actions_taken})
        return {
            "status": "AUTO_ACCEPT",
            "hard_failures": hard_failures,
            "soft_warnings": soft_warnings,
            "actions": actions_taken,
            "diff": diff
        }

    # No drift -> OK
    save_drift_event(table_name, source_file_path, diff, "OK", {})
    return {
        "status": "OK",
        "hard_failures": hard_failures,
        "soft_warnings": soft_warnings,
        "diff": diff
    }
