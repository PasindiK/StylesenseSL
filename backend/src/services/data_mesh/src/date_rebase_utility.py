from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import random
from pathlib import Path
from typing import Any

import pandas as pd


BUSINESS_DATE_COLUMNS = {
    "transaction_date",
    "interaction_date",
    "created_at",
    "updated_at",
    "last_updated",
    "delivery_date",
    "signup_ts",
    "created_ts",
    "updated_ts",
    "transaction_ts",
}

PRIMARY_ANCHOR_COLUMNS = [
    "transaction_date",
    "interaction_date",
    "created_at",
    "updated_at",
    "last_updated",
    "signup_ts",
    "created_ts",
    "updated_ts",
]


@dataclass
class RebaseResult:
    file: str
    shifted_rows: int
    shifted_columns: list[str]
    old_latest_business_date: str | None
    new_latest_business_date: str | None


class BusinessDateRebaseUtility:
    """One-time and repeatable business-date rebasing utility.

    The utility computes a global date delta so the latest detected business date
    becomes today, then shifts all eligible business date columns by the same delta.
    Relative spacing between rows is preserved.
    """

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.targets = [
            data_root / "Data" / "Silver-data",
            data_root / "Data_Mesh_Domains",
        ]

    def run(self, apply_changes: bool = True) -> dict[str, Any]:
        csv_files = self._list_csv_files()
        if not csv_files:
            return {
                "status": "no_files",
                "message": "No CSV files discovered in target directories.",
                "files_scanned": 0,
                "delta_days": 0,
                "results": [],
            }

        old_latest_values: list[datetime] = []
        new_latest_values: list[datetime] = []

        if not self._has_any_business_dates(csv_files):
            return {
                "status": "no_business_dates",
                "message": "No parseable business date columns found.",
                "files_scanned": len(csv_files),
                "delta_days": None,
                "results": [],
            }

        results: list[RebaseResult] = []
        changed_files = 0
        shifted_rows_total = 0

        for file_path in csv_files:
            file_latest = self._file_latest_business_date(file_path)
            if file_latest is None:
                continue
            delta_days = (datetime.now().date() - file_latest.date()).days
            delta = timedelta(days=delta_days)

            result = self._rebase_file(file_path=file_path, delta=delta, apply_changes=apply_changes)
            if result is not None:
                results.append(result)
                changed_files += 1
                shifted_rows_total += result.shifted_rows
                if result.old_latest_business_date:
                    old_latest_values.append(datetime.fromisoformat(result.old_latest_business_date))
                if result.new_latest_business_date:
                    new_latest_values.append(datetime.fromisoformat(result.new_latest_business_date))

        return {
            "status": "applied" if apply_changes else "preview",
            "message": "Business date rebasing completed.",
            "files_scanned": len(csv_files),
            "files_changed": changed_files,
            "shifted_rows_total": shifted_rows_total,
            "delta_days": "per_file",
            "old_latest_business_date": max(old_latest_values).isoformat() if old_latest_values else None,
            "new_latest_business_date": max(new_latest_values).isoformat() if new_latest_values else None,
            "results": [
                {
                    "file": item.file,
                    "shifted_rows": item.shifted_rows,
                    "shifted_columns": item.shifted_columns,
                    "old_latest_business_date": item.old_latest_business_date,
                    "new_latest_business_date": item.new_latest_business_date,
                }
                for item in results
            ],
        }

    def sample_recent_business_date(self, window_days: int = 30, include_time: bool = False) -> str:
        """Reusable helper for future synthetic generation.

        Generates realistic recent dates from [today-window_days, today].
        """
        window = max(1, int(window_days))
        now = datetime.now()
        days_back = random.randint(0, window)
        minutes_back = random.randint(0, 23 * 60)
        value = now - timedelta(days=days_back, minutes=minutes_back)
        if include_time:
            return value.isoformat(sep=" ", timespec="seconds")
        return value.date().isoformat()

    def _list_csv_files(self) -> list[Path]:
        files: list[Path] = []
        for target in self.targets:
            if not target.exists():
                continue
            files.extend(sorted(target.rglob("*.csv")))
        return files

    def _has_any_business_dates(self, csv_files: list[Path]) -> bool:
        return any(self._file_latest_business_date(path) is not None for path in csv_files)

    def _file_latest_business_date(self, file_path: Path) -> datetime | None:
        latest: datetime | None = None
        try:
            df = pd.read_csv(file_path)
        except Exception:
            return None

        available = list(df.columns)
        anchor_cols = [col for col in available if str(col).lower().strip() in PRIMARY_ANCHOR_COLUMNS]
        columns_to_scan = anchor_cols if anchor_cols else self._business_columns(df.columns)

        for col in columns_to_scan:
            parsed = pd.to_datetime(df[col], errors="coerce")
            col_max = parsed.max()
            if pd.notna(col_max):
                dt_value = pd.Timestamp(col_max).to_pydatetime()
                if latest is None or dt_value > latest:
                    latest = dt_value
        return latest

    def _global_latest_business_date(self, csv_files: list[Path]) -> datetime | None:
        latest: datetime | None = None
        for file_path in csv_files:
            file_latest = self._file_latest_business_date(file_path)
            if file_latest is not None and (latest is None or file_latest > latest):
                latest = file_latest
        return latest

    def _rebase_file(self, file_path: Path, delta: timedelta, apply_changes: bool) -> RebaseResult | None:
        try:
            df = pd.read_csv(file_path)
        except Exception:
            return None

        business_cols = self._business_columns(df.columns)
        if not business_cols:
            return None

        shifted_cols: list[str] = []
        shifted_rows = 0
        old_latest: datetime | None = None
        new_latest: datetime | None = None

        for col in business_cols:
            series = df[col]
            parsed = pd.to_datetime(series, errors="coerce")
            if parsed.notna().sum() == 0:
                continue

            col_old_latest = parsed.max()
            shifted = parsed + delta
            if col_old_latest is not None and pd.notna(col_old_latest):
                dt_old = pd.Timestamp(col_old_latest).to_pydatetime()
                dt_new = pd.Timestamp(shifted.max()).to_pydatetime()
                old_latest = dt_old if old_latest is None or dt_old > old_latest else old_latest
                new_latest = dt_new if new_latest is None or dt_new > new_latest else new_latest

            formatted = self._format_shifted(series=series, shifted=shifted)
            changed_mask = formatted.astype(str) != series.astype(str)
            changed_count = int(changed_mask.sum())
            if changed_count > 0:
                shifted_cols.append(col)
                shifted_rows += changed_count
                if apply_changes:
                    df[col] = formatted

        if not shifted_cols:
            return None

        if apply_changes:
            df.to_csv(file_path, index=False)

        return RebaseResult(
            file=str(file_path),
            shifted_rows=shifted_rows,
            shifted_columns=shifted_cols,
            old_latest_business_date=old_latest.isoformat() if old_latest else None,
            new_latest_business_date=new_latest.isoformat() if new_latest else None,
        )

    def _business_columns(self, columns: Any) -> list[str]:
        names = []
        for raw in columns:
            col = str(raw)
            lower = col.lower().strip()
            if lower in BUSINESS_DATE_COLUMNS:
                names.append(col)
                continue
            if lower.endswith("_date"):
                names.append(col)
                continue
            if lower.endswith("_at") and ("created" in lower or "updated" in lower):
                names.append(col)
                continue
        return names

    def _format_shifted(self, series: pd.Series, shifted: pd.Series) -> pd.Series:
        original = series.astype(str).fillna("")
        has_time = original.str.contains(":", regex=False)

        out = original.copy()
        date_mask = shifted.notna() & (~has_time)
        time_mask = shifted.notna() & has_time

        out.loc[date_mask] = shifted.loc[date_mask].dt.strftime("%Y-%m-%d")
        out.loc[time_mask] = shifted.loc[time_mask].dt.strftime("%Y-%m-%d %H:%M:%S")
        return out


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    data_root = base_dir / "data"
    utility = BusinessDateRebaseUtility(data_root=data_root)
    summary = utility.run(apply_changes=True)
    print(summary)
