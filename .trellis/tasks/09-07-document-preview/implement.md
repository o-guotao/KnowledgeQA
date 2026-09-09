# 文档预览 — 执行计划

> 前置：`09-07-batch-upload-validation` 合入后再做（两者都改 `DocumentsPage.tsx`），避免同文件冲突。无严格数据依赖。

## 1. 后端：文件读取接口
- `backend/app/api/documents.py`：新增 `GET /documents/{document_id}/file`（鉴权、404 语义见 design），响应 `Response(content=bytes, media_type=...)` + `Content-Disposition`。扩展名→content_type 用小工具函数。
- 验证：curl 带 token 拉 .pdf → 200 `application/pdf`；非本人 → 404；删除后 → 404。

## 2. 前端：client 取字节
- `frontend/src/api/client.ts` 暴露 `getFileBytes(documentId: string): Promise<ArrayBuffer>`（Authorization 头 + fetch，非 ok 抛 ApiRequestError）。

## 3. 前端：DocumentPreviewModal
- 新增 `frontend/src/components/document/DocumentPreviewModal.tsx`（或就近 pages 目录），含 txt/md 文本视图与 pdf.js 懒加载翻页视图；分页/关闭销毁逻辑见 design。

## 4. 前端：列表入口
- `DocumentsPage.tsx` 行尾加「预览」按钮（`Eye` icon）与选中状态；对话框条件渲染。
- 验证：`npm run build`；手动——ready 的 .md 文本正常；纯图片 PDF（no_text 或历史 failed）逐页翻看正常；无权限/不存在文档提示；打开预览时列表轮询不抖动。

## 5. 依赖与构建
- `frontend/package.json` 增 `pdfjs-dist`；确认 Vite worker 路径；`npm install && npm run build`。
- 若 pdfjs 体积导致构建警告，评估 `vite` chunk 配置（懒加载已隔离）。

## Review Gate
- 对照 `prd.md` acceptance 全绿；文本/纯图 PDF、鉴权、删除后不可预览均验证。
- 与批量上传子任务集成回归由父 implement 第 7 步执行。

## 风险文件 / 回滚点
- `DocumentsPage.tsx`、`client.ts`（共享）；pdfjs-dist 依赖可 `npm rm` 回退。
