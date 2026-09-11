/**
 * Step 28 pure-helper checks (no new test framework).
 * Run: npx --yes tsx src/utils/researchCompare.check.ts
 */
import {
  buildResearchChangeSentences,
  buildResearchChangeSummary,
  compareEvidenceByUrl,
  compareQueryLists,
  normalizeResearchSummary,
  type EvidenceLike,
} from "./researchCompare.ts";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

function ev(url: string, extras: Partial<EvidenceLike> = {}): EvidenceLike {
  return {
    title: extras.title ?? url,
    url,
    snippet: extras.snippet ?? "snip",
    source_name: extras.source_name ?? "src",
  };
}

// Case 1: added/removed/unchanged
{
  const diff = compareEvidenceByUrl(
    [ev("https://a.example/"), ev("https://b.example/"), ev("https://c.example/")],
    [ev("https://b.example/"), ev("https://c.example/"), ev("https://d.example/")],
  );
  const summary = buildResearchChangeSummary({
    evidenceDiff: diff,
    queryDiff: compareQueryLists([], []),
    leftSummary: "same",
    rightSummary: "same",
  });
  assert(summary.evidence.added === 1, "added=1");
  assert(summary.evidence.removed === 1, "removed=1");
  assert(summary.evidence.updated === 0, "updated=0");
  assert(summary.evidence.unchanged === 2, "unchanged=2");
}

// Case 2: metadata updated
{
  const diff = compareEvidenceByUrl(
    [ev("https://same.example/", { snippet: "old" })],
    [ev("https://same.example/", { snippet: "new" })],
  );
  const summary = buildResearchChangeSummary({
    evidenceDiff: diff,
    queryDiff: compareQueryLists(["a"], ["a"]),
    leftSummary: "x",
    rightSummary: "x",
  });
  assert(summary.evidence.updated === 1, "updated=1");
  assert(summary.evidence.unchanged === 0, "unchanged=0 after split");
  assert(summary.evidence.added === 0 && summary.evidence.removed === 0, "no add/remove");
}

// Case 3: query diff
{
  const q = compareQueryLists(["a", "b"], ["b", "c"]);
  const summary = buildResearchChangeSummary({
    evidenceDiff: compareEvidenceByUrl([], []),
    queryDiff: q,
    leftSummary: "",
    rightSummary: "",
  });
  assert(summary.queries.added === 1, "q added");
  assert(summary.queries.removed === 1, "q removed");
  assert(summary.queries.unchanged === 1, "q unchanged");
}

// Case 4: no-change
{
  const left = [ev("https://x.example/")];
  const right = [ev("https://x.example/")];
  const summary = buildResearchChangeSummary({
    evidenceDiff: compareEvidenceByUrl(left, right),
    queryDiff: compareQueryLists(["q1"], ["q1"]),
    leftSummary: "조사 결과입니다.",
    rightSummary: "조사 결과입니다.",
  });
  assert(summary.noStructuralChanges === true, "noChanges");
  assert(summary.summaryChanged === false, "summary unchanged");
  const sentences = buildResearchChangeSentences(summary);
  assert(
    sentences[0]?.includes("변화가 없습니다"),
    `no-change narrative, got: ${sentences.join(" / ")}`,
  );
}

// Case 5: summary-only
{
  const left = [ev("https://x.example/")];
  const right = [ev("https://x.example/")];
  const summary = buildResearchChangeSummary({
    evidenceDiff: compareEvidenceByUrl(left, right),
    queryDiff: compareQueryLists(["q1"], ["q1"]),
    leftSummary: "이전 요약",
    rightSummary: "새 요약",
  });
  assert(summary.summaryChanged === true, "summaryChanged");
  assert(summary.noStructuralChanges === false, "not noChanges");
  const sentences = buildResearchChangeSentences(summary);
  assert(
    sentences.some((s) => s.includes("조사 요약 내용이 변경")),
    `summary-only narrative, got: ${sentences.join(" / ")}`,
  );
  assert(
    sentences.some((s) => s.includes("근거와 검색어는 동일")),
    `summary-only phrasing, got: ${sentences.join(" / ")}`,
  );
}

// Case 6: whitespace-only summary normalize
{
  const a = normalizeResearchSummary("조사 결과\n입니다.");
  const b = normalizeResearchSummary(" 조사 결과\r\n입니다. ");
  assert(a === b, `whitespace normalize equal: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`);
  const summary = buildResearchChangeSummary({
    evidenceDiff: compareEvidenceByUrl([], []),
    queryDiff: compareQueryLists([], []),
    leftSummary: "조사 결과\n입니다.",
    rightSummary: " 조사 결과\r\n입니다. ",
  });
  assert(summary.summaryChanged === false, "whitespace-only → not changed");
  assert(summary.noStructuralChanges === true, "whitespace-only → noChanges");
}

console.log("researchCompare.check.ts: all assertions passed");
