from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .models import FeatureContract, FeatureValidationIssue, FeatureValidationResult

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency
    yaml = None


DEFAULT_CONTRACTS_PATH = Path(__file__).resolve().parent / "contracts" / "recommendation_features.yaml"


def _coerce_contract(name: str, payload: Dict[str, Any]) -> FeatureContract:
    return FeatureContract(
        name=name,
        dtype=str(payload.get("dtype") or "float"),
        minimum=payload.get("minimum"),
        maximum=payload.get("maximum"),
        nullable=bool(payload.get("nullable", True)),
        severity=str(payload.get("severity") or "hard"),
        description=str(payload.get("description") or ""),
    )


def load_contracts(path: Path | None = None) -> List[FeatureContract]:
    target = path or DEFAULT_CONTRACTS_PATH
    if not target.exists():
        return []

    raw: Dict[str, Any]
    if target.suffix.lower() in {".yaml", ".yml"} and yaml is not None:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    else:
        raw = json.loads(target.read_text(encoding="utf-8"))

    features = raw.get("features") or {}
    return [_coerce_contract(name, payload or {}) for name, payload in features.items()]


class FeatureContractValidator:
    def __init__(self, contracts: Iterable[FeatureContract]):
        self.contracts = list(contracts)

    def validate(self, features: Dict[str, Any]) -> FeatureValidationResult:
        issues: List[FeatureValidationIssue] = []
        for contract in self.contracts:
            value = features.get(contract.name)

            if value is None:
                if not contract.nullable:
                    issues.append(
                        FeatureValidationIssue(
                            feature_name=contract.name,
                            severity=contract.severity,
                            message="Feature is null but contract requires a value.",
                        )
                    )
                continue

            if contract.dtype == "float":
                try:
                    numeric = float(value)
                except Exception:
                    issues.append(
                        FeatureValidationIssue(
                            feature_name=contract.name,
                            severity=contract.severity,
                            message=f"Expected float-compatible value, got {type(value).__name__}.",
                        )
                    )
                    continue
                if contract.minimum is not None and numeric < float(contract.minimum):
                    issues.append(
                        FeatureValidationIssue(
                            feature_name=contract.name,
                            severity=contract.severity,
                            message=f"Value {numeric:.4f} is below minimum {contract.minimum}.",
                        )
                    )
                if contract.maximum is not None and numeric > float(contract.maximum):
                    issues.append(
                        FeatureValidationIssue(
                            feature_name=contract.name,
                            severity=contract.severity,
                            message=f"Value {numeric:.4f} exceeds maximum {contract.maximum}.",
                        )
                    )

        return FeatureValidationResult(is_valid=not any(i.severity == "hard" for i in issues), issues=issues)

