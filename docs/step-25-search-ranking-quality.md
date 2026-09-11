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

Shared/dev DB may be empty and hash-based `FakeEmbeddingProvider` is not
semantically meaningful, so Step 25 uses a dedicated labeled corpus on
`TEST_DATABASE_URL` only (Step 24 safety guards unchanged).

The evaluator supports two **embedding modes**. Corpus vectors and query
vectors always use the **same** provider within a run.

| Mode | Provider | Purpose |
|---|---|---|
| `topic` (default) | `TopicAwareEvalEmbeddingProvider` | Deterministic CI / RRF mechanics regression |
| `configured` | production `get_embedding_provider` (e.g. `openai_compatible` + `BAAI/bge-m3`) | Real ranking quality / RRF decision evidence |

Artifacts:

* `backend/tests/fixtures/search_ranking_cases.json` — 26 labeled queries
* `backend/tests/search_quality/` — corpus, metrics, topic provider, runner
* `backend/scripts/evaluate_search_ranking.py` — CLI evaluator

```bash
cd backend
# Deterministic harness (CI / offline)
python scripts/evaluate_search_ranking.py --embedding-mode topic
python scripts/evaluate_search_ranking.py --embedding-mode topic --sweep-rrf-k

# Real BGE-M3 (requires OpenAI-compatible endpoint)
export EMBEDDING_PROVIDER=openai_compatible
export EMBEDDING_API_URL=http://127.0.0.1:8090
export EMBEDDING_MODEL_NAME=BAAI/bge-m3
export EMBEDDING_DIMENSION=1024
python scripts/evaluate_search_ranking.py --embedding-mode configured
python scripts/evaluate_search_ranking.py --embedding-mode configured --sweep-rrf-k
```

Automated pytest (`tests/test_search_ranking_quality.py`) stays on the **topic**
provider so CI never depends on an external embedding endpoint.

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

## Synthetic regression baseline (`--embedding-mode topic`)

**Not** production ranking quality. Used for deterministic harness / RRF
mechanics checks and CI. Do not treat these numbers as BGE-M3 quality.

| Mode | Hit@5 | MRR | nDCG@5 | Exact Top1 | p50 ms |
|---|---:|---:|---:|---:|---:|
| Keyword | 0.615 | 0.596 | 0.523 | 0.583 | ~6 |
| Semantic (topic) | 0.692 | 0.373 | 0.369 | 0.250 | ~3 |
| Hybrid (topic) | 0.808 | 0.700 | 0.630 | 0.667 | ~5 |

Topic-mode RRF K ∈ {10…100} was effectively flat (same as earlier Step 25 note).

## Real BGE-M3 evaluation (`--embedding-mode configured`)

Endpoint: local OpenAI-compatible server (`scripts/dev_embedding_server.py`)
loading **`BAAI/bge-m3`** (1024-d). Corpus + queries both embedded with
production `get_embedding_provider` / `openai_compatible`.

### Baseline (RRF_K=60, candidates=300)

| Mode | Hit@5 | MRR | nDCG@5 | Exact Top1 |
|---|---:|---:|---:|---:|
| Keyword | 0.615 | 0.596 | 0.523 | 0.583 |
| Semantic (BGE-M3) | **1.000** | **0.981** | **0.979** | **0.958** |
| Hybrid (BGE-M3) | **1.000** | **0.981** | **0.971** | **0.958** |

### By category (nDCG@5, BGE-M3)

| Category | Keyword | Semantic | Hybrid |
|---|---:|---:|---:|
| Exact keyword | 0.932 | 0.995 | 0.986 |
| Paraphrase | 0.363 | 0.966 | 0.966 |
| Natural language | 0.153 | 0.992 | 0.992 |
| Ambiguous | 0.287 | 0.983 | 0.983 |
| Multi-topic | 0.727 | 0.936 | 0.883 |

With real BGE-M3, Semantic already saturates most queries; Hybrid preserves
near-ceiling quality while still covering keyword-only exact cases.

### Real BGE RRF K sweep (hybrid)

| K | Hit@5 | MRR | nDCG@5 | Exact Top1 |
|---:|---:|---:|---:|---:|
| 10 | 1.000 | 0.981 | 0.971 | 0.958 |
| 20 | 1.000 | 0.981 | 0.971 | 0.958 |
| 40 | 1.000 | 0.981 | 0.971 | 0.958 |
| **60** | **1.000** | **0.981** | **0.971** | **0.958** |
| 80 | 1.000 | 0.981 | 0.971 | 0.958 |
| 100 | 1.000 | 0.981 | 0.971 | 0.958 |

Completely flat across K ∈ [10, 100]. No Exact Top1 regression anywhere.
**No evidence to change `RRF_K` away from 60.**

## Candidate window limitation

Candidate sweep is **not** used to justify production window=300 on this set:

```text
Candidate sweep은 corpus size < 50이므로
50/100/200/300 비교로 production window 품질을 판단할 수 없음.
따라서 300은 검증 결과로 선택한 값이 아니라 기존 안전한 default를 유지한 것.
```

## Failure patterns (examples)

| Query | Mode | Observation | Notes |
|---|---|---|---|
| `병원` | Semantic/Hybrid (BGE) | Exact Top1 miss (SR-AUTO-01 ahead of SR-MED-WRITE-01) | Both highly relevant hospital automation; Hit@5 OK |
| Paraphrase / NL | Keyword | Many empty hits | Expected without FTS relevance; BGE semantic recovers |
| Short tokens under topic harness | Semantic (topic) | OCR/CRM unstable | Topic harness artifact only — not seen as a BGE failure mode here |

RRF implementation verified: **1-based ranks**, equal keyword/semantic weights,
deterministic tie-break. No off-by-one bug found.

## Final decision

```text
RRF_K: 60 (unchanged)
Keyword candidate: 300 (unchanged — conservative default, not sweep-proven)
Semantic candidate: 300 (unchanged — same note)
Weighted RRF: not introduced
Title boost / keyword relevance rewrite: deferred
```

**Why (real BGE):** Hybrid and Semantic already sit at ~ceiling metrics; RRF K
sweep is flat with **zero Exact Top1 regression**. Changing K would be
cosmetic, not evidence-based.

Production code change beyond docs/eval: injectable `rrf_k` /
`candidate_limit` + `--embedding-mode` only (defaults unchanged).

## Regression

* Deterministic topic harness tests: exact `회의록`, medical paraphrase,
  inventory NL → expected idea ∈ top 3 (`tests/test_search_ranking_quality.py`).
* ACL: private idea excluded under hybrid even with `rrf_k` override.
* RRF unit: 1-based ranks + rejects `rrf_k < 1`.
* Semantic integration / search-mode fallback contracts: unchanged.
* Pytest does **not** call real BGE.

## Latency

Must not confuse the two modes:

```text
Topic eval (ranking/DB path only; no remote embed):
  Keyword p50 ≈ 6 ms
  Semantic p50 ≈ 3 ms
  Hybrid  p50 ≈ 5 ms

Configured BGE-M3 (end-to-end includes embedding API):
  Keyword p50 ≈ 7 ms
  Semantic p50 ≈ 91 ms
  Hybrid  p50 ≈ 97 ms
```

## Remaining TODO

* Optional later: keyword relevance ordering (`ts_rank` / title boost) if larger
  real corpora show exact matches buried by `updated_at`.
* Cross-encoder / query expansion / explainability UI: out of scope until needed.
* Candidate window study on a corpus ≫ 300 ideas.

## Judgment

**SEARCH QUALITY PASS** — synthetic harness retained for CI; real BGE-M3
baseline + RRF K sweep completed; production `RRF_K=60` and candidate 300
retained with evidence.
