# List Pagination & Search Conventions

> Every list endpoint returns one envelope shape and supports `q` + `page` + `page_size`.
> Source of truth: `backend/app/core/pagination.py`, `backend/app/schemas/common.py`.

## The envelope (one shape, no dual-shape branching)

All list endpoints declare `response_model=Page[XxxOut]` and return
`{items, total, page, page_size, pages}`:

```python
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int      # filtered total, NOT the page length
    page: int
    page_size: int
    pages: int      # ceil(total / page_size); 0 = no rows
```

Why one shape: a "bare array unless `page` is passed" variant would force every frontend
call site to branch (`Array.isArray`) and would need two zod schemas per list. The shape
change is therefore deliberately breaking and ships frontend + backend together.

## Query params

```python
class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),  # 20 / 100
    ) -> None: ...
```

- Use an explicit `__init__` (not a dataclass): FastAPI resolves dependency params from
  the function signature, so the `Query(...)` defaults must live there.
- Subclass to change the default page size — e.g. `MessagePageParams` defaults to 50
  (`DEFAULT_MESSAGE_PAGE_SIZE`) because a chat view needs more rows per page.

## The two helpers

```python
rows, total = await paginate(db, stmt, params)          # count first, then offset/limit
return make_page([to_out(row[0]) for row in rows], total, params)
```

- `paginate` returns **Row objects**, not ORM instances: joined selects such as
  `select(Document, User.display_name)` would lose the owner name under `.scalars()`.
  Single-entity queries use `row[0]`.
- `count_rows` clears `order_by/limit/offset` and wraps the statement in a subquery, so
  the count is derived from *the same* filters as the items. Never
  `select(func.count()).select_from(Model)` — it silently over-counts after a join and
  under-counts after `group_by`.

## Hard rule: every paginated query needs a unique tiebreaker

```python
.order_by(Document.folder.asc(), Document.created_at.desc(), Document.id.desc())
#                                                          ^^^^^^^^^^^^^^^^^^ required
```

`created_at` is not unique (batch writes land in the same second, and SQLite's
`CURRENT_TIMESTAMP` has second granularity). Without a unique last sort key the database
may return tied rows in a different order per query, so paging **duplicates or skips**
rows. Always append the primary key.

> Known limitation: for `messages` the tiebreaker is a random UUID, so intra-second
> ordering is stable but arbitrary. Production (Postgres) has microsecond `now()`, so ties
> are effectively impossible; SQLite demo mode could in principle order a user/assistant
> pair within the same second oddly. A monotonic sequence column is the real fix if that
> ever matters (it would need a migration).

## Search: `q` is a literal substring, never a pattern

```python
term = normalize_q(q)                    # trim + truncate to 100 chars; "" -> None
if term is not None:
    stmt = stmt.where(Document.filename.ilike(like_pattern(term), escape=LIKE_ESCAPE))
```

- `escape_like` escapes `\ % _`, so a user typing `100%` or `_` matches literally instead
  of matching everything. **`escape=LIKE_ESCAPE` must be passed** or the escaping is inert.
- `ILIKE` works on both dialects (SQLite degrades it to a case-insensitive `LIKE`).
- `q` empty/whitespace must behave exactly like "no `q`" — that keeps the frontend free to
  always send the parameter.

### Gotcha: JSON columns and non-ASCII search (SQLite vs Postgres)

`documents.tags` is a SQLAlchemy `JSON` column. SQLAlchemy serializes with
`ensure_ascii=True`, so **SQLite stores** `["\u9a8c\u8bc1"]` while **Postgres jsonb**
stores the real characters and renders them back on `CAST(... AS VARCHAR)`.

A naive `cast(Document.tags, String).ilike('%验证%')` therefore **never matches on SQLite**
and matches on Postgres — a dialect-dependent bug that looks like "tags search is broken in
the demo".

Fix: `json_text_search(column, term)` matches both the raw term and its
`unicode_escape` form:

```python
stmt = stmt.where(or_(
    Document.filename.ilike(pattern, escape=LIKE_ESCAPE),
    json_text_search(Document.tags, term),
))
```

## Aggregations, joins and memory-backed lists

- **Aggregate + paginate** works: `group_by` queries go through the same `paginate`
  (the count subquery counts groups). Filter on a grouped column with `where` (before
  grouping), not `having`, when the value is known pre-aggregation (e.g. `User.username`).
  The tiebreaker must be a grouped column or an aggregate.
- **Join + paginate** works: filter columns of either table, count via the same subquery.
- **In-memory lists** (e.g. `/meta/changelog` parsed from `CHANGELOG.md`) filter and slice
  in Python, then `make_page`. Keep the parser's natural order (newest release first).
- **Page-level enrichment** (e.g. attaching each user's quota): after paging, fetch the
  related rows for the **current page's ids only** (`Quota.user_id.in_(page_user_ids)`).
  Do not keep the old "load all rows, then slice" pattern.

## Route ordering

Literal segments must be declared **before** the parameterized route or they are swallowed
as a path parameter (`/documents/stats` → `{document_id}` UUID parse failure). Declare
`/documents/folders` and `/documents/stats` above `/documents/{document_id}`.

## Deliberate exceptions (not oversights)

| Endpoint | Why no pagination/search |
|---|---|
| `GET /admin/usage/daily` | Time series feeding charts; row count is bounded by `days` (≤365) |
| `GET /admin/eval/runs/{id}` (`items`) | One run is ≤500 questions, returned with the detail |
| `GET /documents/folders` | Enumeration semantics (filter chips), not a list to page |
| `GET /admin/eval/runs/{id}/items.csv` | Export means "everything" |
| `GET /feedback/stats`, `/quotas/me`, `/meta/version` | Single objects |

## Boundary behaviour

| Case | Behaviour |
|---|---|
| `page=0`, `page_size=0`, `page_size=101` | 422 (FastAPI validation) |
| `page` beyond `pages` | `items: []`, correct `total`/`pages` — not an error |
| `q=""` / `q="   "` | identical to omitting `q` |
| `q` containing `%` `_` `\` | literal match |
| no rows | `{items: [], total: 0, page: 1, page_size: N, pages: 0}` |

## Frontend pairing

The envelope is consumed by `pageSchema(item)` in `frontend/src/api/schemas.ts`; see
`.trellis/spec/frontend/list-pagination.md`. Any change here must be reflected there —
the contract is verified by validating real responses against those zod schemas.
