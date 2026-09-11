import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import {
  getIdeaResearchRun,
  listIdeaResearchRuns,
} from "../../api/webResearch";
import { apiErrorMessage } from "../../api/client";
import { Button } from "../common/Button";
import type { WebResearchRun, WebResearchRunHistoryItem } from "../../types/api";
import {
  assignResearchVersions,
  compareEvidenceByUrl,
  compareQueryLists,
} from "../../utils/researchCompare";

type VersionedItem = WebResearchRunHistoryItem & { version: number };

type Props = {
  workspaceId: string;
  ideaId: string;
  /** Bump when a new READY run completes so history refetches. */
  refreshKey?: number;
};

function formatCompletedAt(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}.${m}.${day} ${hh}:${mm}`;
}

function DiffRow({
  tone,
  title,
  url,
  note,
}: {
  tone: "added" | "removed" | "unchanged";
  title: string;
  url?: string;
  note?: string;
}) {
  const prefix = tone === "added" ? "+" : tone === "removed" ? "-" : "=";
  const color =
    tone === "added"
      ? "border-[#bbf7d0] bg-[#f0fdf4] text-[#166534]"
      : tone === "removed"
        ? "border-[#fecaca] bg-[#fef2f2] text-[#991b1b]"
        : "border-[rgba(0,0,0,0.07)] bg-white text-[#374151]";

  return (
    <div className={`rounded-lg border px-3 py-2 ${color}`}>
      <p className="text-sm font-medium">
        {prefix} {title}
        {note ? (
          <span className="ml-2 text-[11px] font-normal opacity-80">{note}</span>
        ) : null}
      </p>
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs opacity-80 hover:underline break-all"
        >
          {url}
        </a>
      ) : null}
    </div>
  );
}

export function ResearchHistoryPanel({
  workspaceId,
  ideaId,
  refreshKey = 0,
}: Props) {
  const HISTORY_LIMIT = 20;
  const HISTORY_OFFSET = 0;

  const [items, setItems] = useState<WebResearchRunHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailRun, setDetailRun] = useState<WebResearchRun | null>(null);
  const [detailVersion, setDetailVersion] = useState<number | null>(null);

  const [compareOpen, setCompareOpen] = useState(false);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [leftRun, setLeftRun] = useState<WebResearchRun | null>(null);
  const [rightRun, setRightRun] = useState<WebResearchRun | null>(null);
  const [leftVersion, setLeftVersion] = useState<number | null>(null);
  const [rightVersion, setRightVersion] = useState<number | null>(null);

  // Request sequence guards (same pattern as IdeaListPage) — drop stale responses.
  const historyReqSeqRef = useRef(0);
  const detailReqSeqRef = useRef(0);
  const compareReqSeqRef = useRef(0);

  const fetchHistory = useCallback(async () => {
    if (!workspaceId || !ideaId) return;
    const seq = ++historyReqSeqRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await listIdeaResearchRuns(workspaceId, ideaId, {
        limit: HISTORY_LIMIT,
        offset: HISTORY_OFFSET,
      });
      if (seq !== historyReqSeqRef.current) return;
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      if (seq !== historyReqSeqRef.current) return;
      setError(apiErrorMessage(err, "조사 이력을 불러오지 못했습니다."));
      setItems([]);
      setTotal(0);
    } finally {
      if (seq === historyReqSeqRef.current) {
        setLoading(false);
      }
    }
  }, [workspaceId, ideaId]);

  useEffect(() => {
    // Invalidate in-flight history/detail/compare when Idea/workspace changes.
    historyReqSeqRef.current += 1;
    detailReqSeqRef.current += 1;
    compareReqSeqRef.current += 1;

    setItems([]);
    setTotal(0);
    setError(null);
    setLoading(false);
    setDetailOpen(false);
    setDetailRun(null);
    setDetailError(null);
    setDetailLoading(false);
    setCompareOpen(false);
    setLeftRun(null);
    setRightRun(null);
    setCompareError(null);
    setCompareLoading(false);
    void fetchHistory();
  }, [workspaceId, ideaId, refreshKey, fetchHistory]);

  const versioned = useMemo(
    () =>
      assignResearchVersions(items, total, HISTORY_OFFSET) as VersionedItem[],
    [items, total],
  );
  const latestItem = versioned.find((i) => i.is_latest) ?? versioned[0] ?? null;

  async function openDetail(item: VersionedItem) {
    const seq = ++detailReqSeqRef.current;
    setDetailOpen(true);
    setDetailVersion(item.version);
    setDetailRun(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const data = await getIdeaResearchRun(workspaceId, ideaId, item.id);
      if (seq !== detailReqSeqRef.current) return;
      setDetailRun(data.run);
    } catch (err) {
      if (seq !== detailReqSeqRef.current) return;
      setDetailError(apiErrorMessage(err, "이 조사 결과를 불러올 수 없습니다."));
    } finally {
      if (seq === detailReqSeqRef.current) {
        setDetailLoading(false);
      }
    }
  }

  async function openCompare(item: VersionedItem) {
    if (!latestItem || latestItem.id === item.id) return;
    const seq = ++compareReqSeqRef.current;
    setCompareOpen(true);
    setLeftRun(null);
    setRightRun(null);
    setLeftVersion(item.version);
    setRightVersion(latestItem.version);
    setCompareError(null);
    setCompareLoading(true);
    try {
      const [left, right] = await Promise.all([
        getIdeaResearchRun(workspaceId, ideaId, item.id),
        getIdeaResearchRun(workspaceId, ideaId, latestItem.id),
      ]);
      if (seq !== compareReqSeqRef.current) return;
      setLeftRun(left.run);
      setRightRun(right.run);
    } catch (err) {
      if (seq !== compareReqSeqRef.current) return;
      setCompareError(apiErrorMessage(err, "비교 데이터를 불러오지 못했습니다."));
    } finally {
      if (seq === compareReqSeqRef.current) {
        setCompareLoading(false);
      }
    }
  }

  const evidenceDiff = useMemo(() => {
    if (!leftRun || !rightRun) return null;
    return compareEvidenceByUrl(leftRun.evidence ?? [], rightRun.evidence ?? []);
  }, [leftRun, rightRun]);

  const queryDiff = useMemo(() => {
    if (!leftRun || !rightRun) return null;
    return compareQueryLists(
      leftRun.queries_to_send ?? [],
      rightRun.queries_to_send ?? [],
    );
  }, [leftRun, rightRun]);

  if (!loading && !error && items.length === 0) {
    return null;
  }

  return (
    <div className="pt-2 border-t border-[rgba(0,0,0,0.06)] mt-6">
      <h3 className="text-sm font-semibold text-[#111118] mb-3">조사 이력</h3>

      {loading && (
        <p className="text-sm text-[#6b6b80] flex items-center gap-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          조사 이력 불러오는 중...
        </p>
      )}

      {error && (
        <div className="rounded-xl border border-[rgba(220,38,38,0.2)] bg-[#fef2f2] px-4 py-3">
          <p className="text-sm text-[#dc2626] mb-2">{error}</p>
          <Button variant="secondary" size="sm" onClick={() => void fetchHistory()}>
            다시 시도
          </Button>
        </div>
      )}

      {!loading && !error && items.length === 1 && (
        <p className="text-xs text-[#6b6b80] mb-3">
          아직 비교할 이전 조사 결과가 없습니다.
        </p>
      )}

      {!loading && !error && versioned.length > 0 && (
        <ul className="space-y-2">
          {versioned.map((item) => (
            <li
              key={item.id}
              className="rounded-xl border border-[rgba(0,0,0,0.07)] bg-white px-4 py-3"
            >
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="text-sm font-semibold text-[#111118]">
                  v{item.version}
                </span>
                {item.is_latest && (
                  <span className="text-[11px] font-medium text-[#4f46e5] bg-[#eef2ff] px-1.5 py-0.5 rounded">
                    최신
                  </span>
                )}
                <span className="text-xs text-[#9ca3af]">
                  {formatCompletedAt(item.completed_at ?? item.created_at)}
                </span>
              </div>
              <p className="text-xs text-[#6b6b80] mb-2">
                근거 {item.evidence_count}개
                {item.query_count > 0 ? ` · 검색어 ${item.query_count}개` : ""}
              </p>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={() => void openDetail(item)}>
                  보기
                </Button>
                {!item.is_latest && latestItem && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void openCompare(item)}
                  >
                    최신과 비교
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {detailOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="research-history-detail-title"
        >
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
              <h3
                id="research-history-detail-title"
                className="text-base font-bold text-[#111118]"
              >
                조사 결과 {detailVersion != null ? `v${detailVersion}` : ""}
              </h3>
              <button
                type="button"
                aria-label="닫기"
                className="p-1 rounded-lg hover:bg-[rgba(0,0,0,0.05)]"
                onClick={() => setDetailOpen(false)}
              >
                <X className="w-4 h-4 text-[#6b6b80]" />
              </button>
            </div>
            <div className="px-5 py-4 overflow-y-auto space-y-4">
              {detailLoading && (
                <p className="text-sm text-[#6b6b80] flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  불러오는 중...
                </p>
              )}
              {detailError && <p className="text-sm text-[#dc2626]">{detailError}</p>}
              {detailRun && (
                <>
                  <p className="text-xs text-[#9ca3af]">
                    조사 완료일 {formatCompletedAt(detailRun.completed_at)}
                  </p>
                  {(detailRun.queries_to_send?.length ?? 0) > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-1">
                        검색 Query
                      </h4>
                      <ul className="list-disc pl-4 space-y-0.5">
                        {detailRun.queries_to_send.map((q) => (
                          <li key={q} className="text-sm text-[#111118]">
                            {q}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {detailRun.research_summary && (
                    <div>
                      <h4 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-1">
                        Research summary
                      </h4>
                      <p className="text-sm text-[#111118] whitespace-pre-wrap leading-relaxed">
                        {detailRun.research_summary}
                      </p>
                    </div>
                  )}
                  <div>
                    <h4 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-2">
                      Evidence ({detailRun.evidence?.length ?? 0})
                    </h4>
                    <div className="space-y-2">
                      {(detailRun.evidence ?? []).map((ev) => (
                        <div
                          key={ev.id}
                          className="rounded-lg border border-[rgba(0,0,0,0.07)] p-3"
                        >
                          <a
                            href={ev.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm font-semibold text-[#2563eb] hover:underline"
                          >
                            {ev.title}
                          </a>
                          <p className="text-xs text-[#6b6b80] mt-0.5">
                            {[ev.source_name, ev.domain].filter(Boolean).join(" · ")}
                          </p>
                          {ev.snippet && (
                            <p className="text-sm text-[#111118] mt-1 whitespace-pre-wrap">
                              {ev.snippet}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
            <div className="px-5 py-3 border-t border-[rgba(0,0,0,0.06)] flex justify-end">
              <Button variant="secondary" onClick={() => setDetailOpen(false)}>
                닫기
              </Button>
            </div>
          </div>
        </div>
      )}

      {compareOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="research-compare-title"
        >
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
              <h3
                id="research-compare-title"
                className="text-base font-bold text-[#111118]"
              >
                조사 결과 비교
              </h3>
              <button
                type="button"
                aria-label="닫기"
                className="p-1 rounded-lg hover:bg-[rgba(0,0,0,0.05)]"
                onClick={() => setCompareOpen(false)}
              >
                <X className="w-4 h-4 text-[#6b6b80]" />
              </button>
            </div>
            <div className="px-5 py-4 overflow-y-auto space-y-5">
              {compareLoading && (
                <p className="text-sm text-[#6b6b80] flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  비교 데이터 불러오는 중...
                </p>
              )}
              {compareError && <p className="text-sm text-[#dc2626]">{compareError}</p>}
              {leftRun && rightRun && (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm font-semibold text-[#111118]">
                        v{leftVersion}
                      </p>
                      <p className="text-xs text-[#9ca3af]">
                        {formatCompletedAt(leftRun.completed_at)} 완료
                      </p>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-[#4f46e5]">
                        v{rightVersion} 최신
                      </p>
                      <p className="text-xs text-[#9ca3af]">
                        {formatCompletedAt(rightRun.completed_at)} 완료 · 최신
                      </p>
                    </div>
                  </div>

                  <div>
                    <h4 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-2">
                      요약
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div className="rounded-xl border border-[rgba(0,0,0,0.07)] p-3 bg-[#fafafa]">
                        <p className="text-sm text-[#111118] whitespace-pre-wrap leading-relaxed">
                          {leftRun.research_summary || "요약 없음"}
                        </p>
                      </div>
                      <div className="rounded-xl border border-[rgba(0,0,0,0.07)] p-3 bg-[#fafafa]">
                        <p className="text-sm text-[#111118] whitespace-pre-wrap leading-relaxed">
                          {rightRun.research_summary || "요약 없음"}
                        </p>
                      </div>
                    </div>
                  </div>

                  {queryDiff && (
                    <div>
                      <h4 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-2">
                        검색어
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                        <ul className="space-y-1">
                          {(leftRun.queries_to_send ?? []).map((q) => (
                            <li key={`l-${q}`}>{q}</li>
                          ))}
                        </ul>
                        <ul className="space-y-1">
                          {(rightRun.queries_to_send ?? []).map((q) => (
                            <li key={`r-${q}`}>{q}</li>
                          ))}
                        </ul>
                      </div>
                      <p className="text-xs text-[#6b6b80] mt-2">
                        +{queryDiff.added.length} / -{queryDiff.removed.length} / =
                        {queryDiff.common.length}
                      </p>
                    </div>
                  )}

                  {evidenceDiff && (
                    <div>
                      <h4 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-2">
                        근거 변화
                      </h4>
                      <div className="flex flex-wrap gap-3 text-sm mb-3">
                        <span className="text-[#16a34a]">
                          + 신규 {evidenceDiff.added.length}
                        </span>
                        <span className="text-[#dc2626]">
                          - 제거 {evidenceDiff.removed.length}
                        </span>
                        <span className="text-[#6b6b80]">
                          = 유지 {evidenceDiff.unchanged.length}
                        </span>
                      </div>
                      <div className="space-y-2">
                        {evidenceDiff.added.map((item) => (
                          <DiffRow
                            key={`a-${item.key}`}
                            tone="added"
                            title={item.right?.title || item.key}
                            url={item.right?.url}
                          />
                        ))}
                        {evidenceDiff.removed.map((item) => (
                          <DiffRow
                            key={`r-${item.key}`}
                            tone="removed"
                            title={item.left?.title || item.key}
                            url={item.left?.url}
                          />
                        ))}
                        {evidenceDiff.unchanged.map((item) => (
                          <DiffRow
                            key={`u-${item.key}`}
                            tone="unchanged"
                            title={
                              item.right?.title || item.left?.title || item.key
                            }
                            url={item.right?.url || item.left?.url}
                            note={item.metadataChanged ? "업데이트됨" : undefined}
                          />
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="px-5 py-3 border-t border-[rgba(0,0,0,0.06)] flex justify-end">
              <Button variant="secondary" onClick={() => setCompareOpen(false)}>
                닫기
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
