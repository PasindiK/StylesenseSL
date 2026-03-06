"""
Seasonal Storage Tier Management for Sri Lankan Fashion Retail
Manages medallion layers based on business seasons and realistic lifecycle policy
Includes metadata persistence for tier assignments in Azure
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, StandardBlobTier

logger = logging.getLogger(__name__)


class BusinessSeason(Enum):
    """Sri Lankan business seasons for fashion retail"""

    FESTIVE_SEASON = "festive"
    MONSOON_SEASON = "monsoon"
    DRY_SEASON = "dry"
    HISTORICAL_ARCHIVE = "historical"


class SeasonalTierManager:
    """Manages storage tiers using layer, data age, access hints, and seasonal logic."""

    def __init__(self, azure_connection_string: str):
        self.conn_str = azure_connection_string
        self.client = BlobServiceClient.from_connection_string(azure_connection_string)

        self.season_calendar = {
            1: BusinessSeason.FESTIVE_SEASON,
            2: BusinessSeason.DRY_SEASON,
            3: BusinessSeason.DRY_SEASON,
            4: BusinessSeason.FESTIVE_SEASON,
            5: BusinessSeason.MONSOON_SEASON,
            6: BusinessSeason.MONSOON_SEASON,
            7: BusinessSeason.MONSOON_SEASON,
            8: BusinessSeason.MONSOON_SEASON,
            9: BusinessSeason.MONSOON_SEASON,
            10: BusinessSeason.DRY_SEASON,
            11: BusinessSeason.DRY_SEASON,
            12: BusinessSeason.FESTIVE_SEASON,
        }

        self.festive_dates = {
            (1, 14): "Thai Pongal",
            (2, 5): "Independence Day",
            (4, 13): "Sinhala & Tamil New Year",
            (5, 1): "Labour Day",
            (8, 15): "Assumption Day",
            (10, 31): "Deepavali",
            (12, 25): "Christmas",
        }

        self.tier_config = {
            StandardBlobTier.HOT: {
                "cost": "$$$$",
                "latency_ms": 50,
                "use_case": "Real-time dashboards, AI predictions",
                "description": "High-frequency access",
            },
            StandardBlobTier.COOL: {
                "cost": "$$$",
                "latency_ms": 500,
                "use_case": "Weekly reports, moderate analysis",
                "description": "Moderate-frequency access",
            },
            StandardBlobTier.ARCHIVE: {
                "cost": "$",
                "latency_ms": 5000,
                "use_case": "Historical trends, year-over-year comparison",
                "description": "Rare access, long-term retention",
            },
        }

        self.layer_age_policy = {
            "bronze": {
                "hot_max_age_days": 3,
                "cool_max_age_days": 14,
                "archive_retention_days": 365,
            },
            "silver": {
                "hot_max_age_days": 7,
                "cool_max_age_days": 60,
                "archive_retention_days": 730,
            },
            "gold": {
                "hot_max_age_days": 30,
                "cool_max_age_days": 90,
                "archive_retention_days": 1825,
            },
        }

        self.seasonal_age_multiplier = {
            BusinessSeason.FESTIVE_SEASON: 1.2,
            BusinessSeason.MONSOON_SEASON: 1.0,
            BusinessSeason.DRY_SEASON: 0.9,
            BusinessSeason.HISTORICAL_ARCHIVE: 0.8,
        }

        self.access_policy = {
            "hot_if_accessed_within_days": 1,
            "cool_if_accessed_within_days": 7,
        }

        self.seasonal_keywords = {
            BusinessSeason.FESTIVE_SEASON: [
                "festive",
                "new_year",
                "christmas",
                "deepavali",
                "holiday",
                "partywear",
                "gift",
            ],
            BusinessSeason.MONSOON_SEASON: [
                "monsoon",
                "rain",
                "rainwear",
                "winter",
                "winter_apparel",
                "jacket",
                "hoodie",
            ],
            BusinessSeason.DRY_SEASON: [
                "summer",
                "dry",
                "beach",
                "linen",
                "lightwear",
            ],
            BusinessSeason.HISTORICAL_ARCHIVE: [],
        }

    def get_current_season(self) -> Tuple[BusinessSeason, str]:
        """Determine current business season."""
        now = datetime.now()
        month = now.month

        if (now.month, now.day) in self.festive_dates:
            holiday = self.festive_dates[(now.month, now.day)]
            return BusinessSeason.FESTIVE_SEASON, f"Festive: {holiday}"

        season = self.season_calendar.get(month, BusinessSeason.DRY_SEASON)
        return season, f"{season.value.title()} Season (Month {month})"

    def get_tier_for_season(self, season: BusinessSeason) -> Tuple[StandardBlobTier, str]:
        """Get default tier profile for a season."""
        tier_map = {
            BusinessSeason.FESTIVE_SEASON: (
                StandardBlobTier.HOT,
                "Peak demand: prioritize low-latency retrieval",
            ),
            BusinessSeason.MONSOON_SEASON: (
                StandardBlobTier.COOL,
                "Moderate demand: balanced cost and access",
            ),
            BusinessSeason.DRY_SEASON: (
                StandardBlobTier.COOL,
                "Off-season: optimize for cost while retaining access",
            ),
            BusinessSeason.HISTORICAL_ARCHIVE: (
                StandardBlobTier.ARCHIVE,
                "Historical mode: deep archive posture",
            ),
        }
        return tier_map.get(season, (StandardBlobTier.COOL, "Default"))

    def get_medallion_tier_strategy(self, layer: str, season: BusinessSeason) -> Dict[str, Any]:
        """Get summary strategy for a layer under current seasonal context."""
        normalized_layer = layer.lower()
        policy = self.layer_age_policy.get(normalized_layer, self.layer_age_policy["silver"])
        multiplier = self.seasonal_age_multiplier.get(season, 1.0)
        hot_days = max(1, int(round(policy["hot_max_age_days"] * multiplier)))
        cool_days = max(hot_days + 1, int(round(policy["cool_max_age_days"] * multiplier)))
        seasonal_tier, _ = self.get_tier_for_season(season)

        return {
            "tier": seasonal_tier,
            "retention_days": cool_days,
            "reason": (
                f"{normalized_layer.title()} policy: < {hot_days}d HOT, "
                f"{hot_days}-{cool_days}d COOL, > {cool_days}d ARCHIVE"
            ),
        }

    def _policy_rules_payload(self) -> Dict[str, Any]:
        """Return dashboard-facing policy explanation payload."""
        return {
            "layer_rules": {
                "bronze": {
                    "hot": "< 3 days",
                    "cool": "3-14 days",
                    "archive": "> 14 days",
                },
                "silver": {
                    "hot": "< 7 days",
                    "cool": "7-60 days",
                    "archive": "> 60 days",
                },
                "gold": {
                    "hot": "< 30 days",
                    "cool": "30-90 days",
                    "archive": "> 90 days",
                },
            },
            "access_overrides": {
                "promote_to_hot": "If accessed within 1 day (when access telemetry exists)",
                "promote_archive_to_cool": "If accessed within 7 days (when access telemetry exists)",
            },
            "seasonal_override": "Datasets matching current seasonal product keywords are promoted to HOT",
            "seasonal_examples": {
                "festive": ["festive", "christmas", "deepavali", "partywear"],
                "monsoon": ["monsoon", "rainwear", "winter_apparel", "jacket"],
                "dry": ["summer", "linen", "lightwear"],
            },
        }

    def get_policy_explanation(self) -> Dict[str, Any]:
        """Public method for API layer to render policy transparency panel."""
        return self._policy_rules_payload()

    def _ensure_metadata_container(self):
        """Create tier-metadata container if it doesn't exist."""
        try:
            container_client = self.client.get_container_client("tier-metadata")
            if not container_client.exists():
                container_client.create_container()
                logger.info("✓ Created tier-metadata container")
        except Exception as e:
            logger.warning(f"Could not create metadata container: {e}")

    def _tier_name_to_enum(self, tier_name: str) -> StandardBlobTier:
        normalized = (tier_name or "").strip().upper()
        if normalized == "HOT":
            return StandardBlobTier.HOT
        if normalized == "COOL":
            return StandardBlobTier.COOL
        if normalized == "ARCHIVE":
            return StandardBlobTier.ARCHIVE
        return StandardBlobTier.COOL

    def _tier_value_to_name(self, tier_value: Any) -> str:
        if isinstance(tier_value, StandardBlobTier):
            return str(tier_value.value).upper()
        if isinstance(tier_value, str):
            return tier_value.upper()
        return "HOT"

    def _tier_name_to_bucket(self, tier_name: str) -> str:
        normalized = (tier_name or "").upper()
        if normalized == "HOT":
            return "hot"
        if normalized == "COOL":
            return "cold"
        if normalized == "ARCHIVE":
            return "archive"
        return "warm"

    def _days_since(self, value: Optional[datetime]) -> Optional[int]:
        if value is None:
            return None
        dt_value = value
        if dt_value.tzinfo is None:
            dt_value = dt_value.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        delta = now_utc - dt_value.astimezone(timezone.utc)
        return max(0, int(delta.total_seconds() // 86400))

    def _to_iso(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        dt_value = value
        if dt_value.tzinfo is None:
            dt_value = dt_value.replace(tzinfo=timezone.utc)
        return dt_value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _extract_dataset_name(self, blob_path: str) -> str:
        """Extract stable dataset identifier from blob path."""
        filename = blob_path.split("/")[-1]
        name = re.sub(r"\.(parquet|csv|jsonl?|snappy)$", "", filename, flags=re.IGNORECASE)
        name = re.sub(r"_\d{8}_\d{6}$", "", name)
        name = re.sub(r"_\d{8}$", "", name)

        if name.startswith("batch_"):
            parts = name.split("_")
            if len(parts) >= 2:
                return f"batch_{parts[1]}"
            return "batch"

        for suffix in ["_cleaned", "_enriched", "_curated"]:
            if suffix in name:
                return name.split(suffix)[0]

        return name

    def _matches_seasonal_override(
        self, dataset_name: str, season: BusinessSeason
    ) -> Tuple[bool, Optional[str]]:
        dataset_token = (dataset_name or "").lower()
        keywords = self.seasonal_keywords.get(season, [])
        for keyword in keywords:
            if keyword in dataset_token:
                return True, keyword
        return False, None

    def evaluate_blob_policy(
        self,
        layer: str,
        dataset_name: str,
        last_modified: Optional[datetime],
        last_accessed: Optional[datetime],
        season: Optional[BusinessSeason] = None,
    ) -> Dict[str, Any]:
        """Evaluate target tier for a blob using age, access, and seasonal rules."""
        current_season = season or self.get_current_season()[0]
        layer_name = layer.lower()
        policy = self.layer_age_policy.get(layer_name, self.layer_age_policy["silver"])

        multiplier = self.seasonal_age_multiplier.get(current_season, 1.0)
        hot_limit = max(1, int(round(policy["hot_max_age_days"] * multiplier)))
        cool_limit = max(hot_limit + 1, int(round(policy["cool_max_age_days"] * multiplier)))

        data_age_days = self._days_since(last_modified)
        access_days = self._days_since(last_accessed)

        target_tier = StandardBlobTier.COOL
        retention_days = cool_limit
        reason_type = "age-based"

        if data_age_days is None:
            tier_reason = (
                f"age-based fallback: missing last_modified, defaulting {layer_name} dataset to COOL"
            )
        elif data_age_days < hot_limit:
            target_tier = StandardBlobTier.HOT
            retention_days = hot_limit
            tier_reason = (
                f"age-based: {data_age_days}d old (< {hot_limit}d threshold) for {layer_name} layer"
            )
        elif data_age_days <= cool_limit:
            target_tier = StandardBlobTier.COOL
            retention_days = cool_limit
            tier_reason = (
                f"age-based: {data_age_days}d old (between {hot_limit}-{cool_limit}d) for {layer_name} layer"
            )
        else:
            target_tier = StandardBlobTier.ARCHIVE
            retention_days = policy["archive_retention_days"]
            tier_reason = (
                f"age-based: {data_age_days}d old (> {cool_limit}d threshold), archiving {layer_name} data"
            )

        if access_days is not None:
            if access_days <= self.access_policy["hot_if_accessed_within_days"] and target_tier != StandardBlobTier.HOT:
                target_tier = StandardBlobTier.HOT
                retention_days = hot_limit
                reason_type = "access-based"
                tier_reason = (
                    f"access-based override: accessed {access_days}d ago, promoted to HOT"
                )
            elif (
                access_days <= self.access_policy["cool_if_accessed_within_days"]
                and target_tier == StandardBlobTier.ARCHIVE
            ):
                target_tier = StandardBlobTier.COOL
                retention_days = cool_limit
                reason_type = "access-based"
                tier_reason = (
                    f"access-based override: accessed {access_days}d ago, promoted to COOL"
                )

        seasonal_match, matched_keyword = self._matches_seasonal_override(dataset_name, current_season)
        if seasonal_match:
            target_tier = StandardBlobTier.HOT
            retention_days = hot_limit
            reason_type = "seasonal"
            tier_reason = (
                f"seasonal override: '{matched_keyword}' matches {current_season.value} catalog focus"
            )

        return {
            "target_tier": target_tier,
            "target_policy_tier": self._tier_value_to_name(target_tier),
            "retention_days": retention_days,
            "tier_reason": tier_reason,
            "tier_reason_type": reason_type,
            "data_age_days": data_age_days,
            "access_frequency_days": access_days,
            "hot_threshold_days": hot_limit,
            "cool_threshold_days": cool_limit,
        }

    def _evaluate_blob_and_apply_tier(
        self,
        container_name: str,
        blob: Any,
        season: BusinessSeason,
        apply_changes: bool = True,
    ) -> Dict[str, Any]:
        """Evaluate and optionally apply policy tier for one blob."""
        dataset_name = self._extract_dataset_name(blob.name)
        layer = container_name.lower()
        last_modified = getattr(blob, "last_modified", None)
        last_accessed = getattr(blob, "last_accessed_on", None)

        policy = self.evaluate_blob_policy(
            layer=layer,
            dataset_name=dataset_name,
            last_modified=last_modified,
            last_accessed=last_accessed,
            season=season,
        )

        observed_tier = self._tier_value_to_name(getattr(blob, "blob_tier", None) or "Hot")
        current_tier = observed_tier
        tier_change_applied = False
        tier_apply_error = None

        if apply_changes and observed_tier != policy["target_policy_tier"]:
            try:
                blob_client = self.client.get_blob_client(container_name, blob.name)
                blob_client.set_standard_blob_tier(policy["target_tier"])
                tier_change_applied = True
                try:
                    blob_props = blob_client.get_blob_properties()
                    current_tier = self._tier_value_to_name(
                        getattr(blob_props, "blob_tier", None) or policy["target_tier"]
                    )
                except Exception:
                    current_tier = policy["target_policy_tier"]
            except Exception as exc:
                tier_apply_error = str(exc)
                logger.warning(
                    "Could not set tier for %s/%s to %s: %s",
                    container_name,
                    blob.name,
                    policy["target_policy_tier"],
                    exc,
                )

        return {
            "dataset_name": dataset_name,
            "medallion_layer": layer,
            "blob_path": blob.name,
            "current_blob_tier": current_tier,
            "target_policy_tier": policy["target_policy_tier"],
            "data_age_days": policy["data_age_days"],
            "retention_days": policy["retention_days"],
            "tier_reason": policy["tier_reason"],
            "tier_reason_type": policy["tier_reason_type"],
            "access_frequency_days": policy["access_frequency_days"],
            "last_modified": self._to_iso(last_modified),
            "last_accessed": self._to_iso(last_accessed),
            "tier_change_applied": tier_change_applied,
            "tier_apply_error": tier_apply_error,
        }

    def set_tier_for_layer(
        self, container: str, layer: str, season: Optional[BusinessSeason] = None
    ) -> bool:
        """Apply policy-based tiers for every blob in a medallion layer."""
        current_season = season or self.get_current_season()[0]

        try:
            container_client = self.client.get_container_client(container)
            evaluated_count = 0
            changed_count = 0

            for blob in container_client.list_blobs():
                detail = self._evaluate_blob_and_apply_tier(
                    container_name=container,
                    blob=blob,
                    season=current_season,
                    apply_changes=True,
                )
                evaluated_count += 1
                if detail["tier_change_applied"]:
                    changed_count += 1

            logger.info(
                "✓ Applied policy-based tiering for %s: %s blobs evaluated, %s tier changes",
                layer,
                evaluated_count,
                changed_count,
            )
            return True
        except Exception as e:
            logger.error(f"✗ Failed to set tier for {layer}: {str(e)}")
            return False

    def get_tier_assignments(self) -> Dict[str, Any]:
        """Get current tier assignments from Azure metadata."""
        try:
            self._ensure_metadata_container()
            blob_client = self.client.get_blob_client(
                "tier-metadata", "current_tier_assignments.json"
            )
            data = blob_client.download_blob().readall()
            assignments = json.loads(data)

            for key in ["hot", "warm", "cold", "archive"]:
                assignments.setdefault(key, [])

            assignments.setdefault("dataset_details", [])
            assignments.setdefault("policy_rules", self._policy_rules_payload())
            assignments.setdefault("season", self.get_current_season()[0].value)
            assignments.setdefault("auto_tiering_enabled", True)
            assignments.setdefault("last_updated", datetime.utcnow().isoformat() + "Z")
            return assignments

        except ResourceNotFoundError:
            season, _ = self.get_current_season()
            return {
                "hot": [],
                "warm": [],
                "cold": [],
                "archive": [],
                "dataset_details": [],
                "policy_rules": self._policy_rules_payload(),
                "last_updated": datetime.utcnow().isoformat() + "Z",
                "season": season.value,
                "auto_tiering_enabled": True,
            }
        except Exception as e:
            logger.error(f"Error reading tier assignments: {e}")
            season, _ = self.get_current_season()
            return {
                "hot": [],
                "warm": [],
                "cold": [],
                "archive": [],
                "dataset_details": [],
                "policy_rules": self._policy_rules_payload(),
                "last_updated": datetime.utcnow().isoformat() + "Z",
                "season": season.value,
                "auto_tiering_enabled": True,
            }

    def save_tier_assignments(self, assignments: Dict[str, Any]) -> bool:
        """Save tier assignments to Azure metadata."""
        try:
            self._ensure_metadata_container()

            payload = dict(assignments)
            payload.setdefault("dataset_details", [])
            payload.setdefault("policy_rules", self._policy_rules_payload())
            payload["last_updated"] = datetime.utcnow().isoformat() + "Z"

            blob_client = self.client.get_blob_client(
                "tier-metadata", "current_tier_assignments.json"
            )
            blob_client.upload_blob(json.dumps(payload, indent=2), overwrite=True)

            self._append_to_history(payload)

            logger.info("✓ Saved tier assignments to Azure")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to save tier assignments: {e}")
            return False

    def _append_to_history(self, assignments: Dict[str, Any]):
        """Append current assignment to monthly history log."""
        try:
            history_blob_name = (
                f"history/tier_assignments_{datetime.utcnow().strftime('%Y%m')}.jsonl"
            )
            blob_client = self.client.get_blob_client("tier-metadata", history_blob_name)

            try:
                existing_data = blob_client.download_blob().readall().decode("utf-8")
            except ResourceNotFoundError:
                existing_data = ""

            new_entry = json.dumps(
                {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "assignments": assignments,
                }
            ) + "\n"

            blob_client.upload_blob(existing_data + new_entry, overwrite=True)
            logger.debug(f"✓ Appended to history: {history_blob_name}")
        except Exception as e:
            logger.warning(f"Could not append to history: {e}")

    def sync_tier_assignments_from_azure(self) -> Dict[str, Any]:
        """Scan Azure containers, apply policy tiering, and sync assignment metadata."""
        season, _ = self.get_current_season()
        now_iso = datetime.utcnow().isoformat() + "Z"

        assignments: Dict[str, Any] = {
            "hot": [],
            "warm": [],
            "cold": [],
            "archive": [],
            "dataset_details": [],
            "policy_rules": self._policy_rules_payload(),
            "last_updated": now_iso,
            "season": season.value,
            "auto_tiering_enabled": True,
        }

        bucket_sets = {
            "hot": set(),
            "warm": set(),
            "cold": set(),
            "archive": set(),
        }

        try:
            for container_name in ["bronze", "silver", "gold"]:
                try:
                    container_client = self.client.get_container_client(container_name)

                    for blob in container_client.list_blobs():
                        detail = self._evaluate_blob_and_apply_tier(
                            container_name=container_name,
                            blob=blob,
                            season=season,
                            apply_changes=True,
                        )

                        assignments["dataset_details"].append(detail)

                        bucket = self._tier_name_to_bucket(detail["current_blob_tier"])
                        bucket_sets[bucket].add(detail["dataset_name"])
                except Exception as e:
                    logger.warning(f"Could not scan container {container_name}: {e}")

            assignments["hot"] = sorted(bucket_sets["hot"])
            assignments["warm"] = sorted(bucket_sets["warm"])
            assignments["cold"] = sorted(bucket_sets["cold"])
            assignments["archive"] = sorted(bucket_sets["archive"])

            assignments["dataset_details"] = sorted(
                assignments["dataset_details"],
                key=lambda item: (
                    item.get("medallion_layer", ""),
                    item.get("dataset_name", ""),
                    item.get("blob_path", ""),
                ),
            )

            self.save_tier_assignments(assignments)
            return assignments

        except Exception as e:
            logger.error(f"Error scanning tier assignments: {e}")
            return assignments

    def print_current_strategy(self):
        """Print current seasonal and age-based strategy summary."""
        season, season_desc = self.get_current_season()

        print("\n" + "=" * 70)
        print("SEASONAL + LIFECYCLE TIER STRATEGY".center(70))
        print("=" * 70)
        print(f"\n📅 Current Season: {season_desc}")

        multiplier = self.seasonal_age_multiplier.get(season, 1.0)
        print(f"🌤️  Seasonal age multiplier: {multiplier:.2f}")

        for layer in ["bronze", "silver", "gold"]:
            policy = self.layer_age_policy[layer]
            hot_days = max(1, int(round(policy["hot_max_age_days"] * multiplier)))
            cool_days = max(hot_days + 1, int(round(policy["cool_max_age_days"] * multiplier)))

            print(f"\n{layer.upper()} Layer:")
            print(f"  HOT:      < {hot_days} days")
            print(f"  COOL:     {hot_days}-{cool_days} days")
            print(f"  ARCHIVE:  > {cool_days} days")
            print(f"  Retain archive up to: {policy['archive_retention_days']} days")

        print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        print("Error: AZURE_STORAGE_CONNECTION_STRING not set")
        raise SystemExit(1)

    manager = SeasonalTierManager(conn_str)
    manager.print_current_strategy()

    for layer, container in [("bronze", "bronze"), ("silver", "silver"), ("gold", "gold")]:
        manager.set_tier_for_layer(container, layer)
