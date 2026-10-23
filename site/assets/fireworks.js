/* 한화 로고에 마우스를 올리면 로고와 화면 바탕 위로 여러 색 폭죽이 터진다.
   올려 둔 동안 계속 쏘고, 잠깐 스쳐도 몇 초는 이어진다. 캔버스 한 장이라 클릭은 그대로 통과한다.
   움직임 줄이기 설정이면 켜지 않고, 인쇄에서는 숨긴다(styles.css .fireworks). */
(() => {
  "use strict";

  const logo = document.querySelector(".brand__home");
  if (!logo || !window.requestAnimationFrame) return;
  const reduce = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };

  const MIN_MS = 2200;      // 잠깐 스쳐도 이만큼은 쏜다
  const MAX_PARTS = 1500;   // 불꽃 수 상한(느린 PC 보호)
  // 한화 주황·금색을 중심으로 빨강·분홍·보라·파랑·청록·초록
  const HUES = [24, 24, 42, 52, 0, 335, 290, 265, 215, 190, 150, 110];
  const TYPES = ["ring", "peony", "peony", "willow", "glitter"];

  const rnd = (a, b) => a + Math.random() * (b - a);
  const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

  let cv = null, ctx = null, W = 0, H = 0;
  let rockets = [], parts = [];
  let hover = false, startAt = -1e9, nextLaunch = 0, nextLogo = 0, last = 0, raf = 0;

  function fit() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = document.documentElement.clientWidth;
    H = document.documentElement.clientHeight;
    cv.width = Math.round(W * dpr);
    cv.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function spark(x, y, vx, vy, o) {
    if (parts.length >= MAX_PARTS) return;
    parts.push(Object.assign({ x, y, px: x, py: y, vx, vy, life: 0, ttl: 1.4, hue: 24, light: 62, drag: 0.975, grav: 80, w: 2, glitter: false }, o));
  }

  // 불꽃 모양: 고리, 국화(구), 버들(금색 비), 반짝이
  function burst(x, y, hue, scale = 1, type = pick(TYPES)) {
    const hue2 = Math.random() < 0.5 ? pick(HUES) : hue;    // 두 가지 색
    const n = Math.round(rnd(90, 140) * Math.max(scale, 0.45));
    const v = rnd(250, 360) * scale * Math.min(1.15, Math.max(0.6, W / 1400));
    for (let i = 0; i < n; i++) {
      const a = type === "ring" ? (i / n) * Math.PI * 2 : rnd(0, Math.PI * 2);
      const z = rnd(-1, 1);
      const s = type === "ring" ? v * rnd(0.95, 1.03) : v * Math.sqrt(1 - z * z);   // 구를 정면에서 본 모양
      const o = type === "willow"
        ? { hue: 40, light: rnd(52, 62), ttl: rnd(2.2, 3), drag: 0.962, grav: 55, w: 1.3 }
        : { hue: i % 2 ? hue2 : hue, light: rnd(56, 66), ttl: rnd(1.1, 1.7), glitter: type === "glitter" };
      spark(x, y, Math.cos(a) * s, Math.sin(a) * s, o);
    }
  }

  function logoBurst(hue, scale, type) {
    const b = logo.getBoundingClientRect();
    burst(b.left + b.width / 2, b.top + b.height / 2, hue, scale, type);
  }

  // 화면 아래에서 쏘아 올려 위쪽 절반에서 터진다
  function launch() {
    const x = rnd(W * 0.06, W * 0.94);
    const top = rnd(H * 0.1, H * 0.48);
    const g = 900;
    rockets.push({ x, y: H + 6, px: x, py: H + 6, vx: rnd(-30, 30), vy: -Math.sqrt(2 * g * (H + 6 - top)), g, hue: pick(HUES) });
  }

  function stroke(x1, y1, x2, y2, color, w) {
    ctx.strokeStyle = color;
    ctx.lineWidth = w;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }

  function frame(now) {
    const dt = Math.max(0, Math.min(0.05, (now - last) / 1000));
    last = now;
    const firing = hover || now - startAt < MIN_MS;
    if (firing && now >= nextLaunch) {
      launch();
      if (Math.random() < 0.3) launch();
      nextLaunch = now + rnd(260, 560);
    }
    if (firing && now >= nextLogo) {   // 로고 자리에서도 계속 터진다
      logoBurst(pick(HUES), 0.42, pick(["ring", "peony", "glitter"]));
      nextLogo = now + rnd(650, 1000);
    }

    for (let i = rockets.length - 1; i >= 0; i--) {
      const r = rockets[i];
      r.px = r.x; r.py = r.y;
      r.vy += r.g * dt; r.x += r.vx * dt; r.y += r.vy * dt;
      spark(r.x, r.y, rnd(-20, 20), rnd(10, 50), { hue: 38, light: 68, ttl: rnd(0.25, 0.5), drag: 0.9, grav: 40, w: 1.2 });
      if (r.vy > -30) {
        rockets[i] = rockets[rockets.length - 1];
        rockets.pop();
        burst(r.x, r.y, r.hue);
      }
    }
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i];
      p.life += dt;
      if (p.life >= p.ttl) {
        parts[i] = parts[parts.length - 1];
        parts.pop();
        continue;
      }
      const k = Math.pow(p.drag, dt * 60);
      p.px = p.x; p.py = p.y;
      p.vx *= k; p.vy = p.vy * k + p.grav * dt;
      p.x += p.vx * dt; p.y += p.vy * dt;
    }

    // 지난 장면을 조금씩 지워 꼬리를 남긴다(destination-out이라 페이지 바탕은 어두워지지 않음)
    ctx.globalCompositeOperation = "destination-out";
    ctx.fillStyle = `rgba(0, 0, 0, ${(1 - Math.pow(0.7, dt * 60)).toFixed(3)})`;
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";
    for (const r of rockets) stroke(r.px, r.py, r.x, r.y, `hsla(${r.hue}, 100%, 78%, .95)`, 2.2);
    for (const p of parts) {
      const t = p.life / p.ttl;
      let a = 1 - t * t;
      if (p.glitter && t > 0.3 && Math.random() < 0.5) a *= 0.12;
      stroke(p.px, p.py, p.x, p.y, `hsla(${p.hue}, 100%, ${p.life < 0.1 ? 90 : p.light}%, ${a.toFixed(2)})`, p.w);
    }

    if (firing || rockets.length || parts.length) raf = requestAnimationFrame(frame);
    else stop();
  }

  function stop() {
    raf = 0;
    rockets = [];
    parts = [];
    cv.width = cv.height = 0;   // 쉬는 동안 캔버스 메모리를 비운다
  }

  function start() {
    if (reduce.matches) return;
    if (!cv) {
      cv = document.createElement("canvas");
      cv.className = "fireworks";
      cv.setAttribute("aria-hidden", "true");
      document.body.appendChild(cv);
      ctx = cv.getContext("2d");
      window.addEventListener("resize", () => { if (raf) fit(); });
    }
    const now = performance.now();
    if (!raf) {
      fit();
      last = now;
      nextLaunch = now + 150;
      raf = requestAnimationFrame(frame);
    }
    hover = true;
    if (now - startAt > 400) {   // 들락날락해도 첫 불꽃은 0.4초에 한 번만
      logoBurst(24, 0.5, "ring");
      nextLogo = now + 300;
    }
    startAt = now;
  }

  logo.addEventListener("pointerenter", (ev) => { if (ev.pointerType !== "touch") start(); });
  logo.addEventListener("pointerleave", () => { hover = false; });
})();
