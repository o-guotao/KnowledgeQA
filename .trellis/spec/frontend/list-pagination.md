# List Pagination & Search (frontend)

> One hook + two components cover every list in the app. Source of truth:
> `frontend/src/hooks/usePaginatedQuery.ts`, `components/ui/search-input.tsx`,
> `components/ui/pagination.tsx`, `api/schemas.ts::pageSchema`.

## The three pieces

```tsx
const docsQuery = usePaginatedQuery<KnowledgeDocument>(
  useCallback((params) => get(withQuery("/documents", params), pageSchema(DocumentSchema)), []),
  { pageSize: 10, extraParams: { folder: filterFolder ?? "" } },
);
```

- `pageSchema(item)` → zod schema for the backend `Page[T]` envelope
  (`{items,total,page,page_size,pages}`). Never `z.array(item)` for a list endpoint.
- `withQuery(path, params)` builds the query string and **skips empty/undefined values**, so
  callers can pass an empty `q`/`folder` without special-casing.
- `SearchInput` is fully controlled; the debounce lives in the hook, not the component.
- `Pagination` renders `null` when `pages <= 1`, so it can be dropped in unconditionally.

## Hook behaviour that must not be "simplified" away

| Behaviour | Why it exists |
|---|---|
| `fetchPage` kept in a ref | Call sites pass inline arrow functions; putting it in the effect deps would refetch on every render |
| 300 ms debounce on `query` | Otherwise every keystroke is a request |
| Request-id race guard | Fast typing / fast paging must not let an older response overwrite a newer one |
| `query`/`extraParams` change → reset to page 1 | Otherwise the user searches while on page 3 and sees an empty list |
| `append` mode | Sidebars accumulate pages ("加载更多") instead of replacing |
| Auto-correct when the page goes out of range | Deleting the last row of the last page would otherwise show an empty list forever |

### Gotcha: StrictMode and "mounted" flags

The app renders under `<StrictMode>`, so every effect runs **setup → cleanup → setup** on
mount. Any "mounted" flag that is only cleared in the cleanup ends up `false` forever, and
every async response is then silently discarded — all lists render blank with **no error**.

**Rule**: a mounted guard must reset the flag in the setup, not only clear it in cleanup:

```ts
useEffect(() => {
  mountedRef.current = true;              // required — StrictMode re-runs this setup
  return () => { mountedRef.current = false; };
}, []);
```

Even better, prefer a per-invocation `cancelled` local (like the chat history effect) or the
request-id guard alone — they are immune to this class of bug.

Returned `setItems` exists for optimistic updates (remove a deleted row locally, then
`refresh()` to re-sync `total`/`pages`).

## Page integration rules

- **Counters must not be derived from `items`.** Paged items are one page only. Aggregate
  counts come from a dedicated endpoint (`GET /documents/stats`) or from `total`.
- **"Select all" means the current page.** The selection `Set` itself persists across pages
  (batch delete works on ids, not on the visible list).
- **`enabled`** gates a list that is not visible yet (e.g. `enabled: tab === "team"`).
- **Auxiliary data needs its own mount load.** Counters/enumerations (`/documents/stats`,
  `/documents/folders`) that are only called from a manual `refresh()` never load on first
  render — they sit at their initial value forever (chips stuck at 0, filter buttons
  missing) while the paged list itself works (the hook self-fetches). When replacing a
  component's state block wholesale, audit every `useEffect` in the replaced region.
- Empty states distinguish "no data" from "no match": check `query !== ""` / active filters
  before showing onboarding copy.

## Chat page: history pagination must not break streaming

`messages` deliberately does **not** use `usePaginatedQuery`: it is driven by optimistic
writes + SSE deltas, and the hook's "replace the whole list" semantics would fight that.

- `page=1` is the **newest** page (server orders `created_at desc`); the display list is
  ascending, so an older page is `reverse()`d before being **prepended**.
- The existing `turnSessionRef` guard from `state-management.md` still applies to the
  `activeId` history load. Do not remove it.
- "加载更早" is disabled while a turn is streaming, and its response is dropped if the user
  switched sessions mid-flight (`activeIdRef` check) — prepending into the wrong session is
  otherwise silent data corruption.
- Only the header of the list is touched by "load older"; the streaming tail is never
  re-rendered from a fetch.

## Verifying the contract

Type-checking alone does not prove the UI can parse responses. Run the backend locally and
validate real responses against the bundled zod schemas:

```bash
cd frontend && ./node_modules/.bin/esbuild src/api/schemas.ts --bundle --format=esm --outfile=/tmp/schemas.mjs
# then import pageSchema(...) from that bundle in a node script and safeParse each
# GET /api/<list>?page=1&page_size=N response
```

This catches the failure mode that silently breaks list pages: a `SCHEMA_MISMATCH` thrown by
`api/client.ts` (field renamed, `pages` missing, array still returned, …).

## Gotcha: "all lists are empty" usually means a stale backend

Symptom: every list renders blank right after a pagination/contract change, with no visible
error. Root cause seen in practice: the local backend was started **without `--reload`**, so it
kept serving the pre-change code (bare arrays) while the new frontend parsed with
`pageSchema` — every request threw `SCHEMA_MISMATCH` and the pages rendered as empty.

Diagnosis (30 seconds):

```bash
curl -s "http://127.0.0.1:8000/api/documents?page=1" -H "Authorization: Bearer $TOKEN"
# want: {"items":[...], ...}     got: [{...}]  -> backend is running old code
```

Then restart the backend (with `DEPLOY_PROFILE=local` for the sqlite demo) and hard-refresh.

Prevention: list pages surface `query.error` in the UI (never a silent blank list), and run the
backend with `--reload` during development.
