# File Preview & Authenticated Byte Fetch

> Preview `.txt/.md/.markdown` as UTF-8 text and `.pdf` page-by-page with pdf.js, without ever
> exposing a signed URL or leaking credentials into an `<img>`/`<iframe>`.
> Source of truth: `frontend/src/components/DocumentPreviewModal.tsx`,
> `frontend/src/api/client.ts`, `frontend/src/pages/DocumentsPage.tsx`.

## Authenticated byte fetch — `getFileBytes(documentId)`

Fetching via `<img>`/`<iframe>` cannot attach the JWT header. Fetch bytes manually:

```ts
const response = await fetch(`/api/documents/${id}/file`, { headers: { Authorization: `Bearer ${token}` } });
if (!response.ok) {
  // parse ApiErrorSchema body so 404 surfaces the server message ("文档不存在"),
  // not just "获取文件失败（404）"; clear token on 401 (mirror request())
  throw new ApiRequestError(...);
}
return response.arrayBuffer();
```

## PDF preview lifecycle (concurrency-safe)

pdf.js rendering is a long-lived async pipeline; every stage must be cancellable or the modal
leaks work after unmount / page-flip:

- **Lazy-load + worker path** — `await import("pdfjs-dist")` so the ~365 kB lib + ~1.4 MB worker
  are code-split into chunks fetched only when a PDF preview opens:
  ```ts
  pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
  ```
- **Loading task** — keep `PDFDocumentLoadingTask` in a ref; call `destroy()` in effect cleanup so
  an in-flight download/parse aborts on close instead of finishing then self-destroying.
- **Render task** — keep the current `RenderTask` in a ref; call `cancel()` in the page-render
  effect cleanup. Without this, a fast page-flip renders two pages onto the same canvas and pdf.js
  throws `Cannot use the same canvas during multiple render operations`.
- **Guard state writes** — set a `cancelled`/`disposed` flag in cleanup; never `setState` after
  unmount/switch. Wrap `destroy()`/`cancel()`/`swallow` with a no-op `.catch` to avoid unhandled
  rejections from async cleanup.
- **Fresh mount per document** — render `<DocumentPreviewModal key={document.id} … />` so switching
  the previewed doc remounts effects and resets `pageNo`/state. A stable `document` prop identity
  means the parent list's 5s polling does not reset the open preview.

Canvas output: scale page viewport to container width (clamped ~320–760 px), multiply by
`devicePixelRatio`, and pass `transform: [dpr,0,0,dpr,0,0]` to `page.render` for sharp text.

## Validation constants must mirror the backend

`DocumentsPage.tsx` duplicates the server rules for instant pre-upload feedback: `ALLOWED_EXTS`,
`MAX_UPLOAD_BYTES`, `FORBIDDEN_FILENAME_CHARS`, `CONTROL_CHARS`, and SHA-256 duplicate check.

> **Warning**: The **backend is authoritative** — the frontend mirror exists only for UX and is a
> kept-in-sync pair. When upload rules change in `backend/app/api/documents.py`, update
> `DocumentsPage.tsx` in the same change. Never relax a server check because the client "already
> checks it".

## Wrong vs Correct

#### Wrong — uncancelled in-flight render on page flip

```ts
await page.render({ canvasContext: ctx, viewport }).promise;   // no RenderTask ref / cancel
```

#### Correct

```ts
const task = page.render({ canvasContext: ctx, viewport, transform });
renderTaskRef.current = task;
await task.promise;                      // cleanup: renderTaskRef.current?.cancel()
```
