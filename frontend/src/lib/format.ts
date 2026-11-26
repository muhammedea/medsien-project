export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function shortHash(hash: string | null | undefined): string {
  return hash ? hash.slice(0, 12) : "—";
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/** Show a value exactly as the API returned it; null means "not applicable". */
export function show(v: number | string | null | undefined): string {
  return v === null || v === undefined ? "—" : String(v);
}
