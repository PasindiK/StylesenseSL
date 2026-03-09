from pathlib import Path

import pandas as pd


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "data"
    source_file = root / "Data" / "Silver-data" / "users_clean.csv"
    target_dir = root / "test_cases" / "users_domain"
    target_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(source_file)
    if "signup_ts" not in df.columns:
        raise RuntimeError("users_clean.csv does not contain signup_ts")

    base = df.copy()
    base["signup_ts"] = pd.to_datetime(base["signup_ts"], errors="coerce")

    users_current = base.copy()
    users_stale_30 = base.copy()
    users_stale_60 = base.copy()
    users_stale_distribution = base.copy()

    users_stale_30["signup_ts"] = users_stale_30["signup_ts"] - pd.Timedelta(days=30)
    users_stale_60["signup_ts"] = users_stale_60["signup_ts"] - pd.Timedelta(days=60)
    users_stale_distribution["signup_ts"] = users_stale_distribution["signup_ts"] - pd.Timedelta(days=60)

    if "is_active" in users_stale_distribution.columns and len(users_stale_distribution) > 0:
        cut = max(1, len(users_stale_distribution) // 3)
        users_stale_distribution.loc[users_stale_distribution.index[:cut], "is_active"] = False

    for frame in (users_current, users_stale_30, users_stale_60, users_stale_distribution):
        frame["signup_ts"] = frame["signup_ts"].dt.strftime("%Y-%m-%d")

    users_current.to_csv(target_dir / "users_current.csv", index=False)
    users_stale_30.to_csv(target_dir / "users_stale_30days.csv", index=False)
    users_stale_60.to_csv(target_dir / "users_stale_60days.csv", index=False)
    users_stale_distribution.to_csv(target_dir / "users_stale_distribution_shift.csv", index=False)


if __name__ == "__main__":
    main()
