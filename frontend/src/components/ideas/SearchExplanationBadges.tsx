import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { SearchExplanation } from "../../types/api";

const FIELD_LABELS: Record<string, string> = {
  title: "제목",
  one_line_definition: "한 줄 정의",
  original_text: "원문",
  background: "배경",
  problem: "문제",
  core_concept: "핵심 개념",
  expected_effect: "기대 효과",
};

function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

function modeBadge(mode: SearchExplanation["mode"]): string {
  if (mode === "keyword") return "키워드 일치";
  if (mode === "semantic") return "의미 유사";
  return "키워드+의미";
}

function hybridSummary(exp: SearchExplanation): string {
  const kw = exp.hybrid?.keyword_rank ?? null;
  const sem = exp.hybrid?.semantic_rank ?? null;
  if (kw != null && sem != null) {
    if (kw <= 5 && sem <= 5) return "키워드·의미 검색 모두에서 높은 관련도";
    return "키워드 및 의미 기준으로 관련";
  }
  if (kw == null && sem != null) return "검색어는 다르지만 의미가 유사함";
  if (kw != null && sem == null) return "검색어가 직접 포함됨";
  return "관련 결과";
}

function semanticSummary(): string {
  // MVP: avoid hard-coded similarity buckets as "accuracy".
  return "의미 검색 상위 결과";
}

type Props = {
  explanation?: SearchExplanation | null;
};

export function SearchExplanationBadges({ explanation }: Props) {
  const [open, setOpen] = useState(false);
  if (!explanation) return null;

  const matched = explanation.keyword?.matched_fields ?? [];
  const details: string[] = [];

  if (explanation.mode === "keyword") {
    if (matched.length > 0) {
      details.push(`${matched.map(fieldLabel).join(", ")}에서 검색어 일치`);
    } else if (explanation.keyword?.fts_match) {
      details.push("본문의 검색어 관련 표현과 일치");
    }
    if (explanation.keyword?.rank != null) {
      details.push(`키워드 검색 ${explanation.keyword.rank}위`);
    }
  }

  if (explanation.mode === "semantic") {
    details.push(semanticSummary());
    if (explanation.semantic?.rank != null) {
      details.push(`의미 검색 ${explanation.semantic.rank}위`);
    }
    if (explanation.semantic?.similarity != null) {
      details.push(`의미 유사도 ${explanation.semantic.similarity.toFixed(2)}`);
    }
  }

  if (explanation.mode === "hybrid") {
    details.push(hybridSummary(explanation));
    if (matched.length > 0) {
      details.push(`${matched.map(fieldLabel).join(", ")}에서 검색어 일치`);
    } else if (explanation.keyword?.fts_match) {
      details.push("본문의 검색어 관련 표현과 일치");
    }
    const kw = explanation.hybrid?.keyword_rank;
    const sem = explanation.hybrid?.semantic_rank;
    if (kw != null) details.push(`키워드 검색 ${kw}위`);
    if (sem != null) details.push(`의미 검색 ${sem}위`);
  }

  return (
    <div className="mt-1.5" onClick={(e) => e.stopPropagation()}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-[#eef2ff] text-[10px] font-medium text-[#4338ca]">
          {modeBadge(explanation.mode)}
        </span>
        {explanation.mode === "hybrid" &&
        explanation.hybrid?.keyword_rank != null &&
        explanation.hybrid?.semantic_rank != null ? (
          <span className="text-[10px] text-[#6b6b80]">
            키워드 {explanation.hybrid.keyword_rank}위 · 의미{" "}
            {explanation.hybrid.semantic_rank}위
          </span>
        ) : null}
        {matched.slice(0, 2).map((field) => (
          <span
            key={field}
            className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-[#f0fdf4] text-[10px] text-[#166534]"
          >
            {fieldLabel(field)} 일치
          </span>
        ))}
      </div>
      <button
        type="button"
        className="mt-1 inline-flex items-center gap-0.5 text-[11px] text-[#6b6b80] hover:text-[#4338ca]"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        왜 이 결과인가요?
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && details.length > 0 ? (
        <ul className="mt-1 space-y-0.5 pl-1">
          {details.map((line) => (
            <li key={line} className="text-[11px] text-[#6b6b80] leading-snug">
              • {line}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
