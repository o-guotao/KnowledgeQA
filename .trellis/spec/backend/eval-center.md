# Eval Center Conventions

> Admin-only RAG evaluation subsystem: datasets/runs persisted, worker-async runner,
> admin dashboard tab. Source of truth: `backend/app/services/eval_runner.py`,
> `backend/app/api/admin_eval.py`, migration `0014_eval_center`.

## Architecture

- `eval_datasets` (jsonl payload ≤1MB, ≤500 items, `q`/`gold_doc`/`gold_keywords?` per line),
  `eval_runs` (config snapshot + status machine `pending→running→done|failed` + summary),
  `eval_run_items` (per-question per-group ranks). Deleting a dataset keeps history
  (`dataset_id` SET NULL).
- Runs execute via the existing `tasks` table (`run_eval` type, `max_retries=0`) in the
  worker — never inside a web request. `EVAL_TASK_TIMEOUT_SECONDS` (default 1800s) covers
  the 4-group matrix (+ optional LLM answers).
- **Concurrency gate**: at most one pending/running run; new submissions get 409
  `EVAL_RUN_BUSY`. The runner competes with online traffic for embedding/CPU otherwise.

## Runner isolation rules

- Retrieval runs against a **throwaway sqlite KB** (`eval/sample_docs/` chunked with the
  run's chunk params), self-built engine; the global `SessionLocal` only reads/writes
  eval tables. Temp db file is deleted in `finally`.
- Config groups switch via env override + `get_settings.cache_clear()` (`_group_env`
  context manager restores originals). Rerank and BM25 singletons are reset per group.
- Group matrix `(tag, hybrid, bm25, rerank)`: `baseline` / `hybrid` (tsvector-or-LIKE
  keyword) / `hybrid_bm25` / `hybrid_bm25_rerank` — splitting hybrid vs bm25 quantifies
  the BM25 contribution.
- `top_k` scan retrieves once at `top_k_max` and truncates for Recall@K (K=1..max) —
  no 10x recall cost.
- `with_llm` (default off): answers via the production prompt (`RAG_SYSTEM_PROMPT` +
  `build_rag_user_content`), `gold_keywords` hit rate; degrades silently when no
  `DEEPSEEK_API_KEY`. Injection question (`安全规范.md`) records `injection_blocked`.

## Latency instrumentation (online)

- `rag.retrieve(..., timing=dict)` back-fills `recall_ms` / `rerank_ms` — the
  concurrency-safe way; do NOT monkeypatch `app.services.rerank` in web requests.
- `chat.py` records `ttft_ms` / `total_ms` / `recall_ms` / `rerank_ms` into
  `usage_records` on the first usage row only (tool-loop rounds stay NULL).
- `/admin/eval/online-stats?days=N` aggregates percentiles in Python (dialect-agnostic),
  never `percentile_cont` (sqlite compat).

## Frontend

- `AdminPage` third tab; `pages/admin/EvalCenterTab.tsx` loaded via `React.lazy`
  (keeps recharts out of the main bundle — verify split chunk in build output).
- Charts: direct value labels, solid/dashed line styles (not color-only), table
  fallback data below charts.
