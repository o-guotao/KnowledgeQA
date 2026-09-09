# 文档预览（文本与图片 PDF）— 技术设计

## 结论先行

- **预览 PDF 一律 pdf.js（浏览器端）逐页渲染**，一条路径覆盖 文字型/纯图片型 PDF，保真且不引入后端渲染服务。`.txt/.md/.markdown` 取字节按 UTF-8 解码显示文本。
- 后端只新增**一个带鉴权的原始字节接口** `GET /api/documents/{document_id}/file`，不生成预签名 URL、不做分页 PNG。

## 后端接口

`GET /api/documents/{document_id}/file`（`documents.py` 增补）
- 鉴权 `get_current_user`；按 `(id, user_id)` 查本人文档，无 → 404。
- `object_key` 空或 MinIO 取数失败 → 404（不可预览）。
- `content_type` 按扩展名：`.pdf`→`application/pdf`；`.txt/.md/.markdown`→`text/plain; charset=utf-8`。响应头 `Content-Disposition: inline; filename*=UTF-8''<quoted>`。文件 ≤20MB，直接 `Response(bytes)`，无需流式。

### 与上传子任务的关系
- 预览不依赖 `no_text` 状态逻辑；任何状态（含 `no_text`/`failed`/历史遗留）只要本人文档且对象存在即可预览。仅依赖其产出的 `content_hash` 不影响本任务。

## 前端（`DocumentsPage.tsx` + 新增组件）

- 列表每行加「预览」按钮（图标 `Eye`，任一状态可用；可禁用当文档正在本地上传中的临时行）。
- 新增 `DocumentPreviewModal`：
  - 入参 `{document, onClose}`；挂载时按类型取数。
  - `.txt/.md/.markdown`：`getFileBytes(document.id)` → `TextDecoder('utf-8')` → `<pre className="whitespace-pre-wrap">`，容器内滚动。
  - `.pdf`：动态 `import('pdfjs-dist')` 懒加载，`GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()`；`getDocument({data: arrayBuffer})` 渲染当前页到 `<canvas>`，底部「上一页/下一页/第 x / N 页」；页面尺寸超宽自适应容器宽度。
- 鉴权取字节：复用现有 token，`fetch('/api/documents/{id}/file', {headers:{Authorization:'Bearer '+token}})` → `.arrayBuffer()`；在 `client.ts` 暴露 `getFileBytes(documentId)`。不走 `<iframe>`/`<img>`（避免鉴权外泄/预签名）。
- 打开预览不影响列表轮询；关闭释放 pdfjs 任务（`destroy()`）。

## 关键取舍与风险

- **依赖 pdfjs-dist**：体积 ~数百 KB（懒加载仅 PDF 预览时下载）。Vite worker 路径用 `?url`/import.meta.url，需在 `tsconfig`/打包不报错；若 worker 加载失败回退禁用 worker（`disableWorker`）仍有渲染功能（性能略降）。
- 内存：单文档 ≤20MB ArrayBuffer + pdf.js 内部对象，模态打开期间持有，关闭销毁，可接受。
- 后端 Response 一次性读 bytes（≤20MB）与现有 `get_object` 一致，无新增存储面。
- 中文内容 type 为 text/plain + UTF-8 解码，避免乱码。

## Out of scope
- 在线编辑、PDF 内文本搜索高亮、注释；后端 PDF 出图服务。
