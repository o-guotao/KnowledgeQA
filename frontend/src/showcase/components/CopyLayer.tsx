import type { ReactNode } from "react";

/** 互斥文案层：intro / 个人简历 / 无限可能 的普通文案块；作品文件夹与作品预览作为 children 注入。 */
interface CopyLayerProps {
  copyKey: string;
  onGoToSection: (i: number) => void;
  children?: ReactNode;
}

export function CopyLayer({ copyKey, onGoToSection, children }: CopyLayerProps) {
  return (
    <div className="copy-layer">
      <article className={`copy${copyKey === "intro" ? " is-active" : ""}`} data-copy="intro" data-pos="left">
        <p className="copy__eyebrow">BIAOGE / AGENT DESIGN STUDIO</p>
        <h1 className="copy__title">
          AGENTS
          <br />
          THAT
          <br />
          WORK.
        </h1>
        <p className="copy__desc">
          嗨，我是表哥。
          <br />
          把流程拆给 Agent，把判断留给人。
        </p>
        <a
          className="cta"
          href="#work"
          onClick={(e) => {
            e.preventDefault();
            onGoToSection(2);
          }}
        >
          <span>先认识我，再看作品</span>
          <i className="cta__icon" aria-hidden="true">↗</i>
        </a>
      </article>

      <article className={`copy${copyKey === "0" ? " is-active" : ""}`} data-copy="0" data-pos="left">
        <p className="copy__eyebrow">
          <b>02</b> PHILOSOPHY / 设计理念
        </p>
        <h2 className="copy__title">
          PROMPT.
          <br />
          PLAN.
          <br />
          ACT.
        </h2>
        <p className="copy__desc">让模型不止会聊天，还能把活干完。</p>
      </article>

      {children}

      <article className={`copy${copyKey === "3" ? " is-active" : ""}`} data-copy="3" data-pos="bottom">
        <p className="copy__eyebrow">
          <b>05</b> BEYOND / 无限可能
        </p>
        <h2 className="copy__title">
          STILL
          <br />
          ROLLING.
        </h2>
        <p className="copy__desc">模型会一直变，好奇心不会——所以我还在往前滚。</p>
      </article>
    </div>
  );
}
