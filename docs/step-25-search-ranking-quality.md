# Step 25 — Search ranking quality / RRF evaluation

Goal: measure current Keyword / Semantic / Hybrid ranking quality on a labeled
eval set, sweep RRF K and candidate windows offline, and change production
defaults **only** when metrics justify it.

## Current search structure (production)

### Keyword

* Predicate: `ILIKE` on title, one_line_definition, original_text, background,
  problem, core_concept, expected_effect **or** PostgreSQL FTS (`simple`
  `to_tsvector` / `plainto_tsquery`) on the same concatenated fields.
* Ranking: **`updated_at DESC, id DESC`** (not `ts_rank`).
* Candidate window (hybrid): up to `HYBRID_MAX_RESULT_WINDOW` (300).

### Semantic

* Model: `BAAI/bge-m3`, dimension **1024**.
* Metric: pgvector **cosine distance** (`embedding <=> query`).
* Filters: current `model_name` + `dimension`, ACL via `apply_readable_filter`,
  then list filters (stage/priority/…).
* Tie-break: distance ASC, then `updated_at` / `id`.

### Hybrid

* RRF (1-based ranks):

```text
score(d) = 1/(RRF_K + rank_keyword) + 1/(RRF_K + rank_semantic)
```

* Production `RRF_K = 60`.
* Candidate pool: **300** for both keyword and semantic (full hybrid window).
* Tie-break: higher RRF score → newer `updated_at` → stable `str(uuid)`.
* Pagination: `offset + limit ≤ 300`.
* Empty query: no semantic/hybrid path; falls back to keyword `list_ideas`.
* Semantic unavailable: semantic → 503; hybrid → keyword fallback + banner
  (unchanged Step 21 contract).

### Embedding source text

Canonical fields (priority order): title, one_line_definition, problem,
core_concept, major_features, original_text, background, expected_effect,
target_users, scenarios, challenges, minimum_validation, related_project, tags.

## Evaluation approach

Because shared/dev DB may be empty and hash-based `FakeEmbeddingProvider` is not
semantically meaningful, Step 25 evaluation:

1. Seeds a **dedicated labeled corpus** (~20 ideas, codes `[SR-…]`) into
   `TEST_DATABASE_URL` only.
2. Stores vectors with a **topic-aware eval provider** (centroids + light noise)
   so Semantic/Hybrid ranking is measurable without a live BGE server.
3. Calls production `list_ideas` / `list_semantic_ideas` / `list_hybrid_ideas`
   (same RRF code path; injectable `rrf_k` / `candidate_limit` for experiments).

Artifacts:

* `backend/tests/fixtures/search_ranking_cases.json` — 26 labeled queries
* `backend/tests/search_quality/` — corpus, metrics, topic provider, runner
* `backend/scripts/evaluate_search_ranking.py` — CLI evaluator

```bash
cd backend
python scripts/evaluate_search_ranking.py
python scripts/evaluate_search_ranking.py --sweep-rrf-k
python scripts/evaluate_search_ranking.py --sweep-candidates
```

## Evaluation dataset

| Category | Count | Examples |
|---|---:|---|
| Exact keyword | 8 | 회의록, 재고, 병원, OCR, CRM |
| Paraphrase | 6 | 진료 기록 자동화, 병원 기록 작성 줄이기 |
| Natural language | 6 | 의사가 반복해서 작성하는 문서를 줄이는 방법 |
| Ambiguous | 3 | 환자 기록 검색 vs 환자 기록 자동 작성 |
| Multi-topic | 3 | 병원 업무 자동화, AI 문서 처리 |
| **Total** | **26** | |

Relevance labels: 3 / 2 / 1 / 0 on top ideas per query.

## Baseline (topic-aware eval embeddings, RRF_K=60, candidates=300)

| Mode | Hit@5 | MRR | nDCG@5 | Exact Top1 | p50 ms |
|---|---:|---:|---:|---:|---:|
| Keyword | 0.615 | 0.596 | 0.523 | 0.583 | ~5 |
| Semantic | 0.692 | 0.373 | 0.369 | 0.250 | ~3 |
| Hybrid | **0.808** | **0.700** | **0.630** | **0.667** | ~5 |

### By category (nDCG@5)

| Category | Keyword | Semantic | Hybrid |
|---|---:|---:|---:|
| Exact keyword | 0.932 | 0.512 | **0.959** |
| Paraphrase | 0.363 | 0.412 | **0.525** |
| Natural language | 0.153 | 0.251 | **0.328** |
| Ambiguous | 0.287 | 0.157 | **0.444** |
| Multi-topic | 0.727 | 0.351 | **0.754** |

Hybrid improves every category vs keyword alone, especially exact + ambiguous.
Natural-language absolute scores remain the weakest area (expected without a
real multilingual encoder on this synthetic topic embedding).

## RRF K sweep (hybrid)

| K | Hit@5 | MRR | nDCG@5 | Exact Top1 |
|---:|---:|---:|---:|---:|
| 10 | 0.808 | 0.700 | 0.629 | 0.667 |
| 20 | 0.808 | 0.700 | 0.629 | 0.667 |
| 40 | 0.808 | 0.700 | 0.629 | 0.667 |
| **60** | **0.808** | **0.700** | **0.630** | **0.667** |
| 80 | 0.808 | 0.700 | 0.630 | 0.667 |
| 100 | 0.808 | 0.700 | 0.630 | 0.667 |

On this corpus, K ∈ [10, 100] is effectively flat. No Exact Top1 regression
when moving away from 60, but also **no meaningful gain**.

## Candidate limit sweep (hybrid, K=60)

| Cand | Hit@5 | MRR | nDCG@5 | Exact Top1 | p50 ms |
|---:|---:|---:|---:|---:|---:|
| 50 | 0.808 | 0.700 | 0.630 | 0.667 | ~5 |
| 100 | 0.808 | 0.700 | 0.630 | 0.667 | ~5 |
| 200 | 0.808 | 0.700 | 0.630 | 0.667 | ~5 |
| 300 | 0.808 | 0.700 | 0.630 | 0.667 | ~5 |

Corpus size (~20) ≪ candidate window → no ranking change. Keep production
window **300** for ~1k-idea workspaces.

## Failure patterns (examples)

| Query | Expected | Observed issue | Cause | Change? |
|---|---|---|---|---|
| `OCR` / `CRM` (semantic) | Exact idea top | Semantic miss / overmatch | Short token queries under topic-eval embedding; keyword path still recovers in hybrid | No prod change |
| `진료 기록 자동화` (keyword) | Medical write | Empty keyword hits | No exact ILIKE/FTS token overlap | Hybrid/semantic carry |
| Natural-language medical | Med write top | Lower nDCG | Topic embedding ≠ real BGE; keyword weak on long queries | Future: real-model re-eval |
| Keyword overall | Relevance order | `updated_at` sort | FTS rank unused | Documented; no engine rewrite in Step 25 |

RRF implementation verified: **1-based ranks**, equal keyword/semantic weights,
deterministic tie-break. No off-by-one bug found.

## Final decision

```text
RRF_K: 60 (unchanged)
Keyword candidate: 300 (unchanged)
Semantic candidate: 300 (unchanged)
Weighted RRF: not introduced
Title boost / keyword relevance rewrite: deferred
```

**Why:** Baseline already shows Hybrid > Keyword and Hybrid > Semantic on
Hit@5 / MRR / nDCG@5 / Exact Top1. K and candidate sweeps show no material
improvement. Changing constants without evidence would violate Step 25 rules.

Production code change: only **injectable** `rrf_k` / `candidate_limit` on
`list_hybrid_ideas` / `_rrf_merge` for offline experiments (defaults unchanged).

## Regression

* Representative hybrid tests: exact `회의록`, medical paraphrase, inventory NL
  → expected idea ∈ top 3 (`tests/test_search_ranking_quality.py`).
* ACL: outsider hybrid search returns empty even with `rrf_k` override.
* RRF unit: 1-based ranks + rejects `rrf_k < 1`.
* Search mode contract / semantic unavailable fallback: unchanged.

## Latency

On the eval corpus (local TEST DB, topic provider): keyword/semantic/hybrid
p50 ≈ **3–5 ms**. No candidate expansion latency concern at current size.

## Remaining TODO

* Re-run evaluator against **real BGE-M3** vectors on a read-only sample of
  production-like data when embedding coverage is high.
* Optional later: keyword relevance ordering (`ts_rank` / title boost) if
  real-model eval shows exact matches buried by `updated_at`.
* Cross-encoder / query expansion / explainability UI: out of scope until
  metrics show need.

## Judgment

**SEARCH QUALITY PASS** — baseline established, RRF/candidate sweeps completed,
production defaults retained with evidence, regression tests added.
