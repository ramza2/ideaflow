import { useState, useMemo } from "react";
import { clsx } from "clsx";
import {
  Search,
  X,
  ChevronDown,
  ChevronRight,
  Lightbulb,
  Sparkles,
  Users,
  ClipboardCheck,
  AlertCircle,
  Info,
  MessageCircle,
  Flag,
  BookOpen,
} from "lucide-react";
import { Button } from "../../components/common/Button";
import { SourceBadge } from "../../components/common/Badge";
import { toast } from "../../components/common/Toast";
import {
  HELP_CATEGORIES,
  HELP_ARTICLES,
  FAQ_ITEMS,
  type HelpArticle as HelpArticleData,
  type FAQItem,
} from "../../mocks/help";
import type { SourceBadgeType } from "../../types";

// ─── HelpSearch ────────────────────────────────────────────────

function HelpSearch({
  query,
  onChange,
}: {
  query: string;
  onChange: (q: string) => void;
}) {
  return (
    <div className="relative mt-5">
      <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#9ca3af]" />
      <input
        type="text"
        placeholder="무엇을 도와드릴까요?"
        value={query}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-12 pl-12 pr-10 rounded-xl border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] text-sm text-[#111118] placeholder:text-[#9ca3af] focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/15 focus:border-[#4f46e5] focus:bg-white transition-all"
      />
      {query && (
        <button
          onClick={() => onChange("")}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-[#9ca3af] hover:text-[#6b6b80]"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}

// ─── HelpCategoryNav ────────────────────────────────────────────

function HelpCategoryNav({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <nav className="py-4 space-y-4">
      {HELP_CATEGORIES.map((category) => {
        const isFaq = category.id === "faq";
        const articles = HELP_ARTICLES.filter((a) => a.categoryId === category.id);

        return (
          <div key={category.id}>
            <p className="px-3 mb-1 text-[10px] font-semibold text-[#9ca3af] uppercase tracking-wider">
              {category.label}
            </p>
            {isFaq ? (
              <button
                onClick={() => onSelect("faq")}
                className={clsx(
                  "w-full text-left px-3 py-1.5 rounded-lg text-sm transition-colors",
                  selectedId === "faq"
                    ? "bg-[#ede9fe] text-[#4f46e5] font-medium"
                    : "text-[#6b6b80] hover:bg-[#f4f4f8] hover:text-[#111118]"
                )}
              >
                자주 묻는 질문
              </button>
            ) : (
              <div className="space-y-0.5">
                {articles.map((article) => (
                  <button
                    key={article.id}
                    onClick={() => onSelect(article.id)}
                    className={clsx(
                      "w-full text-left px-3 py-1.5 rounded-lg text-sm transition-colors",
                      selectedId === article.id
                        ? "bg-[#ede9fe] text-[#4f46e5] font-medium"
                        : "text-[#6b6b80] hover:bg-[#f4f4f8] hover:text-[#111118]"
                    )}
                  >
                    {article.title}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}

// ─── QuickHelpCards ─────────────────────────────────────────────

const QUICK_CARDS = [
  {
    id: "first-idea",
    icon: Lightbulb,
    title: "아이디어 등록하기",
    desc: "첫 아이디어를 직접 또는 AI를 통해 등록합니다.",
  },
  {
    id: "ai-draft-review",
    icon: Sparkles,
    title: "AI 초안 검토하기",
    desc: "AI가 정리한 초안을 확인하고 수정합니다.",
  },
  {
    id: "invite-members",
    icon: Users,
    title: "팀원과 공유하기",
    desc: "구성원을 초대하여 아이디어를 함께 관리합니다.",
  },
  {
    id: "reviews",
    icon: ClipboardCheck,
    title: "검토할 아이디어 확인하기",
    desc: "검토함에서 나의 할 일을 처리합니다.",
  },
];

function QuickHelpCards({ onSelect }: { onSelect: (id: string) => void }) {
  return (
    <div>
      <h2 className="text-base font-semibold text-[#111118] mb-4">빠른 도움말</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {QUICK_CARDS.map((card) => (
          <button
            key={card.id}
            onClick={() => onSelect(card.id)}
            className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4 text-left hover:border-[rgba(79,70,229,0.3)] hover:shadow-sm transition-all group"
          >
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-[#ede9fe] flex items-center justify-center shrink-0">
                <card.icon className="w-4 h-4 text-[#4f46e5]" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-[#111118] mb-0.5">{card.title}</p>
                <p className="text-xs text-[#6b6b80] leading-relaxed">{card.desc}</p>
              </div>
              <ChevronRight className="w-4 h-4 text-[#d1d5db] group-hover:text-[#4f46e5] transition-colors mt-0.5 shrink-0" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── SourceLegend ───────────────────────────────────────────────

const SOURCE_LEGEND: Array<{ type: SourceBadgeType; description: string }> = [
  { type: "user_input", description: "사용자가 직접 입력한 내용" },
  { type: "llm_structured", description: "AI가 입력 내용을 기반으로 정리" },
  { type: "llm_inferred", description: "AI가 맥락에서 추론한 내용" },
  { type: "web_evidence", description: "웹 검색 결과에서 가져온 내용" },
  { type: "user_edited", description: "사용자가 직접 수정한 내용" },
];

function SourceLegend() {
  return (
    <div className="bg-[#f8f8fb] rounded-xl border border-[rgba(0,0,0,0.06)] p-4">
      <p className="text-[10px] font-semibold text-[#9ca3af] uppercase tracking-wider mb-3">
        AI 초안 정보 출처 표시
      </p>
      <div className="space-y-2.5">
        {SOURCE_LEGEND.map(({ type, description }) => (
          <div key={type} className="flex items-center gap-3">
            <SourceBadge type={type} />
            <span className="text-sm text-[#6b6b80]">{description}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── HelpArticle ────────────────────────────────────────────────

function HelpArticle({ article }: { article: HelpArticleData }) {
  return (
    <div>
      <div className="mb-5 pb-5 border-b border-[rgba(0,0,0,0.06)]">
        <h2 className="text-lg font-bold text-[#111118] mb-1">{article.title}</h2>
        <p className="text-sm text-[#6b6b80]">{article.summary}</p>
      </div>
      <div className="space-y-4">
        {article.blocks.map((block, i) => {
          if (block.type === "paragraph") {
            return (
              <p key={i} className="text-sm text-[#111118] leading-relaxed">
                {block.text}
              </p>
            );
          }
          if (block.type === "heading") {
            return (
              <h3 key={i} className="text-sm font-semibold text-[#111118] pt-1">
                {block.text}
              </h3>
            );
          }
          if (block.type === "tip") {
            return (
              <div
                key={i}
                className="flex gap-3 bg-[#f0f9ff] border border-[#bae6fd] rounded-xl p-4"
              >
                <Info className="w-4 h-4 text-[#0ea5e9] shrink-0 mt-0.5" />
                <p className="text-sm text-[#0c4a6e] leading-relaxed">{block.text}</p>
              </div>
            );
          }
          if (block.type === "warning") {
            return (
              <div
                key={i}
                className="flex gap-3 bg-[#fffbeb] border border-[#fde68a] rounded-xl p-4"
              >
                <AlertCircle className="w-4 h-4 text-[#d97706] shrink-0 mt-0.5" />
                <p className="text-sm text-[#92400e] leading-relaxed">{block.text}</p>
              </div>
            );
          }
          if (block.type === "steps") {
            return (
              <ol key={i} className="space-y-2.5">
                {block.items?.map((item, j) => (
                  <li key={j} className="flex gap-3 text-sm text-[#111118]">
                    <span className="w-5 h-5 rounded-full bg-[#ede9fe] text-[#4f46e5] text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                      {j + 1}
                    </span>
                    <span className="leading-relaxed">{item}</span>
                  </li>
                ))}
              </ol>
            );
          }
          if (block.type === "source-legend") {
            return <SourceLegend key={i} />;
          }
          return null;
        })}
      </div>
    </div>
  );
}

// ─── FAQSection ─────────────────────────────────────────────────

function FAQSection({
  items,
  expandedIds,
  onToggle,
}: {
  items: FAQItem[];
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  return (
    <div>
      <h2 className="text-base font-semibold text-[#111118] mb-4">자주 묻는 질문</h2>
      <div className="space-y-2">
        {items.map((item) => {
          const isOpen = expandedIds.has(item.id);
          return (
            <div
              key={item.id}
              className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] overflow-hidden"
            >
              <button
                onClick={() => onToggle(item.id)}
                className="w-full flex items-center justify-between px-4 py-3.5 text-left hover:bg-[#f8f8fb] transition-colors"
              >
                <span className="text-sm font-medium text-[#111118] pr-4">{item.question}</span>
                {isOpen ? (
                  <ChevronDown className="w-4 h-4 text-[#4f46e5] shrink-0" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-[#9ca3af] shrink-0" />
                )}
              </button>
              {isOpen && (
                <div className="px-4 pb-4 pt-1 border-t border-[rgba(0,0,0,0.04)]">
                  <p className="text-sm text-[#6b6b80] leading-relaxed">{item.answer}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── SystemInfoCard ─────────────────────────────────────────────

function SystemInfoCard() {
  return (
    <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4">
      <h3 className="text-sm font-semibold text-[#111118] mb-3">시스템 정보</h3>
      <div className="space-y-2.5">
        {[
          { label: "IdeaFlow 버전", value: "0.1.0", mono: true },
          { label: "LLM", value: "Qwen3-14B", mono: true },
        ].map(({ label, value, mono }) => (
          <div key={label} className="flex items-center justify-between">
            <span className="text-xs text-[#6b6b80]">{label}</span>
            <span className={clsx("text-xs text-[#111118]", mono && "font-mono")}>{value}</span>
          </div>
        ))}
        {[
          { label: "LLM 상태", status: "정상", ok: true },
          { label: "웹 검색 상태", status: "정상", ok: true },
        ].map(({ label, status, ok }) => (
          <div key={label} className="flex items-center justify-between">
            <span className="text-xs text-[#6b6b80]">{label}</span>
            <div className="flex items-center gap-1.5">
              <div
                className={clsx(
                  "w-1.5 h-1.5 rounded-full",
                  ok ? "bg-[#16a34a]" : "bg-[#dc2626]"
                )}
              />
              <span
                className={clsx(
                  "text-xs font-medium",
                  ok ? "text-[#16a34a]" : "text-[#dc2626]"
                )}
              >
                {status}
              </span>
            </div>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-[#9ca3af] mt-3 pt-3 border-t border-[rgba(0,0,0,0.04)] leading-relaxed">
        시스템 상태 자세히 보기는 시스템 관리자만 사용할 수 있습니다.
      </p>
    </div>
  );
}

// ─── SupportCard ────────────────────────────────────────────────

function SupportCard() {
  return (
    <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4">
      <h3 className="text-sm font-semibold text-[#111118] mb-1">원하는 답을 찾지 못하셨나요?</h3>
      <p className="text-xs text-[#6b6b80] mb-4 leading-relaxed">
        시스템 관리자에게 문의하거나 문제 내용을 전달해 주세요.
      </p>
      <div className="flex flex-col gap-2">
        <Button
          variant="secondary"
          size="sm"
          icon={<MessageCircle className="w-3.5 h-3.5" />}
          onClick={() =>
            toast.info("관리자 문의", "담당 관리자에게 문의 요청이 전달됩니다.")
          }
        >
          관리자에게 문의
        </Button>
        <Button
          variant="ghost"
          size="sm"
          icon={<Flag className="w-3.5 h-3.5" />}
          onClick={() =>
            toast.info("문제 신고", "접수가 완료되면 관리자가 확인합니다.")
          }
        >
          문제 신고
        </Button>
      </div>
    </div>
  );
}

// ─── Search result type ─────────────────────────────────────────

interface SearchResult {
  type: "article" | "faq";
  id: string;
  title: string;
  summary: string;
  categoryLabel: string;
}

// ─── HelpPage (main) ────────────────────────────────────────────

export function HelpPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedFaqIds, setExpandedFaqIds] = useState<Set<string>>(new Set());

  const isSearching = searchQuery.trim().length > 0;

  const searchResults = useMemo<SearchResult[]>(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return [];
    const results: SearchResult[] = [];

    for (const article of HELP_ARTICLES) {
      const hit =
        article.title.toLowerCase().includes(q) ||
        article.summary.toLowerCase().includes(q) ||
        article.blocks.some(
          (b) =>
            b.text?.toLowerCase().includes(q) ||
            b.items?.some((item) => item.toLowerCase().includes(q))
        );
      if (hit) {
        const cat = HELP_CATEGORIES.find((c) => c.id === article.categoryId);
        results.push({
          type: "article",
          id: article.id,
          title: article.title,
          summary: article.summary,
          categoryLabel: cat?.label ?? "",
        });
      }
    }

    for (const faq of FAQ_ITEMS) {
      if (
        faq.question.toLowerCase().includes(q) ||
        faq.answer.toLowerCase().includes(q)
      ) {
        results.push({
          type: "faq",
          id: faq.id,
          title: faq.question,
          summary: faq.answer,
          categoryLabel: "FAQ",
        });
      }
    }

    return results;
  }, [searchQuery]);

  function toggleFaq(id: string) {
    setExpandedFaqIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleSelect(id: string) {
    setSelectedId(id === "faq" ? "faq" : id);
    setSearchQuery("");
    // Expand all FAQs when navigating from search to faq
    if (id.startsWith("faq-")) {
      setExpandedFaqIds((prev) => new Set([...prev, id]));
      setSelectedId("faq");
    }
  }

  const selectedArticle =
    selectedId && selectedId !== "faq"
      ? HELP_ARTICLES.find((a) => a.id === selectedId) ?? null
      : null;

  const mobileSelectValue = isSearching ? "" : (selectedId ?? "");

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="px-4 sm:px-8 pt-6 pb-5 bg-white border-b border-[rgba(0,0,0,0.06)]">
        <div className="flex items-center gap-2 mb-0.5">
          <BookOpen className="w-5 h-5 text-[#4f46e5]" />
          <h1 className="text-xl font-bold text-[#111118]">도움말</h1>
        </div>
        <p className="text-sm text-[#6b6b80]">IdeaFlow 사용법과 자주 묻는 질문을 확인하세요.</p>
        <HelpSearch query={searchQuery} onChange={setSearchQuery} />
      </div>

      {/* Mobile: category select */}
      <div className="md:hidden px-4 py-3 bg-white border-b border-[rgba(0,0,0,0.05)]">
        <select
          value={mobileSelectValue}
          onChange={(e) => handleSelect(e.target.value)}
          className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f4f4f8] px-3 text-sm text-[#111118] focus:outline-none focus:border-[#4f46e5]"
        >
          <option value="">카테고리 선택...</option>
          {HELP_CATEGORIES.map((cat) => (
            <optgroup key={cat.id} label={cat.label}>
              {cat.id === "faq" ? (
                <option value="faq">자주 묻는 질문</option>
              ) : (
                HELP_ARTICLES.filter((a) => a.categoryId === cat.id).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.title}
                  </option>
                ))
              )}
            </optgroup>
          ))}
        </select>
      </div>

      {/* Main 2-column layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left nav — desktop only */}
        <aside className="hidden md:flex flex-col w-[240px] shrink-0 border-r border-[rgba(0,0,0,0.06)] bg-[#fafafa] overflow-y-auto">
          <div className="px-3">
            <HelpCategoryNav
              selectedId={isSearching ? null : selectedId}
              onSelect={handleSelect}
            />
          </div>
        </aside>

        {/* Right content */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-4 sm:px-8 py-6 max-w-[860px]">
            {isSearching ? (
              /* Search results */
              <div>
                <p className="text-sm text-[#6b6b80] mb-4">
                  <span className="font-medium text-[#111118]">
                    &ldquo;{searchQuery}&rdquo;
                  </span>{" "}
                  검색 결과 {searchResults.length}건
                </p>
                {searchResults.length === 0 ? (
                  <div className="flex flex-col items-center py-16 text-center">
                    <Search className="w-10 h-10 text-[#e5e5ef] mb-3" />
                    <p className="text-sm font-medium text-[#111118] mb-1">
                      검색 결과가 없습니다
                    </p>
                    <p className="text-sm text-[#9ca3af]">
                      다른 검색어를 시도하거나 카테고리에서 직접 찾아보세요.
                    </p>
                    <button
                      onClick={() => setSearchQuery("")}
                      className="mt-4 text-sm text-[#4f46e5] hover:underline"
                    >
                      검색 초기화
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {searchResults.map((result) => (
                      <button
                        key={`${result.type}-${result.id}`}
                        onClick={() => handleSelect(result.id)}
                        className="w-full bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4 text-left hover:border-[rgba(79,70,229,0.3)] hover:shadow-sm transition-all group"
                      >
                        <div className="flex items-start gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1.5">
                              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-[#f0f0f5] text-[#6b6b80]">
                                {result.categoryLabel}
                              </span>
                            </div>
                            <p className="text-sm font-semibold text-[#111118] mb-0.5">
                              {result.title}
                            </p>
                            <p className="text-xs text-[#6b6b80] line-clamp-2">
                              {result.summary}
                            </p>
                          </div>
                          <ChevronRight className="w-4 h-4 text-[#d1d5db] group-hover:text-[#4f46e5] mt-0.5 shrink-0 transition-colors" />
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : selectedId === null ? (
              /* Home state */
              <QuickHelpCards onSelect={handleSelect} />
            ) : selectedId === "faq" ? (
              /* FAQ */
              <FAQSection
                items={FAQ_ITEMS}
                expandedIds={expandedFaqIds}
                onToggle={toggleFaq}
              />
            ) : selectedArticle ? (
              /* Article */
              <HelpArticle article={selectedArticle} />
            ) : null}
          </div>

          {/* Bottom: SystemInfoCard + SupportCard */}
          <div className="px-4 sm:px-8 pb-8 max-w-[860px]">
            <div className="border-t border-[rgba(0,0,0,0.06)] pt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <SystemInfoCard />
              <SupportCard />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
