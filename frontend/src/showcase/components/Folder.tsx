import { useEffect, useRef } from "react";

/**
 * 作品文件夹面板（v2 交互序列）：
 * 1. PortFolio-bg 按钮停靠面板左下侧（合着的橙色文件夹）；
 * 2. 点击 → beat-2 弹图弹出（蓝色背景已键控透明，整图保留、底部不裁剪）；
 * 3. 弹图就位后才出现「收起文件夹」——收起按钮 / ESC / 空白栏都只收起弹图，
 *    不跳节；继续叙事靠滚动。
 */
interface FolderProps {
  /** copyKey === '1' 时该节可见 */
  active: boolean;
  open: boolean;
  /** 收起弹出的图片（收起按钮 / ESC / 点空白栏） */
  onClose: () => void;
  /** PortFolio-bg 按钮：合 → 开 */
  onToggle: () => void;
}

export function Folder({ active, open, onClose, onToggle }: FolderProps) {
  const openBtnRef = useRef<HTMLButtonElement | null>(null);

  // 键盘可达：ESC 收起（仅面板在屏上时才动滚动，别的节按 ESC 不该弹走）
  useEffect(() => {
    if (!active || !open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === "Esc") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, open, onClose]);

  // 合上时把焦点交回 PortFolio-bg 按钮：被隐藏的状态不能继续持有焦点。
  // 必须等 0.3s 的 visibility 延迟过渡结束再聚焦 —— 立即 focus() 时按钮仍是
  // visibility:hidden，浏览器会静默忽略（焦点丢到 <body>）。
  // 且只在「打开过又收起」时回焦点，页面首载不抢焦点。
  const wasOpenRef = useRef(open);
  useEffect(() => {
    const wasOpen = wasOpenRef.current;
    wasOpenRef.current = open;
    if (!wasOpen || open) return;
    const t = setTimeout(() => {
      if (document.activeElement === document.body) {
        openBtnRef.current?.focus();
      }
    }, 320);
    return () => clearTimeout(t);
  }, [open]);

  return (
    <section
      className={`copy copy--panel folder${active ? " is-active" : ""}${open ? " is-open" : ""}`}
      data-copy="1"
      aria-label="作品文件夹"
    >
      <header className="folder__head">
        <p className="folder__eyebrow">BIAOGE / SELECTED WORK</p>
        <h2 className="folder__title">A FOLDER FULL OF IDEAS.</h2>
        {/* 打开后才出现「收起文件夹」（交互序列第 3 步） */}
        {open ? (
          <button type="button" className="folder__close" onClick={onClose}>
            收起文件夹 <span className="folder__close-x" aria-hidden="true">✕</span>
          </button>
        ) : null}
      </header>

      <div
        className="folder__deck"
        onClick={(e) => {
          // 点空白栏收起：可点区只挂 deck 这一块（按钮/弹图是「东西」，不算空白）
          if (e.target instanceof Element && e.target.closest(".folder__openbtn, .folder__beat2")) return;
          if (active && open) onClose();
        }}
      >
        {/* PortFolio-bg 按钮：停靠面板左下侧（交互序列第 1 步） */}
        <button
          type="button"
          className="folder__openbtn"
          onClick={onToggle}
          aria-expanded={open ? "true" : "false"}
          aria-label={open ? "合上作品文件夹" : "翻开作品文件夹"}
          ref={openBtnRef}
        >
          <img className="folder__openbtn-art" src="/media/folder.png" alt="" />
        </button>

        {/* beat-2 弹图：蓝色背景已键控为透明（整图保留，底部不裁剪） */}
        <div className="folder__beat2" aria-hidden={open ? "false" : "true"}>
          <div className="folder__beat2-frame">
            <img
              className="folder__beat2-art"
              src="/media/beat-2-nobg.png"
              alt="作品文件夹内页：RAG知识库、网站设计、Agent设计三张卡片"
            />
          </div>
        </div>
      </div>

      <p className="folder__hint">
        三指 · 开合 · 翻页
        <span className="folder__hint-sep" aria-hidden="true">/</span>
        点击空白栏或按 ESC 收起
      </p>
    </section>
  );
}
