# Step 27 — Search explainability

Goal: show **why** each search hit matched, without changing ranking.

## Scope

| Changed | Unchanged |
|---|---|
| Additive `search_explanation` on list items when `q` is set | Keyword order (`updated_at DESC, id DESC`) |
| Keyword matched fields / FTS flag | Semantic cosine order |
| Semantic distance → similarity reuse | `RRF_K = 60`, candidate window 300 |
| Hybrid keyword/semantic ranks + RRF score | ACL, filters, pagination totals |
| Compact UI badges + collapsed details | Embedding model / query expansion |

Out of scope: LLM explanations, cross-encoders, score tuning, highlight engines,
analytics/click tracking.

## API contract (additive)

`GET /api/v1/workspaces/{id}/ideas` still returns:

```json
{ "items": [...], "total": N, "limit": L, "offset": O }
```

When `q` is non-empty, each item may include:

```json
"search_explanation": {
  "mode": "keyword" | "semantic" | "hybrid",
  "keyword": {
    "matched_fields": ["title", "problem"],
    "fts_match": false,
    "rank": 2
  },
  "semantic": {
    "distance": 0.13,
    "similarity": 0.87,
    "rank": 1
  },
  "hybrid": {
    "keyword_rank": 3,
    "semantic_rank": 1,
    "rrf_score": 0.032
  }
}
```

Rules:

* No `q` / filter-only list / idea detail → `search_explanation` is `null`/absent.
* Only **final page items** get explanations (no candidate leak).
* Hybrid ranks are **candidate-window ranks**, not page-local indices.
* One-sided hybrid hits allow `keyword_rank` or `semantic_rank` to be `null`.

## Keyword explain

Fields mirror `_search_predicate` (ILIKE + FTS `simple`):

```text
title, one_line_definition, original_text, background,
problem, core_concept, expected_effect
```

* `matched_fields`: case-insensitive substring checks equivalent to `ILIKE %q%`
  on the final page rows only (no extra DB round-trips).
* If the idea is a keyword hit but no ILIKE field matches → `fts_match: true`
  (FTS-only; UI says “본문의 검색어 관련 표현과 일치”).
* Tags are **not** explained unless/until keyword search includes them.

## Semantic explain

* Reuses SQL `cosine_distance` already selected with the ranking query.
* `similarity ≈ 1 - distance` for normalized vectors.
* **Similarity ≠ probability / accuracy.** UI prefers “의미 검색 상위 결과”
  plus optional raw similarity; no “정확도 N%” wording.

## Hybrid explain

Built from existing keyword/semantic id lists + `_rrf_merge_with_scores`:

```text
score(d) = Σ 1 / (RRF_K + rank_list(d)), RRF_K = 60
```

Frontend copy (compact):

| Situation | Wording |
|---|---|
| Both top-ish | 키워드·의미 검색 모두에서 높은 관련도 |
| Semantic only | 검색어는 다르지만 의미가 유사함 |
| Keyword only | 검색어가 직접 포함됨 |
| Both, lower | 키워드 및 의미 기준으로 관련 |

RRF contribution terms are not shown in the default UI.

## ACL & performance

* Readable filter + filters apply before ranking; explanations attach after.
* Private / unreadable ideas never appear with ranks/scores/matched fields.
* No per-result N+1 queries; match checks run in-process on the page slice.

## UI

* Badges: `[키워드 일치]` / `[의미 유사]` / `[키워드+의미]` (+ field chips).
* Details collapsed under “왜 이 결과인가요?”.
* Empty `q` → no badges.
* Semantic-unavailable hybrid fallback banner (Step 21) unchanged.

## Ranking regression (Step 25 topic harness)

Before (Step 25 baseline) and after explainability — identical:

| Mode | Hit@5 | MRR | nDCG@5 | Exact Top1 |
|---|---:|---:|---:|---:|
| Keyword | 0.615 | 0.596 | 0.523 | 0.583 |
| Semantic (topic) | 0.692 | 0.373 | 0.369 | 0.250 |
| Hybrid (topic) | 0.808 | 0.700 | 0.630 | 0.667 |

Latency (topic harness p50, explain on): Keyword ~4.7 ms, Semantic ~3.2 ms,
Hybrid ~4.8 ms — no meaningful regression vs Step 25 (~3–6 ms).

`_rrf_merge_with_scores` preserves the previous `_rrf_merge` order (unit-tested).

## Judgment

**SEARCH EXPLAINABILITY PASS**

* Keyword field matches visible; FTS-only distinguished
* Semantic meaning visible without fake “accuracy %”
* Hybrid keyword/semantic rank relation visible
* Ranking unchanged; ACL leak none; page-local ranks avoided; no N+1
