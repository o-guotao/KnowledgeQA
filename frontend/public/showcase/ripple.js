/* ripple.js — 鼠标波纹层（v4）
   ============================================================================
   光标附近一圈细亮环，点击时向外扩散。四条要求与它们的落点：

     缩小影响范围        可见半径 influence = 160px，包络在边界严格归零
     靠近鼠标的波纹更细  波前用对数相位，环距 s(r) = 2π(r0+r)/K 随半径递增
                         （光标处 16px → 边界 56px）；描边 0.8px → 2.0px
     点击时向外扩散      每次点击发 2 圈、错开 140ms，easeOutCubic 扩张到边界
     去掉黑色拖尾        加色混合 + 每帧全清屏 + 环境场无状态 + 点击环有限寿命

   三条防止「黑色拖尾」的机制缺一不可：
     1. globalCompositeOperation = 'lighter' —— 环与环之间只相加，不压暗
     2. 每帧 clearRect(0,0,S,S) —— 不残留上一帧（反馈缓冲式拖尾的根因就是不清屏）
     3. 环境场**无状态** —— 每帧从 r 与 t 直接解出波前，没有可累积的历史量

   画布只有 560×560 并随光标移动，不是全屏 ——
   「影响范围小」由几何尺寸强制成立，不靠参数自觉；栅格量也降两个数量级。

   依赖：无。传统脚本（非 type=module），file:// 下双击可用。
   ========================================================================== */
(function () {
  'use strict';

  var TWO_PI = Math.PI * 2;

  var CONFIG = {
    /* ── 影响范围 ─────────────────────────────────────────────────────── */
    influence: 160,          /* px，波纹可见的最远半径 */
    maskPad: 120,            /* px，画布比 influence 多留的余量：
                                容纳被光标位移拖到边缘的点击环，避免硬切直线 */

    /* ── 波前几何（对数相位）─────────────────────────────────────────────
       φ(r) = K·ln(1 + r/r0)，波前解 φ = 2πk + ωt 得
         r_k = r0·(exp((2πk + ωt)/K) − 1)
       环距 s(r) = 2π(r0 + r)/K 随半径线性增长 —— 这就是「近处更细」。
       下面两个值由「近端环距 ≈ 16px、可见 ≈ 5 圈」解出（详见 design.md §12.4）。 */
    gapR0: 64,
    gapK: 25,
    waveOmega: 6,            /* rad/s，波前外推速度。近端 ≈15px/s，远端 ≈54px/s */

    /* ── 线宽与强度 ───────────────────────────────────────────────────── */
    widthNear: 0.8,          /* px，光标处最细 */
    widthFar: 2.0,           /* px，边界处 */
    alpha: 0.16,             /* 环境场峰值不透明度 */
    color: '255, 244, 226',  /* 暖白。用 rgba 三元组而非 hex，便于逐环插值 */

    /* ── 点击环 ───────────────────────────────────────────────────────── */
    clickRings: 2,           /* 一次点击发几圈 */
    clickDelay: 140,         /* ms，圈与圈之间错开 */
    clickLife: 720,          /* ms，单圈寿命 */
    clickAlpha: 0.5,
    maxRings: 24,            /* 存活环数上限，超出丢最旧的 —— 内存有界 */

    /* ── 全局淡入淡出与停机 ───────────────────────────────────────────── */
    fadeEase: 0.14,
    fadeSnap: 0.002,         /* 收敛判据。**必须吸附到精确 0**，否则循环永不停止 */
    dprCap: 2
  };


  /* ==========================================================================
     纯函数 —— 不含任何 DOM 访问，可在 node 里直接断言
     ========================================================================== */

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  /* 包络：(1 − u²)²，u = r/influence。
     管「影响范围」：u ≥ 1 恒为 0，所以不存在越界可见的环。
     [0,1] 上单调不增，导数 −4u(1−u²) ≤ 0。 */
  function envelope(r, c) {
    c = c || CONFIG;
    var u = r / c.influence;
    if (u <= 0) return 1;
    if (u >= 1) return 0;
    var t = 1 - u * u;
    return t * t;
  }

  /* 波前半径：φ = 2πk + phase 反解。phase 走满一圈时连续性成立 ——
     旧的 k=0 环正好等于新的 k=1 环，同时圆心处新生一圈。 */
  function wavefrontRadius(k, phase, c) {
    c = c || CONFIG;
    return c.gapR0 * (Math.exp((TWO_PI * k + phase) / c.gapK) - 1);
  }

  /* 环距：s(r) = dr/dφ · 2π = 2π(r0 + r)/K。随 r 严格递增 ——
     这是「靠近鼠标的波纹更细」唯一需要断言的不等式。 */
  function ringSpacing(r, c) {
    c = c || CONFIG;
    return TWO_PI * (c.gapR0 + r) / c.gapK;
  }

  /* 描边宽度：近细远粗。 */
  function strokeWidth(r, c) {
    c = c || CONFIG;
    return c.widthNear + (c.widthFar - c.widthNear) * clamp(r / c.influence, 0, 1);
  }

  /* 当前有几个波前落在影响范围内。加硬上限防参数退化时死循环
     （gapK ≤ 0 会让 exp 爆掉或恒 0）。 */
  function visibleRingCount(phase, c) {
    c = c || CONFIG;
    var n = 0;
    while (n < 4096 && wavefrontRadius(n, phase, c) < c.influence) n++;
    return n;
  }

  function easeOutCubic(u) {
    var v = 1 - clamp(u, 0, 1);
    return 1 - v * v * v;
  }

  /* 点击环状态。
     注意 tau < 0（错开的那一圈还没启动）必须返回 alive: true ——
     若返回 null，调用方的 filter 会把待启动的环直接丢掉，第二圈永远不出场。 */
  function clickRingState(ring, now, c) {
    c = c || CONFIG;
    var tau = now - ring.t0 - ring.delay;
    if (tau < 0) return { r: 0, alpha: 0, alive: true, pending: true };
    var u = clamp(tau / c.clickLife, 0, 1);
    var r = c.influence * easeOutCubic(u);
    var fade = 1 - u;
    /* 寿命终点 r = influence ⟹ envelope = 0 ⟹ alpha = 0。
       寿命与包络零点重合，环必然死透，不需要超时兜底。 */
    return {
      r: r,
      alpha: c.clickAlpha * envelope(r, c) * fade * fade,
      alive: u < 1,
      pending: false
    };
  }

  /* 阻尼一步，并吸附到目标值。
     吸附是必须的：纯阻尼永远只是逼近 0，循环就永远不会停。 */
  function fadeStep(alpha, target, ease, snap) {
    var next = alpha + (target - alpha) * ease;
    if (Math.abs(target - next) < snap) next = target;
    return next;
  }

  /* 环数上限：超出丢最旧的 —— 内存与单帧绘制量都有界。 */
  function capRings(rings, c) {
    c = c || CONFIG;
    while (rings.length > c.maxRings) rings.shift();
    return rings;
  }

  /* 停机判据：淡尽且无环 → 可以停 rAF，稳态零开销。 */
  function isSilent(alpha, rings) {
    return alpha === 0 && rings.length === 0;
  }

  function totalAlpha(rings, now, c) {
    c = c || CONFIG;
    var sum = 0;
    for (var i = 0; i < rings.length; i++) {
      var s = clickRingState(rings[i], now, c);
      if (s) sum += s.alpha;
    }
    return sum;
  }

  function hasFinePointer() {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  }

  function prefersReducedMotion() {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }


  /* ==========================================================================
     浏览器部分 —— 全部 DOM 访问收在 init() 内
     ========================================================================== */

  function init() {
    /* 触屏没有悬停指针，效果无意义；reduced-motion 下不做动效。
       两者都**不创建画布** —— 不是创建了再隐藏。 */
    if (!hasFinePointer() || prefersReducedMotion()) return;
    if (typeof document === 'undefined' || !document.body) return;

    var canvas = document.createElement('canvas');
    canvas.className = 'ripple';
    canvas.setAttribute('aria-hidden', 'true');
    document.body.appendChild(canvas);

    var ctx = canvas.getContext('2d');
    if (!ctx) { canvas.parentNode.removeChild(canvas); return; }

    var maskR = 0;
    var edgeMask = null;
    var dpr = 1;

    var pointer = { x: 0, y: 0 };
    var pointerInside = false;
    var rings = [];
    var alpha = 0;             /* 全局淡入淡出，0 = 完全不可见 */
    var rafId = 0;
    var lastNow = 0;
    var waveT = 0;             /* 秒，累加而非用绝对时间 —— 暂停后不跳相位 */

    var S = 2 * (CONFIG.influence + CONFIG.maskPad);

    function resize() {
      var next = Math.min(window.devicePixelRatio || 1, CONFIG.dprCap);
      dpr = next;
      canvas.width = Math.round(S * dpr);
      canvas.height = Math.round(S * dpr);
      canvas.style.width = S + 'px';
      canvas.style.height = S + 'px';
      /* 设 width/height 会重置整个 2D 上下文状态（含 transform），
         所以 transform 与渐变都必须在这之后重建。 */
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      maskR = S / 2;
      edgeMask = ctx.createRadialGradient(maskR, maskR, 0, maskR, maskR, maskR);
      var solid = CONFIG.influence / maskR;
      edgeMask.addColorStop(0, 'rgba(255,255,255,1)');
      edgeMask.addColorStop(solid, 'rgba(255,255,255,1)');
      edgeMask.addColorStop(1, 'rgba(255,255,255,0)');
    }

    function place() {
      /* 画布中心恒等于光标位置。环境场因此天然以光标为心，
         几何上不可能被画布边界切到，只有点击环需要边缘遮罩。 */
      canvas.style.transform =
        'translate3d(' + (pointer.x - maskR) + 'px,' + (pointer.y - maskR) + 'px,0)';
    }

    /* 变换只在 resize() 里设一次，之后全部按 CSS px 作图 ——
       所以这里直接按 CSS px 清即可，不必来回切变换。 */
    function clearCanvas() { ctx.clearRect(0, 0, S, S); }

    function draw(now) {
      ctx.clearRect(0, 0, S, S);                 /* 每帧全清 —— 不残留 */
      ctx.globalCompositeOperation = 'lighter';  /* 环与环之间只相加 */

      var cx = maskR, cy = maskR;
      var phase = (CONFIG.waveOmega * waveT) % TWO_PI;
      if (phase < 0) phase += TWO_PI;

      /* 1. 环境场：无状态，每帧从 phase 解出全部波前 */
      var count = visibleRingCount(phase, CONFIG);
      for (var k = 0; k < count; k++) {
        var r = wavefrontRadius(k, phase, CONFIG);
        if (r < 0.75) continue;                  /* 零半径圆弧画不出东西 */
        var a = CONFIG.alpha * envelope(r, CONFIG) * alpha;
        if (a <= 0.002) continue;                /* 边界附近直接跳过 */
        ctx.strokeStyle = 'rgba(' + CONFIG.color + ',' + a.toFixed(4) + ')';
        ctx.lineWidth = strokeWidth(r, CONFIG);
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, TWO_PI);
        ctx.stroke();
      }

      /* 2. 点击环：锚在点击处，随光标移动在画布局部坐标里漂移 */
      var anyClick = false;
      if (rings.length) {
        var ox = pointer.x - maskR, oy = pointer.y - maskR;
        for (var i = 0; i < rings.length; i++) {
          var st = clickRingState(rings[i], now, CONFIG);
          if (!st || st.pending || st.r < 0.75) continue;
          var ca = st.alpha * alpha;
          if (ca <= 0.002) continue;
          anyClick = true;              /* 真画了才算，否则不必付遮罩那一笔 */
          ctx.strokeStyle = 'rgba(' + CONFIG.color + ',' + ca.toFixed(4) + ')';
          ctx.lineWidth = strokeWidth(st.r, CONFIG);
          ctx.beginPath();
          ctx.arc(rings[i].x - ox, rings[i].y - oy, st.r, 0, TWO_PI);
          ctx.stroke();
        }
      }

      /* 3. 边缘软遮罩 —— **只在有点击环时施加**。
         环境场永远以光标为心，不可能越界，所以空闲时省掉每帧一次
         1120² 的渐变填充；只有被光标位移拖到边缘的点击环需要它，
         否则那个环会被画布边界硬切出一道直线。 */
      if (anyClick) {
        ctx.globalCompositeOperation = 'destination-in';
        ctx.fillStyle = edgeMask;
        ctx.fillRect(0, 0, S, S);
      }
      ctx.globalCompositeOperation = 'source-over';
    }

    function recycle(now) {
      var kept = [];
      for (var i = 0; i < rings.length; i++) {
        var st = clickRingState(rings[i], now, CONFIG);
        if (st && st.alive) kept.push(rings[i]);
      }
      rings = kept;
    }

    function step(now) {
      rafId = 0;
      if (document.hidden) return;               /* visibilitychange 会重启 */

      var dt = lastNow ? Math.min(now - lastNow, 64) : 16;
      lastNow = now;
      waveT += dt / 1000;

      alpha = fadeStep(alpha, pointerInside ? 1 : 0, CONFIG.fadeEase, CONFIG.fadeSnap);
      recycle(now);

      if (isSilent(alpha, rings)) {
        /* 淡尽且无环 → 停机。稳态零开销，不会和擦洗的 rAF 抢帧。 */
        clearCanvas();
        lastNow = 0;
        return;
      }

      draw(now);
      rafId = window.requestAnimationFrame(step);
    }

    function ensureRunning() {
      if (rafId || document.hidden) return;
      lastNow = 0;
      rafId = window.requestAnimationFrame(step);
    }

    function spawn(x, y, now) {
      for (var i = 0; i < CONFIG.clickRings; i++) {
        rings.push({ x: x, y: y, t0: now, delay: i * CONFIG.clickDelay });
      }
      capRings(rings, CONFIG);
    }

    /* ── 事件 ───────────────────────────────────────────────────────── */

    function onMove(e) {
      if (e.pointerType === 'touch') return;
      pointer.x = e.clientX;
      pointer.y = e.clientY;
      pointerInside = true;
      place();          /* 先摆位再起循环，首帧就不会从画布左上角滑进来 */
      ensureRunning();
    }

    function onDown(e) {
      if (e.pointerType === 'touch') return;
      pointer.x = e.clientX;
      pointer.y = e.clientY;
      pointerInside = true;
      place();
      spawn(e.clientX, e.clientY, performance.now());
      alpha = Math.max(alpha, 0.35);   /* 冷启动时别让第一圈太暗 */
      ensureRunning();
    }

    function onLeave() { pointerInside = false; ensureRunning(); }

    function onVisibility() {
      if (document.hidden) {
        if (rafId) { window.cancelAnimationFrame(rafId); rafId = 0; }
      } else {
        ensureRunning();
      }
    }

    function onResize() {
      var next = Math.min(window.devicePixelRatio || 1, CONFIG.dprCap);
      if (next === dpr) return;    /* 尺寸固定，只有 DPR 变化（跨屏拖动）才需重建 */
      resize();
      place();
    }

    resize();
    place();

    document.addEventListener('pointermove', onMove, { passive: true });
    document.addEventListener('pointerdown', onDown, { passive: true });
    /* pointerleave / pointerenter **不冒泡**，挂在 document 上收不到 ——
       它们的 target 是 html/body，永远不等于 document 本身。
       要监听「指针离开视口」只能盯 documentElement 的 mouseleave，
       这是个别无他法的老坑。重新进入不需要专门的监听：
       pointermove 一定会先到，它自己会把 pointerInside 置回 true。 */
    document.documentElement.addEventListener('mouseleave', onLeave);
    window.addEventListener('blur', onLeave);
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', onVisibility);
  }


  /* ==========================================================================
     双环境出口
     showcase.js 是同一个模式：浏览器里 init()，node 里导出纯函数供断言。
     frontend/package.json 是 "type": "module"，测试必须用 vm 而不是 require。
     ========================================================================== */

  var API = {
    CONFIG: CONFIG,
    clamp: clamp,
    envelope: envelope,
    wavefrontRadius: wavefrontRadius,
    ringSpacing: ringSpacing,
    strokeWidth: strokeWidth,
    visibleRingCount: visibleRingCount,
    easeOutCubic: easeOutCubic,
    clickRingState: clickRingState,
    fadeStep: fadeStep,
    capRings: capRings,
    isSilent: isSilent,
    totalAlpha: totalAlpha,
    hasFinePointer: hasFinePointer,
    prefersReducedMotion: prefersReducedMotion
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  if (typeof globalThis !== 'undefined') globalThis.__ripple = API;

  if (typeof document !== 'undefined') init();
})();
