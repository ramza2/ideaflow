import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { clsx } from "clsx";
import {
  Search,
  Filter,
  SlidersHorizontal,
  LayoutGrid,
  LayoutList,
  Download,
  Plus,
  StarOff,
  MoreHorizontal,
  Sparkles,
  X,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { listIdeas } from "../../api/ideas";
import { listCategories, listMembers, listStages } from "../../api/workspaces";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "../../components/common/Button";
import { ApiPriorityBadge, StageLabelBadge } from "../../components/common/Badge";
import { Avatar } from "../../components/common/Avatar";
import { EmptyState } from "../../components/common/EmptyState";
import { IdeaCreateMenu } from "../../components/ideas/IdeaCreateMenu";
import { toast } from "../../components/common/Toast";
import { toDisplayUser } from "../../utils/avatar";
import type { CategoryPublic, IdeaListItem, IdeaPriority, StagePublic } from "../../types/api";

type Tab = "all" | "mine" | "assigned";
type ViewMode = "list" | "card";

const TABS: { id: Tab | "participating" | "favorite"; label: string; disabled?: boolean }[] = [
  { id: "all", label: "전체" },
  { id: "mine", label: "내가 작성" },
  { id: "participating", label: "참여 중", disabled: true },
  { id: "assigned", label: "담당" },
  { id: "favorite", label: "즐겨찾기", disabled: true },
];

const PRIORITY_OPTIONS: { value: IdeaPriority | ""; label: string }[] = [
  { value: "", label: "전체 우선순위" },
  { value: "HIGH", label: "높음" },
  { value: "MEDIUM", label: "중간" },
  { value: "LOW", label: "낮음" },
];

interface Filters {
  stage_id: string;
  priority: IdeaPriority | "";
  category_id: string;
  author_id: string;
}

const PAGE_SIZE = 50;
const EMPTY_FILTERS: Filters = { stage_id: "", priority: "", category_id: "", author_id: "" };

function filtersFromSearchParams(params: URLSearchParams): Filters {
  return {
    stage_id: params.get("stage_id") ?? "",
    priority: (params.get("priority") as IdeaPriority | "") || "",
    category_id: params.get("category_id") ?? "",
    author_id: params.get("author_id") ?? "",
  };
}

function offsetFromSearchParams(params: URLSearchParams): number {
  const raw = Number(params.get("offset") ?? "0");
  if (!Number.isFinite(raw) || raw < 0) return 0;
  return Math.floor(raw / PAGE_SIZE) * PAGE_SIZE;
}

export function IdeaListPage() {
  const navigate = useNavigate();
  const { workspaceId = "" } = useParams();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const [tab, setTab] = useState<Tab>("all");
  const [view, setView] = useState<ViewMode>("list");
  // URL q is the persisted search Source of Truth for API requests.
  const urlQuery = searchParams.get("q") ?? "";
  // Local draft while the user types; debounced writes go back to URL q.
  const [searchInput, setSearchInput] = useState(urlQuery);
  const [filterOpen, setFilterOpen] = useState(false);
  const [filters, setFilters] = useState<Filters>(() => filtersFromSearchParams(searchParams));
  const [activeFilters, setActiveFilters] = useState<Filters>(() => filtersFromSearchParams(searchParams));

  // URL is source of truth for pagination offset
  const offset = offsetFromSearchParams(searchParams);

  const [items, setItems] = useState<IdeaListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stages, setStages] = useState<StagePublic[]>([]);
  const [categories, setCategories] = useState<CategoryPublic[]>([]);
  const [memberOptions, setMemberOptions] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    if (!workspaceId) return;
    void Promise.all([
      listStages(workspaceId),
      listCategories(workspaceId),
      listMembers(workspaceId),
    ]).then(([s, c, m]) => {
      setStages(s);
      setCategories(c);
      setMemberOptions(
        m.filter((x) => x.status === "ACTIVE").map((x) => ({ id: x.user_id, name: x.name })),
      );
    }).catch(() => {
      // Non-blocking for list display
    });
  }, [workspaceId]);

  const syncSearchParams = useCallback(
    (next: { q?: string; filters?: Filters; offset?: number }) => {
      const params = new URLSearchParams();
      const q = next.q !== undefined ? next.q : (searchParams.get("q") ?? "");
      const f = next.filters ?? filtersFromSearchParams(searchParams);
      const nextOffset = next.offset !== undefined ? next.offset : offsetFromSearchParams(searchParams);
      if (q) params.set("q", q);
      if (f.stage_id) params.set("stage_id", f.stage_id);
      if (f.priority) params.set("priority", f.priority);
      if (f.category_id) params.set("category_id", f.category_id);
      if (f.author_id) params.set("author_id", f.author_id);
      if (nextOffset > 0) params.set("offset", String(nextOffset));
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  // External URL q changes (Global Search, Back/Forward) → sync input draft.
  useEffect(() => {
    setSearchInput((prev) => (prev === urlQuery ? prev : urlQuery));
  }, [urlQuery]);

  // Debounced local input → URL q (resets offset).
  // Depend only on searchInput so an external URL change cannot re-schedule a
  // push of the previous draft. Compare against the live URL at fire time.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchParams((prev) => {
        const currentQ = prev.get("q") ?? "";
        if (searchInput === currentQ) return prev;

        const params = new URLSearchParams();
        if (searchInput) params.set("q", searchInput);
        const stageId = prev.get("stage_id");
        const priority = prev.get("priority");
        const categoryId = prev.get("category_id");
        const authorId = prev.get("author_id");
        if (stageId) params.set("stage_id", stageId);
        if (priority) params.set("priority", priority);
        if (categoryId) params.set("category_id", categoryId);
        if (authorId) params.set("author_id", authorId);
        // Omit offset → reset to 0 when q changes from local input.
        return params;
      }, { replace: true });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput, setSearchParams]);

  // Keep local filter draft in sync when URL filters change (e.g. refresh)
  useEffect(() => {
    const fromUrl = filtersFromSearchParams(searchParams);
    setActiveFilters(fromUrl);
    setFilters(fromUrl);
  }, [
    searchParams.get("stage_id"),
    searchParams.get("priority"),
    searchParams.get("category_id"),
    searchParams.get("author_id"),
  ]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!workspaceId || !user) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    const params: Parameters<typeof listIdeas>[1] = {
      limit: PAGE_SIZE,
      offset,
    };
    if (urlQuery) params.q = urlQuery;
    if (activeFilters.stage_id) params.stage_id = activeFilters.stage_id;
    if (activeFilters.priority) params.priority = activeFilters.priority;
    if (activeFilters.category_id) params.category_id = activeFilters.category_id;

    if (tab === "mine") {
      params.author_id = user.id;
    } else if (tab === "assigned") {
      params.assignee_id = user.id;
    } else if (activeFilters.author_id) {
      params.author_id = activeFilters.author_id;
    }

    void listIdeas(workspaceId, params)
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(apiErrorMessage(err));
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, user, urlQuery, activeFilters, tab, offset]);

  const activeFilterCount = Object.values(activeFilters).filter(Boolean).length;
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);
  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  function applyFilters(next: Filters, nextOffset = 0) {
    setFilters(next);
    setActiveFilters(next);
    syncSearchParams({ filters: next, offset: nextOffset, q: urlQuery });
  }

  function removeFilterKey(key: keyof Filters) {
    applyFilters({ ...activeFilters, [key]: "" });
  }

  function handleApplyFilters() {
    applyFilters({ ...filters });
    setFilterOpen(false);
    toast.info("필터가 적용되었습니다");
  }

  function handleClearFilters() {
    applyFilters({ ...EMPTY_FILTERS });
    toast.info("필터가 초기화되었습니다");
  }

  function goPrev() {
    if (!canPrev) return;
    syncSearchParams({ offset: Math.max(0, offset - PAGE_SIZE), q: urlQuery, filters: activeFilters });
  }

  function goNext() {
    if (!canNext) return;
    syncSearchParams({ offset: offset + PAGE_SIZE, q: urlQuery, filters: activeFilters });
  }

  function handleDisabledTab(id: string) {
    if (id === "participating") {
      toast.info("참여자 기능은 추후 제공됩니다");
      return;
    }
    if (id === "favorite") {
      toast.info("즐겨찾기 기능은 추후 제공됩니다");
    }
  }

  const stageLabel = (id: string) => stages.find((s) => s.id === id)?.label ?? id;
  const categoryName = (id: string) => categories.find((c) => c.id === id)?.name ?? id;

  const hasSearchOrFilter = Boolean(urlQuery) || activeFilterCount > 0;
  const emptyCopy = hasSearchOrFilter
    ? {
        title: "검색/필터 결과가 없습니다",
        description: "검색어나 필터 조건을 변경해 보세요.",
      }
    : tab === "mine"
      ? {
          title: "내가 작성한 아이디어가 없습니다",
          description: "새 아이디어를 등록해 보세요.",
        }
      : tab === "assigned"
        ? {
            title: "담당 중인 아이디어가 없습니다",
            description: "담당자로 지정된 아이디어가 없습니다.",
          }
        : {
            title: "등록된 아이디어가 없습니다",
            description: "첫 번째 아이디어를 등록해 보세요.",
          };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 sm:px-8 pt-6 pb-4 border-b border-[rgba(0,0,0,0.06)] bg-white">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold text-[#111118]">아이디어</h1>
            <p className="text-sm text-[#6b6b80]">총 {total}건</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={<Download className="w-3.5 h-3.5" />}
              disabled
              title="추후 제공 예정"
              className="hidden sm:inline-flex"
            >
              내보내기
            </Button>
            <IdeaCreateMenu
              workspaceId={workspaceId}
              align="right"
              trigger={({ toggle }) => (
                <Button
                  variant="primary"
                  size="sm"
                  icon={<Plus className="w-3.5 h-3.5" />}
                  onClick={toggle}
                >
                  <span className="hidden sm:inline">새 아이디어</span>
                </Button>
              )}
            />
          </div>
        </div>

        <div className="flex gap-1 -mb-px overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              disabled={t.disabled}
              onClick={() => {
                if (t.disabled) {
                  handleDisabledTab(t.id);
                  return;
                }
                setTab(t.id as Tab);
                syncSearchParams({ offset: 0, q: urlQuery, filters: activeFilters });
              }}
              className={clsx(
                "px-3 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
                t.disabled && "opacity-50 cursor-not-allowed",
                !t.disabled && tab === t.id
                  ? "border-[#4f46e5] text-[#4f46e5]"
                  : "border-transparent text-[#6b6b80] hover:text-[#111118]",
              )}
              title={t.disabled ? "추후 제공 예정" : undefined}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-4 sm:px-8 py-3 bg-white border-b border-[rgba(0,0,0,0.06)] flex items-center gap-2 sm:gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[160px] max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9ca3af]" />
          <input
            type="text"
            placeholder="목록 검색..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-full h-8 pl-8 pr-3 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f4f4f8] text-sm placeholder:text-[#9ca3af] focus:outline-none focus:bg-white focus:border-[rgba(0,0,0,0.15)] transition-all"
          />
        </div>

        <Button
          variant="ghost"
          size="sm"
          icon={<Filter className="w-3.5 h-3.5" />}
          onClick={() => setFilterOpen(true)}
          className={activeFilterCount > 0 ? "text-[#4f46e5] bg-[#ede9fe] hover:bg-[#e0dcfc]" : ""}
        >
          필터
          {activeFilterCount > 0 && (
            <span className="ml-1 w-4 h-4 rounded-full bg-[#4f46e5] text-white text-[10px] flex items-center justify-center font-bold">
              {activeFilterCount}
            </span>
          )}
        </Button>

        <div
          className="inline-flex items-center gap-1.5 px-2.5 h-8 text-sm text-[#6b6b80]"
          title="정렬은 최종 수정일 기준입니다"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">최종 수정일</span>
        </div>

        {activeFilterCount > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            {activeFilters.stage_id && (
              <span className="flex items-center gap-1 px-2 py-1 rounded-full bg-[#ede9fe] text-xs text-[#4f46e5]">
                단계: {stageLabel(activeFilters.stage_id)}
                <button type="button" onClick={() => removeFilterKey("stage_id")}><X className="w-3 h-3" /></button>
              </span>
            )}
            {activeFilters.priority && (
              <span className="flex items-center gap-1 px-2 py-1 rounded-full bg-[#ede9fe] text-xs text-[#4f46e5]">
                우선순위: {PRIORITY_OPTIONS.find((o) => o.value === activeFilters.priority)?.label}
                <button type="button" onClick={() => removeFilterKey("priority")}><X className="w-3 h-3" /></button>
              </span>
            )}
            {activeFilters.category_id && (
              <span className="flex items-center gap-1 px-2 py-1 rounded-full bg-[#ede9fe] text-xs text-[#4f46e5]">
                분야: {categoryName(activeFilters.category_id)}
                <button type="button" onClick={() => removeFilterKey("category_id")}><X className="w-3 h-3" /></button>
              </span>
            )}
            {activeFilters.author_id && (
              <span className="flex items-center gap-1 px-2 py-1 rounded-full bg-[#ede9fe] text-xs text-[#4f46e5]">
                작성자: {memberOptions.find((m) => m.id === activeFilters.author_id)?.name ?? "선택됨"}
                <button type="button" onClick={() => removeFilterKey("author_id")}><X className="w-3 h-3" /></button>
              </span>
            )}
            <button type="button" onClick={handleClearFilters} className="text-xs text-[#6b6b80] hover:text-[#dc2626] underline">전체 초기화</button>
          </div>
        )}

        <div className="ml-auto flex items-center gap-1">
          {[
            { mode: "list" as ViewMode, Icon: LayoutList },
            { mode: "card" as ViewMode, Icon: LayoutGrid },
          ].map(({ mode, Icon }) => (
            <button
              key={mode}
              type="button"
              onClick={() => setView(mode)}
              className={clsx(
                "w-7 h-7 flex items-center justify-center rounded-md transition-colors",
                view === mode ? "bg-[#ede9fe] text-[#4f46e5]" : "text-[#6b6b80] hover:bg-[#f4f4f8]",
              )}
            >
              <Icon className="w-4 h-4" />
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-4">
        {loading ? (
          <div className="py-16 text-center text-sm text-[#6b6b80]">불러오는 중...</div>
        ) : error ? (
          <EmptyState title="아이디어를 불러올 수 없습니다" description={error} />
        ) : items.length === 0 ? (
          <EmptyState
            icon={<Sparkles className="w-6 h-6" />}
            title={emptyCopy.title}
            description={emptyCopy.description}
            action={
              activeFilterCount > 0 ? (
                <Button variant="secondary" size="sm" onClick={handleClearFilters}>필터 초기화</Button>
              ) : !urlQuery ? (
                <IdeaCreateMenu
                  workspaceId={workspaceId}
                  align="left"
                  trigger={({ toggle }) => (
                    <Button
                      variant="primary"
                      size="sm"
                      icon={<Plus className="w-3.5 h-3.5" />}
                      onClick={toggle}
                    >
                      새 아이디어
                    </Button>
                  )}
                />
              ) : null
            }
          />
        ) : view === "list" ? (
          <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] overflow-hidden overflow-x-auto">
            <div className="min-w-[800px]">
              <div className="grid grid-cols-[60px_1fr_100px_90px_70px_64px_64px_100px_36px] gap-3 px-4 py-2.5 border-b border-[rgba(0,0,0,0.06)] bg-[#f8f8fb]">
                {["코드", "아이디어", "분야", "단계", "우선순위", "작성자", "담당자", "수정일", ""].map((h, i) => (
                  <span key={i} className="text-xs font-medium text-[#6b6b80]">{h}</span>
                ))}
              </div>
              {items.map((idea) => {
                const author = toDisplayUser(idea.author);
                const assignee = idea.assignee ? toDisplayUser(idea.assignee) : null;
                return (
                  <div
                    key={idea.id}
                    className="grid grid-cols-[60px_1fr_100px_90px_70px_64px_64px_100px_36px] gap-3 px-4 py-3 border-b border-[rgba(0,0,0,0.04)] items-center hover:bg-[#f8f8fb] cursor-pointer transition-colors group"
                    onClick={() => navigate(`/w/${workspaceId}/ideas/${idea.id}`)}
                  >
                    <span className="text-xs font-mono text-[#9ca3af]">{idea.idea_code}</span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          title="즐겨찾기 기능은 추후 제공됩니다"
                          onClick={(e) => {
                            e.stopPropagation();
                            toast.info("즐겨찾기 기능은 추후 제공됩니다");
                          }}
                          className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 text-[#9ca3af]"
                        >
                          <StarOff className="w-3 h-3" />
                        </button>
                        <p className="text-sm font-medium text-[#111118] truncate">{idea.title}</p>
                      </div>
                      <p className="text-xs text-[#6b6b80] truncate">{idea.one_line_definition ?? ""}</p>
                    </div>
                    <span className="text-xs text-[#6b6b80] truncate">{idea.category?.name ?? "—"}</span>
                    <StageLabelBadge label={idea.stage.label} />
                    <ApiPriorityBadge priority={idea.priority} />
                    <div><Avatar user={author} size="xs" /></div>
                    <div>{assignee ? <Avatar user={assignee} size="xs" /> : null}</div>
                    <span className="text-xs text-[#9ca3af]">{new Date(idea.updated_at).toLocaleDateString("ko")}</span>
                    <button type="button" onClick={(e) => e.stopPropagation()} className="w-7 h-7 flex items-center justify-center rounded-md text-[#9ca3af] hover:text-[#6b6b80] hover:bg-[#f0f0f5]">
                      <MoreHorizontal className="w-4 h-4" />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map((idea) => {
              const author = toDisplayUser(idea.author);
              return (
                <div
                  key={idea.id}
                  onClick={() => navigate(`/w/${workspaceId}/ideas/${idea.id}`)}
                  className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4 hover:border-[rgba(0,0,0,0.12)] hover:shadow-sm cursor-pointer transition-all"
                >
                  <StageLabelBadge label={idea.stage.label} />
                  <p className="text-sm font-semibold text-[#111118] mb-1 line-clamp-2 mt-2">{idea.title}</p>
                  <p className="text-xs text-[#6b6b80] mb-3 line-clamp-2">{idea.one_line_definition ?? ""}</p>
                  <div className="flex flex-wrap gap-1 mb-3">
                    {idea.tags.slice(0, 3).map((tag) => (
                      <span key={tag.id} className="px-1.5 py-0.5 rounded-md bg-[#f0f0f5] text-[10px] text-[#6b6b80]">{tag.name}</span>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <Avatar user={author} size="xs" />
                    <span className="text-xs text-[#9ca3af]">{new Date(idea.updated_at).toLocaleDateString("ko")}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {!loading && !error && total > 0 && (
          <div className="flex items-center justify-center gap-3 mt-6 pb-2">
            <Button variant="secondary" size="sm" icon={<ChevronLeft className="w-3.5 h-3.5" />} disabled={!canPrev} onClick={goPrev}>
              이전
            </Button>
            <span className="text-sm text-[#6b6b80]">
              {pageStart}–{pageEnd} / {total}
            </span>
            <Button variant="secondary" size="sm" disabled={!canNext} onClick={goNext}>
              다음
              <ChevronRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </div>
        )}
      </div>

      {filterOpen && (
        <div className="fixed inset-0 z-40 flex justify-end">
          <div className="absolute inset-0 bg-black/20" onClick={() => setFilterOpen(false)} />
          <div className="relative bg-white w-full max-w-xs h-full shadow-2xl flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[rgba(0,0,0,0.07)]">
              <p className="text-sm font-bold text-[#111118]">필터</p>
              <button type="button" onClick={() => setFilterOpen(false)} className="w-7 h-7 flex items-center justify-center rounded-lg text-[#6b6b80] hover:bg-[#f4f4f8]">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
              <div>
                <label className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider block mb-2">단계</label>
                <div className="flex flex-wrap gap-1.5">
                  <button type="button" onClick={() => setFilters((p) => ({ ...p, stage_id: "" }))} className={clsx("px-2.5 py-1 rounded-full text-xs border", !filters.stage_id ? "bg-[#4f46e5] text-white border-[#4f46e5]" : "border-[rgba(0,0,0,0.1)] text-[#6b6b80]")}>전체</button>
                  {stages.map((s) => (
                    <button key={s.id} type="button" onClick={() => setFilters((p) => ({ ...p, stage_id: s.id }))} className={clsx("px-2.5 py-1 rounded-full text-xs border", filters.stage_id === s.id ? "bg-[#4f46e5] text-white border-[#4f46e5]" : "border-[rgba(0,0,0,0.1)] text-[#6b6b80]")}>
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider block mb-2">우선순위</label>
                <div className="flex flex-wrap gap-1.5">
                  {PRIORITY_OPTIONS.map((opt) => (
                    <button key={opt.value || "all"} type="button" onClick={() => setFilters((p) => ({ ...p, priority: opt.value }))} className={clsx("px-2.5 py-1 rounded-full text-xs border", filters.priority === opt.value ? "bg-[#4f46e5] text-white border-[#4f46e5]" : "border-[rgba(0,0,0,0.1)] text-[#6b6b80]")}>
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider block mb-2">분야</label>
                <div className="flex flex-wrap gap-1.5">
                  <button type="button" onClick={() => setFilters((p) => ({ ...p, category_id: "" }))} className={clsx("px-2.5 py-1 rounded-full text-xs border", !filters.category_id ? "bg-[#4f46e5] text-white border-[#4f46e5]" : "border-[rgba(0,0,0,0.1)] text-[#6b6b80]")}>전체</button>
                  {categories.map((c) => (
                    <button key={c.id} type="button" onClick={() => setFilters((p) => ({ ...p, category_id: c.id }))} className={clsx("px-2.5 py-1 rounded-full text-xs border", filters.category_id === c.id ? "bg-[#4f46e5] text-white border-[#4f46e5]" : "border-[rgba(0,0,0,0.1)] text-[#6b6b80]")}>
                      {c.name}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider block mb-2">작성자</label>
                <div className="space-y-1">
                  <button type="button" onClick={() => setFilters((p) => ({ ...p, author_id: "" }))} className={clsx("w-full text-left px-3 py-2 rounded-lg text-sm", !filters.author_id ? "bg-[#ede9fe] text-[#4f46e5]" : "text-[#6b6b80] hover:bg-[#f4f4f8]")}>전체</button>
                  {memberOptions.map((m) => (
                    <button key={m.id} type="button" onClick={() => setFilters((p) => ({ ...p, author_id: m.id }))} className={clsx("w-full text-left px-3 py-2 rounded-lg text-sm", filters.author_id === m.id ? "bg-[#ede9fe] text-[#4f46e5]" : "text-[#111118] hover:bg-[#f4f4f8]")}>
                      {m.name}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="px-5 py-4 border-t border-[rgba(0,0,0,0.07)] flex gap-2">
              <Button variant="ghost" className="flex-1" onClick={handleClearFilters}>초기화</Button>
              <Button variant="primary" className="flex-1" onClick={handleApplyFilters}>적용</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
