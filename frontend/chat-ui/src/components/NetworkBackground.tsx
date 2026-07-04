import { useEffect, useRef } from "react";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
}

const PARTICLE_COUNT = 90;
const LINK_DIST = 130;
const MAX_SPEED = 0.6;

// ボディー部分の背景として、ノードがランダムに漂い、近づくと線で結ばれる
// ネットワーク風のアニメーションをCanvasで描画する
export function NetworkBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let width = 0;
    let height = 0;
    let particles: Particle[] = [];

    const resize = () => {
      const parent = canvas.parentElement;
      width = parent?.clientWidth ?? window.innerWidth;
      height = parent?.clientHeight ?? window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const initParticles = () => {
      particles = Array.from({ length: PARTICLE_COUNT }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * MAX_SPEED,
        vy: (Math.random() - 0.5) * MAX_SPEED,
        // 大小の点がランダムに混在するよう、一部だけ大きな半径にする
        // (全て同じ大きさだと画面全体がぼやけて見づらいため)
        r:
          Math.random() < 0.22
            ? Math.random() * 3 + 2.6 // 目立つ大きな点
            : Math.random() * 1 + 0.5, // 背景の小さな点
      }));
    };

    const step = () => {
      ctx.clearRect(0, 0, width, height);

      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x <= 0 || p.x >= width) p.vx *= -1;
        if (p.y <= 0 || p.y >= height) p.vy *= -1;
        p.x = Math.min(Math.max(p.x, 0), width);
        p.y = Math.min(Math.max(p.y, 0), height);
      }

      ctx.strokeStyle = "rgba(74, 78, 88, 0.6)";
      ctx.lineWidth = 0.8;
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const a = particles[i];
          const b = particles[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < LINK_DIST) {
            ctx.globalAlpha = 1 - dist / LINK_DIST;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }
      ctx.globalAlpha = 1;

      for (const p of particles) {
        // 大きい点ほど濃く、小さい点ほど淡くして目立つノードと
        // 背景の点をはっきり区別できるようにする
        ctx.fillStyle = p.r > 2 ? "#2b2e36" : "#8a8f98";
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    resize();
    initParticles();
    step();

    // requestAnimationFrame はタブが非アクティブ(背景)になると停止してしまうため、
    // 背景で流れ続ける演出としては setInterval を使う
    const intervalId = window.setInterval(step, 33);
    window.addEventListener("resize", resize);

    // サイドバーの開閉・ドラッグリサイズでも親要素(.chat-body)のサイズが変わるため
    // window の resize イベントだけでなく ResizeObserver でも追従させる
    const resizeObserver = new ResizeObserver(() => resize());
    if (canvas.parentElement) {
      resizeObserver.observe(canvas.parentElement);
    }

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("resize", resize);
      resizeObserver.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} className="chat-body-canvas" aria-hidden="true" />;
}
