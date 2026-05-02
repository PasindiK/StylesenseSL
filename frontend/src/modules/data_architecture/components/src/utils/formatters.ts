function coerceFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

/** Recharts Tooltip value can be string | number | array; narrow safely for TS + runtime. */
export function formatRechartsCount(value: unknown): string {
  const n = coerceFiniteNumber(value);
  return n !== null ? n.toLocaleString() : 'N/A';
}

export function formatRechartsGb(value: unknown): string {
  const n = coerceFiniteNumber(value);
  return n !== null ? `${n.toFixed(2)} GB` : 'N/A';
}

export function formatRechartsBytesTooltip(value: unknown): string {
  const n = coerceFiniteNumber(value);
  return n !== null ? formatBytes(n) : 'N/A';
}

export function formatBytes(sizeBytes: number): string {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = sizeBytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

export function compactDateTime(value: string | null | undefined): string {
  if (!value) {
    return 'N/A';
  }
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) {
    return value;
  }
  return dt.toLocaleString();
}

export function pct(value: number, fallback = 0): string {
  const safe = Number.isFinite(value) ? value : fallback;
  return `${safe.toFixed(1)}%`;
}
