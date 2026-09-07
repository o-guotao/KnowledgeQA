# Documents API & Ingest Contract

> Owner-scoped document lifecycle for the KnowledgeQA app. Raw bytes live in MinIO;
> metadata lives in Postgres; ingest tasks chunk extracted text into pgvector.
> Source of truth: `backend/app/api/documents.py`, `backend/app/models/document.py`,
> migration `0006_document_content_hash`.

## Document Status Machine

```
uploaded ──(ingest task)──> processing ──> ready
                                    └────> failed
no_text  (terminal: image-only PDF with no text layer; stored + previewable, NOT ingested, OCR reserved)
```

Statuses: `uploaded | processing | ready | failed | no_text`. Only `uploaded` enqueues an ingest `Task`.

## POST /documents — upload validation pipeline

Order is load-bearing (each stage short-circuits with a 4xx before any store):

| # | Check | Failure |
|---|-------|---------|
| 1 | `await file.read()` non-empty | `EMPTY_FILE` 400 |
| 2 | `len(data) <= 20MB` | `FILE_TOO_LARGE` 413 |
| 3 | `_normalize_filename(raw)`: basename, reject control chars + `<>:"/\|?*`, strip, length 1..255 | `INVALID_FILENAME` 400 |
| 4 | ext in `.txt/.md/.markdown/.pdf` | `BAD_FILE_TYPE` 400 |
| 5 | `sha256(data)`; pre-query `(user_id, content_hash)` duplicate | `DUPLICATE_DOCUMENT` 409 (message names the existing file) |
| 6 | `.pdf` → `extract_text` probe | unparseable/encrypted → `BAD_FILE_TYPE` 400 "PDF 无法解析…", **not stored**; zero text → status `no_text` (stored, no task) |
| 7 | flush row, `put_object`, enqueue `ingest_document` Task iff status == `uploaded` | |
| 8 | commit; on `IntegrityError` rollback → `DUPLICATE_DOCUMENT` 409 | concurrent double-upload backstop |

Object key convention: `{user_id}/{document_id}/{filename}`.

### Concurrency backstop — partial unique index

Duplicate detection is pre-query + DB-unique. The DB layer is:

```sql
-- migration 0006
CREATE UNIQUE INDEX ix_documents_user_content_hash
  ON documents (user_id, content_hash)
  WHERE content_hash IS NOT NULL;
```

> **Warning**: The SQLAlchemy model must keep its own matching `Index(...)` in
> `__table_args__` (same name/columns/`postgresql_where`) or the ORM metadata and the
> live schema drift apart. Migration and model are a kept-in-sync pair.

## GET /documents/{document_id}/file — raw-byte preview

- Owner-scoped (`user_id == current`), auth via `get_current_user`.
- 404 when: no such owned document, `object_key` empty, **or MinIO read fails** (deleted object).
  MinIO failures are logged, never surfaced as 5xx.
- Response: `Response(content=data, media_type=_media_type(filename))` + header
  `Content-Disposition: inline; filename*=UTF-8''{urllib.parse.quote(filename)}`.
- `_media_type`: `.pdf` → `application/pdf`; `.md/.markdown` → `text/markdown; charset=utf-8`;
  else `text/plain; charset=utf-8`.
- Route ordering is safe: `/documents/{document_id}` does not shadow
  `/documents/{document_id}/file` (FastAPI matches by segment count).

## Other endpoints

- `GET /documents` — owner list, newest first.
- `GET /documents/{id}` — owner fetch.
- `GET /chunks/{chunk_id}` — citation jump: returns chunk text + owning doc name + total chunk count.
- `DELETE /documents/{id}` — 204. Cancels stale `ingest_document` tasks for that doc, deletes the
  row (chunks + vectors cascade via FK `ondelete=CASCADE`), then best-effort MinIO delete.

## Validation & Error Matrix

| Condition | HTTP | `detail.code` |
|-----------|------|---------------|
| empty upload | 400 | `EMPTY_FILE` |
| > 20MB | 413 | `FILE_TOO_LARGE` |
| bad filename (chars/length) | 400 | `INVALID_FILENAME` |
| unsupported ext / corrupt-encrypted PDF | 400 | `BAD_FILE_TYPE` |
| duplicate content (existing or concurrent) | 409 | `DUPLICATE_DOCUMENT` |
| owned doc / object missing | 404 | (app-level `not_found`) |

## Wrong vs Correct

#### Wrong — decrypt/corrupt PDF falls to the worker and only fails asynchronously

```python
status = "no_text" if not extract_text(...) else "uploaded"   # unparseable → worker failed later
```

#### Correct — resolve no-text vs unparseable inside the request

```python
try:
    no_text = not extract_text(filename, data)
except Exception:
    raise AppError("BAD_FILE_TYPE", "PDF 无法解析（文件损坏或已加密），未保存", 400)
status = "no_text" if no_text else "uploaded"
```

## Tests Required

- Re-upload same bytes under a different filename → 409 naming the original file.
- Two parallel identical uploads → exactly one 201, the other 409 (partial-unique-index path).
- Image-only PDF → 201 `status=no_text` and **zero** rows in `tasks`.
- `GET .../file` for no_text doc → 200 `application/pdf`, served bytes byte-equal to uploaded bytes.
- `GET .../file` for deleted doc / other user's doc → 404.
