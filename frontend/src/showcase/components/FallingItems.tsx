/**
 * 无限可能节的级联下坠元素：复用作品素材（folder/card PNG）作为图片元素，
 * 随滚动进度以不同延迟/速度/旋转从视口上方坠落 —— 「越落越快」的 easeInCubic
 * 与主背景图的下坠同一套纪律：由进度现算、可倒放、静止零写入。
 */
import { useEffect, useRef } from "react";
import type { RefObject } from "react";

import { CONFIG, clamp, sectionSpans } from "../showcaseMath";

/** 单个下坠元素：位置/尺寸/节奏（delay 与 fall 为该节长度的比例）。 */
interface FallItem {
  src: string;
  alt: string;
  left: string; // 水平位置（vw）
  top: string; // 落定后的纵向位置（vh）
  width: number; // px
  delay: number; // 起跳延迟（占节长比例）
  fall: number; // 下坠耗时（占节长比例）
  spin: number; // 下坠过程中的总旋转（deg），落定时归零
}

const ITEMS: FallItem[] = [
  { src: "/media/folder.png", alt: "", left: "7vw", top: "26vh", width: 150, delay: 0.0, fall: 0.42, spin: -7 },
  { src: "/media/card-rag.png", alt: "", left: "66vw", top: "22vh", width: 118, delay: 0.06, fall: 0.46, spin: 10 },
  { src: "/media/card-web.png", alt: "", left: "30vw", top: "50vh", width: 96, delay: 0.13, fall: 0.5, spin: -13 },
  { src: "/media/card-agent.png", alt: "", left: "79vw", top: "56vh", width: 108, delay: 0.09, fall: 0.44, spin: 6 },
  { src: "/media/card-rag.png", alt: "", left: "50vw", top: "38vh", width: 76, delay: 0.2, fall: 0.52, spin: 16 },
];

/** 起跳高度（vh）：元素从视口上方整段跌入；overflow:hidden 天然裁掉视口外的部分。 */
const FALL_FROM_VH = 135;

interface FallingItemsProps {
  /** copyKey === '3'（无限可能 / 收尾沿用） */
  active: boolean;
  /** 共享滚动进度（ShowcasePage 的 progressRef） */
  progressRef: RefObject<number>;
}

export function FallingItems({ active, progressRef }: FallingItemsProps) {
  const itemRefs = useRef<Array<HTMLImageElement | null>>([]);
  const lastStyles = useRef<string[]>([]);

  useEffect(() => {
    const span = sectionSpans()[CONFIG.beatCuts.length] ?? null;
    if (!span) return;
    let rafId = 0;

    const frame = () => {
      const p = progressRef.current ?? 0;
      const lp = clamp((p - span[0]) / (span[1] - span[0]), 0, 1); // 节内局部进度
      for (let i = 0; i < ITEMS.length; i++) {
        const el = itemRefs.current[i];
        if (!el) continue;
        const it = ITEMS[i];
        if (!it) continue;
        const u = clamp((lp - it.delay) / it.fall, 0, 1);
        const k = u * u * u; // easeInCubic：越落越快、落地即停
        const y = (k - 1) * FALL_FROM_VH; // vh；k=1 时精确为 0（落定）
        const rot = (1 - k) * it.spin; // 旋转随下坠同步收敛
        const style = `translate3d(0,${y.toFixed(2)}vh,0) rotate(${rot.toFixed(2)}deg)`;
        if (lastStyles.current[i] !== style) {
          lastStyles.current[i] = style;
          el.style.transform = style;
        }
      }
      rafId = window.requestAnimationFrame(frame);
    };

    rafId = window.requestAnimationFrame(frame);
    return () => window.cancelAnimationFrame(rafId);
  }, [progressRef]);

  return (
    <div className={`fall${active ? " is-active" : ""}`} aria-hidden="true">
      {ITEMS.map((it, i) => (
        <img
          key={`${it.src}-${i}`}
          src={it.src}
          alt={it.alt}
          className="fall__item"
          style={{ left: it.left, top: it.top, width: it.width }}
          ref={(el) => {
            itemRefs.current[i] = el;
          }}
        />
      ))}
    </div>
  );
}
