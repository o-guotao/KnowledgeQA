/**
 * 滚动进度引擎：main 视频的滚动驱动 seek（自 showcase.js 等价移植）。
 *
 * 三条纪律（与原实现一致）：
 * 1) 不从 main.currentTime 读回控制量 —— 只信自己维护的 applied，防 seek 振荡。
 * 2) 值没变不写 DOM（scrollDirty 惰性重算）。
 * 3) 视频就绪（HAVE_CURRENT_DATA）前 seek 挂起 pendingSeek，canplay 补写。
 *
 * 高频值全部走 ref，绝不进 React state —— rAF 循环里 setState 会每帧 rerender。
 */
import { useCallback, useEffect, useRef } from "react";
import type { RefObject } from "react";

import { CONFIG, clamp, progressToTime } from "./showcaseMath";

interface UseScrollProgressOptions {
  trackRef: RefObject<HTMLDivElement | null>;
  mainVideoRef: RefObject<HTMLVideoElement | null>;
}

export function useScrollProgress({ trackRef, mainVideoRef }: UseScrollProgressOptions) {
  /** 滚动进度 p ∈ [0,1]（scrollDirty 收敛后的缓存值） */
  const progressRef = useRef(0);
  /** 最后一次写进 main.currentTime 的值（控制量唯一真源） */
  const appliedRef = useRef(0);
  /** main 时长（loadedmetadata 后换真值） */
  const durationRef = useRef(CONFIG.fallbackDuration);
  const scrollDirtyRef = useRef(true);
  const pendingSeekRef = useRef<number | null>(null);

  const computeProgress = useCallback((): number => {
    const docEl = document.documentElement;
    const max = docEl.scrollHeight - window.innerHeight;
    if (max <= 0) return 0;
    return clamp(window.scrollY / max, 0, 1);
  }, []);

  /** 页面高度 = main 时长 × 100vh */
  const layoutTrack = useCallback(() => {
    if (trackRef.current) trackRef.current.style.height = durationRef.current * 100 + "vh";
    scrollDirtyRef.current = true;
  }, [trackRef]);

  const writeSeek = useCallback(
    (t: number) => {
      const v = mainVideoRef.current;
      if (!v) return;
      // HAVE_CURRENT_DATA 之前写入会被忽略，挂起等 canplay 补写
      if (v.readyState >= 2) {
        v.currentTime = t;
        pendingSeekRef.current = null;
      } else {
        pendingSeekRef.current = t;
      }
    },
    [mainVideoRef],
  );

  /** loadedmetadata → 真时长；重算高度与 applied（防刷新在中部时先跳末尾再倒回）。 */
  const readDuration = useCallback(() => {
    const v = mainVideoRef.current;
    if (!v) return;
    const d = v.duration;
    if (!isFinite(d) || d <= 0 || d === durationRef.current) return;
    durationRef.current = d;
    layoutTrack();
    appliedRef.current = progressToTime(progressRef.current, d);
    writeSeek(appliedRef.current);
  }, [mainVideoRef, layoutTrack, writeSeek]);

  /** 每帧第 1 步：scrollDirty 收敛 + main 阻尼 seek（deadzone 内直接收敛）。 */
  const seekTick = useCallback(() => {
    if (scrollDirtyRef.current) {
      scrollDirtyRef.current = false;
      progressRef.current = computeProgress();
    }
    const target = progressToTime(progressRef.current, durationRef.current);
    const diff = target - appliedRef.current;
    if (Math.abs(diff) <= CONFIG.seekDeadzone) {
      if (appliedRef.current !== target) {
        appliedRef.current = target;
        writeSeek(appliedRef.current);
      }
    } else {
      let step = diff * CONFIG.ease;
      if (Math.abs(step) > CONFIG.maxStep) step = (step < 0 ? -1 : 1) * CONFIG.maxStep;
      appliedRef.current += step;
      writeSeek(appliedRef.current);
    }
  }, [computeProgress, writeSeek]);

  useEffect(() => {
    const markDirty = () => {
      scrollDirtyRef.current = true;
    };
    window.addEventListener("scroll", markDirty, { passive: true });
    window.addEventListener("resize", markDirty, { passive: true });
    window.addEventListener("orientationchange", markDirty, { passive: true });
    // 视口/track 高度变化时重算进度（移动端地址栏收起等）
    const ro =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(markDirty)
        : null;
    ro?.observe(document.body);

    const v = mainVideoRef.current;
    if (v) {
      const onCanplay = () => {
        if (pendingSeekRef.current === null) return;
        v.currentTime = pendingSeekRef.current;
        pendingSeekRef.current = null;
      };
      // 首帧 nudge：canplay 之前先写极小偏移逼解码器吐首帧，否则部分浏览器显示黑帧。
      // 只对「目标就是 0」做；pendingSeek 已为 null 说明画面已画好，不能动。
      const onLoadeddata = () => {
        if (pendingSeekRef.current !== 0) return;
        v.currentTime = 0.001;
      };
      const onError = () => {
        // 素材缺失 → 让出位置露出 backdrop，无其它容错分支
        v.closest(".stage")?.classList.add("is-missing");
      };
      v.addEventListener("loadedmetadata", readDuration);
      v.addEventListener("canplay", onCanplay);
      v.addEventListener("loadeddata", onLoadeddata);
      v.addEventListener("error", onError);
      if (v.readyState >= 1) readDuration(); // 元数据可能早于本 effect 就绪

      return () => {
        ro?.disconnect();
        window.removeEventListener("scroll", markDirty);
        window.removeEventListener("resize", markDirty);
        window.removeEventListener("orientationchange", markDirty);
        v.removeEventListener("loadedmetadata", readDuration);
        v.removeEventListener("canplay", onCanplay);
        v.removeEventListener("loadeddata", onLoadeddata);
        v.removeEventListener("error", onError);
      };
    }
    return () => {
      ro?.disconnect();
      window.removeEventListener("scroll", markDirty);
      window.removeEventListener("resize", markDirty);
      window.removeEventListener("orientationchange", markDirty);
    };
  }, [readDuration, mainVideoRef]);

  return { progressRef, appliedRef, durationRef, seekTick, layoutTrack, computeProgress, writeSeek };
}
