import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { clsx } from "clsx";
import {
  Search,
  Filter,
  SlidersHorizontal,
  LayoutGrid,
  LayoutList,
  Download,
  Plus,
  Star,
  StarOff,
  MoreHorizontal,
  MessageSquare,
  ChevronRight,
  Sparkles,
  X,
  ChevronDown,
} from "lucide-react";
import { MOCK_IDEAS } from "../../mocks/ideas";
import { MOCK_USERS, getUserById } from "../../mocks/users";
import { Button } from "../../components/common/Button";
import { StageBadge, PriorityBadge } from "../../components/common/Badge";
import { Avatar, AvatarGroup } from "../../components/common/Avatar";
import { EmptyState } from "../../components/common/EmptyState";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { toast } from "../../components/common/Toast";
import type { Idea, IdeaStage, Priority } from "../../types";

type Tab = "all" | "mine" | "participating" | "assigned" | "favorite";
type ViewMode = "list" | "card";

const TABS: { id: Tab; label: string }[] = [
  { id: "all", label: "전체" },
  { id: "mine", label: "내가 작성" },
  { id: "participating", label: "참여 중" },
  { id: "assigned", label: "담당" },
  { id: "favorite", label: "즐겨찾기" },
];

const STAGE_OPTIONS: { value: IdeaStage | ""; label: string }[] = [
  { value: "", label: "전체 단계" },
  { value: "draft", label: "초안" },
  { value: "reviewing", label: "검토 중" },
  { value: "validated", label: "검증 후보" },
  { value: "executing", label: "실행 중" },
  { value: "paused", label: "보류" },
  { value: "archived", label: "보관" },
];

const PRIORITY_OPTIONS: { value: Priority | ""; label: string }[] = [
  { value: "", label: "전체 우선순위" },
  { value: "high", label: "높음" },
  { value: "medium", label: "중간" },
  { value: "low", label: "낮음" },
];

const FIELD_OPTIONS = [
  "", "기술/AI", "기술/인프라", "기술/개발", "제품/서비스",
  "업무 개선", "사업/마케팅", "개인 프로젝트", "기타",
];

interface Filters {
  stage: IdeaStage | "";
  priority: Priority | "";
  field: string;
  authorId: string;
}

export function IdeaListPage() {
  const navigate = useNavigate();
  const { workspaceId = "personal" } = useParams();
  const [tab, setTab] = useState<Tab>("all");
  const [view, setView] = useState<ViewMode>("list");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filterOpen, setFilterOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [filters, setFilters] = useState<Filters>({ stage: "", priority: "", field: "", authorId: "" });
  const [activeFilters, setActiveFilters] = useState<Filters>({ stage: "", priority: "", field: "", authorId: "" });
  const [favorites, setFavorites] = useState<Set<string>>(
    new Set(MOCK_IDEAS.filter((i) => i.isFavorite).map((i) => i.id))
  );
  const [sortBy, setSortBy] = useState<"updated" | "created" | "title">("updated");
  const [sortOpen, setSortOpen] = useState(false);

  const currentUserId = "u-001";

  const activeFilterCount = Object.values(activeFilters).filter(Boolean).length;

  function filterIdeas(ideas: Idea[]): Idea[] {
    let result = [...ideas];
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (i) =>
          i.title.toLowerCase().includes(q) ||
          i.oneLiner.toLowerCase().includes(q) ||
          i.code.toLowerCase().includes(q)
      );
    }
    if (tab === "mine") result = result.filter((i) => i.authorId === currentUserId);
    if (tab === "participating") result = result.filter((i) => i.participantIds.includes(currentUserId));
    if (tab === "assigned") result = result.filter((i) => i.assigneeId === currentUserId);
    if (tab === "favorite") result = result.filter((i) => favorites.has(i.id));
    if (activeFilters.stage) result = result.filter((i) => i.stage === activeFilters.stage);
    if (activeFilters.priority) result = result.filter((i) => i.priority === activeFilters.priority);
    if (activeFilters.field) result = result.filter((i) => i.field === activeFilters.field);
    if (activeFilters.authorId) result = result.filter((i) => i.authorId === activeFilters.authorId);

    result.sort((a, b) => {
      if (sortBy === "updated") return b.updatedAt.localeCompare(a.updatedAt);
      if (sortBy === "created") return b.createdAt.localeCompare(a.createdAt);
      return a.title.localeCompare(b.title, "ko");
    });
    return result;
  }

  const filtered = filterIdeas(MOCK_IDEAS);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleFavorite(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    const isAdding = !favorites.has(id);
    setFavorites((prev) => {
      const next = new Set(prev);
      isAdding ? next.add(id) : next.delete(id);
      return next;
    });
    toast.info(isAdding ? "즐겨찾기에 추가되었습니다" : "즐겨찾기에서 제거되었습니다");
  }

  function handleApplyFilters() {
    setActiveFilters({ ...filters });
    setFilterOpen(false);
    toast.info("필터가 적용되었습니다");
  }

  function handleClearFilters() {
    const empty: Filters = { stage: "", priority: "", field: "", authorId: "" };
    setFilters(empty);
    setActiveFilters(empty);
    toast.info("필터가 초기화되었습니다");
  }

  function handleBulkDelete() {
    setDeleteConfirm(true);
  }

  function confirmDelete() {
    const count = selected.size;
    setSelected(new Set());
    setDeleteConfirm(false);
    toast.success(`${count}건이 삭제되었습니다`);
  }

  function handleExport() {
    toast.info("Excel 파일 준비 중...", "잠시 후 다운로드가 시작됩니다.");
  }

  const SORT_LABELS = { updated: "최종 수정일", created: "작성일", title: "이름 순" };

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="px-4 sm:px-8 pt-6 pb-4 border-b border-[rgba(0,0,0,0.06)] bg-white">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold text-[#111118]">아이디어</h1>
            <p className="text-sm text-[#6b6b80]">총 {MOCK_IDEAS.length}건</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" icon={<Download className="w-3.5 h-3.5" />} onClick={handleExport} className="hidden sm:inline-flex">
              내보내기
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={<Plus className="w-3.5 h-3.5" />}
              onClick={() => navigate(`/w/${workspaceId}/ideas/new`)}
            >
              <span className="hidden sm:inline">새 아이디어</span>
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 -mb-px overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={clsx(
                "px-3 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
                tab === t.id
                  ? "border-[#4f46e5] text-[#4f46e5]"
                  : "border-transparent text-[#6b6b80] hover:text-[#111118]"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Toolbar */}
      <div className="px-4 sm:px-8 py-3 bg-white border-b border-[rgba(0,0,0,0.06)] flex items-center gap-2 sm:gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[160px] max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9ca3af]" />
          <input
            type="text"
            placeholder="목록 검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full h-8 pl-8 pr-3 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f4f4f8] text-sm placeholder:text-[#9ca3af] focus:outline-none focus:bg-white focus:border-[rgba(0,0,0,0.15)] transition-all"
          />
        </div>

        <div className="relative">
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
        </div>

        {/* Sort dropdown */}
        <div className="relative">
          <Button
            variant="ghost"
            size="sm"
            icon={<SlidersHorizontal className="w-3.5 h-3.5" />}
            onClick={() => setSortOpen(!sortOpen)}
          >
            <span className="hidden sm:inline">{SORT_LABELS[sortBy]}</span>
            <ChevronDown className="w-3 h-3 ml-0.5" />
          </Button>
          {sortOpen && (
            <div className="absolute top-full left-0 mt-1 w-36 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg py-1 z-20">
              {(Object.entries(SORT_LABELS) as [typeof sortBy, string][]).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => { setSortBy(key); setSortOpen(false); }}
                  className={clsx(
                    "w-full text-left px-3 py-2 text-sm hover:bg-[#f4f4f8]",
                    sortBy === key ? "text-[#4f46e5] font-medium" : "text-[#111118]"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Active filter chips */}
        {activeFilterCount > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            {activeFilters.stage && (
              <span className="flex items-center gap-1 px-2 py-1 rounded-full bg-[#ede9fe] text-xs text-[#4f46e5]">
                단계: {STAGE_OPTIONS.find((o) => o.value === activeFilters.stage)?.label}
                <button onClick={() => setActiveFilters((p) => ({ ...p, stage: "" }))}><X className="w-3 h-3" /></button>
              </span>
            )}
            {activeFilters.priority && (
              <span className="flex items-center gap-1 px-2 py-1 rounded-full bg-[#ede9fe] text-xs text-[#4f46e5]">
                우선순위: {PRIORITY_OPTIONS.find((o) => o.value === activeFilters.priority)?.label}
                <button onClick={() => setActiveFilters((p) => ({ ...p, priority: "" }))}><X className="w-3 h-3" /></button>
              </span>
            )}
            {activeFilters.field && (
              <span className="flex items-center gap-1 px-2 py-1 rounded-full bg-[#ede9fe] text-xs text-[#4f46e5]">
                분야: {activeFilters.field}
                <button onClick={() => setActiveFilters((p) => ({ ...p, field: "" }))}><X className="w-3 h-3" /></button>
              </span>
            )}
            <button onClick={handleClearFilters} className="text-xs text-[#6b6b80] hover:text-[#dc2626] underline">전체 초기화</button>
          </div>
        )}

        <div className="ml-auto flex items-center gap-1">
          {[
            { mode: "list" as ViewMode, Icon: LayoutList },
            { mode: "card" as ViewMode, Icon: LayoutGrid },
          ].map(({ mode, Icon }) => (
            <button
              key={mode}
              onClick={() => setView(mode)}
              className={clsx(
                "w-7 h-7 flex items-center justify-center rounded-md transition-colors",
                view === mode ? "bg-[#ede9fe] text-[#4f46e5]" : "text-[#6b6b80] hover:bg-[#f4f4f8]"
              )}
            >
              <Icon className="w-4 h-4" />
            </button>
          ))}
        </div>
      </div>

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <div className="px-4 sm:px-8 py-2.5 bg-[#ede9fe] border-b border-[#ddd6fe] flex items-center gap-2 sm:gap-3 flex-wrap">
          <span className="text-sm font-medium text-[#4f46e5]">{selected.size}건 선택됨</span>
          <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap ml-2">
            {["단계 변경", "담당자 지정", "태그 추가"].map((a) => (
              <Button key={a} variant="ghost" size="sm">{a}</Button>
            ))}
            <Button variant="ghost" size="sm" onClick={handleExport}>내보내기</Button>
            <Button variant="danger" size="sm" onClick={handleBulkDelete}>삭제</Button>
          </div>
          <button onClick={() => setSelected(new Set())} className="ml-auto text-xs text-[#4f46e5] hover:underline">
            선택 해제
          </button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-4">
        {filtered.length === 0 ? (
          <EmptyState
            icon={<Sparkles className="w-6 h-6" />}
            title={search || activeFilterCount > 0 ? "검색/필터 결과가 없습니다" : "아직 아이디어가 없습니다"}
            description={search || activeFilterCount > 0 ? "검색어나 필터 조건을 변경해 보세요." : "첫 번째 아이디어를 등록해 보세요."}
            action={
              activeFilterCount > 0 ? (
                <Button variant="secondary" size="sm" onClick={handleClearFilters}>필터 초기화</Button>
              ) : !search ? (
                <Button variant="primary" size="sm" icon={<Plus className="w-3.5 h-3.5" />} onClick={() => navigate(`/w/${workspaceId}/ideas/new`)}>
                  새 아이디어
                </Button>
              ) : null
            }
          />
        ) : view === "list" ? (
          <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] overflow-hidden overflow-x-auto">
            <div className="min-w-[800px]">
              <div className="grid grid-cols-[28px_60px_1fr_100px_90px_70px_64px_64px_100px_36px] gap-3 px-4 py-2.5 border-b border-[rgba(0,0,0,0.06)] bg-[#f8f8fb]">
                {["", "코드", "아이디어", "분야", "단계", "우선순위", "작성자", "담당자", "수정일", ""].map((h, i) => (
                  <span key={i} className="text-xs font-medium text-[#6b6b80]">{h}</span>
                ))}
              </div>
              {filtered.map((idea) => {
                const author = getUserById(idea.authorId);
                const assignee = idea.assigneeId ? getUserById(idea.assigneeId) : undefined;
                const isSel = selected.has(idea.id);
                return (
                  <div
                    key={idea.id}
                    className={clsx(
                      "grid grid-cols-[28px_60px_1fr_100px_90px_70px_64px_64px_100px_36px] gap-3 px-4 py-3 border-b border-[rgba(0,0,0,0.04)] items-center hover:bg-[#f8f8fb] cursor-pointer transition-colors group",
                      isSel && "bg-[#f5f3ff]"
                    )}
                    onClick={() => navigate(`/w/${workspaceId}/ideas/${idea.id}`)}
                  >
                    <div onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={isSel} onChange={() => toggleSelect(idea.id)} className="w-3.5 h-3.5 accent-[#4f46e5]" />
                    </div>
                    <span className="text-xs font-mono text-[#9ca3af]">{idea.code}</span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <button onClick={(e) => toggleFavorite(idea.id, e)} className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                          {favorites.has(idea.id) ? <Star className="w-3 h-3 text-[#d97706] fill-[#d97706]" /> : <StarOff className="w-3 h-3 text-[#9ca3af]" />}
                        </button>
                        <p className="text-sm font-medium text-[#111118] truncate">{idea.title}</p>
                      </div>
                      <p className="text-xs text-[#6b6b80] truncate">{idea.oneLiner}</p>
                    </div>
                    <span className="text-xs text-[#6b6b80] truncate">{idea.field}</span>
                    <StageBadge stage={idea.stage} />
                    <PriorityBadge priority={idea.priority} />
                    <div>{author && <Avatar user={author} size="xs" />}</div>
                    <div>{assignee && <Avatar user={assignee} size="xs" />}</div>
                    <span className="text-xs text-[#9ca3af]">{new Date(idea.updatedAt).toLocaleDateString("ko")}</span>
                    <button
                      onClick={(e) => e.stopPropagation()}
                      className="w-7 h-7 flex items-center justify-center rounded-md text-[#9ca3af] hover:text-[#6b6b80] hover:bg-[#f0f0f5] transition-colors"
                    >
                      <MoreHorizontal className="w-4 h-4" />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((idea) => {
              const author = getUserById(idea.authorId);
              const participants = idea.participantIds.map((id) => getUserById(id)).filter(Boolean) as any[];
              return (
                <div
                  key={idea.id}
                  onClick={() => navigate(`/w/${workspaceId}/ideas/${idea.id}`)}
                  className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4 hover:border-[rgba(0,0,0,0.12)] hover:shadow-sm cursor-pointer transition-all group"
                >
                  <div className="flex items-start justify-between mb-2">
                    <StageBadge stage={idea.stage} />
                    <div className="flex items-center gap-1 text-xs text-[#9ca3af]">
                      <MessageSquare className="w-3.5 h-3.5" />
                      {idea.commentCount}
                    </div>
                  </div>
                  <p className="text-sm font-semibold text-[#111118] mb-1 line-clamp-2">{idea.title}</p>
                  <p className="text-xs text-[#6b6b80] mb-3 line-clamp-2">{idea.oneLiner}</p>
                  <div className="flex flex-wrap gap-1 mb-3">
                    {idea.tags.slice(0, 3).map((tag) => (
                      <span key={tag} className="px-1.5 py-0.5 rounded-md bg-[#f0f0f5] text-[10px] text-[#6b6b80]">{tag}</span>
                    ))}
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {author && <Avatar user={author} size="xs" />}
                      <span className="text-xs text-[#9ca3af]">{new Date(idea.updatedAt).toLocaleDateString("ko")}</span>
                    </div>
                    <AvatarGroup users={participants} max={3} size="xs" />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Filter Drawer ── */}
      {filterOpen && (
        <div className="fixed inset-0 z-40 flex justify-end">
          <div className="absolute inset-0 bg-black/20" onClick={() => setFilterOpen(false)} />
          <div className="relative bg-white w-full max-w-xs h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[rgba(0,0,0,0.07)]">
              <p className="text-sm font-bold text-[#111118]">필터</p>
              <button onClick={() => setFilterOpen(false)} className="w-7 h-7 flex items-center justify-center rounded-lg text-[#6b6b80] hover:bg-[#f4f4f8]">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
              {/* Stage */}
              <div>
                <label className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider block mb-2">단계</label>
                <div className="flex flex-wrap gap-1.5">
                  {STAGE_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setFilters((p) => ({ ...p, stage: opt.value as IdeaStage | "" }))}
                      className={clsx(
                        "px-2.5 py-1 rounded-full text-xs border transition-colors",
                        filters.stage === opt.value
                          ? "bg-[#4f46e5] text-white border-[#4f46e5]"
                          : "border-[rgba(0,0,0,0.1)] text-[#6b6b80] hover:border-[#4f46e5] hover:text-[#4f46e5]"
                      )}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Priority */}
              <div>
                <label className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider block mb-2">우선순위</label>
                <div className="flex flex-wrap gap-1.5">
                  {PRIORITY_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setFilters((p) => ({ ...p, priority: opt.value as Priority | "" }))}
                      className={clsx(
                        "px-2.5 py-1 rounded-full text-xs border transition-colors",
                        filters.priority === opt.value
                          ? "bg-[#4f46e5] text-white border-[#4f46e5]"
                          : "border-[rgba(0,0,0,0.1)] text-[#6b6b80] hover:border-[#4f46e5] hover:text-[#4f46e5]"
                      )}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Field */}
              <div>
                <label className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider block mb-2">분야</label>
                <div className="flex flex-wrap gap-1.5">
                  {FIELD_OPTIONS.map((opt) => (
                    <button
                      key={opt}
                      onClick={() => setFilters((p) => ({ ...p, field: opt }))}
                      className={clsx(
                        "px-2.5 py-1 rounded-full text-xs border transition-colors",
                        filters.field === opt
                          ? "bg-[#4f46e5] text-white border-[#4f46e5]"
                          : "border-[rgba(0,0,0,0.1)] text-[#6b6b80] hover:border-[#4f46e5] hover:text-[#4f46e5]"
                      )}
                    >
                      {opt || "전체 분야"}
                    </button>
                  ))}
                </div>
              </div>

              {/* Author */}
              <div>
                <label className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider block mb-2">작성자</label>
                <div className="space-y-1">
                  <button
                    onClick={() => setFilters((p) => ({ ...p, authorId: "" }))}
                    className={clsx(
                      "w-full text-left px-3 py-2 rounded-lg text-sm transition-colors",
                      !filters.authorId ? "bg-[#ede9fe] text-[#4f46e5]" : "text-[#6b6b80] hover:bg-[#f4f4f8]"
                    )}
                  >
                    전체
                  </button>
                  {MOCK_USERS.filter((u) => u.role !== "admin").map((u) => (
                    <button
                      key={u.id}
                      onClick={() => setFilters((p) => ({ ...p, authorId: u.id }))}
                      className={clsx(
                        "w-full text-left px-3 py-2 rounded-lg text-sm transition-colors flex items-center gap-2",
                        filters.authorId === u.id ? "bg-[#ede9fe] text-[#4f46e5]" : "text-[#111118] hover:bg-[#f4f4f8]"
                      )}
                    >
                      <div className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] text-white font-semibold shrink-0" style={{ backgroundColor: u.avatarColor }}>
                        {u.avatarInitials}
                      </div>
                      {u.name}
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

      {/* Delete confirm dialog */}
      <ConfirmDialog
        open={deleteConfirm}
        onClose={() => setDeleteConfirm(false)}
        onConfirm={confirmDelete}
        title={`${selected.size}건을 삭제하시겠습니까?`}
        description="삭제된 아이디어는 복구할 수 없습니다."
        confirmLabel="삭제"
        variant="danger"
      />
    </div>
  );
}
