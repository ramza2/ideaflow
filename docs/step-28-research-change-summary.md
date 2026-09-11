# Step 28 — Research change summary UX

Goal: when Compare opens, show a deterministic “what changed?” summary at the
top of the modal — **without LLM, API, migration, or polling**.

## Policy

| Item | Decision |
|---|---|
| Computation | Frontend pure helpers on the two already-fetched run details |
| Extra API | **0** |
| Extra DB | **0** |
| Migration | **none** |
| LLM | **none** |
| Polling | **none** (existing READY → history refetch only) |

Source of truth for diffs remains Step 26:

* `compareEvidenceByUrl` (normalized URL identity; metadata = title/snippet/source_name)
* `compareQueryLists`
* Absolute versions via `assignResearchVersions`

## Change Summary structure

```ts
{
  evidence: { added, removed, updated, unchanged },
  queries: { added, removed, unchanged },
  summaryChanged: boolean,
  noStructuralChanges: boolean
}
```

### Evidence 4-bucket UX

Internal Step 26 buckets: `added` / `removed` / `unchanged`.

UX split:

* `updated` = `unchanged` items with `metadataChanged === true`
* `unchanged` (UX) = remaining same-URL items with no metadata change

`updated` is **not** double-counted inside `unchanged`.

### Query summary

Reuses `compareQueryLists` → added / removed / unchanged (`common`).

### Research summary

`normalizeResearchSummary`:

1. trim
2. CRLF → LF
3. collapse consecutive horizontal whitespace
4. tidy spaces around newlines / collapse 3+ blank lines

Then string equality. No semantic / LLM comparison.

Whitespace-only differences → `summaryChanged = false`.

## Narrative

`buildResearchChangeSentences(summary)` returns deterministic Korean sentences
from counts (examples):

* No change → “검색어, 근거 및 조사 요약에 변화가 없습니다.”
* Summary only → “근거와 검색어는 동일하지만 조사 요약 내용이 변경되었습니다.”
* Evidence added/removed → count-based sentences
* Updated-only → “근거 출처 구성은 동일하지만 …”

Forbidden: severity scores, “대폭 변경”, change rates, LLM prose.

## Compare snapshot policy

Compare fetches **past run + latest-at-open** once and keeps that pair while
the dialog is open.

* Dialog right label: `vN · 비교 기준` (completed-at only; not a live “최신” badge)
* History list badge: still `최신` (live after READY refresh)
* `refreshKey` (new READY) → **history refetch only**; Compare stays open with the same left/right pair
* `workspaceId` / `ideaId` change → full reset (close Compare/detail, invalidate all request seqs)
* New READY while dialog open → **no** auto-refetch / re-pair of Compare
* Close + reopen → new latest

`prevRefreshKeyRef` absorbs the current `refreshKey` on identity change so a
same-commit idea switch + READY bump does not double-fetch history.

## UI layout

```text
버전 정보
변경 요약   ← Step 28
요약 (side-by-side)
검색어
근거 변화 (detailed rows)
```

Desktop: change summary counts in 3 columns. Mobile: stacked.

Colors reuse Step 26 tones (+ green, − red, ~ amber, = neutral) with text/symbols
(not color alone).

## Future TODO

* LLM natural-language change summary
* Arbitrary A/B version selector
* Semantic paragraph / word diff
* Research change notifications / analytics

## Judgment

Frontend-only additive UX on existing Compare data path.
