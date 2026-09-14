import type { AiDraft } from "../types/api";

const MAX_QUERY_LENGTH = 200;

function compactText(value: string | null | undefined, max = 80): string {
  if (!value) return "";
  return value.replace(/\s+/g, " ").trim().slice(0, max).trim();
}

/**
 * Deterministic web-research query suggestions when the LLM left research_topics empty.
 * Does not call LLM/search APIs — used only when opening the approval panel.
 */
export function buildFallbackResearchQueries(
  source: Pick<
    AiDraft,
    "title" | "one_line_definition" | "core_concept" | "problem"
  > | null | undefined,
): string[] {
  if (!source) return [];

  const title = compactText(source.title, 80);
  const oneLine = compactText(source.one_line_definition, 60);
  const core = compactText(source.core_concept, 60);
  const problem = compactText(source.problem, 60);

  const candidates: string[] = [];
  if (title) candidates.push(title);

  if (title && oneLine) {
    candidates.push(compactText(`${title} ${oneLine}`, MAX_QUERY_LENGTH));
  } else if (oneLine) {
    candidates.push(oneLine);
  }

  const thirdSeed = core || problem;
  if (title && thirdSeed) {
    candidates.push(compactText(`${title} ${thirdSeed}`, MAX_QUERY_LENGTH));
  } else if (thirdSeed && !title) {
    candidates.push(thirdSeed);
  }

  const seen = new Set<string>();
  const unique: string[] = [];
  for (const q of candidates) {
    const cleaned = q.trim().slice(0, MAX_QUERY_LENGTH).trim();
    if (!cleaned) continue;
    const key = cleaned.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(cleaned);
    if (unique.length >= 3) break;
  }
  return unique;
}
