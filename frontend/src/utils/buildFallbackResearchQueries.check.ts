/**
 * Pure-helper checks for web-research query fallback.
 * Run: npx --yes tsx src/utils/buildFallbackResearchQueries.check.ts
 */
import { buildFallbackResearchQueries } from "./buildFallbackResearchQueries.ts";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

{
  const qs = buildFallbackResearchQueries({
    title: "병원 청소 품질 AI 판정",
    one_line_definition: "청소 전후 사진을 비교하여 품질을 판정",
    core_concept: "Vision AI 기반 Before/After 비교",
    problem: null,
  });
  assert(qs.length >= 1 && qs.length <= 3, "expected 1..3 queries");
  assert(qs[0] === "병원 청소 품질 AI 판정", "title should be first");
  assert(qs.every((q) => q.trim().length > 0), "no empty queries");
  assert(qs.every((q) => q.length <= 200), "max 200 chars");
}

{
  const qs = buildFallbackResearchQueries({ title: "단독 제목" });
  assert(qs.length === 1, "title-only yields one query");
  assert(qs[0] === "단독 제목", "title-only value");
}

{
  const qs = buildFallbackResearchQueries({
    title: null,
    one_line_definition: null,
    core_concept: null,
    problem: null,
  });
  assert(qs.length === 0, "empty source yields no queries");
}

{
  const qs = buildFallbackResearchQueries({
    title: "동일",
    one_line_definition: "동일",
    core_concept: "동일",
  });
  assert(new Set(qs.map((q) => q.toLowerCase())).size === qs.length, "deduped");
}

console.log("buildFallbackResearchQueries.check.ts: ok");
