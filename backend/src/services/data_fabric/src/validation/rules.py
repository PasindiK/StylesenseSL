"""Validation rules and rule engine."""

from abc import ABC, abstractmethod
from typing import Optional, List, Callable, Any
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class ValidationRule(ABC):
    """Abstract base class for validation rules."""

    def __init__(self, name: str, description: Optional[str] = None):
        """Initialize rule.

        Args:
            name: Rule name
            description: Rule description
        """
        self.name = name
        self.description = description

    @abstractmethod
    def evaluate(self, data: pd.DataFrame) -> bool:
        """Evaluate rule against data.

        Args:
            data: DataFrame to validate

        Returns:
            True if rule passes, False otherwise
        """
        pass


class ColumnExistsRule(ValidationRule):
    """Rule that checks if required columns exist."""

    def __init__(self, required_columns: List[str]):
        """Initialize column exists rule.

        Args:
            required_columns: List of required column names
        """
        super().__init__(
            "column_exists", f"Checks for required columns: {required_columns}"
        )
        self.required_columns = required_columns

    def evaluate(self, data: pd.DataFrame) -> bool:
        """Check if columns exist."""
        missing = set(self.required_columns) - set(data.columns)
        if missing:
            logger.warning(f"Missing columns: {missing}")
            return False
        return True


class NonEmptyDataRule(ValidationRule):
    """Rule that checks if data is not empty."""

    def __init__(self):
        """Initialize non-empty data rule."""
        super().__init__("non_empty_data", "Checks if data is not empty")

    def evaluate(self, data: pd.DataFrame) -> bool:
        """Check if data is not empty."""
        if len(data) == 0:
            logger.warning("Data is empty")
            return False
        return True


class NoNullValuesRule(ValidationRule):
    """Rule that checks for null values in specific columns."""

    def __init__(self, columns: List[str]):
        """Initialize no null values rule.

        Args:
            columns: Columns that should not have nulls
        """
        super().__init__("no_null_values", f"Checks for null values in {columns}")
        self.columns = columns

    def evaluate(self, data: pd.DataFrame) -> bool:
        """Check for null values."""
        for col in self.columns:
            if col in data.columns and data[col].isnull().any():
                logger.warning(f"Null values found in column: {col}")
                return False
        return True


class CustomRule(ValidationRule):
    """Rule based on custom function."""

    def __init__(self, name: str, func: Callable, description: Optional[str] = None):
        """Initialize custom rule.

        Args:
            name: Rule name
            func: Function that takes DataFrame and returns bool
            description: Rule description
        """
        super().__init__(name, description)
        self.func = func

    def evaluate(self, data: pd.DataFrame) -> bool:
        """Evaluate custom rule."""
        try:
            result = self.func(data)
            if not result:
                logger.warning(f"Custom rule '{self.name}' failed")
            return result
        except Exception as e:
            logger.error(f"Error evaluating rule '{self.name}': {e}")
            return False


class RuleEngine:
    """Engine for evaluating validation rules."""

    def __init__(self):
        """Initialize rule engine."""
        self.rules: List[ValidationRule] = []

    def add_rule(self, rule: ValidationRule) -> None:
        """Add a validation rule.

        Args:
            rule: Rule to add
        """
        self.rules.append(rule)
        logger.info(f"Added rule: {rule.name}")

    def add_rules(self, rules: List[ValidationRule]) -> None:
        """Add multiple validation rules.

        Args:
            rules: Rules to add
        """
        for rule in rules:
            self.add_rule(rule)

    def evaluate(self, data: pd.DataFrame, fail_fast: bool = False) -> dict:
        """Evaluate all rules against data.

        Args:
            data: DataFrame to validate
            fail_fast: Stop on first failure

        Returns:
            Dictionary with rule results
        """
        results = {
            "passed_rules": [],
            "failed_rules": [],
            "total_rules": len(self.rules),
            "all_passed": True,
        }

        for rule in self.rules:
            try:
                if rule.evaluate(data):
                    results["passed_rules"].append(rule.name)
                    logger.info(f"✓ Rule passed: {rule.name}")
                else:
                    results["failed_rules"].append(rule.name)
                    results["all_passed"] = False
                    logger.warning(f"✗ Rule failed: {rule.name}")
                    if fail_fast:
                        break
            except Exception as e:
                results["failed_rules"].append(rule.name)
                results["all_passed"] = False
                logger.error(f"Error evaluating rule {rule.name}: {e}")

        return results
