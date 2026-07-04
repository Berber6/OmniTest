# Fix Plan: Task 1 + Task 2 Critical Bugs

## Priority Order (P0 → P2)

---

### Fix 1: Double-JSON encoding in Task 1 routes (P0 — Data corruption)

**File:** `backend/app/api/task1_routes.py`

**Lines 243, 348-349:** `json.dumps()` on values being written to SQLAlchemy `JSON` columns causes double-encoding.

**Fix:** Remove `json.dumps()`, pass raw Python objects:
```python
# Line 243: change from
source_chunks=json.dumps(f.source_chunks),
# to
source_chunks=f.source_chunks,

# Lines 348-349: change from
steps_json=json.dumps([step.model_dump() for step in s.steps]),
expectations_json=json.dumps([exp.model_dump() for exp in s.expectations]),
# to
steps_json=[step.model_dump() for step in s.steps],
expectations_json=[exp.model_dump() for exp in s.expectations],
```

Also fix the read-side compensating code (lines ~325, 476-477) that does `json.loads() if isinstance(x, str)` — after the write fix, SQLAlchemy will return parsed objects directly, so the `isinstance` guards become unnecessary. Simplify to direct field access.

**Verification:** Re-run extract + generate pipeline, check DB values are single-encoded. Read back features/scenarios via API — no nested strings.

---

### Fix 2: app_config.py derives base_url from settings (P0 — Wrong URL risk)

**File:** `backend/app/task2/agent/app_config.py`

**Lines 33:** Hardcodes `base_url="https://demo.4gaboards.com"` ignoring `settings.login_url`.

**Fix:** Derive dynamically:
```python
@classmethod
def from_settings(cls) -> "TargetAppConfig":
    base_url = settings.login_url.replace("/login", "").rstrip("/")
    return cls(
        name="4gaboards",
        base_url=base_url,
        login_url="/login",
        ...
    )
```

Also update the class default (line 19) to be empty/placeholder and always use `from_settings()` at runtime.

**Verification:** If `settings.login_url` changes via .env, `app_config.base_url` follows automatically.

---

### Fix 3: Hardcoded Chinese retrieval queries → dynamic (P1 — Coverage ceiling)

**File:** `backend/app/task1/extractor.py`

**Lines 58-64:** 5 static Chinese queries against English docs.

**Fix:** Generate queries dynamically from the crawl manifest (page titles + section headings). Add a helper that reads the manifest JSON and extracts unique page titles/section keywords, producing 5-8 bilingual queries (English title + Chinese translation keyword). If manifest unavailable, fall back to existing queries.

**Verification:** Re-run extraction — more features, fewer missed pages.

---

### Fix 4: max_distance threshold too aggressive (P1 — Coverage filter)

**File:** `backend/app/task1/vector_store.py`

**Lines 147, 179, 220:** `max_distance=0.50` filters out cross-lingual matches.

**Fix:** Raise default to 0.70 and add `max_distance` as a configurable parameter on `Settings` (e.g., `rag_max_distance: float = 0.70`). Pass it through from routes to extractor/generator.

**Verification:** Re-run extraction — previously excluded chunks (e.g. import/export) now survive.

---

### Fix 5: Mixed-language fallback query (P1 — Retrieval quality)

**File:** `backend/app/task1/generator.py`

**Line 53:** `f"how to {feature.name}"` produces nonsense like `"how to 创建Board"`.

**Fix:** Use feature.description (English-friendly) or just the feature name alone as fallback:
```python
query=f"{feature.name} {feature.description}",
```
(Falls back to same-style query as primary, just fewer results.)

---

### Fix 6: runner.py verify fallback always-fail → heuristic default (P1 — False negatives)

**File:** `backend/app/task2/agent/runner.py`

**Lines 661-666:** Fallback returns `passed=False` even on transient LLM failure when execution steps succeeded.

**Fix:** If all executed steps reported success and LLM verification just failed (network/rate-limit), default to `passed=True` with low confidence (0.3) and reason "LLM验证不可用，基于执行步骤成功推断". Only hard-fail if execution steps themselves failed.

---

### Fix 7: Inject UIElementRegistry into scenario generation prompt (P2 — Grounding)

**File:** `backend/app/task1/generator.py`

Currently `GENERATE_SCENARIOS_PROMPT.format()` only receives `{chunks}` and `{images}`.

**Fix:** Add `{ui_elements}` placeholder to the prompt. Load `UIElementRegistry` from `ui_registry.json` at generation start, inject `format_for_prompt()` output. This constrains the LLM's `target` descriptions to actual UI elements.

**Also:** Update `generate_scenarios.py` prompt template to include a section like:
```
## 可用UI元素
{ui_elements}
请仅在上述元素范围内指定 target 字段。
```

---

### Fix 8: Dead code cleanup (P2 — Code hygiene)

Multiple unreachable lines across both tasks:
- `vector_store.py:89-93` — logger.info after return
- `nodes/execute.py:278,193-194` — dead returns
- `nodes/reflect.py:480` — unreachable return
- `nodes/verify.py:96-99` — unreachable branch

**Fix:** Remove each unreachable block. No functional change.

---

## Execution Order

1. Fix 1 (double-JSON) — data corruption, must fix first
2. Fix 2 (app_config URL) — runtime correctness
3. Fix 3 + Fix 4 + Fix 5 (retrieval quality) — re-run pipeline together
4. Fix 6 (verify fallback) — reduces false negatives
5. Fix 7 (UI registry injection) — improves scenario grounding
6. Fix 8 (dead code) — cleanup, no urgency

## What I'm NOT doing (out of scope per Rule 2)

- NOT refactoring the entire Task 2 architecture (observe→act loop is already in runner.py)
- NOT rewriting element_resolver.py's VLM pipeline
- NOT adding scenario preconditions/setup steps (requires prompt redesign beyond scope)
- NOT changing the legacy LangGraph nodes beyond dead-code removal (runner.py is the active path)
