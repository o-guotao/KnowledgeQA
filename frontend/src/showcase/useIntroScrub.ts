/**
 * 首屏交互引擎：鼠标擦洗 intro 视频时间轴 + 八向视线读数（自 showcase.js 等价移植）。
 *
 * - 精确指针（hover+fine）才做擦洗；触屏 / reduced-motion 退回自动循环。
 * - 离开首屏主动「回正」到中性朝向（resetEase 比跟手快，落在 0.5s 淡出内）。
 * - 鼠标一次没动过 / 互动被暂停时同样走回正支 —— 人物保持初始朝向待机。
 * - shouldWriteIntro 门控：回正收干净后零写入。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

import { CONFIG, clamp, gazeLabel, mouseToIntroTime, shouldWriteIntro } from "./showcaseMath";
import type { Segment } from "./showcaseMath";

interface UseIntroScrubOptions {
  introVideoRef: RefObject<HTMLVideoElement | null>;
  introInnerRef: RefObject<HTMLElement | null>;
  /** 擦洗模式下刮掉 loop/autoplay 并停住；循环模式播起来 */
  onScrubMode: (scrub: boolean) => void;
}

export function useIntroScrub({ introVideoRef, introInnerRef, onScrubMode }: UseIntroScrubOptions) {
  const reducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  /** 有精确指针才做鼠标擦洗（触屏/reduced-motion 退自动循环） */
  const scrubMode =
    CONFIG.intro.mode === "scrub" &&
    typeof window !== "undefined" &&
    window.matchMedia("(hover: hover) and (pointer: fine)").matches &&
    !reducedMotion;

  const [interactionPaused, setInteractionPausedState] = useState(false);
  const interactionPausedRef = useRef(false);

  const introDurationRef = useRef(CONFIG.intro.fallbackDuration);
  const introAppliedRef = useRef(-1); // -1 = 未初始化
  const introWrittenRef = useRef<number | null>(null);
  const mx01Ref = useRef(0.5);
  const my01Ref = useRef(0.5);
  const mouseMovedRef = useRef(false);
  const pyRef = useRef(0);
  const lastPyWRef = useRef<string | null>(null);

  const introTarget = useCallback(
    () => mouseToIntroTime(mx01Ref.current, introDurationRef.current, CONFIG.intro.invert),
    [],
  );
  /** 回正帧。复用同一映射，resetAt=0 即片头。 */
  const introResetTime = useCallback(
    () => mouseToIntroTime(CONFIG.intro.resetAt, introDurationRef.current, false),
    [],
  );

  /** loadedmetadata → 真时长；首次跨到真值时吸附 introApplied，防「鼠标没动画面自己滑」。 */
  const readIntroDuration = useCallback(() => {
    const vi = introVideoRef.current;
    if (!vi) return;
    const d = vi.duration;
    if (!isFinite(d) || d <= 0 || d === introDurationRef.current) return;
    const firstReal = introDurationRef.current === CONFIG.intro.fallbackDuration;
    introDurationRef.current = d;
    if (introAppliedRef.current < 0 || firstReal) {
      introAppliedRef.current =
        mouseMovedRef.current && segRef.current === "intro" && !interactionPausedRef.current
          ? introTarget()
          : introResetTime();
    }
  }, [introVideoRef, introTarget, introResetTime]);

  /** 最近一次段名（回正条件的依赖，由外部每帧喂入） */
  const segRef = useRef<Segment>("intro");

  /** 每帧第 4 步：intro 擦洗/回正 + tiltY 纵向触感。 */
  const introTick = useCallback(
    (seg: Segment) => {
      segRef.current = seg;
      const vi = introVideoRef.current;
      if (!scrubMode || !vi) return;

      const resetT = introResetTime();
      const following = seg === "intro" && mouseMovedRef.current && !interactionPausedRef.current;
      const it = following ? introTarget() : resetT;
      const ie = following ? CONFIG.intro.ease : CONFIG.intro.resetEase;

      if (introAppliedRef.current < 0) introAppliedRef.current = it;
      introAppliedRef.current += (it - introAppliedRef.current) * ie;
      if (Math.abs(it - introAppliedRef.current) < 0.008) introAppliedRef.current = it;

      if (
        vi.readyState >= 2 &&
        shouldWriteIntro(seg, introAppliedRef.current, introWrittenRef.current, resetT)
      ) {
        vi.currentTime = introAppliedRef.current;
        introWrittenRef.current = introAppliedRef.current;
      }

      // 纵向只做极小位移触感；离开首屏与回正一起归零
      const tpy = following ? (my01Ref.current - 0.5) * CONFIG.intro.tiltY : 0;
      pyRef.current += (tpy - pyRef.current) * CONFIG.intro.ease;
      if (Math.abs(tpy - pyRef.current) < 0.02) pyRef.current = tpy;

      const inner = introInnerRef.current;
      if (inner) {
        const wy = pyRef.current.toFixed(2);
        if (wy !== lastPyWRef.current) {
          lastPyWRef.current = wy;
          inner.style.setProperty("--py", wy + "px");
        }
      }
    },
    [scrubMode, introVideoRef, introResetTime, introTarget, introInnerRef],
  );

  /** 每帧第 5 步：视线读数（只在真变化时返回新值，由调用方决定渲染方式）。 */
  const gazeTick = useCallback(
    (seg: Segment): string => {
      const gazeOn = seg === "intro" && mouseMovedRef.current && !interactionPausedRef.current;
      return gazeOn ? gazeLabel(mx01Ref.current, my01Ref.current) : "LOOKING AT YOU";
    },
    [],
  );

  /** 播放态：同一时刻至多一段在播；intro 仅「循环模式 + 未暂停 + 首屏」三条件同时成立才播。 */
  const syncPlayback = useCallback(
    (seg: Segment) => {
      const vi = introVideoRef.current;
      const introShouldPlay = !scrubMode && !interactionPausedRef.current && seg === "intro";
      if (introShouldPlay) {
        if (vi && vi.paused) {
          const pr = vi.play();
          if (pr && pr.catch) pr.catch(() => undefined);
        }
      } else if (vi && !vi.paused) {
        vi.pause();
      }
    },
    [scrubMode, introVideoRef],
  );

  /** 暂停互动（只停互动层，不停滚动叙事）。 */
  const setInteractionPaused = useCallback(
    (on: boolean) => {
      interactionPausedRef.current = on;
      setInteractionPausedState(on);
      syncPlayback(segRef.current);
    },
    [syncPlayback],
  );

  useEffect(() => {
    const vi = introVideoRef.current;
    if (!vi) return;

    const onPointerMove = (e: PointerEvent) => {
      if (!scrubMode) return;
      mx01Ref.current = clamp(e.clientX / window.innerWidth, 0, 1);
      my01Ref.current = clamp(e.clientY / window.innerHeight, 0, 1);
      mouseMovedRef.current = true; // 首次移动后，人物才开始跟手
    };
    window.addEventListener("pointermove", onPointerMove, { passive: true });

    // iOS：没有用户手势就解码不出来。首个手势里点火一次。
    let unlocked = false;
    const unlock = () => {
      if (unlocked) return;
      unlocked = true;
      if (!scrubMode) {
        const ip = vi.play();
        if (ip && ip.catch) ip.catch(() => undefined);
      }
    };
    ["pointerdown", "touchstart", "wheel", "keydown"].forEach((ev) =>
      window.addEventListener(ev, unlock, { passive: true }),
    );

    // 模式上线：擦洗模式刮掉 loop/autoplay 并停住（鼠标静止画面必须定住）
    if (scrubMode) {
      vi.pause();
      vi.loop = false;
      vi.removeAttribute("loop");
      vi.removeAttribute("autoplay");
    } else {
      vi.loop = true;
      const pr = vi.play();
      if (pr && pr.catch) pr.catch(() => undefined);
    }
    onScrubMode(scrubMode);
    vi.addEventListener("loadedmetadata", readIntroDuration);
    vi.addEventListener("error", () => vi.closest(".stage")?.classList.add("is-missing"));
    if (vi.readyState >= 1) readIntroDuration();

    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      ["pointerdown", "touchstart", "wheel", "keydown"].forEach((ev) =>
        window.removeEventListener(ev, unlock),
      );
      vi.removeEventListener("loadedmetadata", readIntroDuration);
    };
  }, [scrubMode, introVideoRef, readIntroDuration, onScrubMode]);

  return {
    scrubMode,
    interactionPaused,
    setInteractionPaused,
    introTick,
    gazeTick,
    syncPlayback,
    /** intro 时长（HUD 首屏时间码用；真值到位后由 readIntroDuration 更新） */
    introDurationRef,
    introAppliedRef,
  };
}
