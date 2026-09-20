import type { RefObject } from "react";

import { SECTIONS, sectionTicks } from "../showcaseMath";

interface HudProps {
  /** 当前 copyKey → 派生序号与节文案（与导航同源） */
  copyKey: string;
  /** p 已离开首屏（滑轨提示行淡出） */
  scrolled: boolean;
  /** 高频写入由页面 rAF 循环直插（fill/knob/time/tot），本组件只持 DOM ref */
  fillRef: RefObject<HTMLElement>;
  knobRef: RefObject<HTMLElement>;
  timeRef: RefObject<HTMLElement>;
  totRef: RefObject<HTMLElement>;
  paused: boolean;
  onTogglePause: () => void;
}

export function Hud({ copyKey, scrolled, fillRef, knobRef, timeRef, totRef, paused, onTogglePause }: HudProps) {
  const sectionIndex = copyKey === "intro" ? 0 : Number(copyKey) + 1;
  const section = SECTIONS[sectionIndex] ?? SECTIONS[4];

  return (
    <div className={`hud${scrolled ? " is-scrolled" : ""}`}>
      <p className="scroll-hint">
        <span>SCROLL TO EXPLORE</span>
        <i className="scroll-hint__arrow" aria-hidden="true" />
      </p>

      <div className="hud__row">
        <span className="hud__cell hud__cell--left">
          <b>{String(sectionIndex + 1).padStart(2, "0")}</b> / <span>{section.en} {section.zh}</span>
        </span>

        <span className="hud__cell hud__cell--center">
          <span className="hud__track">
            <i className="hud__fill" ref={fillRef} />
            <i className="hud__knob" ref={knobRef} />
            {sectionTicks().map((t) => (
              <i
                key={t}
                className="hud__tick"
                aria-hidden="true"
                style={{ left: `${(t * 100).toFixed(2)}%` }}
              />
            ))}
          </span>
        </span>

        <span className="hud__cell hud__cell--right">
          <b ref={timeRef}>00:00</b> / <span ref={totRef}>00:10</span>
          <button
            type="button"
            className={`hud__pause${paused ? " is-paused" : ""}`}
            onClick={onTogglePause}
          >
            {paused ? "继续互动" : "暂停互动"}
          </button>
        </span>
      </div>
    </div>
  );
}
