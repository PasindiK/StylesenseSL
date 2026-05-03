from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class MetricResult:
    risk: float
    z_score: float
    baseline_mean: float | None
    baseline_std: float | None
    latest_value: float | None
    sample_size: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk": round(float(self.risk), 6),
            "z_score": round(float(self.z_score), 6),
            "baseline_mean": None if self.baseline_mean is None else round(float(self.baseline_mean), 6),
            "baseline_std": None if self.baseline_std is None else round(float(self.baseline_std), 6),
            "latest_value": None if self.latest_value is None else round(float(self.latest_value), 6),
            "sample_size": int(self.sample_size),
            "confidence": round(float(self.confidence), 6),
        }


class GovernanceIntelligenceEngine:
    """Adaptive Domain Governance Reliability Index (ADGRI) engine.

    Formal model:
      r = [r_v, r_f, r_d] where each r_i in [0,1] is instability risk.
      c = [c_v, c_f, c_d] where each c_i in [0,1] is confidence.
      w_i = c_i / sum(c)  (confidence-aware adaptive weighting)
      R_adgri = w_v*r_v + w_f*r_f + w_d*r_d
      ADGRI = 100 * (1 - R_adgri)
    """

    def __init__(
        self,
        data_path: Path,
        monitoring_history_path: Path,
        rolling_window_days: int = 14,
    ) -> None:
        self.data_path = data_path
        self.monitoring_history_path = monitoring_history_path
        self.pipeline_log_path = monitoring_history_path.parent / "logs" / "pipeline_log.json"
        self.rolling_window_days = max(7, int(rolling_window_days))

    def governance_summary(self) -> dict[str, Any]:
        domains = self._list_domains()
        results: list[dict[str, Any]] = []
        for domain in domains:
            try:
                results.append(self._compute_domain_governance(domain))
            except Exception as exc:
                results.append({"domain_name": domain, "error": str(exc)})

        ranked = [item for item in results if "governance_score" in item]
        ranked.sort(key=lambda item: item.get("governance_score", 0.0), reverse=True)

        as_of = datetime.now().isoformat(timespec="seconds")
        return {
            "index_name": "Adaptive Domain Governance Reliability Index (ADGRI)",
            "formula": {
                "weighted_risk": "R_adgri = w_v*r_v + w_f*r_f + w_d*r_d",
                "weights": "w_i = c_i / (c_v + c_f + c_d)",
                "score": "ADGRI = 100 * (1 - R_adgri)",
            },
            "window_days": self.rolling_window_days,
            "generated_at": as_of,
            "as_of": as_of,
            "trend_basis": "governance_refresh_cycles",
            "domains": ranked,
            "errors": [item for item in results if "governance_score" not in item],
        }

    def governance_domain(self, domain_name: str) -> dict[str, Any]:
        return self._compute_domain_governance(domain_name)

    def evaluate_domain_scenarios(self, domain_name: str) -> dict[str, Any]:
        baseline = self._compute_domain_governance(domain_name)
        base_volume = float(baseline["volume_stability"]["risk"])
        base_freshness = float(baseline["freshness_stability"]["risk"])
        base_distribution = float(baseline["distribution_stability"]["risk"])
        base_conf_score = float((baseline.get("confidence") or {}).get("score", 0.0))
        base_conf_level = str((baseline.get("confidence") or {}).get("level", self._confidence_label(base_conf_score)))
        base_trend_direction = str(baseline.get("trend_direction") or "stable")
        base_trend_slope = float(baseline.get("trend_slope") or 0.0)
        weights = baseline.get("weights", {"volume": 1 / 3, "freshness": 1 / 3, "distribution": 1 / 3})

        scenario_inputs = {
            "normal_behavior": (base_volume, base_freshness, base_distribution),
            "delayed_refresh": (base_volume, min(1.0, base_freshness + 0.30), base_distribution),
            "sudden_volume_drop": (min(1.0, base_volume + 0.35), base_freshness, base_distribution),
            "distribution_shift": (base_volume, base_freshness, min(1.0, base_distribution + 0.35)),
        }

        scenarios: list[dict[str, Any]] = []
        for scenario_name, (rv, rf, rd) in scenario_inputs.items():
            contributions = {
                "volume": float(weights.get("volume", 0.0)) * rv,
                "freshness": float(weights.get("freshness", 0.0)) * rf,
                "distribution": float(weights.get("distribution", 0.0)) * rd,
            }
            weighted_risk = contributions["volume"] + contributions["freshness"] + contributions["distribution"]
            score = max(0.0, 100.0 * (1.0 - weighted_risk))
            score_delta = score - float(baseline["adgri_score"])
            top_factor = max(contributions.items(), key=lambda item: item[1])[0]

            perturbation = (
                abs(rv - base_volume) * float(weights.get("volume", 0.0))
                + abs(rf - base_freshness) * float(weights.get("freshness", 0.0))
                + abs(rd - base_distribution) * float(weights.get("distribution", 0.0))
            )
            scenario_conf_score = self._bounded(base_conf_score * (1.0 - min(0.6, perturbation)))
            scenario_conf_level = self._confidence_label(scenario_conf_score)

            projected_slope = round(float(base_trend_slope + (score_delta / 10.0)), 6)
            if projected_slope > 0.2:
                trend_response = "improving"
            elif projected_slope < -0.2:
                trend_response = "deteriorating"
            else:
                trend_response = "stable"

            scenarios.append(
                {
                    "scenario": scenario_name,
                    "adgri_score": round(score, 4),
                    "delta_vs_baseline": round(score_delta, 4),
                    "top_contributor": top_factor,
                    "trend_response": {
                        "baseline_direction": base_trend_direction,
                        "baseline_slope": round(float(base_trend_slope), 6),
                        "projected_direction": trend_response,
                        "projected_slope": projected_slope,
                    },
                    "confidence": {
                        "score": round(float(scenario_conf_score), 6),
                        "level": scenario_conf_level,
                    },
                    "contribution_breakdown": {
                        "volume": round(float(contributions["volume"]), 6),
                        "freshness": round(float(contributions["freshness"]), 6),
                        "distribution": round(float(contributions["distribution"]), 6),
                    },
                }
            )

        return {
            "domain_name": domain_name,
            "baseline": {
                "adgri_score": baseline.get("adgri_score"),
                "weights": baseline.get("weights"),
                "trend": {
                    "direction": base_trend_direction,
                    "slope": round(float(base_trend_slope), 6),
                },
                "confidence": {
                    "score": round(float(base_conf_score), 6),
                    "level": base_conf_level,
                },
                "risks": {
                    "volume": base_volume,
                    "freshness": base_freshness,
                    "distribution": base_distribution,
                },
            },
            "scenarios": scenarios,
        }

    def _compute_domain_governance(self, domain_name: str) -> dict[str, Any]:
        evaluation_ts = datetime.now()
        history = self._load_history_for_domain(domain_name)
        domain_df, file_path = self._load_domain_csv(domain_name)
        current_row_count = int(len(domain_df))

        refresh_observations = self._build_refresh_observations(
            domain_name=domain_name,
            history=history,
            domain_file_path=file_path,
            current_row_count=current_row_count,
        )

        refresh_row_series = pd.to_numeric(refresh_observations["row_count"], errors="coerce") if not refresh_observations.empty else pd.Series(dtype=float)
        volume_metric = self._metric_from_series(refresh_row_series)

        distribution_payload = self._distribution_metric(domain_df)
        freshness_metric, latest_refresh_ts, freshness_source = self._freshness_metric(
            history=history,
            refresh_observations=refresh_observations,
            evaluation_ts=evaluation_ts,
            domain_file_path=file_path,
            latest_business_data_date=distribution_payload.get("latest_business_data_date"),
        )
        distribution_metric = distribution_payload["metric"]

        weights = self._dynamic_weights(
            volume_metric.confidence,
            freshness_metric.confidence,
            distribution_metric.confidence,
        )

        contributions = {
            "volume": weights["volume"] * volume_metric.risk,
            "freshness": weights["freshness"] * freshness_metric.risk,
            "distribution": weights["distribution"] * distribution_metric.risk,
        }
        weighted_risk = contributions["volume"] + contributions["freshness"] + contributions["distribution"]
        adgri_score = max(0.0, 100.0 * (1.0 - weighted_risk))

        top_factor = max(contributions.items(), key=lambda item: item[1])[0]
        trend = self._risk_trend(refresh_observations, distribution_metric.risk, weights)
        trend_last7 = trend[-7:]
        trend_summary = self._trend_summary(trend_last7)

        confidence_value = self._bounded(
            (weights["volume"] * volume_metric.confidence)
            + (weights["freshness"] * freshness_metric.confidence)
            + (weights["distribution"] * distribution_metric.confidence)
        )

        low_score_reason_label = self._low_score_reason_label(
            adgri_score=adgri_score,
            freshness_risk=freshness_metric.risk,
            distribution_risk=distribution_metric.risk,
            volume_risk=volume_metric.risk,
            latest_business_data_date=distribution_payload.get("latest_business_data_date"),
        )

        return {
            "index_name": "Adaptive Domain Governance Reliability Index (ADGRI)",
            "formula": {
                "weighted_risk": "R_adgri = w_v*r_v + w_f*r_f + w_d*r_d",
                "weights": "w_i = c_i / (c_v + c_f + c_d)",
                "score": "ADGRI = 100 * (1 - R_adgri)",
            },
            "domain_name": domain_name,
            "file": str(file_path),
            "as_of": evaluation_ts.isoformat(timespec="seconds"),
            "latest_governance_evaluation_time": evaluation_ts.isoformat(timespec="seconds"),
            "latest_domain_refresh_time": latest_refresh_ts.isoformat(timespec="seconds") if latest_refresh_ts is not None else None,
            "latest_domain_file_update_time": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(timespec="seconds") if file_path.exists() else None,
            "latest_business_data_date": distribution_payload.get("latest_business_data_date"),
            "freshness_reference": freshness_source,
            "trend_label": "Governance Evaluation Trend",
            "business_trend_label": "Business Data Trend",
            "trend_basis": "governance_refresh_cycles",
            "adgri_score": round(adgri_score, 4),
            "governance_score": round(adgri_score, 4),
            "weighted_risk": round(weighted_risk, 6),
            "weights": {k: round(float(v), 6) for k, v in weights.items()},
            "contribution_breakdown": {
                "volume": {
                    "weighted_risk": round(float(contributions["volume"]), 6),
                    "score_impact": round(float(contributions["volume"] * 100.0), 4),
                },
                "freshness": {
                    "weighted_risk": round(float(contributions["freshness"]), 6),
                    "score_impact": round(float(contributions["freshness"] * 100.0), 4),
                },
                "distribution": {
                    "weighted_risk": round(float(contributions["distribution"]), 6),
                    "score_impact": round(float(contributions["distribution"] * 100.0), 4),
                },
            },
            "low_score_reason_label": low_score_reason_label,
            "top_reason": self._top_reason_text(top_factor),
            "explanation": self._explanation_text(contributions),
            "confidence": {
                "score": round(float(confidence_value), 6),
                "level": self._confidence_label(confidence_value),
            },
            "volume_stability": volume_metric.to_dict(),
            "freshness_stability": freshness_metric.to_dict(),
            "distribution_stability": {
                **distribution_metric.to_dict(),
                "numeric_columns_used": distribution_payload["numeric_columns_used"],
                "date_column": distribution_payload["date_column"],
            },
            "risk_trend": trend_last7,
            "trend_direction": trend_summary["direction"],
            "trend_slope": trend_summary["slope"],
            "trend_change_rate": trend_summary["change_rate"],
            "last_updated": evaluation_ts.isoformat(timespec="seconds"),
        }

    def _list_domains(self) -> list[str]:
        if not self.data_path.exists():
            return []
        domains = [d.name for d in self.data_path.iterdir() if d.is_dir() and d.name.lower().endswith("_domain")]
        return sorted(domains)

    def _load_history_for_domain(self, domain_name: str) -> pd.DataFrame:
        if not self.monitoring_history_path.exists():
            return pd.DataFrame(columns=["domain_name", "row_count", "timestamp"])

        df = pd.read_csv(self.monitoring_history_path)
        if df.empty or "domain_name" not in df.columns:
            return pd.DataFrame(columns=["domain_name", "row_count", "timestamp"])

        df["domain_name"] = df["domain_name"].astype(str).str.strip().str.lower()
        target = domain_name.strip().lower()
        df = df[df["domain_name"] == target].copy()
        if df.empty:
            return pd.DataFrame(columns=["domain_name", "row_count", "timestamp"])

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

        if "row_count" in df.columns:
            df["row_count"] = pd.to_numeric(df["row_count"], errors="coerce")

        if "freshness_hours" in df.columns:
            df["freshness_hours"] = pd.to_numeric(df["freshness_hours"], errors="coerce")

        return df

    def _load_domain_csv(self, domain_name: str) -> tuple[pd.DataFrame, Path]:
        file_path = self.data_path / domain_name / f"{domain_name}.csv"
        if not file_path.exists():
            raise ValueError(f"Domain CSV not found for {domain_name}")
        return pd.read_csv(file_path), file_path

    def _metric_from_series(self, values: pd.Series) -> MetricResult:
        clean = pd.to_numeric(values, errors="coerce").dropna()
        n = int(len(clean))
        if n == 0:
            return MetricResult(0.5, 0.0, None, None, None, 0, 0.1)
        if n == 1:
            one = float(clean.iloc[0])
            return MetricResult(0.45, 0.0, one, 0.0, one, 1, 0.2)

        latest = float(clean.iloc[-1])
        baseline = clean.iloc[-(self.rolling_window_days + 1):-1]
        if len(baseline) < 2:
            baseline = clean.iloc[:-1]

        baseline_mean = float(baseline.mean()) if len(baseline) else float(clean.mean())
        baseline_std = float(baseline.std(ddof=0)) if len(baseline) else float(clean.std(ddof=0))
        z = self._safe_z(latest, baseline_mean, baseline_std)
        risk = self._z_to_risk(z)

        variability = abs(baseline_std) / (abs(baseline_mean) + 1e-9)
        confidence = self._bounded((math.log1p(len(baseline)) / math.log1p(self.rolling_window_days)) * (1.0 / (1.0 + variability)))

        return MetricResult(risk, z, baseline_mean, baseline_std, latest, int(len(baseline)), confidence)

    def _freshness_metric(
        self,
        history: pd.DataFrame,
        refresh_observations: pd.DataFrame,
        evaluation_ts: datetime,
        domain_file_path: Path,
        latest_business_data_date: str | None,
    ) -> tuple[MetricResult, datetime | None, str]:
        timestamps = pd.to_datetime(refresh_observations.get("timestamp", pd.Series(dtype="datetime64[ns]")), errors="coerce").dropna()
        real_refresh_ts = sorted([ts for ts in timestamps.tolist() if ts <= evaluation_ts]) if not timestamps.empty else []
        latest_refresh = real_refresh_ts[-1] if real_refresh_ts else None

        parsed_business_date = pd.to_datetime(latest_business_data_date, errors="coerce") if latest_business_data_date else pd.NaT
        if pd.notna(parsed_business_date):
            latest_business_ts = pd.Timestamp(parsed_business_date).to_pydatetime()
            latest_lag_hours = max(0.0, (evaluation_ts - latest_business_ts).total_seconds() / 3600.0)

            historical_freshness = pd.to_numeric(history.get("freshness_hours", pd.Series(dtype=float)), errors="coerce").dropna()
            baseline = historical_freshness.iloc[-self.rolling_window_days:]
            if len(baseline) >= 2:
                baseline_mean = float(baseline.mean())
                baseline_std = float(baseline.std(ddof=0))
                z = self._safe_z(latest_lag_hours, baseline_mean, baseline_std)
                risk = self._z_to_risk(z)
                variability = abs(baseline_std) / (abs(baseline_mean) + 1e-9)
                confidence = self._bounded((math.log1p(len(baseline)) / math.log1p(self.rolling_window_days)) * (1.0 / (1.0 + variability)))
                return (
                    MetricResult(
                        risk=risk,
                        z_score=z,
                        baseline_mean=baseline_mean,
                        baseline_std=baseline_std,
                        latest_value=latest_lag_hours,
                        sample_size=int(len(baseline)),
                        confidence=confidence,
                    ),
                    latest_refresh,
                    "business_data_date",
                )

            heuristic_risk = self._bounded(latest_lag_hours / (24.0 * 7.0))
            return (
                MetricResult(
                    risk=heuristic_risk,
                    z_score=0.0,
                    baseline_mean=latest_lag_hours,
                    baseline_std=0.0,
                    latest_value=latest_lag_hours,
                    sample_size=int(len(baseline)),
                    confidence=0.3,
                ),
                latest_refresh,
                "business_data_date",
            )

        if timestamps.empty:
            age = self._file_age_hours(domain_file_path)
            return MetricResult(0.45, 0.0, age, 0.0, age, 0, 0.15), None, "domain_refresh_time_fallback"

        if latest_refresh is None:
            age = self._file_age_hours(domain_file_path)
            return MetricResult(0.45, 0.0, age, 0.0, age, 0, 0.15), None, "domain_refresh_time_fallback"

        latest_lag_hours = max(0.0, (evaluation_ts - latest_refresh).total_seconds() / 3600.0)

        if len(real_refresh_ts) >= 2:
            intervals = pd.Series(real_refresh_ts).diff().dt.total_seconds().dropna() / 3600.0
            if len(intervals) >= 2:
                baseline_mean = float(intervals.mean())
                baseline_std = float(intervals.std(ddof=0))
                z = self._safe_z(latest_lag_hours, baseline_mean, baseline_std)
                risk = self._z_to_risk(z)
                variability = abs(baseline_std) / (abs(baseline_mean) + 1e-9)
                confidence = self._bounded((math.log1p(len(intervals)) / math.log1p(self.rolling_window_days)) * (1.0 / (1.0 + variability)))
                return (
                    MetricResult(
                        risk=risk,
                        z_score=z,
                        baseline_mean=baseline_mean,
                        baseline_std=baseline_std,
                        latest_value=latest_lag_hours,
                        sample_size=int(len(intervals)),
                        confidence=confidence,
                    ),
                    latest_refresh,
                    "domain_refresh_time_fallback",
                )

        return (
            MetricResult(0.4, 0.0, latest_lag_hours, 0.0, latest_lag_hours, len(real_refresh_ts), 0.2),
            latest_refresh,
            "domain_refresh_time_fallback",
        )

    def _distribution_metric(self, df: pd.DataFrame) -> dict[str, Any]:
        date_col = self._find_date_column(df)
        numeric_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]

        filtered_numeric = []
        for col in numeric_cols:
            lowered = col.lower()
            if lowered.endswith("id") or lowered in {"id", "_id"}:
                continue
            filtered_numeric.append(col)

        if not date_col or not filtered_numeric:
            return {
                "metric": MetricResult(0.45, 0.0, None, None, None, 0, 0.2),
                "numeric_columns_used": filtered_numeric,
                "date_column": date_col,
                "latest_business_data_date": None,
            }

        local = df[[date_col] + filtered_numeric].copy()
        local[date_col] = pd.to_datetime(local[date_col], errors="coerce")
        local = local.dropna(subset=[date_col])
        if local.empty:
            return {
                "metric": MetricResult(0.45, 0.0, None, None, None, 0, 0.2),
                "numeric_columns_used": filtered_numeric,
                "date_column": date_col,
                "latest_business_data_date": None,
            }

        latest_business_data_date = local[date_col].max()

        local["_day"] = local[date_col].dt.date
        grouped = local.groupby("_day")
        if len(grouped) < 3:
            return {
                "metric": MetricResult(0.4, 0.0, None, None, None, int(len(grouped)), 0.25),
                "numeric_columns_used": filtered_numeric,
                "date_column": date_col,
                "latest_business_data_date": latest_business_data_date.isoformat() if pd.notna(latest_business_data_date) else None,
            }

        daily_features = pd.DataFrame(index=sorted(grouped.groups.keys()))
        for col in filtered_numeric:
            daily_features[f"{col}__mean"] = grouped[col].mean()
            daily_features[f"{col}__var"] = grouped[col].var(ddof=0).fillna(0.0)

        daily_features = daily_features.dropna(how="all")
        if len(daily_features) < 3:
            return {
                "metric": MetricResult(0.4, 0.0, None, None, None, int(len(daily_features)), 0.25),
                "numeric_columns_used": filtered_numeric,
                "date_column": date_col,
                "latest_business_data_date": latest_business_data_date.isoformat() if pd.notna(latest_business_data_date) else None,
            }

        latest_vector = daily_features.iloc[-1]
        baseline = daily_features.iloc[-(self.rolling_window_days + 1):-1]
        if len(baseline) < 2:
            baseline = daily_features.iloc[:-1]

        z_values: list[float] = []
        for column in daily_features.columns:
            series = pd.to_numeric(baseline[column], errors="coerce").dropna()
            if len(series) < 2:
                continue
            mean = float(series.mean())
            std = float(series.std(ddof=0))
            latest_value = float(latest_vector[column]) if pd.notna(latest_vector[column]) else mean
            z_values.append(self._safe_z(latest_value, mean, std))

        if not z_values:
            return {
                "metric": MetricResult(0.35, 0.0, None, None, None, int(len(baseline)), 0.3),
                "numeric_columns_used": filtered_numeric,
                "date_column": date_col,
                "latest_business_data_date": latest_business_data_date.isoformat() if pd.notna(latest_business_data_date) else None,
            }

        aggregate_z = float(math.sqrt(sum(z ** 2 for z in z_values) / len(z_values)))
        risk = self._z_to_risk(aggregate_z)
        baseline_volatility = float(baseline.std(ddof=0).mean()) if len(baseline) else 0.0
        baseline_level = float(baseline.mean().abs().mean()) if len(baseline) else 1.0
        variability = baseline_volatility / (baseline_level + 1e-9)
        confidence = self._bounded((math.log1p(len(baseline)) / math.log1p(self.rolling_window_days)) * (1.0 / (1.0 + variability)))

        metric = MetricResult(
            risk=risk,
            z_score=aggregate_z,
            baseline_mean=float(baseline.mean().mean()) if len(baseline) else None,
            baseline_std=float(baseline.std(ddof=0).mean()) if len(baseline) else None,
            latest_value=float(latest_vector.mean()),
            sample_size=int(len(baseline)),
            confidence=confidence,
        )
        return {
            "metric": metric,
            "numeric_columns_used": filtered_numeric,
            "date_column": date_col,
            "latest_business_data_date": latest_business_data_date.isoformat() if pd.notna(latest_business_data_date) else None,
        }

    def _risk_trend(self, refresh_observations: pd.DataFrame, distribution_risk: float, weights: dict[str, float]) -> list[dict[str, Any]]:
        if refresh_observations.empty or "timestamp" not in refresh_observations.columns:
            return []

        work = refresh_observations.copy()
        work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
        work = work.dropna(subset=["timestamp"]).sort_values("timestamp")
        if len(work) < 2:
            return []

        row_counts = pd.to_numeric(work.get("row_count"), errors="coerce")
        intervals = work["timestamp"].diff().dt.total_seconds() / 3600.0

        points: list[dict[str, Any]] = []
        for i in range(1, len(work)):
            baseline_rows = row_counts.iloc[max(0, i - self.rolling_window_days):i]
            baseline_int = intervals.iloc[max(1, i - self.rolling_window_days + 1):i]
            latest_row = row_counts.iloc[i]
            latest_interval = intervals.iloc[i]

            row_risk = self._point_risk(latest_row, baseline_rows)
            freshness_risk = self._point_risk(latest_interval, baseline_int)
            weighted_risk = (
                weights["volume"] * row_risk
                + weights["freshness"] * freshness_risk
                + weights["distribution"] * distribution_risk
            )
            score = max(0.0, 100.0 * (1.0 - weighted_risk))
            points.append(
                {
                    "date": work.iloc[i]["timestamp"].isoformat(timespec="seconds"),
                    "governance_score": round(float(score), 4),
                    "risk": round(float(weighted_risk), 6),
                }
            )
        return points

    def _build_refresh_observations(
        self,
        domain_name: str,
        history: pd.DataFrame,
        domain_file_path: Path,
        current_row_count: int,
    ) -> pd.DataFrame:
        points: list[dict[str, Any]] = []
        normalized_domain = self._normalize_domain_name(domain_name)

        if not history.empty and "timestamp" in history.columns and "row_count" in history.columns:
            temp = history[["timestamp", "row_count"]].dropna(subset=["timestamp"]).copy()
            temp["timestamp"] = pd.to_datetime(temp["timestamp"], errors="coerce")
            temp["row_count"] = pd.to_numeric(temp["row_count"], errors="coerce")
            for _, row in temp.dropna(subset=["timestamp", "row_count"]).iterrows():
                points.append(
                    {
                        "timestamp": row["timestamp"],
                        "row_count": int(row["row_count"]),
                    }
                )

        if self.pipeline_log_path.exists():
            try:
                raw = pd.read_json(self.pipeline_log_path)
            except ValueError:
                raw = pd.DataFrame()
            if not raw.empty and {"domain", "timestamp", "rows_processed"}.issubset(raw.columns):
                raw["domain_norm"] = raw["domain"].astype(str).apply(self._normalize_domain_name)
                filtered = raw[raw["domain_norm"] == normalized_domain].copy()
                if "status" in filtered.columns:
                    filtered = filtered[filtered["status"].astype(str).str.upper() == "SUCCESS"]
                filtered["timestamp"] = pd.to_datetime(filtered["timestamp"], errors="coerce")
                filtered["rows_processed"] = pd.to_numeric(filtered["rows_processed"], errors="coerce")
                for _, row in filtered.dropna(subset=["timestamp", "rows_processed"]).iterrows():
                    points.append(
                        {
                            "timestamp": row["timestamp"],
                            "row_count": int(row["rows_processed"]),
                        }
                    )

        if domain_file_path.exists():
            file_ts = datetime.fromtimestamp(domain_file_path.stat().st_mtime)
            points.append({"timestamp": file_ts, "row_count": int(current_row_count)})

        obs = pd.DataFrame(points)
        if obs.empty:
            return pd.DataFrame(columns=["timestamp", "row_count"])

        obs["timestamp"] = pd.to_datetime(obs["timestamp"], errors="coerce")
        obs["row_count"] = pd.to_numeric(obs["row_count"], errors="coerce")
        obs = obs.dropna(subset=["timestamp", "row_count"]).sort_values("timestamp")
        obs = obs.drop_duplicates(subset=["timestamp"], keep="last")
        return obs

    def _normalize_domain_name(self, value: str) -> str:
        return str(value).strip().lower().replace("interaction_domain", "interaction_domain")

    def _trend_summary(self, trend_points: list[dict[str, Any]]) -> dict[str, Any]:
        if len(trend_points) < 2:
            return {"direction": "stable", "slope": 0.0, "change_rate": 0.0}

        y = [float(point.get("governance_score", 0.0)) for point in trend_points]
        n = len(y)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(y) / n

        denom = sum((xi - x_mean) ** 2 for xi in x)
        slope = 0.0 if denom == 0 else sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n)) / denom

        start = y[0]
        end = y[-1]
        change_rate = 0.0 if abs(start) < 1e-9 else (end - start) / abs(start)

        if slope > 0.2:
            direction = "improving"
        elif slope < -0.2:
            direction = "deteriorating"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "slope": round(float(slope), 6),
            "change_rate": round(float(change_rate), 6),
        }

    def _point_risk(self, latest: Any, baseline: pd.Series) -> float:
        baseline_clean = pd.to_numeric(baseline, errors="coerce").dropna()
        if pd.isna(latest):
            return 0.5
        if len(baseline_clean) < 2:
            return 0.45
        mean = float(baseline_clean.mean())
        std = float(baseline_clean.std(ddof=0))
        z = self._safe_z(float(latest), mean, std)
        return self._z_to_risk(z)

    def _dynamic_weights(self, volume_conf: float, freshness_conf: float, distribution_conf: float) -> dict[str, float]:
        raw = {
            "volume": max(1e-6, float(volume_conf)),
            "freshness": max(1e-6, float(freshness_conf)),
            "distribution": max(1e-6, float(distribution_conf)),
        }
        total = sum(raw.values())
        return {k: v / total for k, v in raw.items()}

    def _z_to_risk(self, z: float) -> float:
        positive_z = max(0.0, float(z))
        risk = math.erf(positive_z / math.sqrt(2.0))
        return self._bounded(risk)

    def _safe_z(self, latest: float, mean: float, std: float) -> float:
        if std <= 1e-9:
            denom = abs(mean) * 0.05 + 1e-9
            return abs(latest - mean) / denom
        return abs(latest - mean) / std

    def _bounded(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _find_date_column(self, df: pd.DataFrame) -> str | None:
        preferred = ["transaction_date", "interaction_date", "signup_ts", "updated_ts", "created_ts"]
        for col in preferred:
            if col in df.columns:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notna().mean() >= 0.5:
                    return col

        candidates = [col for col in df.columns if "date" in col.lower() or col.lower().endswith("_ts")]
        for col in candidates:
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().mean() >= 0.5:
                return col
        return None

    def _file_age_hours(self, file_path: Path) -> float:
        if not file_path.exists():
            return 0.0
        return max(0.0, (datetime.now().timestamp() - file_path.stat().st_mtime) / 3600.0)

    def _confidence_label(self, score: float) -> str:
        if score >= 0.67:
            return "high"
        if score >= 0.34:
            return "medium"
        return "low"

    def _top_reason_text(self, top_factor: str) -> str:
        mapping = {
            "volume": "Volume instability contributed most to ADGRI degradation.",
            "freshness": "Freshness instability contributed most to ADGRI degradation.",
            "distribution": "Distribution instability contributed most to ADGRI degradation.",
        }
        return mapping.get(top_factor, "Multiple factors contributed to ADGRI degradation.")

    def _low_score_reason_label(
        self,
        adgri_score: float,
        freshness_risk: float,
        distribution_risk: float,
        volume_risk: float,
        latest_business_data_date: str | None,
    ) -> str:
        if float(adgri_score) >= 80.0:
            return "Healthy score"

        stale_date_likely = False
        if latest_business_data_date:
            parsed = pd.to_datetime(latest_business_data_date, errors="coerce")
            if pd.notna(parsed):
                lag_days = max(0.0, (datetime.now() - pd.Timestamp(parsed).to_pydatetime()).total_seconds() / 86400.0)
                stale_date_likely = lag_days > 30.0

        high_freshness = float(freshness_risk) >= 0.7
        high_distribution = float(distribution_risk) >= 0.7
        elevated_freshness = float(freshness_risk) >= 0.35
        elevated_distribution = float(distribution_risk) >= 0.35
        elevated_volume = float(volume_risk) >= 0.35

        if stale_date_likely and (elevated_freshness or high_freshness) and (elevated_distribution or high_distribution):
            return "Low due to combined freshness + distribution instability"
        if stale_date_likely and (elevated_freshness or high_freshness):
            return "Low due to stale business dates"
        if high_distribution or elevated_distribution:
            return "Low due to abnormal value distribution"
        if elevated_freshness:
            return "Low due to freshness instability"
        if elevated_volume:
            return "Low due to volume instability"
        return "Low due to combined risk signals"

    def _explanation_text(self, contributions: dict[str, float]) -> str:
        ordered = sorted(contributions.items(), key=lambda item: item[1], reverse=True)
        top = ordered[0][0]
        second = ordered[1][0] if len(ordered) > 1 else ordered[0][0]
        return f"Governance score decreased mainly due to {top} instability and elevated {second} deviation."
