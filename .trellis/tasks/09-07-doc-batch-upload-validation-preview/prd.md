# 文档批量上传、上传校验与预览

## Goal

改善文档管理的录入与检视体验：一次可传多份文档；上传即校验（重复、文件名、类型、大小、图片型 PDF），尽早把错误暴露给用户而不是留到后台任务；文档入库后可在列表预览内容（含纯图片 PDF 逐页查看），便于判断是否需要保留。

## 子任务映射

- `09-07-batch-upload-validation` — 批量上传 + 上传校验（前端批量 UI、后端批量接口、重复检测、文件名规范化、图片型 PDF 上传时快速失败）
- `09-07-document-preview` — 文档预览（文本预览 + 图片型 PDF 逐页渲染 + 带鉴权内容接口）

## 确认事实（仓库证据）

- 现上传：单文件 `POST /api/documents`（`backend/app/api/documents.py:27`），校验 空/大小≤20MB/扩展名白名单 `.txt/.md/.markdown/.pdf`，之后入库 MinIO 并入队 worker 切分（`worker/main.py:73`）。
- PDF 提取用 pypdf，纯图片 PDF（无文字层）提取为空 → worker 报「文档提取后无文本内容」置 failed（`worker/main.py:88-90`、`app/services/chunking.py:22`）。
- `documents` 表无 (user_id, filename) 唯一约束，同名可重复上传（`app/models/document.py`）。
- 前端上传为单文件 input，逐文件 alert 报错（`frontend/src/pages/DocumentsPage.tsx:51`）。
- 尚无"取文档原文/文本"只读接口；`storage.get_object` 可从 MinIO 取字节（`app/services/storage.py:39`）。前端 DocumentOut 不含 object/content（`app/schemas/document.py:7`、`frontend/src/api/schemas.ts:75`）。

## Requirements（跨子任务约束）

- 上传上限维持单文件 ≤ 20MB；批量同一次可选择多份。
- 校验错误必须返回**明确可读**的错误码与文案，前端展示而非裸 alert。
- 图片型 PDF（无文字层）：上传成功但进入**新增「不可检索」状态**——正常保存原文件、不投递 worker 切分、不产生 chunk，供预览与将来上游处理（如 OCR）。既避免 worker 空转，也避免把文档"当场删掉"。
- 重复文件判定 = **内容哈希（SHA-256）**：新增 `documents.content_hash` 列 + 迁移；新上传必算必存；前端用浏览器哈希预检、后端权威校验；仅对比本人未删除文档。存量（哈希为空）文档无法参与哈希判重，退回按文件名粗查——作为已知限制记录。
- 预览必须鉴权，仅本人文档可读。

## Acceptance Criteria（parent 级集成验收）

- [ ] 一次可上传多份文档，均通过校验后入库进入切分流水线。
- [ ] 重复（同内容改名重传应被判重）/超限/类型不符/空文件任一情况下，用户在上传界面即得到明确中文错误；同一批次内其余合法文件正常入库。
- [ ] 同名但内容不同的文件允许共存（哈希判重不误伤）。
- [ ] 纯图片型 PDF 上传成功、状态为「不可检索」、不投递切分任务、可在列表预览。
- [ ] 列表内文档可打开预览；有文字内容显示文本，纯图片 PDF 可逐页看图。
- [ ] 现有单文件上传与删除行为不回归。

## Out of Scope

- 上传进度条 / 断点续传 / 拖拽排序等增强交互（本期不做，除非实现成本极低顺带）。
- OCR 文字识别（图片型 PDF 仍不提供文本检索，仅可预览与拒收）。

## Notes

- 复杂任务，需 design.md + implement.md 后才能 start。批量传输形态（前端逐文件调用现有单文件接口 vs 后端单请求多文件）在 design.md 中决策。
