"""Data validation automation script.

Usage:
    python scripts/validation_runner.py --dataset data/processed.csv --config validation_config.json
"""

import argparse
import logging
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from configs.logging_config import setup_logging, get_logger
from src.validation import (
    SchemaValidator,
    RangeValidator,
    DataValidator,
    RuleEngine,
    ColumnExistsRule,
)
import pandas as pd

logger = get_logger(__name__)


def validate_dataset(filepath: str, schema: dict) -> dict:
    """Validate a dataset.

    Args:
        filepath: Path to dataset
        schema: Expected schema

    Returns:
        Validation results
    """
    logger.info(f"Validating dataset: {filepath}")

    df = pd.read_csv(filepath)
    logger.info(f"Loaded dataset with {len(df)} rows, {len(df.columns)} columns")

    results = {"valid": True, "checks": []}

    # Schema validation
    schema_validator = SchemaValidator(schema)
    schema_result = schema_validator.validate(df)
    results["checks"].append(
        {"check": "schema", "valid": schema_result.is_valid, "message": schema_result.message}
    )

    # Column existence check
    rule_engine = RuleEngine()
    rule_engine.add_rule(ColumnExistsRule(list(schema.keys())))
    rule_results = rule_engine.evaluate(df)
    results["checks"].append(
        {
            "check": "columns_exist",
            "valid": rule_results["all_passed"],
            "passed_rules": rule_results["passed_rules"],
        }
    )

    results["valid"] = all(check["valid"] for check in results["checks"])
    logger.info(f"Validation completed: valid={results['valid']}")

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Data Fabric Validation Runner")
    parser.add_argument("--dataset", required=True, help="Path to dataset")
    parser.add_argument("--config", help="Path to validation configuration JSON")
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    setup_logging()
    logging.getLogger().setLevel(args.log_level)

    logger.info("Validation runner started")

    try:
        # Load configuration
        schema = {}
        if args.config and Path(args.config).exists():
            with open(args.config, "r") as f:
                config = json.load(f)
                schema = config.get("schema", {})

        results = validate_dataset(args.dataset, schema)

        print("\n" + "=" * 50)
        print("VALIDATION RESULTS")
        print("=" * 50)
        print(f"Overall Valid: {results['valid']}")
        print(f"Checks performed: {len(results['checks'])}")
        for check in results["checks"]:
            status = "✓ PASS" if check["valid"] else "✗ FAIL"
            print(f"  {status}: {check['check']}")

        logger.info("Validation completed")

        sys.exit(0 if results["valid"] else 1)

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
