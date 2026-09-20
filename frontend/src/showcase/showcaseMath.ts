/**
 * showcase 滚动叙事 — 纯函数与配置（自 public/showcase/showcase.js 等价移植）。
 *
 * 核心模型：滚动进度 p ∈ [0,1] 是唯一输入；p × main.duration = main.currentTime。
 * 本模块无 DOM 依赖，可在 node 里直接断言。
 */

export interface ShowcaseConfig {
  /** main 元数据到位前的兜底时长（秒）。页面总高度 = 该值 × 100vh。 */
  fallbackDuration: number;
  /** 四个节奏点的分界（占全长比例），对应五节导航（节的序号 = beat + 1）。 */
  beatCuts: number[];
  /** p <= 此值 → intro 段（首屏，鼠标擦洗）。 */
  introAt: number;
  /** p >= 此值 → outro 段（静态图淡入叠在 main 末帧上）。 */
  outroAt: number;
  /** 秒。差距小于它就直接收敛，不再阻尼。 */
  seekDeadzone: number;
  /** 阻尼系数，越大越跟手、越小越顺滑。 */
  ease: number;
  /** 单帧最大推进秒数，防止快速滚动时一次跳太远。 */
  maxStep: number;
  intro: {
    mode: "scrub" | "loop";
    invert: boolean;
    ease: number;
    /** 离开首屏时「回正」的阻尼，比跟手快：要落在 0.5s 淡出内。 */
    resetEase: number;
    /** 回正到哪一帧（占总长比例）。0 = 片头。 */
    resetAt: number;
    /** 纵向微位移幅度(px)，纯触感反馈。 */
    tiltY: number;
    fallbackDuration: number;
  };
  sceneDrop: {
    /** 下落占该节长度的比例，其余时间静止在落点。 */
    dropSpan: number;
    /** 起始位移（层高的倍数）。-1 = 整体在视口上方。 */
    from: number;
  };
}

export const CONFIG: ShowcaseConfig = {
  /** main 元数据到位前的兜底时长（秒）。页面总高度 = 该值 × 100vh。
   *  取 10 与 intro-loop.mp4 的 10.04s 对齐：HUD 总时间码在首屏（intro 时长）与
   *  其余节（该值）之间不再出现 00:10 → 00:06 的跳变。放入 main.mp4 后由真实时长接管。 */
  fallbackDuration: 10,
  /** 四个节奏点的分界（占全长比例），对应五节导航（节的序号 = beat + 1）。
   *  main.mp4 已导入（10.04s 单镜头人物转头动画：正脸 → 侧脸 → 大笑 → 回正），
   *  视频内无场景切换点，五节叙事由文案层与背景分镜承载 —— 故分界保持等分节奏，
   *  各节画面分别落在 1.6-3.6s（侧脸）/ 3.6-5.6s（笑）/ 5.6-7.6s（正面）/ 7.6-9.8s（回正）。 */
  beatCuts: [0.36, 0.56, 0.76],
  /** p <= 此值 → intro 段（首屏，鼠标擦洗）。≈ 一屏（80vh 滚动量）。 */
  introAt: 0.16,
  /** p >= 此值 → outro 段（静态图淡入叠在 main 末帧上）。 */
  outroAt: 0.98,
  seekDeadzone: 0.02,
  ease: 0.18,
  maxStep: 0.35,
  intro: {
    mode: "scrub",
    invert: false,
    ease: 0.12,
    resetEase: 0.26,
    resetAt: 0,
    tiltY: 8,
    /* 与 intro-loop.mp4 的 10.04s 对齐：loadedmetadata 前 HUD 时间码不再瞬显 00:05 */
    fallbackDuration: 10,
  },
  sceneDrop: {
    /** 下落占该节长度的比例，其余时间静止在落点。
     *  取 0.22：完成点早于导航落点（节内 25%），点导航进来时主图已完全落下覆盖全屏。 */
    dropSpan: 0.22,
    from: -1,
  },
};

export function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}

export type Segment = "intro" | "main" | "outro";

/** 滚动进度 → 生效段 */
export function segmentOf(p: number): Segment {
  if (p <= CONFIG.introAt) return "intro";
  if (p >= CONFIG.outroAt) return "outro";
  return "main";
}

/** 滚动进度 → 主视频时间（秒） */
export function progressToTime(p: number, duration: number): number {
  return clamp(p, 0, 1) * duration;
}

/** 滚动进度 → 第几个节奏点（0 起）。只吃 p —— 与视频时长完全无关。 */
export function beatIndexAt(p: number): number {
  const cuts = CONFIG.beatCuts;
  for (let i = 0; i < cuts.length; i++) {
    const cut = cuts[i];
    if (cut !== undefined && p < cut) return i;
  }
  return cuts.length; // 收尾沿用最后一段画面
}

/** 秒 → "mm:ss" */
export function formatTime(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}

/** 分节刻度在滑轨上的位置（0..1）。取自 beatCuts，与导航、HUD 序号同源。 */
export function sectionTicks(): number[] {
  return CONFIG.beatCuts.slice();
}

/** 每一节的进度区间 [[起, 止], ...]，不含首屏；末节到 outroAt。 */
export function sectionSpans(): Array<[number, number]> {
  const cuts = CONFIG.beatCuts;
  const spans: Array<[number, number]> = [];
  let prev = CONFIG.introAt;
  for (let i = 0; i < cuts.length; i++) {
    const cut = cuts[i];
    if (cut === undefined) break;
    spans.push([prev, cut]);
    prev = cut;
  }
  spans.push([prev, CONFIG.outroAt]);
  return spans;
}

/** 第 i 个导航节（0 = 首屏）该滚到哪个进度。取该节前 25% 处，稳稳落在节内。 */
export function sectionTarget(i: number): number {
  if (i <= 0) return 0;
  const spans = sectionSpans();
  const s = spans[i - 1];
  if (!s) return 1;
  return s[0] + (s[1] - s[0]) * 0.25;
}

/** 「无限可能」背景层的下坠位移（占层高的倍数，负值 = 在视口上方）。easeInCubic。 */
export function sceneDropY(p: number, span: [number, number] | null): number {
  if (!span) return 0;
  const w = (span[1] - span[0]) * CONFIG.sceneDrop.dropSpan;
  if (!(w > 0)) return 0;
  const u = clamp((p - span[0]) / w, 0, 1);
  const k = u * u * u;
  return CONFIG.sceneDrop.from * (1 - k);
}

/** 八向视线标签。y 轴向下为正（屏幕坐标系），90° 是 DOWN。 */
const GAZE_LABELS = [
  "LOOKING RIGHT", //   0°
  "LOOKING DOWN RIGHT", // 45°
  "LOOKING DOWN", // 90°
  "LOOKING DOWN LEFT", // 135°
  "LOOKING LEFT", // 180°
  "LOOKING UP LEFT", // 225°
  "LOOKING UP", // 270°
  "LOOKING UP RIGHT", // 315°
] as const;

export function gazeLabel(x01: number, y01: number, dead = 0.14): string {
  const dx = clamp(x01, 0, 1) - 0.5;
  const dy = clamp(y01, 0, 1) - 0.5;
  const r = Math.sqrt(dx * dx + dy * dy);
  if (r < dead) return "LOOKING AT YOU";
  const deg = (Math.atan2(dy, dx) * 180) / Math.PI; // -180..180
  const i = Math.round(((deg + 360) % 360) / 45) % 8;
  return GAZE_LABELS[i] ?? "LOOKING AT YOU";
}

/** 首屏该不该把 introApplied 写进 currentTime（回正的门条件）。 */
export function shouldWriteIntro(
  seg: Segment,
  introApplied: number,
  introWritten: number | null,
  resetT: number,
): boolean {
  if (introApplied === introWritten) return false; // 值没变 → 零写入
  if (seg === "intro") return true; // 首屏 → 持续跟手
  // 离开首屏 → 一直写到回正彻底收干净为止
  return !(introApplied === resetT && introWritten === resetT);
}

/** 鼠标横向归一化位置 → intro 时间（秒）。留 0.04s 余量防末帧黑屏。 */
export function mouseToIntroTime(x01: number, duration: number, invert: boolean): number {
  const x = invert ? 1 - clamp(x01, 0, 1) : clamp(x01, 0, 1);
  const max = Math.max(0, duration - 0.04);
  return clamp(x * max, 0, max);
}

/** 五节导航的文案与英文（HUD 序号旁英文与导航同源）。 */
export const SECTIONS = [
  { zh: "初次见遇", en: "INTRO" },
  { zh: "设计理念", en: "PHILOSOPHY" },
  { zh: "作品文件夹", en: "WORK" },
  { zh: "作品预览", en: "PREVIEW" },
  { zh: "无限可能", en: "BEYOND" },
] as const;
