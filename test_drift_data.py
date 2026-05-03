import pandas as pd

df = pd.read_csv('semantic_internal_drift_1000_records.csv')
split = len(df) // 2
early = df.iloc[:split]
late = df.iloc[split:]

print('EARLY HALF:')
print(f'quality_score mean: {early["quality_score"].mean():.3f}, std: {early["quality_score"].std():.3f}')
print(f'score_source values: {early["score_source"].value_counts().to_dict()}')

print('\nLATE HALF:')
print(f'quality_score mean: {late["quality_score"].mean():.3f}, std: {late["quality_score"].std():.3f}')
print(f'score_source values: {late["score_source"].value_counts().to_dict()}')

print('\nAll data:')
print(df.describe())
