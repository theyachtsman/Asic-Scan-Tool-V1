/**
 * Shared formatting utilities
 */

/** Format hashrate with auto-scaling: TH/s → PH/s → EH/s */
export function formatHashrate(ths: number): string {
  if (ths <= 0) return '0 TH/s';
  if (ths >= 1_000_000) return `${(ths / 1_000_000).toFixed(2)} EH/s`;
  if (ths >= 1_000) return `${(ths / 1_000).toFixed(2)} PH/s`;
  return `${ths.toFixed(2)} TH/s`;
}

/** Format power in watts, auto-scale to kW */
export function formatPower(watts: number): string {
  if (watts <= 0) return '—';
  if (watts >= 1000) return `${(watts / 1000).toFixed(2)} kW`;
  return `${watts.toFixed(0)} W`;
}

/** Format temperature */
export function formatTemp(c: number): string {
  if (c <= 0) return '—';
  return `${c.toFixed(1)}°C`;
}
