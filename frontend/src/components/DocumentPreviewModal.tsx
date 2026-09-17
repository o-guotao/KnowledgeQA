import { ChevronLeft, ChevronRight, FileSpreadsheet, FileText, Image as ImageIcon, Loader2, Table2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { getFileBytes } from "../api/client";
import type { KnowledgeDocument } from "../api/schemas";
import { Button } from "./ui/button";

interface DocumentPreviewModalProps {
  document: KnowledgeDocument;
  onClose: () => void;
}

export type DocKind = "pdf" | "text" | "image" | "docx" | "xlsx";

/** 按扩展名选择预览渲染器 */
export function docKind(filename: string): DocKind {
  const n = filename.toLowerCase();
  if (n.endsWith(".pdf")) return "pdf";
  if (n.endsWith(".png") || n.endsWith(".jpg") || n.endsWith(".jpeg") || n.endsWith(".webp")) return "image";
  if (n.endsWith(".docx")) return "docx";
  if (n.endsWith(".xlsx")) return "xlsx";
  return "text";
}

function imageMime(filename: string): string {
  const n = filename.toLowerCase();
  if (n.endsWith(".png")) return "image/png";
  if (n.endsWith(".webp")) return "image/webp";
  return "image/jpeg";
}

type PreviewState =
  | { kind: "loading" }
  | { kind: "text"; text: string }
  | { kind: "error"; message: string };

/** 静默吞掉异步清理（destroy/cancel）可能产生的 rejection，避免 unhandled rejection。 */
function swallow(p: unknown): void {
  if (p && typeof (p as Promise<unknown>).catch === "function") {
    (p as Promise<unknown>).catch(() => undefined);
  }
}

const KIND_META: Record<DocKind, { label: string; cls: string }> = {
  pdf: { label: "PDF", cls: "bg-red-500/10 text-red-600 border-red-500/20" },
  text: { label: "文本", cls: "bg-slate-500/10 text-slate-500 border-slate-500/20" },
  image: { label: "图片", cls: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" },
  docx: { label: "Word", cls: "bg-blue-500/10 text-blue-600 border-blue-500/20" },
  xlsx: { label: "表格", cls: "bg-indigo-500/10 text-indigo-600 border-indigo-500/20" },
};

/** 文档预览弹窗：按文件类型分发渲染——
 * pdf 用 pdf.js 逐页渲染；txt/md 显示 UTF-8 文本；图片用原图 blob；
 * docx 用 docx-preview 保留排版；xlsx 用 SheetJS 渲染表格 + sheet 切换。 */
export function DocumentPreviewModal({ document, onClose }: DocumentPreviewModalProps) {
  const [state, setState] = useState<PreviewState>({ kind: "loading" });
  const [numPages, setNumPages] = useState(0);
  const [pageNo, setPageNo] = useState(1);
  const [renderErr, setRenderErr] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [sheets, setSheets] = useState<string[]>([]);
  const [sheetIdx, setSheetIdx] = useState(0);
  const [sheetRows, setSheetRows] = useState<string[][]>([]);
  const [sheetTruncated, setSheetTruncated] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const docxRef = useRef<HTMLDivElement>(null);
  // pdfjs 文档句柄（含 destroy/getPage/numPages），类型随运行时对象，宽松处理
  const docHandle = useRef<any>(null);
  // 进行中的 PDF 加载任务（可 destroy 以中断加载）与当前渲染任务（可 cancel 以让出 canvas）
  const loadingTaskRef = useRef<any>(null);
  const renderTaskRef = useRef<any>(null);
  // xlsx workbook 缓存：切 sheet 时避免重复取字节/重新解析
  const workbookRef = useRef<{ wb: import("xlsx").WorkBook; XLSX: typeof import("xlsx") } | null>(null);
  const kind = docKind(document.filename);
  const isPdfDoc = kind === "pdf";

  // 图片：取字节转 blob URL（卸载/换文档时 revoke 防泄漏）
  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;
    if (kind === "image") {
      getFileBytes(document.id)
        .then((buf) => {
          if (cancelled) return;
          url = URL.createObjectURL(new Blob([buf], { type: imageMime(document.filename) }));
          setImageUrl(url);
          setState({ kind: "text", text: "" }); // 图片用 imageUrl 渲染，text 为空占位
        })
        .catch((err) => {
          if (!cancelled) setState({ kind: "error", message: err instanceof Error ? err.message : "读取失败" });
        });
    }
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
      setImageUrl(null);
    };
  }, [document, kind]);

  // docx：懒加载 docx-preview 渲染到容器
  useEffect(() => {
    let cancelled = false;
    if (kind !== "docx") return;
    setState({ kind: "loading" });
    (async () => {
      try {
        const buf = await getFileBytes(document.id);
        if (cancelled) return;
        const { renderAsync } = await import("docx-preview");
        if (cancelled || !docxRef.current) return;
        await renderAsync(buf, docxRef.current, undefined, {
          inWrapper: true,
          ignoreLastRenderedPageBreak: true,
        });
        // 安全：文档中可夹带外部超链接（团队空间他人上传），预览只做展示不可跳转
        docxRef.current.querySelectorAll("a").forEach((a) => {
          a.removeAttribute("href");
          a.style.pointerEvents = "none";
          a.style.textDecoration = "underline";
        });
        if (!cancelled) setState({ kind: "text", text: "" }); // docx 用容器渲染，text 为空占位
      } catch (err) {
        console.error("docx preview failed", err);
        if (!cancelled) setState({ kind: "error", message: `文档无法渲染（${err instanceof Error ? err.message : "未知错误"}）` });
      }
    })();
    return () => {
      cancelled = true;
      if (docxRef.current) docxRef.current.innerHTML = "";
    };
  }, [document, kind]);

  // xlsx：懒加载 SheetJS 解析为结构化行数据（React 渲染天然转义，避免 sheet_to_html 的注入面）
  useEffect(() => {
    let cancelled = false;
    if (kind !== "xlsx") return;
    setState({ kind: "loading" });
    (async () => {
      try {
        const buf = await getFileBytes(document.id);
        if (cancelled) return;
        const XLSX = await import("xlsx");
        if (cancelled) return;
        const wb = XLSX.read(buf, { type: "array" });
        if (cancelled) return;
        workbookRef.current = { wb, XLSX };
        const names = wb.SheetNames;
        setSheets(names);
        setSheetIdx(0);
        applySheetRows(0);
        setState({ kind: "text", text: "" }); // xlsx 用 sheetRows 渲染，text 为空占位
      } catch (err) {
        console.error("xlsx preview failed", err);
        if (!cancelled) setState({ kind: "error", message: `表格无法解析（${err instanceof Error ? err.message : "未知错误"}）` });
      }
    })();
    return () => {
      cancelled = true;
      workbookRef.current = null;
    };
  }, [document, kind]);

  // 装载文本
  useEffect(() => {
    let cancelled = false;
    if (kind === "text") {
      getFileBytes(document.id)
        .then((buf) => {
          if (cancelled) return;
          const text = new TextDecoder("utf-8").decode(buf);
          setState(text.trim() ? { kind: "text", text } : { kind: "error", message: "无可预览的文本内容" });
        })
        .catch((err) => {
          if (!cancelled) setState({ kind: "error", message: err instanceof Error ? err.message : "读取失败" });
        });
    }
    return () => {
      cancelled = true;
    };
  }, [document, kind]);

  // 装载 PDF（懒加载 pdfjs-dist；每次渲染当前页）
  useEffect(() => {
    if (!isPdfDoc) return;
    let disposed = false;
    (async () => {
      // 取字节失败（404/越权/网络）直接透出错误信息，不误报为“PDF 解析失败”
      let buf: ArrayBuffer;
      try {
        buf = await getFileBytes(document.id);
      } catch (err) {
        if (!disposed) setState({ kind: "error", message: err instanceof Error ? err.message : "读取失败" });
        return;
      }
      if (disposed) return;
      try {
        const pdfjs = await import("pdfjs-dist");
        if (disposed) return;
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();
        const loadingTask = pdfjs.getDocument({ data: new Uint8Array(buf) });
        loadingTaskRef.current = loadingTask;
        const pdf = await loadingTask.promise;
        loadingTaskRef.current = null;
        if (disposed) {
          // 卸载/换文档发生在加载完成瞬间：立即释放，避免残留
          swallow(pdf.destroy());
          return;
        }
        docHandle.current = pdf;
        setState({ kind: "text", text: "" }); // PDF 用 canvas 渲染，text 为空占位
        setNumPages(pdf.numPages);
        setPageNo(1);
      } catch (err) {
        if (!disposed) {
          setState({ kind: "error", message: `PDF 无法解析（${err instanceof Error ? err.message : "未知错误"}）` });
        }
      }
    })();
    return () => {
      disposed = true;
      // 中断尚未完成的加载（若已加载完成则 docHandle 承担释放）
      swallow(loadingTaskRef.current?.destroy());
      loadingTaskRef.current = null;
      swallow(docHandle.current?.destroy());
      docHandle.current = null;
    };
  }, [document, isPdfDoc]);

  // PDF 当前页渲染到 canvas
  useEffect(() => {
    if (!isPdfDoc || !numPages) return;
    let cancelled = false;
    let renderTask: any = null;
    (async () => {
      const pdf = docHandle.current;
      if (!pdf) return;
      try {
        const page = await pdf.getPage(pageNo);
        if (cancelled) return;
        const canvas = canvasRef.current;
        const container = containerRef.current;
        if (!canvas || !container) return;
        const targetWidth = Math.max(320, Math.min(760, container.clientWidth - 48));
        const base = page.getViewport({ scale: 1 });
        const scale = targetWidth / base.width;
        const viewport = page.getViewport({ scale });
        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * dpr);
        canvas.height = Math.floor(viewport.height * dpr);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        renderTask = page.render({
          canvasContext: ctx,
          viewport,
          transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
        });
        renderTaskRef.current = renderTask;
        await renderTask.promise;
        if (cancelled) return; // 避免卸载/换页后 setState
        setRenderErr(null);
      } catch (err) {
        if (!cancelled) setRenderErr(err instanceof Error ? err.message : "渲染失败");
      } finally {
        // 仅在仍是本任务时清引用，避免误清下一个渲染任务
        if (renderTaskRef.current === renderTask) renderTaskRef.current = null;
      }
    })();
    return () => {
      cancelled = true;
      // 快速翻页/关闭时取消在途渲染，避免同一 canvas 并发 render 抛错或写脏画面
      renderTaskRef.current?.cancel?.();
      renderTaskRef.current = null;
    };
  }, [isPdfDoc, numPages, pageNo]);

  // 大表只预览前 500 行，避免渲染卡顿；其余提示截断
  const MAX_PREVIEW_ROWS = 500;

  /** 从缓存的 workbook 取第 idx 个 sheet 的行数据写入状态 */
  function applySheetRows(idx: number): void {
    const cached = workbookRef.current;
    if (!cached) return;
    const { wb, XLSX } = cached;
    const name = wb.SheetNames[idx];
    const ws = name ? wb.Sheets[name] : undefined;
    if (!ws) {
      setSheetRows([]);
      setSheetTruncated(false);
      return;
    }
    // header:1 取二维数组，defval 补空、raw:false 取格式化后的显示字符串
    const rows = XLSX.utils.sheet_to_json<unknown[]>(ws, { header: 1, raw: false, defval: "" });
    const mapped = rows.map((r) => r.map((v) => String(v ?? "")));
    setSheetRows(mapped.slice(0, MAX_PREVIEW_ROWS));
    setSheetTruncated(mapped.length > MAX_PREVIEW_ROWS);
  }

  // xlsx 切 sheet：直接读内存中缓存的 workbook，无需重复取字节
  const switchSheet = (idx: number) => {
    setSheetIdx(idx);
    applySheetRows(idx);
  };

  const goPage = (next: number) => {
    const n = Math.max(1, Math.min(numPages, next));
    setPageNo(n);
  };

  const meta = KIND_META[kind];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 sm:p-8"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            {kind === "image" ? (
              <ImageIcon size={16} className="shrink-0 text-emerald-500" />
            ) : kind === "xlsx" ? (
              <FileSpreadsheet size={16} className="shrink-0 text-indigo-500" />
            ) : kind === "docx" ? (
              <FileText size={16} className="shrink-0 text-blue-500" />
            ) : (
              <FileText size={16} className="shrink-0 text-slate-400" />
            )}
            <p className="truncate text-sm font-medium text-ink" title={document.filename}>
              {document.filename}
            </p>
            <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-medium ${meta.cls}`}>
              {meta.label}
            </span>
          </div>
          <Button variant="ghost" size="icon" aria-label="关闭预览" onClick={onClose} className="cursor-pointer">
            <X size={18} />
          </Button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          {state.kind === "loading" && kind !== "docx" ? (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-400">
              <Loader2 size={16} className="animate-spin" /> 加载中…
            </div>
          ) : state.kind === "error" ? (
            <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-red-600">
              <p>{state.message}</p>
              <Button variant="outline" size="sm" onClick={onClose} className="cursor-pointer">
                关闭
              </Button>
            </div>
          ) : isPdfDoc ? (
            <div ref={containerRef} className="flex min-h-0 flex-1 flex-col overflow-auto bg-slate-100 p-6">
              {renderErr ? (
                <div className="text-sm text-red-600">本页渲染失败：{renderErr}</div>
              ) : (
                <div className="mx-auto">
                  <canvas ref={canvasRef} className="mx-auto rounded shadow" />
                </div>
              )}
            </div>
          ) : kind === "image" ? (
            <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-slate-100 p-6">
              {imageUrl && (
                <img
                  src={imageUrl}
                  alt={document.filename}
                  className="max-h-full max-w-full rounded shadow cursor-zoom-in object-contain"
                  onClick={(e) => {
                    const el = e.currentTarget;
                    el.classList.toggle("max-h-full");
                    el.classList.toggle("max-w-full");
                    el.classList.toggle("cursor-zoom-in");
                    el.classList.toggle("cursor-zoom-out");
                  }}
                />
              )}
            </div>
          ) : kind === "docx" ? (
            <div className="min-h-0 flex-1 overflow-auto bg-slate-100 p-6">
              {/* 容器必须始终挂载：effect 里 renderAsync 直接写入它，loading 期间只是被覆盖层盖住 */}
              <div ref={docxRef} className="mx-auto w-fit" />
              {state.kind === "loading" && (
                <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-400">
                  <Loader2 size={16} className="animate-spin" /> 加载中…
                </div>
              )}
            </div>
          ) : kind === "xlsx" ? (
            <div className="min-h-0 flex-1 overflow-auto bg-slate-50 p-6">
              {sheetRows.length > 0 ? (
                <div className="mx-auto max-w-full space-y-2">
                  <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
                    <table className="border-collapse text-[13px] text-slate-900">
                      <tbody>
                        {sheetRows.map((row, ri) => (
                          <tr key={ri} className={ri === 0 ? "bg-slate-100" : ri % 2 === 0 ? "bg-slate-50" : "bg-white"}>
                            {row.map((cell, ci) =>
                              ri === 0 ? (
                                <th key={ci} className="sticky top-0 max-w-[320px] truncate border border-slate-200 px-3 py-1.5 text-left font-semibold text-slate-700">
                                  {cell}
                                </th>
                              ) : (
                                <td key={ci} className="max-w-[320px] truncate border border-slate-200 px-3 py-1.5 text-left hover:bg-blue-50">
                                  {cell}
                                </td>
                              ),
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {sheetTruncated && (
                    <p className="text-xs text-slate-400">仅预览前 {MAX_PREVIEW_ROWS} 行，完整内容请下载查看</p>
                  )}
                </div>
              ) : (
                <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-400">
                  <Loader2 size={16} className="animate-spin" /> 渲染中…
                </div>
              )}
            </div>
          ) : (
            <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words p-6 text-sm leading-6 text-ink">
              {state.kind === "text" ? state.text : ""}
            </pre>
          )}
        </div>

        {isPdfDoc && numPages > 0 && (
          <div className="flex items-center justify-center gap-4 border-t border-slate-100 px-4 py-2.5 text-sm text-slate-600">
            <Button
              variant="ghost"
              size="icon"
              aria-label="上一页"
              disabled={pageNo <= 1}
              onClick={() => goPage(pageNo - 1)}
              className="cursor-pointer"
            >
              <ChevronLeft size={18} />
            </Button>
            <span>
              第 {pageNo} / {numPages} 页
            </span>
            <Button
              variant="ghost"
              size="icon"
              aria-label="下一页"
              disabled={pageNo >= numPages}
              onClick={() => goPage(pageNo + 1)}
              className="cursor-pointer"
            >
              <ChevronRight size={18} />
            </Button>
          </div>
        )}

        {kind === "xlsx" && sheets.length > 1 && (
          <div className="flex items-center justify-center gap-2 overflow-x-auto border-t border-slate-100 px-4 py-2.5 text-sm">
            <Table2 size={14} className="shrink-0 text-slate-400" />
            {sheets.map((name, idx) => (
              <button
                key={name}
                type="button"
                onClick={() => switchSheet(idx)}
                className={`shrink-0 cursor-pointer rounded-md border px-2.5 py-1 text-xs transition-colors ${
                  idx === sheetIdx
                    ? "border-blue-500/30 bg-blue-500/10 font-medium text-blue-600"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {name}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
