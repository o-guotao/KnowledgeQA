import type { RefObject } from "react";

/**
 * 三个影像台：intro（首屏，鼠标擦洗）/ main（滚动驱动 seek）/ outro（静态图淡入）。
 * 视频刻意不放 poster —— 缺失时露出 .backdrop，保证背景恒定。
 */
interface StageVideoProps {
  introVideoRef: RefObject<HTMLVideoElement>;
  introInnerRef: RefObject<HTMLDivElement>;
  mainVideoRef: RefObject<HTMLVideoElement>;
  /** seg = 'intro' | 'main' | 'outro'（main 台在 [outroAt,1] 仍亮，停末帧） */
  seg: string;
}

export function StageVideo({ introVideoRef, introInnerRef, mainVideoRef, seg }: StageVideoProps) {
  return (
    <>
      <section className={`stage stage--main${seg !== "intro" ? " is-active" : ""}`} data-stage="main">
        <div className="stage__inner">
          <video
            className="stage__video"
            data-role="main"
            src="/media/main.mp4"
            muted
            playsInline
            webkit-playsinline="true"
            preload="auto"
            ref={mainVideoRef}
          />
        </div>
      </section>

      <section className={`stage stage--intro${seg === "intro" ? " is-active" : ""}`} data-stage="intro">
        <div className="stage__inner" ref={introInnerRef}>
          <div className="stage__poster" style={{ ["--poster" as string]: "url(/media/intro.jpeg)" }} />
          <video
            className="stage__video"
            data-role="intro"
            src="/media/intro-loop.mp4"
            muted
            playsInline
            webkit-playsinline="true"
            preload="auto"
            autoPlay
            loop
            ref={introVideoRef}
          />
        </div>
      </section>

      <section className={`stage stage--outro${seg === "outro" ? " is-active" : ""}`} data-stage="outro">
        <div className="stage__inner">
          <div className="stage__poster" style={{ ["--poster" as string]: "url(/media/beat-3.jpeg)" }} />
        </div>
      </section>
    </>
  );
}
