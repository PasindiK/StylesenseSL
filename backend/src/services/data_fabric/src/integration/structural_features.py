"""Structural feature extraction for relationship candidates.

This module focuses on schema-level signals only:
- Column name similarity
- Datatype compatibility score
- Left/Right uniqueness ratios
- Left/Right null percentages
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

import pandas as pd


class StructuralFeatureExtractor:
    """Extract structural features that indicate key-like behavior."""

    TYPE_COMPATIBILITY_MATRIX: Dict[Tuple[str, str], float] = {
        ("int", "int"): 1.0,
        ("int", "float"): 0.8,
        ("int", "numeric"): 0.9,
        ("int", "string"): 0.2,
        ("float", "float"): 1.0,
        ("float", "numeric"): 0.9,
        ("float", "string"): 0.2,
        ("numeric", "numeric"): 1.0,
        ("numeric", "string"): 0.2,
        ("string", "string"): 1.0,
        ("date", "date"): 1.0,
        ("datetime", "datetime"): 1.0,
        ("date", "datetime"): 0.9,
        ("datetime", "date"): 0.9,
        ("bool", "bool"): 1.0,
    }

    def name_similarity(self, left_col: str, right_col: str) -> float:
        """Compute normalized name similarity in [0, 1]."""
        left_norm = self._normalize_name(left_col)
        right_norm = self._normalize_name(right_col)

        if not left_norm and not right_norm:
            return 1.0
        if not left_norm or not right_norm:
            return 0.0

        max_len = max(len(left_norm), len(right_norm))
        if max_len == 0:
            levenshtein_similarity = 1.0
        else:
            distance = self._levenshtein_distance(left_norm, right_norm)
            levenshtein_similarity = 1.0 - (distance / max_len)

        token_score = self._token_jaccard_similarity(left_col, right_col)

        # Blend character-level and token-level similarity.
        score = (0.7 * levenshtein_similarity) + (0.3 * token_score)
        return float(max(0.0, min(1.0, score)))

    def type_score(self, left: pd.Series, right: pd.Series) -> float:
        """Return datatype compatibility score in [0, 1]."""
        left_type = self._series_type(left)
        right_type = self._series_type(right)

        key = (left_type, right_type)
        if key in self.TYPE_COMPATIBILITY_MATRIX:
            return self.TYPE_COMPATIBILITY_MATRIX[key]

        reverse_key = (right_type, left_type)
        if reverse_key in self.TYPE_COMPATIBILITY_MATRIX:
            return self.TYPE_COMPATIBILITY_MATRIX[reverse_key]

        if left_type == right_type:
            return 1.0

        return 0.0

    @staticmethod
    def uniqueness_ratio(series: pd.Series) -> float:
        """Compute unique_values / total_rows in [0, 1]."""
        total_rows = len(series)
        if total_rows == 0:
            return 0.0
        return float(series.nunique(dropna=True) / total_rows)

    @staticmethod
    def null_percentage(series: pd.Series) -> float:
        """Compute null_count / total_rows in [0, 1]."""
        total_rows = len(series)
        if total_rows == 0:
            return 0.0
        return float(series.isna().sum() / total_rows)

    def extract(
        self,
        left_col: str,
        right_col: str,
        left_series: pd.Series,
        right_series: pd.Series,
    ) -> Dict[str, float]:
        """Extract full structural feature set for a candidate pair."""
        return {
            "name_similarity": round(self.name_similarity(left_col, right_col), 6),
            "type_score": round(self.type_score(left_series, right_series), 6),
            "uniqueness_ratio_left": round(self.uniqueness_ratio(left_series), 6),
            "uniqueness_ratio_right": round(self.uniqueness_ratio(right_series), 6),
            "null_percentage_left": round(self.null_percentage(left_series), 6),
            "null_percentage_right": round(self.null_percentage(right_series), 6),
        }

    @staticmethod
    def _normalize_name(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.lower())

    @staticmethod
    def _tokenize_name(name: str) -> set:
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
        tokens = re.findall(r"[a-z0-9]+", normalized.lower())
        return set(tokens)

    def _token_jaccard_similarity(self, left_col: str, right_col: str) -> float:
        left_tokens = self._tokenize_name(left_col)
        right_tokens = self._tokenize_name(right_col)

        if not left_tokens and not right_tokens:
            return 1.0
        if not left_tokens or not right_tokens:
            return 0.0

        intersection = len(left_tokens.intersection(right_tokens))
        union = len(left_tokens.union(right_tokens))
        if union == 0:
            return 0.0
        return float(intersection / union)

    @staticmethod
    def _series_type(series: pd.Series) -> str:
        if pd.api.types.is_bool_dtype(series):
            return "bool"
        if pd.api.types.is_integer_dtype(series):
            return "int"
        if pd.api.types.is_float_dtype(series):
            return "float"
        if pd.api.types.is_numeric_dtype(series):
            return "numeric"
        if pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"

        # Try parsing object/string to date-like values to classify as date.
        if pd.api.types.is_string_dtype(series) or series.dtype == object:
            non_null = series.dropna()
            if non_null.empty:
                return "string"

            sample = non_null.head(min(100, len(non_null)))
            try:
                parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
            except TypeError:
                parsed = pd.to_datetime(sample, errors="coerce")
            parse_ratio = parsed.notna().mean()
            if parse_ratio >= 0.8:
                has_time = ((parsed.dt.hour != 0) | (parsed.dt.minute != 0) | (parsed.dt.second != 0)).any()
                return "datetime" if has_time else "date"

            return "string"

        return "unknown"

    @staticmethod
    def _levenshtein_distance(a: str, b: str) -> int:
        if a == b:
            return 0
        if not a:
            return len(b)
        if not b:
            return len(a)

        prev_row = list(range(len(b) + 1))
        for i, char_a in enumerate(a, start=1):
            current_row = [i]
            for j, char_b in enumerate(b, start=1):
                insert_cost = current_row[j - 1] + 1
                delete_cost = prev_row[j] + 1
                replace_cost = prev_row[j - 1] + (0 if char_a == char_b else 1)
                current_row.append(min(insert_cost, delete_cost, replace_cost))
            prev_row = current_row

        return prev_row[-1]
