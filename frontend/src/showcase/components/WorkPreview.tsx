import { useState } from "react";

/** 「作品预览」节：iframe 实时内嵌 /app（所见即所得）+ 三张可点卡片。 */
const CARDS = [
  {
    key: "rag",
    art: "/media/card-rag.png",
    title: "RAG知识库",
    desc: "检索增强生成的企业问答 Agent：上传、切分、召回、带引用回答。",
    href: "/app",
    enabled: true,
  },
  {
    key: "web",
    art: "/media/card-web.png",
    title: "网站设计",
    desc: "本页 —— Agent 作品集门面：电影化滚动叙事。",
    href: null,
    enabled: false,
  },
  {
    key: "agent",
    art: "/media/card-agent.png",
    title: "Agent设计",
    desc: "能自己干活的执行者，正在路上。",
    href: null,
    enabled: false,
  },
] as const;

interface WorkPreviewProps {
  active: boolean;
}

export function WorkPreview({ active }: WorkPreviewProps) {
  // iframe 默认不吃指针（滚动叙事不被劫持），点「进入交互」后放行；离开该节自动收回
  const [live, setLive] = useState(false);
  const interactive = live && active;

  return (
    <article className={`copy copy--preview${active ? " is-active" : ""}`} data-copy="2" data-pos="top">
      <p className="copy__eyebrow">
        <b>04</b> PREVIEW / 作品预览
      </p>
      <h2 className="copy__title">
        RAG
        <br />
        WEB
        <br />
        AGENT.
      </h2>
      <p className="copy__desc">RAG、网站、Agent，三张卡片，三次把想法落地。</p>

      <div className={`preview-frame${interactive ? " is-live" : ""}`}>
        {interactive ? (
          <iframe
            className="preview-frame__view"
            src="/app"
            title="KnowledgeQA 实时预览"
          />
        ) : (
          <>
            {/* 静态底图用产品登录页截图（此前用 intro.jpeg 人像，与预览对象无关） */}
            <img className="preview-frame__ghost" src="/media/app-preview.png" alt="" aria-hidden="true" />
            <p className="sr-only">此处实时预览 KnowledgeQA 应用，需启用交互后体验。</p>
          </>
        )}
        {!active || interactive ? null : (
          <button type="button" className="preview-frame__enter" onClick={() => setLive(true)}>
            <span className="preview-frame__enter-pill">点击进入实时交互</span>
          </button>
        )}
        {interactive ? (
          <a className="preview-frame__open" href="/app" target="_blank" rel="noopener noreferrer" title="在新标签页全屏打开">
            全屏打开 ↗
          </a>
        ) : null}
      </div>

      <div className="preview-cards">
        {CARDS.map((c) =>
          c.enabled ? (
            <a key={c.key} className="preview-card is-enabled" href={c.href} title={`打开${c.title}`}>
              <img className="preview-card__art" src={c.art} alt="" loading="lazy" />
              <span className="preview-card__title">{c.title}</span>
              <span className="preview-card__desc">{c.desc}</span>
            </a>
          ) : (
            <div key={c.key} className="preview-card" aria-disabled="true" title="敬请期待">
              <img className="preview-card__art" src={c.art} alt="" loading="lazy" />
              <span className="preview-card__title">{c.title}</span>
              <span className="preview-card__desc">{c.desc}</span>
            </div>
          ),
        )}
      </div>
    </article>
  );
}
