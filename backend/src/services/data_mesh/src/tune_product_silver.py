from pathlib import Path
import numpy as np
import pandas as pd

p = Path('/Users/nandunmadawa/Desktop/DATAMESHSTYLESENSESL/backend/src/services/data_mesh/data/Data/Silver-data/products_clean.csv')
df = pd.read_csv(p)

n = len(df)
now = pd.Timestamp.now()
base_date = (now.normalize() - pd.Timedelta(days=1))
offsets = np.arange(n) % 120
new_dates = base_date - pd.to_timedelta(offsets, unit='D')

df['created_ts'] = pd.Series(new_dates, index=df.index).dt.strftime('%Y-%m-%d') + ' 00:00:00'
created = pd.to_datetime(df['created_ts'], errors='coerce')
latest_day = created.max().normalize()
latest_mask = created.dt.normalize() == latest_day
baseline_mask = created.dt.normalize() < latest_day

numeric_cols = [c for c in ['price_LKR', 'popularity_score', 'stock_count'] if c in df.columns]
for col in numeric_cols:
    base = pd.to_numeric(df.loc[baseline_mask, col], errors='coerce').dropna()
    if base.empty:
        continue
    target_mean = float(base.mean())
    target_std = float(base.std(ddof=0))
    latest_idx = df.index[latest_mask]
    sample = base.sample(n=len(latest_idx), replace=True, random_state=42).to_numpy(dtype=float)
    current_std = float(np.std(sample))
    if current_std > 1e-9 and target_std > 0:
        sample = (sample - float(np.mean(sample))) * (target_std / current_std) + target_mean
    else:
        sample = np.full(len(latest_idx), target_mean)
    lo = float(base.quantile(0.01))
    hi = float(base.quantile(0.99))
    sample = np.clip(sample, lo, hi)
    if col == 'stock_count':
        sample = np.maximum(0, np.round(sample)).astype(int)
    df.loc[latest_idx, col] = sample

if 'stock_count' in df.columns:
    df['stock_count'] = pd.to_numeric(df['stock_count'], errors='coerce').fillna(0).round().clip(lower=0).astype(int)

df.to_csv(p, index=False)
print({'rows': n, 'latest_day_rows': int(latest_mask.sum()), 'latest_day': str(latest_day.date())})
