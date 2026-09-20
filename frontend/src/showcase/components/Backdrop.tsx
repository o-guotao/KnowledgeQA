import type { RefObject } from "react";

/** 背景层键与文案层同源：'0'=个人简历(intro.jpeg) / '1'=作品文件夹(beat-1) / '3'=无限可能(beat-3)。
 *  初次见遇与作品预览刻意不给层，直接落回底图（bg-wall.jpeg）。 */
interface BackdropProps {
  copyKey: string;
  /** data-drop 层（无限可能）：transform 由 rAF 循环按滚动进度直写 */
  dropRef: RefObject<HTMLDivElement>;
  /** 根元素：视差降级时由循环写入 --par CSS 变量 */
  rootRef: RefObject<HTMLDivElement>;
  /** 作品文件夹打开时：beat-1 背景人物向右下缩放，给弹图让位 */
  shrunk?: boolean;
}

export function Backdrop({ copyKey, dropRef, rootRef, shrunk = false }: BackdropProps) {
  return (
    <div className="backdrop" aria-hidden="true" ref={rootRef}>
      <div
        className={`backdrop__scene${copyKey === "0" ? " is-active" : ""}`}
        style={{ ["--scene" as string]: "url(/media/intro.jpeg)" }}
      />
      <div
        className={`backdrop__scene${copyKey === "1" ? " is-active" : ""}${shrunk ? " is-shrunk" : ""}`}
        style={{ ["--scene" as string]: "url(/media/bg-wall.jpeg)" }}
      >
        {/* 人物是独立元素：缩放只动它，背景墙面（bg-wall）始终全屏不动 */}
        <img className="backdrop__person" src="/media/beat-1-person.png" alt="" />
      </div>
      <div
        className={`backdrop__scene${copyKey === "3" ? " is-active" : ""}`}
        data-drop=""
        ref={dropRef}
        style={{ ["--scene" as string]: "url(/media/beat-3.jpeg)" }}
      />
    </div>
  );
}
