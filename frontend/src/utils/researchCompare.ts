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

/* --- Step 28: deterministic Change Summary (no LLM) --- */

export type ResearchChangeSummary = {
  evidence: {
    added: number;
    removed: number;
    updated: number;
    unchanged: number;
  };
  queries: {
    added: number;
    removed: number;
    unchanged: number;
  };
  summaryChanged: boolean;
  noStructuralChanges: boolean;
};

/**
 * Normalize research_summary for equality checks.
 * trim + CRLF→LF + collapse consecutive whitespace.
 */
export function normalizeResearchSummary(text: string | null | undefined): string {
  return (text ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .trim()
    .replace(/[ \t\f\v]+/g, " ")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n");
}

/**
 * Build UX change summary from existing Step 26 diffs.
 * `updated` = unchanged items with metadataChanged=true (not double-counted).
 */
export function buildResearchChangeSummary(input: {
  evidenceDiff: EvidenceDiffResult;
  queryDiff: { added: string[]; removed: string[]; common: string[] };
  leftSummary: string | null | undefined;
  rightSummary: string | null | undefined;
}): ResearchChangeSummary {
  const updated = input.evidenceDiff.unchanged.filter((i) => i.metadataChanged).length;
  const unchanged = input.evidenceDiff.unchanged.length - updated;
  const evidence = {
    added: input.evidenceDiff.added.length,
    removed: input.evidenceDiff.removed.length,
    updated,
    unchanged,
  };
  const queries = {
    added: input.queryDiff.added.length,
    removed: input.queryDiff.removed.length,
    unchanged: input.queryDiff.common.length,
  };
  const summaryChanged =
    normalizeResearchSummary(input.leftSummary) !==
    normalizeResearchSummary(input.rightSummary);
  const evidenceStructural =
    evidence.added + evidence.removed + evidence.updated > 0;
  const queryStructural = queries.added + queries.removed > 0;
  const noStructuralChanges =
    !evidenceStructural && !queryStructural && !summaryChanged;
  return {
    evidence,
    queries,
    summaryChanged,
    noStructuralChanges,
  };
}

/** Deterministic Korean narrative sentences from counts (no LLM). */
export function buildResearchChangeSentences(
  summary: ResearchChangeSummary,
): string[] {
  if (summary.noStructuralChanges) {
    return ["검색어, 근거 및 조사 요약에 변화가 없습니다."];
  }

  const { evidence: ev, queries: q, summaryChanged } = summary;
  const evidenceStructural = ev.added + ev.removed + ev.updated > 0;
  const queryStructural = q.added + q.removed > 0;
  const sentences: string[] = [];

  if (!evidenceStructural && !queryStructural && summaryChanged) {
    return ["근거와 검색어는 동일하지만 조사 요약 내용이 변경되었습니다."];
  }

  if (!evidenceStructural && queryStructural) {
    const parts: string[] = [];
    if (q.added > 0) parts.push(`검색어 ${q.added}개가 추가`);
    if (q.removed > 0) parts.push(`${q.removed}개가 제거`);
    sentences.push(`근거 목록은 동일하며, ${parts.join("되고 ")}되었습니다.`);
  } else if (evidenceStructural && !queryStructural) {
    if (ev.added === 0 && ev.removed === 0 && ev.updated > 0) {
      sentences.push(
        `근거 출처 구성은 동일하지만 기존 근거 ${ev.updated}개의 내용이 업데이트되었습니다.`,
      );
    } else {
      const parts: string[] = [];
      if (ev.added > 0) parts.push(`새로운 근거 ${ev.added}개가 추가`);
      if (ev.removed > 0) parts.push(`${ev.removed}개가 제외`);
      if (parts.length > 0) {
        const prefix = q.added + q.removed === 0 ? "검색어는 동일하며, " : "";
        sentences.push(`${prefix}${parts.join("되고 ")}되었습니다.`);
      }
      if (ev.updated > 0) {
        sentences.push(
          `기존 근거 ${ev.updated}개는 내용이 업데이트되었습니다.`,
        );
      }
    }
  } else {
    // Both evidence and query changed (and/or summary).
    if (ev.added > 0 || ev.removed > 0) {
      const parts: string[] = [];
      if (ev.added > 0) parts.push(`새로운 근거 ${ev.added}개가 추가`);
      if (ev.removed > 0) parts.push(`${ev.removed}개가 제외`);
      sentences.push(
        `최신 조사에서는 ${parts.join("되고 ")}되었습니다.`,
      );
    }
    if (ev.updated > 0) {
      sentences.push(
        `기존 근거 ${ev.updated}개는 내용이 업데이트되었습니다.`,
      );
    }
    if (q.added > 0 || q.removed > 0) {
      const parts: string[] = [];
      if (q.added > 0) parts.push(`${q.added}개가 추가`);
      if (q.removed > 0) parts.push(`${q.removed}개가 제거`);
      sentences.push(`검색어는 ${parts.join("되고 ")}되었습니다.`);
    }
  }

  if (summaryChanged) {
    sentences.push("조사 요약 내용이 변경되었습니다.");
  }

  return sentences.length > 0
    ? sentences
    : ["검색어, 근거 및 조사 요약에 변화가 없습니다."];
}
