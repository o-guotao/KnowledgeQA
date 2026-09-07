import { ChevronLeft, ChevronRight, FileText, Loader2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { getFileBytes } from "../api/client";
import type { KnowledgeDocument } from "../api/schemas";
import { Button } from "./ui/button";

interface DocumentPreviewModalProps {
  document: KnowledgeDocument;
  onClose: () => void;
}

type PreviewState =
  | { kind: "loading" }
  | { kind: "text"; text: string }
  | { kind: "error"; message: string };

function isPdf(name: string): boolean {
  return name.toLowerCase().endsWith(".pdf");
}

/** 静默吞掉异步清理（destroy/cancel）可能产生的 rejection，避免 unhandled rejection。 */
function swallow(p: unknown): void {
  if (p && typeof (p as Promise<unknown>).catch === "function") {
    (p as Promise<unknown>).catch(() => undefined);
  }
}

/** 文档预览弹窗：.txt/.md/.markdown 显示 UTF-8 文本；.pdf 用 pdf.js 逐页渲染（覆盖文字/纯图片 PDF）。 */
export function DocumentPreviewModal({ document, onClose }: DocumentPreviewModalProps) {
  const [state, setState] = useState<PreviewState>({ kind: "loading" });
  const [numPages, setNumPages] = useState(0);
  const [pageNo, setPageNo] = useState(1);
  const [renderErr, setRenderErr] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  // pdfjs 文档句柄（含 destroy/getPage/numPages），类型随运行时对象，宽松处理
  const docHandle = useRef<any>(null);
  // 进行中的 PDF 加载任务（可 destroy 以中断加载）与当前渲染任务（可 cancel 以让出 canvas）
  const loadingTaskRef = useRef<any>(null);
  const renderTaskRef = useRef<any>(null);
  const isPdfDoc = isPdf(document.filename);

  // 装载文本
  useEffect(() => {
    let cancelled = false;
    if (!isPdfDoc) {
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
  }, [document, isPdfDoc]);

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

  const goPage = (next: number) => {
    const n = Math.max(1, Math.min(numPages, next));
    setPageNo(n);
  };

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
            <FileText size={16} className="shrink-0 text-slate-400" />
            <p className="truncate text-sm font-medium text-ink" title={document.filename}>
              {document.filename}
            </p>
          </div>
          <Button variant="ghost" size="icon" aria-label="关闭预览" onClick={onClose} className="cursor-pointer">
            <X size={18} />
          </Button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          {state.kind === "loading" ? (
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
          ) : (
            <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words p-6 text-sm leading-6 text-ink">
              {state.text}
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
      </div>
    </div>
  );
}
