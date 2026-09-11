/**
 * Deterministic Research version comparison (Step 26).
 * Evidence identity = normalized URL. No LLM / no heavy diff library.
 */

export type EvidenceLike = {
  id?: string;
  title: string;
  url: string;
  domain?: string | null;
  source_name?: string | null;
  snippet?: string | null;
};

export type EvidenceDiffKind = "added" | "removed" | "unchanged";

export type EvidenceDiffItem = {
  kind: EvidenceDiffKind;
  key: string;
  left?: EvidenceLike;
  right?: EvidenceLike;
  metadataChanged?: boolean;
};

export type EvidenceDiffResult = {
  added: EvidenceDiffItem[];
  removed: EvidenceDiffItem[];
  unchanged: EvidenceDiffItem[];
};

/** MVP URL normalize: trim, lowercase, drop fragment, strip trailing slash. */
export function normalizeEvidenceUrl(url: string): string {
  const raw = (url || "").trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    parsed.hash = "";
    let href = parsed.toString().toLowerCase();
    if (href.endsWith("/") && parsed.pathname !== "/") {
      href = href.slice(0, -1);
    }
    return href;
  } catch {
    return raw.replace(/#.*$/, "").replace(/\/+$/, "").toLowerCase();
  }
}

function metadataChanged(a: EvidenceLike, b: EvidenceLike): boolean {
  return (
    (a.title || "").trim() !== (b.title || "").trim() ||
    (a.snippet || "").trim() !== (b.snippet || "").trim() ||
    (a.source_name || "").trim() !== (b.source_name || "").trim()
  );
}

/**
 * Compare evidence lists by normalized URL.
 * Result order is deterministic: sorted by key within each bucket.
 */
export function compareEvidenceByUrl(
  left: EvidenceLike[],
  right: EvidenceLike[],
): EvidenceDiffResult {
  const leftMap = new Map<string, EvidenceLike>();
  const rightMap = new Map<string, EvidenceLike>();

  for (const item of left) {
    const key = normalizeEvidenceUrl(item.url);
    if (!key || leftMap.has(key)) continue;
    leftMap.set(key, item);
  }
  for (const item of right) {
    const key = normalizeEvidenceUrl(item.url);
    if (!key || rightMap.has(key)) continue;
    rightMap.set(key, item);
  }

  const added: EvidenceDiffItem[] = [];
  const removed: EvidenceDiffItem[] = [];
  const unchanged: EvidenceDiffItem[] = [];

  const allKeys = Array.from(new Set([...leftMap.keys(), ...rightMap.keys()])).sort();
  for (const key of allKeys) {
    const l = leftMap.get(key);
    const r = rightMap.get(key);
    if (l && r) {
      unchanged.push({
        kind: "unchanged",
        key,
        left: l,
        right: r,
        metadataChanged: metadataChanged(l, r),
      });
    } else if (r && !l) {
      added.push({ kind: "added", key, right: r });
    } else if (l && !r) {
      removed.push({ kind: "removed", key, left: l });
    }
  }

  return { added, removed, unchanged };
}

export function compareQueryLists(
  left: string[],
  right: string[],
): { added: string[]; removed: string[]; common: string[] } {
  const norm = (q: string) => q.trim().toLowerCase();
  const leftSet = new Set(left.map(norm).filter(Boolean));
  const rightSet = new Set(right.map(norm).filter(Boolean));
  const leftOrig = new Map(left.map((q) => [norm(q), q] as const));
  const rightOrig = new Map(right.map((q) => [norm(q), q] as const));

  const added: string[] = [];
  const removed: string[] = [];
  const common: string[] = [];

  for (const key of Array.from(rightSet).sort()) {
    if (leftSet.has(key)) common.push(rightOrig.get(key) || key);
    else added.push(rightOrig.get(key) || key);
  }
  for (const key of Array.from(leftSet).sort()) {
    if (!rightSet.has(key)) removed.push(leftOrig.get(key) || key);
  }
  return { added, removed, common };
}

/**
 * Absolute Research version across the full READY history.
 *
 * API returns newest-first pages; oldest READY is always v1 and newest is v{total}.
 * For a page: version = total - offset - index
 * (no DB version column).
 */
export function assignResearchVersions<T extends { id: string }>(
  itemsNewestFirst: T[],
  total: number,
  offset = 0,
): Array<T & { version: number }> {
  const safeTotal = Math.max(0, total);
  const safeOffset = Math.max(0, offset);
  return itemsNewestFirst.map((item, index) => ({
    ...item,
    version: safeTotal - safeOffset - index,
  }));
}
