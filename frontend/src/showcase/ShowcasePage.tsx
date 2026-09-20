/**
 * 滚动叙事门面首页（/）：五节互斥叙事 + 首屏鼠标擦洗 + HUD + 波纹层。
 *
 * 状态归属约定（见 useScrollProgress / useIntroScrub 头注）：
 * - 高频值（进度/applied/滑轨/时间码/下坠）全部 ref 直写，绝不进 React state。
 * - React state 只承载低频互斥态：当前 copyKey、段名、视线读数、文件夹开合、暂停。
 * - copyKey 是唯一的「节」状态源 —— 文案、背景、导航、HUD 序号同键同刻切换。
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { Backdrop } from "./components/Backdrop";
import { CopyLayer } from "./components/CopyLayer";
import { FallingItems } from "./components/FallingItems";
import { Folder } from "./components/Folder";
import { Hero } from "./components/Hero";
import { Hud } from "./components/Hud";
import { StageVideo } from "./components/StageVideo";
import { Topbar } from "./components/Topbar";
import { WorkPreview } from "./components/WorkPreview";
import "./showcase.css";
import { CONFIG, beatIndexAt, formatTime, sceneDropY, sectionSpans, sectionTarget, segmentOf } from "./showcaseMath";
import type { Segment } from "./showcaseMath";
import { useIntroScrub } from "./useIntroScrub";
import { useScrollProgress } from "./useScrollProgress";

export function ShowcasePage() {
  // ── DOM refs ─────────────────────────────────────────────────────────
  const trackRef = useRef<HTMLDivElement | null>(null);
  const mainVideoRef = useRef<HTMLVideoElement | null>(null);
  const introVideoRef = useRef<HTMLVideoElement | null>(null);
  const introInnerRef = useRef<HTMLDivElement | null>(null);
  const dropRef = useRef<HTMLDivElement | null>(null);
  const backdropRootRef = useRef<HTMLDivElement | null>(null);
  const hudFillRef = useRef<HTMLElement | null>(null);
  const hudKnobRef = useRef<HTMLElement | null>(null);
  const hudTimeRef = useRef<HTMLElement | null>(null);
  const hudTotRef = useRef<HTMLElement | null>(null);

  // ── 低频互斥态 ───────────────────────────────────────────────────────
  const [seg, setSeg] = useState<Segment>("intro");
  const [copyKey, setCopyKey] = useState("intro");
  const [gaze, setGaze] = useState("LOOKING AT YOU");
  const [folderOpen, setFolderOpen] = useState(false);
  const [scrubBody, setScrubBody] = useState(false);

  const { progressRef, appliedRef, durationRef, seekTick, layoutTrack, computeProgress } =
    useScrollProgress({ trackRef, mainVideoRef });

  const { scrubMode, interactionPaused, setInteractionPaused, introTick, gazeTick, syncPlayback, introDurationRef, introAppliedRef } =
    useIntroScrub({
      introVideoRef,
      introInnerRef,
      onScrubMode: (scrub) => {
        document.body.classList.toggle("is-scrub", scrub);
        setScrubBody(scrub);
      },
    });

  // ── 高频写值备忘（值没变不写 DOM） ──────────────────────────────────
  const last = useRef({
    seg: null as Segment | null,
    copyKey: null as string | null,
    fill: null as string | null,
    time: null as string | null,
    tot: null as string | null,
    drop: null as string | null,
    par: null as string | null,
  });

  // ── 跳到第 i 节（落点 sectionTarget 现算） ─────────────────────────────
  const goToSection = useCallback((i: number) => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    if (max <= 0) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: sectionTarget(i) * max, behavior: reduced ? "auto" : "smooth" });
  }, []);

  // ── rAF 主循环：单循环承载全部每帧工作 ───────────────────────────────
  useEffect(() => {
    const spans = sectionSpans();
    const dropSpan = spans[CONFIG.beatCuts.length] ?? null;
    let rafId = 0;

    const frame = () => {
      seekTick(); // 1) main 阻尼 seek（含 scrollDirty 收敛）
      const p = progressRef.current;
      const curSeg = segmentOf(p);

      // 2) 段变化 → React state（低频；stage/hero 类与播放态在 render/副作用中联动）
      if (curSeg !== last.current.seg) {
        last.current.seg = curSeg;
        setSeg(curSeg);
        syncPlayback(curSeg);
      }

      // 3) 节奏点 → copyKey（文案/背景/导航/HUD 序号同键同刻）
      const beat = curSeg === "intro" ? -1 : curSeg === "outro" ? CONFIG.beatCuts.length : beatIndexAt(p);
      const key = beat < 0 ? "intro" : String(beat);
      if (key !== last.current.copyKey) {
        last.current.copyKey = key;
        setCopyKey(key);
        setFolderOpen(false); // 离开作品文件夹节合上内页
      }

      // 4) 首屏擦洗 + 5) 视线读数
      introTick(curSeg);
      const g = gazeTick(curSeg);
      setGaze((prev) => (prev === g ? prev : g));

      // 6) HUD 直写
      const fill = p.toFixed(4);
      if (fill !== last.current.fill) {
        last.current.fill = fill;
        if (hudFillRef.current) hudFillRef.current.style.transform = `scaleX(${fill})`;
        if (hudKnobRef.current) hudKnobRef.current.style.left = `${(p * 100).toFixed(2)}%`;
      }
      // 时间码显示当前段自己的时间轴（首屏 intro / 其余 main）
      const shown = curSeg === "intro" ? (scrubMode ? Math.max(0, introAppliedRef.current) : (introVideoRef.current?.currentTime ?? 0)) : appliedRef.current;
      const total = curSeg === "intro" ? introDurationRef.current : durationRef.current;
      const t = formatTime(shown);
      if (t !== last.current.time) {
        last.current.time = t;
        if (hudTimeRef.current) hudTimeRef.current.textContent = t;
      }
      const tot = formatTime(total);
      if (tot !== last.current.tot) {
        last.current.tot = tot;
        if (hudTotRef.current) hudTotRef.current.textContent = tot;
      }

      // 7) 下坠层直写（每帧从 p 现算：可倒放、可停在中间态、静止零写入）
      const pct = (sceneDropY(p, dropSpan) * 100).toFixed(3);
      if (pct !== last.current.drop) {
        last.current.drop = pct;
        if (dropRef.current) dropRef.current.style.transform = `translate3d(0,${pct}%,0)`;
      }

      // 8) 视差降级：无 main.mp4 时给当前节背景写 --par（该节内进度 0..1）
      if (mainVideoRef.current && mainVideoRef.current.closest(".stage")?.classList.contains("is-missing")) {
        const span = beat >= 0 && beat < spans.length ? spans[beat] : null;
        if (span) {
          const par = ((p - span[0]) / (span[1] - span[0])).toFixed(4);
          if (par !== last.current.par) {
            last.current.par = par;
            backdropRootRef.current?.style.setProperty("--par", par);
          }
        }
      }

      rafId = window.requestAnimationFrame(frame);
    };

    rafId = window.requestAnimationFrame(frame);
    return () => window.cancelAnimationFrame(rafId);
  }, [seekTick, progressRef, appliedRef, durationRef, introTick, gazeTick, syncPlayback, scrubMode, introAppliedRef, introDurationRef, introVideoRef, mainVideoRef]);

  // ── 启动时序：layoutTrack + 首帧就位（刷新在中部时不要从 0 动画） ──────
  useEffect(() => {
    layoutTrack();
    document.body.classList.add("showcase-on");
    // useScrollProgress 的 duration 挂载即绪时已在 hook 内完成 applied 初始化
    return () => {
      document.body.classList.remove("is-scrub", "showcase-on");
    };
  }, [layoutTrack]);

  const sectionIndex = copyKey === "intro" ? 0 : Number(copyKey) + 1;

  return (
    <div className="showcase">
      <Backdrop copyKey={copyKey} dropRef={dropRef} rootRef={backdropRootRef} shrunk={folderOpen} />
      <FallingItems active={copyKey === "3"} progressRef={progressRef} />
      <StageVideo
        introVideoRef={introVideoRef}
        introInnerRef={introInnerRef}
        mainVideoRef={mainVideoRef}
        seg={seg}
      />
      {/* 弹图打开时整屏压暗（is-dim），把主视频人物从弹图卡片背后按下去 */}
      <div className={`scrim${folderOpen ? " is-dim" : ""}`} aria-hidden="true" />
      <Topbar sectionIndex={sectionIndex} onGoToSection={goToSection} />
      <Hero active={seg === "intro"} gaze={gaze} />
      <CopyLayer copyKey={copyKey} onGoToSection={goToSection}>
        <Folder
          active={copyKey === "1"}
          open={folderOpen}
          onClose={() => setFolderOpen(false)}
          onToggle={() => setFolderOpen((v) => !v)}
        />
        <WorkPreview active={copyKey === "2"} />
      </CopyLayer>
      <Hud
        copyKey={copyKey}
        scrolled={seg !== "intro"}
        fillRef={hudFillRef}
        knobRef={hudKnobRef}
        timeRef={hudTimeRef}
        totRef={hudTotRef}
        paused={interactionPaused}
        onTogglePause={() => setInteractionPaused(!interactionPaused)}
      />
      <div className="scroll-track" aria-hidden="true" ref={trackRef} />
      {/* 滚动条隐藏/清屏由 CSS 管理；scrubBody 仅用于断言（body class 已在 hook 内切换） */}
      <span hidden data-scrub={String(scrubBody)} />
    </div>
  );
}
