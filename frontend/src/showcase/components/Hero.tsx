/** 首屏四块附加文案：右栏 A CURIOUS MIND / 左下署名 / 右下 HELLO YOU 视线读数。 */
interface HeroProps {
  active: boolean;
  /** 八向视线读数（rAF 循环经 React state 下传 —— 仅 9 个离散值，变更频率低） */
  gaze: string;
}

export function Hero({ active, gaze }: HeroProps) {
  return (
    <div className={`hero${active ? " is-active" : ""}`} data-hero>
      <aside className="hero__aside">
        {/* 折行写死 <br>：最长一行 5.556em，回退字体下也不换行错乱。
            原为 h2 —— 但它在 DOM 中先于主标题 h1（AGENTS THAT WORK.），标题层级倒序；
            这两块是装饰性字组，降为 p 语义更准确 */}
        <p className="hero__aside-title">
          AGENT
          <br />
          MIND.
        </p>
        <p className="hero__aside-desc">
          观察任务，也观察流程。
          <br />
          每一次重复操作，都可能成为
          <br />
          下一个智能体的起点。
        </p>
      </aside>

      <p className="hero__foot">
        我把大模型从「聊天工具」变成「能自己干活的执行者」。
        <br />
        流程交给它们，判断留给人类，也给涌现的能力，留一点敬畏。
      </p>

      <aside className="hero__gaze">
        <p className="hero__gaze-title">HELLO, YOU.</p>
        <p className="hero__gaze-desc">移动鼠标，我会看向你的位置。</p>
        <p className="hero__gaze-read" data-gaze aria-live="off">
          {gaze}
        </p>
      </aside>
    </div>
  );
}
