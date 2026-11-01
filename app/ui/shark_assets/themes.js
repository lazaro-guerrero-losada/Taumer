// ASCII Ambient Background Engines for Taumer — Light Mode
// Shares the exact monochrome slate palette, 5-point subsample rasterizer,
// wake diffusion grid, and ASCII glyph ramps from ASCII Sharks.
// Themes:
//   1. "sharks"    — ASCII Sharks (window.OceanEngine in sharks.js)
//   2. "jellyfish" — Pulsing Jellyfish (Deep Sea Zen)
//   4. "mantas"    — Manta Rays (Graceful Ocean Glide)

(function () {
  "use strict";

  const TAU = Math.PI * 2;
  const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
  const rand = (lo, hi) => lo + Math.random() * (hi - lo);

  function smoothstep(e0, e1, x) {
    const t = clamp((x - e0) / (e1 - e0), 0, 1);
    return t * t * (3 - 2 * t);
  }

  function angleDiff(a, b) {
    let d = (b - a) % TAU;
    if (d > Math.PI) d -= TAU;
    if (d < -Math.PI) d += TAU;
    return d;
  }

  function hash3(x, y, z) {
    let h =
      Math.imul(x | 0, 374761393) ^
      Math.imul(y | 0, 668265263) ^
      Math.imul(z | 0, 1442695041);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  }

  const K1 = 1 / 260;
  const K2 = 1 / 310;
  const K3 = 1 / 190;
  const CURRENT_SCALE = 3400;

  function flowCurrent(x, y, t, out) {
    const a = x * K1 + t * 0.07;
    const b = y * K2 - t * 0.05;
    const c = (x + y) * K3 + t * 0.11;
    out.x = (-K2 * Math.sin(a) * Math.sin(b) + 0.5 * K3 * Math.cos(c)) * CURRENT_SCALE;
    out.y = (-K1 * Math.cos(a) * Math.cos(b) - 0.5 * K3 * Math.cos(c)) * CURRENT_SCALE;
    return out;
  }

  // Exact same ASCII constants & palette as sharks.js
  const ALPHA_LEVELS = 6;
  const AMBIENT_ALPHAS = [0.3, 0.45, 0.6, 0.75, 0.9];
  const ACCENTS = ["#e0892c", "#e03a32", "#b44ae0", "#33c8cc", "#3cb54a", "#3150e8", "#d9c14a"];
  const SKIN_RAMP = ":;t%SX8#@";
  const FIN_GLYPHS = "%;tS:";
  const RIDGE_GLYPHS = "@8%";
  const EDGE_HEAVY = ":;";
  const EDGE_LIGHT = ".',`";
  const MARK_GLYPHS = "#%@";

  const FLAG_BODY = 1;
  const FLAG_EDGE = 2;
  const FLAG_FIN = 3;
  const FLAG_RIDGE = 4;
  const FLAG_EYE = 5;
  const FLAG_MARK = 6;
  const FLAG_WHITE_PATCH = 7;
  const FLAG_WHITE_SPOT = 8;

  const SUBSAMPLES = [0.25, 0.3, 0.75, 0.3, 0.25, 0.72, 0.75, 0.72];
  const STEP = 1 / 60;
  const MAX_STEPS = 4;

  // ── SHARED BASE ASCII RENDERER ───────────────────────────────────────────

  class BaseAsciiRenderer {
    constructor(canvas, kinds, tints) {
      const ctx = canvas.getContext("2d", { alpha: false });
      if (!ctx) throw new Error("2D canvas unavailable");
      this.canvas = canvas;
      this.ctx = ctx;
      this.bg = document.createElement("canvas");
      this.kinds = kinds;
      this.tints = tints;

      this.dpr = 1;
      this.width = 0;
      this.height = 0;
      this.cw = 12;
      this.ch = 18;
      this.cols = 0;
      this.rows = 0;
      this.fontFamily = "ui-monospace, Menlo, monospace";

      this.energy = new Float32Array(0);
      this.energyTmp = new Float32Array(0);
      this.heat = new Float32Array(0);
      this.dotStyles = [];

      this.cellFlag = new Uint8Array(0);
      this.cellShade = new Float32Array(0);
      this.cellKey = new Uint32Array(0);
      this.cellDepth = new Float32Array(0);
      this.cellKind = new Uint8Array(0);

      this.ambientStamp = new Uint32Array(0);
      this.frameId = 0;
      this.ambientBuckets = AMBIENT_ALPHAS.map(() => []);
      this.ambientGlyph = "-";

      this.hitFlag = 0;
      this.hitShade = 0;
      this.hitS = 0;
      this.hitV = 0;
      this.hitDist = 0;

      for (let l = 0; l < ALPHA_LEVELS; l++) {
        const a = (0.35 * (l + 1)) / ALPHA_LEVELS;
        this.dotStyles.push(`rgba(14, 165, 233, ${a.toFixed(3)})`);
      }
    }

    get cellWidth() { return this.cw; }
    get cellHeight() { return this.ch; }

    setFontFamily(family) {
      if (family) this.fontFamily = family;
    }

    resize(width, height, dpr) {
      const prevCols = this.cols;
      const prevRows = this.rows;
      this.width = width;
      this.height = height;
      this.dpr = dpr;
      this.cw = clamp(Math.round(width / 124), 8, 13);
      this.ch = Math.round(this.cw * 1.45);
      this.cols = Math.ceil(width / this.cw);
      this.rows = Math.ceil(height / this.ch);

      this.canvas.width = Math.round(width * dpr);
      this.canvas.height = Math.round(height * dpr);
      this.bg.width = this.canvas.width;
      this.bg.height = this.canvas.height;

      const n = this.cols * this.rows;
      if (this.cols !== prevCols || this.rows !== prevRows) {
        this.energy = new Float32Array(n);
        this.energyTmp = new Float32Array(n);
        this.heat = new Float32Array(n);
        this.cellFlag = new Uint8Array(n);
        this.cellShade = new Float32Array(n);
        this.cellKey = new Uint32Array(n);
        this.cellDepth = new Float32Array(n);
        this.cellKind = new Uint8Array(n);
        this.ambientStamp = new Uint32Array(n);
      }

      this.paintBackground();
    }

    paintBackground() {
      const g = this.bg.getContext("2d");
      if (!g) return;
      const { width: W, height: H, dpr, cw, ch } = this;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.fillStyle = "#fafbfe";
      g.fillRect(0, 0, W, H);
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.strokeStyle = "rgba(0, 0, 0, 0.035)";
      g.lineWidth = 1;
      g.beginPath();
      for (let c = 0; c <= Math.ceil(W / cw); c++) {
        const x = Math.round(c * cw * dpr) + 0.5;
        g.moveTo(x, 0);
        g.lineTo(x, H * dpr);
      }
      for (let r = 0; r <= Math.ceil(H / ch); r++) {
        const y = Math.round(r * ch * dpr) + 0.5;
        g.moveTo(0, y);
        g.lineTo(W * dpr, y);
      }
      g.stroke();
    }

    cellIndex(x, y) {
      const c = Math.floor(x / this.cw);
      const r = Math.floor(y / this.ch);
      if (c < 0 || r < 0 || c >= this.cols || r >= this.rows) return -1;
      return r * this.cols + c;
    }

    stamp(field, x, y, radius, amount) {
      const c0 = Math.floor(x / this.cw);
      const r0 = Math.floor(y / this.ch);
      for (let r = r0 - radius; r <= r0 + radius; r++) {
        for (let c = c0 - radius; c <= c0 + radius; c++) {
          if (c < 0 || r < 0 || c >= this.cols || r >= this.rows) continue;
          const d = Math.hypot(c - c0, (r - r0) * 1.4);
          if (d > radius + 0.5) continue;
          const i = r * this.cols + c;
          field[i] = Math.min(1.6, field[i] + amount * (1 - d / (radius + 1)));
        }
      }
    }

    consumeEvents(world) {
      for (const e of world.events) {
        if (e.kind === "eat" || e.kind === "divide") {
          this.stamp(this.heat, e.x, e.y, e.kind === "divide" ? 3 : 2, 1);
          this.stamp(this.energy, e.x, e.y, e.kind === "divide" ? 5 : 3, 1.0);
        } else if (e.kind === "pulse") {
          this.stamp(this.energy, e.x, e.y, 4, 0.7);
        } else {
          this.stamp(this.energy, e.x, e.y, 6, 1.4);
        }
      }
      world.events.length = 0;
    }

    diffuse(dt) {
      const { cols, rows, energy, energyTmp: tmp, heat } = this;
      const decay = Math.exp(-dt * 1.5);
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const i = r * cols + c;
          const l = c > 0 ? energy[i - 1] : energy[i];
          const rt = c < cols - 1 ? energy[i + 1] : energy[i];
          const u = r > 0 ? energy[i - cols] : energy[i];
          const d = r < rows - 1 ? energy[i + cols] : energy[i];
          tmp[i] = (energy[i] * 4 + l + rt + u + d) * 0.125 * decay;
        }
      }
      this.energy = tmp;
      this.energyTmp = energy;
      const heatDecay = Math.exp(-dt * 2.2);
      for (let i = 0; i < heat.length; i++) heat[i] *= heatDecay;
    }

    drawDots() {
      const { ctx, cols, rows, cw, ch, energy, cellFlag } = this;
      const n = cols * rows;
      for (let i = 0; i < n; i++) {
        const e = energy[i];
        if (cellFlag[i] || e < 0.42) continue;
        const col = i % cols;
        const row = (i / cols) | 0;
        const level = clamp(Math.floor((e - 0.42) * 6), 0, ALPHA_LEVELS - 1);
        ctx.fillStyle = this.dotStyles[level];
        const size = Math.max(2, Math.round(cw * 0.22));
        ctx.fillRect(
          Math.round(col * cw + cw * 0.66 - size / 2),
          Math.round(row * ch + ch * 0.64 - size / 2),
          size,
          size
        );
      }
    }

    drawHeat() {
      const { ctx, heat, cols, cw, ch } = this;
      for (let i = 0; i < heat.length; i++) {
        const h = heat[i];
        if (h < 0.08) continue;
        const col = i % cols;
        const row = (i / cols) | 0;
        ctx.fillStyle = h > 0.5 ? `rgba(255,120,60,${h.toFixed(2)})` : `rgba(220,40,40,${(h * 1.6).toFixed(2)})`;
        ctx.fillText(h > 0.6 ? "*" : "·", col * cw + cw / 2, row * ch + ch / 2 + 1);
      }
    }

    markAmbient(particles) {
      const { ambientStamp, ambientBuckets, cellFlag } = this;
      const frame = ++this.frameId;
      for (const bucket of ambientBuckets) bucket.length = 0;
      for (let pass = 0; pass < 2; pass++) {
        for (const p of particles) {
          if (!p.alive || (p.depth > 0.78 ? 0 : 1) !== pass) continue;
          const i = this.cellIndex(p.x, p.y);
          if (i < 0 || ambientStamp[i] === frame || cellFlag[i]) continue;
          ambientStamp[i] = frame;
          const glint = clamp(Math.abs(p.turn || 0) / 3.5, 0, 1);
          const v = 0.3 + (0.4 * (p.depth - 0.55)) / 0.45 + 0.3 * Math.max(glint, p.alarm || 0);
          ambientBuckets[clamp(Math.floor(v * AMBIENT_ALPHAS.length), 0, AMBIENT_ALPHAS.length - 1)].push(i);
        }
      }
    }

    drawAmbient(customGlyphs) {
      const { ctx, cw, ch, cols, ambientBuckets } = this;
      for (let b = 0; b < ambientBuckets.length; b++) {
        const bucket = ambientBuckets[b];
        if (!bucket.length) continue;
        const a = AMBIENT_ALPHAS[b];
        ctx.fillStyle = `rgba(51, 65, 85, ${a * 0.75})`;
        for (const i of bucket) {
          const chGlyph = customGlyphs ? customGlyphs[(i + b) % customGlyphs.length] : this.ambientGlyph;
          ctx.fillText(chGlyph, (i % cols) * cw + cw / 2, ((i / cols) | 0) * ch + ch / 2 + 1);
        }
      }
    }

    drawCells(t) {
      const { ctx, cols, rows, cw, ch, cellFlag, cellShade, cellKey, cellDepth, cellKind, kinds, tints } = this;
      const n = cols * rows;
      for (let i = 0; i < n; i++) {
        const flag = cellFlag[i];
        if (!flag) continue;
        const col = i % cols;
        const row = (i / cols) | 0;
        const x = col * cw;
        const y = row * ch;
        const key = cellKey[i];
        const shade = cellShade[i];
        const dim = 0.78 + 0.22 * cellDepth[i];
        const kindName = kinds[cellKind[i]] || kinds[0];
        const [tr, tg, tb] = tints[kindName] || [0.94, 0.97, 1.03];

        const tick = Math.floor(t * 2.4 + (key % 997) / 97);
        const roll = hash3(key, tick, 7);

        if (flag === FLAG_EDGE) {
          const set = shade >= 0.5 ? EDGE_HEAVY : EDGE_LIGHT;
          const glyph = set[(key >>> 8) % set.length];
          ctx.fillStyle = roll < 0.07 ? ACCENTS[key % ACCENTS.length] : "rgba(100, 116, 139, 0.65)";
          ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
          continue;
        }

        let bgLevel;
        let glyph;
        if (flag === FLAG_RIDGE) {
          bgLevel = 100;
          glyph = RIDGE_GLYPHS[(key >>> 8) % RIDGE_GLYPHS.length];
        } else if (flag === FLAG_EYE) {
          bgLevel = 36;
          glyph = "o";
        } else if (flag === FLAG_MARK) {
          bgLevel = 115;
          glyph = MARK_GLYPHS[(key >>> 8) % MARK_GLYPHS.length];
        } else if (flag === FLAG_FIN) {
          bgLevel = 190 - shade * 65;
          glyph = FIN_GLYPHS[(key >>> 8) % FIN_GLYPHS.length];
        } else {
          bgLevel = 224 - shade * 105;
          const jitter = ((key >>> 4) % 3) - 1;
          glyph = SKIN_RAMP[clamp(Math.floor(shade * 8.99) + jitter, 0, SKIN_RAMP.length - 1)];
        }

        bgLevel *= dim;
        const r = Math.min(255, Math.round(bgLevel * tr));
        const g = Math.min(255, Math.round(bgLevel * tg));
        const b = Math.min(255, Math.round(bgLevel * tb + 3));
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.fillRect(x + 1, y + 1, cw - 1, ch - 1);

        let glyphColor;
        if (flag === FLAG_EYE) {
          glyphColor = "#ffffff";
        } else if (flag === FLAG_MARK) {
          glyphColor = "#0f172a";
        } else if (roll < 0.08) {
          glyphColor = ACCENTS[key % ACCENTS.length];
        } else if (roll < 0.12) {
          glyphColor = "#ffffff";
        } else if (bgLevel < 138) {
          glyphColor = "#f8fafc";
        } else {
          glyphColor = "#1e293b";
        }
        ctx.fillStyle = glyphColor;
        ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
      }
    }
  }

  // ── SHARED ENGINE LOOP WRAPPER ───────────────────────────────────────────

  class BaseLoopEngine {
    constructor(canvas, world, renderer) {
      this.canvas = canvas;
      this.world = world;
      this.renderer = renderer;
      this.renderer.setFontFamily(getComputedStyle(canvas).fontFamily);
      this.raf = 0;
      this.last = 0;
      this.acc = 0;
      this.disposed = false;

      this.onResize = () => this.resize();
      window.addEventListener("pointermove", this.onPointerMove, { passive: true });
      window.addEventListener("pointerdown", this.onPointerDown, { passive: true });
      document.documentElement.addEventListener("pointerleave", this.onPointerLeave);
      window.addEventListener("pointerleave", this.onPointerLeave);
      window.addEventListener("blur", this.onPointerLeave);
      window.addEventListener("resize", this.onResize);

      this.resizeObserver = new ResizeObserver(this.onResize);
      this.resizeObserver.observe(canvas);

      this.resize();
      this.schedule();
    }

    destroy() {
      this.disposed = true;
      cancelAnimationFrame(this.raf);
      if (this.resizeObserver) this.resizeObserver.disconnect();
      window.removeEventListener("pointermove", this.onPointerMove);
      window.removeEventListener("pointerdown", this.onPointerDown);
      document.documentElement.removeEventListener("pointerleave", this.onPointerLeave);
      window.removeEventListener("pointerleave", this.onPointerLeave);
      window.removeEventListener("blur", this.onPointerLeave);
      window.removeEventListener("resize", this.onResize);
    }

    resize() {
      const rect = this.canvas.getBoundingClientRect();
      const w = rect.width > 10 ? rect.width : window.innerWidth;
      const h = rect.height > 10 ? rect.height : window.innerHeight;
      if (w < 1 || h < 1) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.renderer.resize(w, h, dpr);
      this.world.resize(w, h, this.renderer.cellWidth, this.renderer.cellHeight);
    }

    schedule() {
      cancelAnimationFrame(this.raf);
      if (this.disposed) return;
      this.last = performance.now();
      this.raf = requestAnimationFrame(this.frame);
    }

    frame = (now) => {
      if (this.disposed) return;
      const dt = Math.min(0.1, (now - this.last) / 1000);
      this.last = now;
      this.acc += dt;
      let steps = 0;
      while (this.acc >= STEP && steps < MAX_STEPS) {
        this.world.step(STEP);
        this.acc -= STEP;
        steps++;
      }
      if (steps === MAX_STEPS) this.acc = 0;
      this.renderer.render(this.world, dt);
      this.raf = requestAnimationFrame(this.frame);
    };

    toLocal(e) {
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const inside = x >= 0 && y >= 0 && x <= rect.width && y <= rect.height;
      return { x, y, inside };
    }

    onPointerMove = (e) => {
      const { x, y, inside } = this.toLocal(e);
      const p = this.world.pointer;
      p.x = x;
      p.y = y;
      p.active = inside;
    };

    onPointerDown = (e) => {
      if (
        e.target &&
        e.target !== this.canvas &&
        e.target.closest &&
        e.target.closest(".focus-card, .modal-backdrop, .floating-pill, button, input, select, a")
      ) {
        return;
      }
      const { x, y, inside } = this.toLocal(e);
      if (inside) this.world.splash(x, y);
    };

    onPointerLeave = () => {
      this.world.pointer.active = false;
    };
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 1. PULSING JELLYFISH ENGINE ("jellyfish")
  // ═══════════════════════════════════════════════════════════════════════════

  const TENTACLE_NODES = 18;
  const JELLY_ACCENTS = ["#db2777", "#c026d3", "#9333ea", "#ec4899", "#a855f7", "#e11d48"];
  const JELLY_SHAPES = {
    moon: {
      bellLen: 0.36,
      bellRad: 0.28,
      domePower: 0.70,
      lobes: 8,
      canals: 8,
      // 5 well-spaced tails (3 central frilled oral arms + 2 outer long marginal tentacles)
      chainFracs: [-0.80, -0.38, 0.0, 0.38, 0.80],
      chainOral: [false, true, true, true, false],
      oralWidth: 0.025,
      tentacleWidth: 0.018,
      gonadRing: true,
      tint: [1.05, 0.73, 1.06], // Orchid / mauve gray-pink
    },
    compass: {
      bellLen: 0.37,
      bellRad: 0.27,
      domePower: 0.72,
      lobes: 10,
      canals: 6,
      chainFracs: [-0.82, -0.40, 0.0, 0.40, 0.82],
      chainOral: [false, true, true, true, false],
      oralWidth: 0.026,
      tentacleWidth: 0.018,
      compassMarks: true,
      tint: [1.11, 0.72, 0.92], // Dusty rose gray-pink
    },
    lion: {
      bellLen: 0.35,
      bellRad: 0.29,
      domePower: 0.68,
      lobes: 12,
      canals: 10,
      // 6 well-spaced tails across the wide lion's mane bell
      chainFracs: [-0.84, -0.48, -0.16, 0.16, 0.48, 0.84],
      chainOral: [false, true, true, true, true, false],
      oralWidth: 0.025,
      tentacleWidth: 0.018,
      gonadRing: true,
      tint: [1.14, 0.69, 0.96], // Vivid magenta-rose gray-pink
    },
    crystal: {
      bellLen: 0.38,
      bellRad: 0.26,
      domePower: 0.76,
      lobes: 8,
      canals: 6,
      chainFracs: [-0.76, -0.26, 0.26, 0.76],
      chainOral: [false, true, true, false],
      oralWidth: 0.025,
      tentacleWidth: 0.018,
      tint: [0.95, 0.72, 1.13], // Amethyst lavender gray-purple
    },
  };
  const JELLY_KINDS = Object.keys(JELLY_SHAPES);
  const JELLY_TINTS = {};
  for (const k of JELLY_KINDS) JELLY_TINTS[k] = JELLY_SHAPES[k].tint;

  const DEFAULT_JELLIES = [
    { kind: "compass", size: 1.0 },
    { kind: "moon", size: 0.92 },
    { kind: "lion", size: 0.94 },
    { kind: "crystal", size: 0.84 },
  ];

  class JellyWorld {
    constructor(specs = DEFAULT_JELLIES) {
      this.specs = specs;
      this.width = 0;
      this.height = 0;
      this.time = 0;
      this.jellies = [];
      this.plankton = [];
      this.events = [];
      this.pointer = { x: 0, y: 0, active: false };
      this.tmp = { x: 0, y: 0 };
    }

    resize(width, height) {
      const first = this.width === 0;
      this.width = width;
      this.height = height;
      if (first || this.jellies.length === 0) {
        this.seed();
        return;
      }
      for (const p of this.plankton) {
        p.x = clamp(p.x, 0, width);
        p.y = clamp(p.y, 0, height);
      }
    }

    seed() {
      const { width: W, height: H } = this;
      const minSide = Math.min(W, H) || 600;
      const baseLength = clamp(minSide * 0.42, 195, 380);
      const count = this.specs.length;
      const isSwarm = count > 6;

      this.jellies = [];
      for (let i = 0; i < count; i++) {
        const { kind, size } = this.specs[i];
        const shape = JELLY_SHAPES[kind] || JELLY_SHAPES.moon;
        const length = baseLength * size;
        // Distinct orbital lanes scaled so both 4-jelly and 22-mini-jelly blooms fit inside the screen
        const orbitRadius = isSwarm
          ? minSide * (0.20 + (i % 7) * 0.042 + rand(-0.012, 0.012))
          : minSide * (0.24 + i * 0.052 + rand(-0.015, 0.015));
        const a = (i / count) * TAU + rand(-0.18, 0.18);
        const orbitDir = i % 2 === 0 ? 1 : -1;
        const x = W / 2 + Math.cos(a) * orbitRadius * (W / minSide) * 0.88;
        const y = H / 2 + Math.sin(a) * orbitRadius;
        const heading = a + (orbitDir * Math.PI) / 2;

        const pulsePhase = (i / count) * TAU;
        const initContract = Math.sin(pulsePhase);
        const initExpandOut = Math.max(0, -initContract);
        const initContractIn = Math.max(0, initContract);
        const initBellLen = length * shape.bellLen * (1 + 0.12 * initContractIn + 0.32 * initExpandOut);
        const initBellRad = length * shape.bellRad * (1 - 0.16 * initContractIn + 0.03 * initExpandOut);
        const chains = [];
        // Mini jellyfish (< 0.56 size) use 3 well-spaced tails so tails never crowd on a small bell
        const isMini = size < 0.56;
        const fracs = isMini ? [-0.72, 0.0, 0.72] : shape.chainFracs || [-0.80, -0.36, 0.0, 0.36, 0.80];
        const orals = isMini ? [false, true, false] : shape.chainOral || [false, true, true, true, false];
        for (let c = 0; c < fracs.length; c++) {
          const isOral = orals[c];
          const frac = fracs[c];
          const chainLen = length * (isOral ? rand(0.56, 0.65) : rand(0.70, 0.84));
          const seg = chainLen / (TENTACLE_NODES - 1);
          const nodes = new Float32Array(TENTACLE_NODES * 2);
          const nx = -Math.sin(heading);
          const ny = Math.cos(heading);
          const attachDist = initBellLen * 0.84;
          const baseX = x - Math.cos(heading) * attachDist + nx * frac * initBellRad;
          const baseY = y - Math.sin(heading) * attachDist + ny * frac * initBellRad;
          // Staggered phase per tail so adjacent tails ripple in a harmonious wave without merging
          const phaseOff = c * 0.65;
          const trailAngle = heading + Math.PI + frac * 0.10;
          nodes[0] = baseX;
          nodes[1] = baseY;
          for (let n = 1; n < TENTACLE_NODES; n++) {
            const s = n / (TENTACLE_NODES - 1);
            const travelWave = Math.sin(pulsePhase - 1.3 - s * 4.2 + phaseOff);
            const waveAmp = (isOral ? 0.42 : 0.48) * Math.pow(s, 0.65);
            const ang = trailAngle + travelWave * waveAmp;
            nodes[n * 2] = nodes[(n - 1) * 2] + Math.cos(ang) * seg;
            nodes[n * 2 + 1] = nodes[(n - 1) * 2 + 1] + Math.sin(ang) * seg;
          }
          chains.push({
            isOral,
            frac,
            length: chainLen,
            nodes,
            trailAngle,
            phaseOff,
          });
        }

        this.jellies.push({
          id: i + 1,
          kind,
          size,
          length,
          x,
          y,
          heading,
          speed: isMini ? 9 : 11,
          pulsePhase,
          pulseRate: rand(0.74, 0.96), // Slow, hypnotic wave-swimming cadence
          contract: Math.sin(pulsePhase),
          turn: 0,
          wander: 0,
          orbitDir,
          orbitRadius,
          depth: clamp(0.72 + size * 0.28, 0.78, 1.0),
          chains,
          lastPulseEmit: 0,
        });
      }
      this.jellies.sort((a, b) => a.length - b.length);

      const pTotal = clamp(Math.round((W * H) / 5200), 75, 260);
      this.plankton = [];
      for (let i = 0; i < pTotal; i++) {
        const dir = rand(0, TAU);
        const spd = rand(6, 18);
        this.plankton.push({
          x: rand(0, W),
          y: rand(0, H),
          vx: Math.cos(dir) * spd,
          vy: Math.sin(dir) * spd,
          alarm: 0,
          alive: true,
          turn: 0,
          depth: rand(0.55, 1),
          phase: rand(0, TAU),
        });
      }
    }

    splash(x, y) {
      this.events.push({ kind: "splash", x, y });
      const r = 240;
      for (const p of this.plankton) {
        const dx = p.x - x;
        const dy = p.y - y;
        const d = Math.hypot(dx, dy);
        if (d > r || d < 1e-3) continue;
        const k = (1 - d / r) * 200;
        p.vx += (dx / d) * k;
        p.vy += (dy / d) * k;
        p.alarm = 1;
      }
    }

    step(dt) {
      this.time += dt;
      this.stepPlankton(dt);
      this.stepJellies(dt);
    }

    stepPlankton(dt) {
      const { plankton, jellies, pointer, width: W, height: H, time, tmp: cur } = this;
      const calm = Math.exp(-dt * 0.8);
      for (const p of plankton) {
        p.alarm *= calm;
        flowCurrent(p.x, p.y, time, cur);
        let ax = cur.x * 0.38 - p.vx * 0.65 + Math.cos(time * 0.7 + p.phase) * 6;
        let ay = cur.y * 0.38 - p.vy * 0.65 + Math.sin(time * 0.6 + p.phase) * 6;

        for (const jel of jellies) {
          const dx = p.x - jel.x;
          const dy = p.y - jel.y;
          const r = jel.length * 0.38 + 32;
          const d = Math.hypot(dx, dy);
          if (d < r && d > 1e-3) {
            const w = (1 - d / r) ** 2;
            ax += (dx / d) * 320 * w;
            ay += (dy / d) * 320 * w;
            p.alarm = Math.max(p.alarm, w * 0.7);
          }
        }

        if (pointer.active) {
          const dx = p.x - pointer.x;
          const dy = p.y - pointer.y;
          const d = Math.hypot(dx, dy);
          if (d < 130 && d > 1e-3) {
            const w = (1 - d / 130) ** 2;
            ax += (dx / d) * 650 * w;
            ay += (dy / d) * 650 * w;
            p.alarm = Math.max(p.alarm, w * 0.8);
          }
        }

        const before = Math.atan2(p.vy, p.vx);
        p.vx += ax * dt;
        p.vy += ay * dt;
        const spd = Math.hypot(p.vx, p.vy);
        const maxSpd = 34 + p.alarm * 65;
        if (spd > maxSpd) {
          p.vx *= maxSpd / spd;
          p.vy *= maxSpd / spd;
        }
        p.turn = angleDiff(before, Math.atan2(p.vy, p.vx)) / dt;
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        if (p.x < -20) p.x = W + 20;
        else if (p.x > W + 20) p.x = -20;
        if (p.y < -20) p.y = H + 20;
        else if (p.y > H + 20) p.y = -20;
      }
    }

    stepJellies(dt) {
      const { jellies, pointer, width: W, height: H, time, tmp: cur } = this;
      const minSide = Math.min(W, H) || 1;
      const cxW = W / 2;
      const cyW = H / 2;

      for (const jel of jellies) {
        const L = jel.length;
        const shape = JELLY_SHAPES[jel.kind] || JELLY_SHAPES.moon;

        // Continuous, slow sinusoidal swimming wave (no sudden turbo/propeller jump)
        jel.pulsePhase = (jel.pulsePhase + dt * jel.pulseRate) % TAU;
        jel.contract = Math.sin(jel.pulsePhase);
        // Smooth wave thrust lags the apex contraction as the wave travels down the bell margin
        const waveThrust = Math.pow(0.5 + 0.5 * Math.sin(jel.pulsePhase - 0.55), 1.35);

        if (jel.contract > 0.85 && time - jel.lastPulseEmit > 2.6) {
          jel.lastPulseEmit = time;
          const rimX = jel.x - Math.cos(jel.heading) * L * shape.bellLen * 0.85;
          const rimY = jel.y - Math.sin(jel.heading) * L * shape.bellLen * 0.85;
          this.events.push({ kind: "pulse", x: rimX, y: rimY });
        }

        const fx0 = Math.cos(jel.heading);
        const fy0 = Math.sin(jel.heading);
        const nx0 = -fy0;
        const ny0 = fx0;

        let dx = fx0 * 1.4;
        let dy = fy0 * 1.4;
        jel.wander = clamp(jel.wander + (Math.random() - 0.5) * dt * 0.9, -0.55, 0.55);
        dx += Math.cos(jel.heading + jel.wander) * 0.24;
        dy += Math.sin(jel.heading + jel.wander) * 0.24;

        const rx = (jel.x - cxW) / (W / minSide);
        const ry = jel.y - cyW;
        const rDist = Math.hypot(rx, ry) || 1;
        const targetR = jel.orbitRadius * (1 + 0.14 * Math.sin(time * 0.03 + jel.id));
        const radial = clamp((targetR - rDist) / targetR, -1, 1);
        dx += ((-ry / rDist) * jel.orbitDir + (rx / rDist) * radial * 0.75) * 0.48;
        dy += ((rx / rDist) * jel.orbitDir + (ry / rDist) * radial * 0.75) * 0.48;

        // Pointer avoidance: steer laterally so it glides aside rather than flipping 180 deg
        if (pointer.active) {
          const pdx = jel.x - pointer.x;
          const pdy = jel.y - pointer.y;
          const pd = Math.hypot(pdx, pdy);
          const pRange = L * 0.75 + 70;
          if (pd < pRange && pd > 1e-3) {
            const pw = (1 - pd / pRange) * 1.6;
            const side = pdx * nx0 + pdy * ny0 >= 0 ? 1 : -1;
            dx += nx0 * side * pw;
            dy += ny0 * side * pw;
          }
        }

        // Predictive Path-Crossing Radar (Closest Point of Approach) & Non-Sticking Avoidance:
        // 1. Amplified radar anticipates future path intersections up to 6.5s ahead and steers
        //    smoothly along a stable lateral side while gently modulating speed so one jellyfish
        //    glides ahead and the other yields behind.
        // 2. Any close-contact cushion is strictly lateral (perpendicular to heading), NEVER
        //    opposing forward swimming velocity so jellyfish can never get stuck in place!
        let latSlide = 0;
        let speedMod = 1.0;
        let radarUrgency = 0;

        for (const other of jellies) {
          if (other === jel) continue;
          const otherShape = JELLY_SHAPES[other.kind] || JELLY_SHAPES.moon;

          // Vector from jel to other
          const toX = other.x - jel.x;
          const toY = other.y - jel.y;
          const curDist = Math.hypot(toX, toY) || 1;

          // Relative velocity for Closest Point of Approach (CPA) prediction
          const ovx = Math.cos(other.heading) * other.speed;
          const ovy = Math.sin(other.heading) * other.speed;
          const rvx = ovx - fx0 * jel.speed;
          const rvy = ovy - fy0 * jel.speed;
          const rv2 = rvx * rvx + rvy * rvy;
          const tCPA = rv2 > 1e-2 ? clamp(-(toX * rvx + toY * rvy) / rv2, 0, 6.5) : 0;
          const cpaX = toX + rvx * tCPA;
          const cpaY = toY + rvy * tCPA;
          const cpaDist = Math.hypot(cpaX, cpaY);
          const effDist = Math.min(curDist, cpaDist * 0.92 + curDist * 0.08);

          // Amplified predictive radar radius (compact for mini-jellyfish swarm so 22 jellies share the screen)
          const radarRadius = (L + other.length) * (jellies.length > 6 ? 0.65 : 1.18);
          if (effDist < radarRadius) {
            const ahead = (toX / curDist) * fx0 + (toY / curDist) * fy0;
            if (ahead > -0.35) {
              const proximity = Math.pow(1 - effDist / radarRadius, 1.25);
              radarUrgency = Math.max(radarUrgency, proximity);

              // Stable lateral pass side: use lateral offset at CPA, with deterministic tie-breaker by id
              const latOffset = -(cpaX * nx0 + cpaY * ny0);
              const passSide = Math.abs(latOffset) > L * 0.14
                ? (latOffset > 0 ? 1 : -1)
                : (jel.id < other.id ? 1 : -1);

              const steerW = proximity * 2.35 * (0.55 + 0.45 * Math.max(0, ahead));
              dx += nx0 * passSide * steerW;
              dy += ny0 * passSide * steerW;

              // Gentle speed yield/boost so crossing paths naturally stagger instead of meeting simultaneously
              if (ahead > 0.15) {
                speedMod *= jel.id < other.id ? 1 + 0.16 * proximity : 1 - 0.14 * proximity;
              }
            }
          }

          // Purely lateral soft slide if bells or upper tentacles get close (NEVER opposes forward speed!)
          const oMidX = other.x - Math.cos(other.heading) * other.length * 0.26;
          const oMidY = other.y - Math.sin(other.heading) * other.length * 0.26;
          for (const [oxP, oyP, rScale] of [[other.x, other.y, 1.0], [oMidX, oMidY, 0.82]]) {
            const cx = jel.x - oxP;
            const cy = jel.y - oyP;
            const cd = Math.hypot(cx, cy);
            const contactDist = (L * shape.bellRad + other.length * otherShape.bellRad) * 1.12 * rScale;
            if (cd < contactDist && cd > 1e-3) {
              const push = (1 - cd / contactDist) * 18;
              const latProj = (cx / cd) * nx0 + (cy / cd) * ny0;
              const slideSign = Math.abs(latProj) > 0.08 ? Math.sign(latProj) : (jel.id < other.id ? 1 : -1);
              latSlide += slideSign * push;
            }
          }
        }

        // Wide, smooth boundary radar so jellyfish curve gracefully along screen edges without getting pinned
        const edgePad = 128;
        const over = Math.max(-jel.x + edgePad, jel.x - (W - edgePad), -jel.y + edgePad, jel.y - (H - edgePad));
        let edgeUrgency = 0;
        if (over > 0) {
          edgeUrgency = clamp(over / (edgePad * 0.85), 0, 1);
          const w = edgeUrgency * 2.4;
          const toX = cxW - jel.x;
          const toY = cyW - jel.y;
          const d = Math.hypot(toX, toY) || 1;
          const ux = toX / d;
          const uy = toY / d;
          const forwardDot = ux * fx0 + uy * fy0;
          if (forwardDot < 0) {
            const side = ux * nx0 + uy * ny0 >= 0 ? 1 : -1;
            dx += (nx0 * side * 0.90 + ux * 0.45) * w;
            dy += (ny0 * side * 0.90 + uy * 0.45) * w;
          } else {
            dx += ux * w;
            dy += uy * w;
          }
        }

        const desired = Math.atan2(dy, dx);
        // Smooth turn rate that gently adapts when anticipating a path crossing or curving near a border
        const urgency = Math.max(radarUrgency, edgeUrgency);
        const maxTurn = (0.24 + 0.22 * urgency) * dt;
        const turned = clamp(angleDiff(jel.heading, desired), -maxTurn, maxTurn);
        jel.heading += turned;
        jel.turn += (turned / dt - jel.turn) * Math.min(1, dt * 2.2);

        // Slow, serene wave-swimming speed with gentle crossing stagger
        const baseGlide = 6.2 + L * 0.008;
        const pulseBoost = (10.5 + L * 0.016) * waveThrust;
        const targetSpeed = (baseGlide + pulseBoost) * clamp(speedMod, 0.82, 1.18);
        jel.speed += (targetSpeed - jel.speed) * Math.min(1, dt * 2.0);

        flowCurrent(jel.x, jel.y, time, cur);
        const fx = Math.cos(jel.heading);
        const fy = Math.sin(jel.heading);
        const nx = -fy;
        const ny = fx;

        jel.x = clamp(jel.x + (fx * jel.speed + nx * latSlide + cur.x * 0.08) * dt, -10, W + 10);
        jel.y = clamp(jel.y + (fy * jel.speed + ny * latSlide + cur.y * 0.08) * dt, -10, H + 10);

        // Update trailing oral arms & marginal tentacles with a smooth, unified travelling wave
        // Bell length grows taller & rounder when waving outward so the head is never flat!
        const expandOut = Math.max(0, -jel.contract);
        const contractIn = Math.max(0, jel.contract);
        const curBellLen = L * shape.bellLen * (1 + 0.12 * contractIn + 0.32 * expandOut);
        const curBellRad = L * shape.bellRad * (1 - 0.16 * contractIn + 0.03 * expandOut);
        const attachDist = curBellLen * 0.84;

        for (const ch of jel.chains) {
          const nodes = ch.nodes;
          // Rim flare wave at the attachment point
          const rimWave = Math.sin(jel.pulsePhase - 1.55);
          const lat = ch.frac * curBellRad * (1 + 0.08 * rimWave);
          nodes[0] = jel.x - fx * attachDist + nx * lat;
          nodes[1] = jel.y - fy * attachDist + ny * lat;

          // Smoothly blend the chain's base trailing direction toward opposite of bell heading
          const targetTrail = jel.heading + Math.PI + ch.frac * (0.10 + 0.08 * rimWave);
          const trailDiff = angleDiff(ch.trailAngle, targetTrail);
          ch.trailAngle += trailDiff * Math.min(1, dt * 2.8);

          const seg = ch.length / (TENTACLE_NODES - 1);
          let prevAngle = ch.trailAngle;

          for (let k = 1; k < TENTACLE_NODES; k++) {
            const s = k / (TENTACLE_NODES - 1);
            const px = nodes[(k - 1) * 2];
            const py = nodes[(k - 1) * 2 + 1];

            // Slow travelling S-wave continuing seamlessly from the bell down the length of the tail
            const travelWave = Math.sin(jel.pulsePhase - 1.3 - s * 4.2 + ch.phaseOff);
            const waveAmp = (ch.isOral ? 0.42 : 0.48) * Math.pow(s, 0.65);
            const desiredSegAngle = ch.trailAngle + travelWave * waveAmp;

            // Blend existing segment orientation smoothly toward the travelling wave angle
            const curSegAngle = Math.atan2(nodes[k * 2 + 1] - py, nodes[k * 2] - px);
            let angle = curSegAngle + angleDiff(curSegAngle, desiredSegAngle) * Math.min(1, dt * 5.5);
            const maxBend = ch.isOral ? 0.25 : 0.28;
            angle = prevAngle + clamp(angleDiff(prevAngle, angle), -maxBend, maxBend);

            nodes[k * 2] = px + Math.cos(angle) * seg;
            nodes[k * 2 + 1] = py + Math.sin(angle) * seg;
            prevAngle = angle;
          }
        }
      }
    }
  }

  class JellyRenderer extends BaseAsciiRenderer {
    constructor(canvas) {
      super(canvas, JELLY_KINDS, JELLY_TINTS);
      this.ambientGlyph = "·";
      this.curJel = null;
      this.curShape = JELLY_SHAPES.moon;
      // Soft rose-lavender wake dots to match the gray-pink / purple-gray jellyfish palette
      this.dotStyles = [];
      for (let l = 0; l < ALPHA_LEVELS; l++) {
        const a = (0.34 * (l + 1)) / ALPHA_LEVELS;
        this.dotStyles.push(`rgba(192, 108, 168, ${a.toFixed(3)})`);
      }
    }

    render(world, dt) {
      const { ctx, dpr, cols, ch } = this;
      if (cols === 0) return;
      const t = world.time;

      this.consumeEvents(world);
      this.rasterizeJellies(world.jellies, t);
      this.depositWake(world);
      this.diffuse(dt);

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(this.bg, 0, 0);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      this.markAmbient(world.plankton);
      this.drawDots();

      ctx.font = `600 ${Math.round(ch * 0.74)}px ${this.fontFamily}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      this.drawHeat();
      this.drawAmbient(["-", "·", "°"]);
      this.drawCells(t);
    }

    depositWake(world) {
      const { energy } = this;
      for (const p of world.plankton) {
        const i = this.cellIndex(p.x, p.y);
        if (i >= 0) energy[i] = Math.min(1.6, energy[i] + 0.008 + p.alarm * 0.025);
      }
      for (const jel of world.jellies) {
        for (const ch of jel.chains) {
          for (let k = TENTACLE_NODES - 4; k < TENTACLE_NODES; k++) {
            const i = this.cellIndex(ch.nodes[k * 2], ch.nodes[k * 2 + 1]);
            if (i >= 0) energy[i] = Math.min(1.6, energy[i] + 0.026 + jel.speed * 0.001);
          }
        }
      }
      if (world.pointer.active) {
        this.stamp(energy, world.pointer.x, world.pointer.y, 1, 0.08);
      }
    }

    sampleJelly(px, py) {
      const jel = this.curJel;
      const shape = this.curShape;
      const L = jel.length;
      const fx = Math.cos(jel.heading);
      const fy = Math.sin(jel.heading);
      const nx = -fy;
      const ny = fx;

      // 1. Check Bell / Umbrella Dome with Fluent Travelling Wave Profile
      // Keep the contracted shape sleek, and when waving outward (expandOut > 0) make the head bigger, deeper & rounder!
      const expandOut = Math.max(0, -jel.contract);
      const contractIn = Math.max(0, jel.contract);
      const curBellLen = L * shape.bellLen * (1 + 0.12 * contractIn + 0.32 * expandOut);
      const curBellRad = L * shape.bellRad * (1 - 0.16 * contractIn + 0.03 * expandOut);
      const relX = px - jel.x;
      const relY = py - jel.y;
      const u = -(relX * fx + relY * fy);
      const v = relX * nx + relY * ny;
      const a = Math.abs(v);

      const sBell = u / (curBellLen || 1);
      if (sBell >= -0.02 && sBell <= 1.15) {
        const sClamped = clamp(sBell, 0, 1);
        // Travelling peristaltic wave propagating down the lower skirt (s > 0.55), keeping the upper crown big & round!
        const waveAlongBell = Math.sin(jel.pulsePhase - sClamped * 2.15);
        const waveFlare = 1 - 0.07 * waveAlongBell * smoothstep(0.55, 0.98, sClamped);
        const effDomePower = shape.domePower + 0.22 * expandOut;

        let domeProfile;
        if (sClamped < 0.74) {
          domeProfile = Math.pow(Math.sin(((sClamped / 0.74) * Math.PI) / 2), effDomePower) * waveFlare;
        } else {
          const k = (sClamped - 0.74) / 0.26;
          domeProfile = (1 - (0.05 + 0.08 * contractIn) * k * k) * waveFlare;
        }
        const domeW = curBellRad * domeProfile;
        const across = a / (domeW || 1);

        // Full, deep subumbrella arch + scalloped lappet rim so the head never looks flat in the center
        const lappetWave = 0.034 * Math.cos(across * shape.lobes * Math.PI + jel.pulsePhase * 0.5);
        const rimS = (0.88 + 0.04 * expandOut) + (0.12 - 0.04 * expandOut) * Math.pow(clamp(across, 0, 1), 1.45) + lappetWave;

        if (a <= domeW && sBell >= 0 && sBell <= rimS) {
          this.hitDist = 0;
          this.hitS = sClamped * 0.35;
          this.hitV = v;

          const facing = (nx * -0.6 + ny * -0.8) * (v / (curBellRad || 1));
          let shade = 0.58 - across * across * 0.36 + (1 - sClamped) * 0.18 + facing * 0.20 + waveAlongBell * 0.06;
          let flag = FLAG_BODY;

          const canalWave = Math.abs(Math.sin(across * shape.canals * Math.PI * 0.5));
          const ringR = Math.hypot((sClamped - 0.40) * 2.2, across * 1.35);

          if (sBell > rimS - 0.14 || across > 0.85) {
            flag = FLAG_FIN;
            shade = 0.36 + 0.24 * (1 - across);
          } else if (shape.gonadRing && ringR > 0.26 && ringR < 0.52 && across < 0.58) {
            flag = FLAG_RIDGE;
            shade = 0.92;
          } else if (shape.compassMarks && canalWave > 0.86 && sClamped > 0.10 && sClamped < 0.75) {
            flag = FLAG_MARK;
            shade = 0.88;
          } else if (canalWave > 0.93 && sClamped > 0.14 && sClamped < 0.76) {
            flag = FLAG_RIDGE;
            shade = 0.88;
          } else if (sClamped < 0.14 && across < 0.45) {
            shade = Math.max(shade, 0.74);
          }

          this.hitFlag = flag;
          this.hitShade = clamp(shade, 0, 1);
          return true;
        }
      }

      // 2. Check Iconic Oral Arms & Marginal Tentacles (well-spaced & minimum-width protected so they never vanish)
      let bestDist = Infinity;
      const isMini = (jel.size || 1) < 0.56;
      const minOralPx = isMini ? Math.max(3.6, this.ch * 0.25) : Math.max(4.8, this.ch * 0.34);
      const minTentPx = isMini ? Math.max(3.2, this.ch * 0.22) : Math.max(4.1, this.ch * 0.29);

      for (let cIdx = 0; cIdx < jel.chains.length; cIdx++) {
        const ch = jel.chains[cIdx];
        const nodes = ch.nodes;
        const baseW = L * (ch.isOral ? shape.oralWidth : shape.tentacleWidth);

        for (let k = 0; k < TENTACLE_NODES - 1; k++) {
          const ax = nodes[k * 2];
          const ay = nodes[k * 2 + 1];
          const bx = nodes[(k + 1) * 2];
          const by = nodes[(k + 1) * 2 + 1];
          const abx = bx - ax;
          const aby = by - ay;
          const ab2 = abx * abx + aby * aby || 1e-6;
          const apx = px - ax;
          const apy = py - ay;
          const t = clamp((apx * abx + apy * aby) / ab2, 0, 1);
          const qx = ax + abx * t;
          const qy = ay + aby * t;
          const d = Math.hypot(px - qx, py - qy);
          if (d < bestDist) bestDist = d;

          const sChain = (k + t) / (TENTACLE_NODES - 1);
          let w;
          if (ch.isOral) {
            const frill = 0.85 + 0.22 * Math.sin(sChain * 12 - jel.pulsePhase + cIdx * 1.5);
            w = Math.max(minOralPx * (1 - 0.22 * sChain), baseW * (1 - 0.40 * Math.pow(sChain, 0.95)) * frill);
          } else {
            w = Math.max(minTentPx * (1 - 0.18 * sChain), baseW * (1 - 0.28 * sChain));
          }

          if (d <= w) {
            const across = d / (w || 1);
            this.hitDist = 0;
            this.hitS = 0.35 + sChain * 0.65;
            this.hitV = (abx * apy - aby * apx >= 0 ? d : -d) + cIdx * 12;
            if (ch.isOral) {
              this.hitFlag = across < 0.56 ? FLAG_BODY : FLAG_FIN;
              this.hitShade = (0.68 - 0.20 * sChain) * (1 - across * 0.28);
            } else {
              this.hitFlag = across < 0.46 ? FLAG_BODY : FLAG_FIN;
              this.hitShade = 0.52 + 0.22 * (1 - sChain) * (1 - across * 0.25);
            }
            return true;
          }
        }
      }

      this.hitDist = Math.min(bestDist, Math.hypot(relX, relY));
      return false;
    }

    rasterizeJellies(jellies, t) {
      const { cellFlag, cellShade, cellKey, cellDepth, cellKind, cw, ch, cols, rows } = this;
      cellFlag.fill(0);

      for (const jel of jellies) {
        this.curJel = jel;
        this.curShape = JELLY_SHAPES[jel.kind] || JELLY_SHAPES.moon;
        const kindIndex = Math.max(0, JELLY_KINDS.indexOf(jel.kind));
        const L = jel.length;

        const pad = L * 0.38;
        let minX = jel.x - pad;
        let maxX = jel.x + pad;
        let minY = jel.y - pad;
        let maxY = jel.y + pad;
        for (const chain of jel.chains) {
          const n = chain.nodes;
          for (let k = 0; k < TENTACLE_NODES; k++) {
            const nx = n[k * 2];
            const ny = n[k * 2 + 1];
            if (nx < minX) minX = nx;
            if (nx > maxX) maxX = nx;
            if (ny < minY) minY = ny;
            if (ny > maxY) maxY = ny;
          }
        }
        const reach = L * 0.09 + 16;
        const c0 = Math.max(0, Math.floor((minX - reach) / cw));
        const c1 = Math.min(cols - 1, Math.floor((maxX + reach) / cw));
        const r0 = Math.max(0, Math.floor((minY - reach) / ch));
        const r1 = Math.min(rows - 1, Math.floor((maxY + reach) / ch));
        if (c0 > c1 || r0 > r1) continue;

        const skipBeyond = L * 0.09 + Math.hypot(cw, ch);

        for (let r = r0; r <= r1; r++) {
          for (let c = c0; c <= c1; c++) {
            const x = c * cw;
            const y = r * ch;
            const centerHit = this.sampleJelly(x + cw / 2, y + ch / 2);
            if (!centerHit && this.hitDist > skipBeyond) continue;

            let bestFlag = centerHit ? this.hitFlag : 0;
            let bestShade = centerHit ? this.hitShade : 0;
            let bestS = centerHit ? this.hitS : 0;
            let bestV = centerHit ? this.hitV : 0;

            let hits = centerHit ? 1 : 0;
            for (let k = 0; k < SUBSAMPLES.length; k += 2) {
              if (this.sampleJelly(x + SUBSAMPLES[k] * cw, y + SUBSAMPLES[k + 1] * ch)) {
                hits++;
                if (!bestFlag || this.hitShade > bestShade) {
                  bestFlag = this.hitFlag;
                  bestShade = this.hitShade;
                  bestS = this.hitS;
                  bestV = this.hitV;
                }
              }
            }
            if (hits === 0) continue;
            const coverage = hits / 5;

            const i = r * cols + c;
            const key = (hash3(Math.round(bestS * 52), Math.round(bestV / (cw * 0.9)), jel.id) * 4294967295) >>> 0;
            cellKey[i] = key;
            cellDepth[i] = jel.depth;
            cellKind[i] = kindIndex;

            // Keep tails (bestS >= 0.35) solid even when angled/horizontal so tentacles never break up or vanish!
            const isTail = bestS >= 0.35;
            if ((centerHit && coverage >= 0.4) || (isTail && (hits >= 2 || bestShade > 0.44)) || coverage >= 0.6) {
              cellFlag[i] = bestFlag || FLAG_FIN;
              const flicker = (hash3(c, r, Math.floor(t * 4)) - 0.5) * 0.05;
              cellShade[i] = clamp(bestShade + flicker, 0, 1);
            } else {
              cellFlag[i] = FLAG_EDGE;
              cellShade[i] = coverage;
            }
          }
        }
      }
    }

    drawCells(t) {
      const { ctx, cols, rows, cw, ch, cellFlag, cellShade, cellKey, cellDepth, cellKind, kinds, tints } = this;
      const n = cols * rows;
      for (let i = 0; i < n; i++) {
        const flag = cellFlag[i];
        if (!flag) continue;
        const col = i % cols;
        const row = (i / cols) | 0;
        const x = col * cw;
        const y = row * ch;
        const key = cellKey[i];
        const shade = cellShade[i];
        const dim = 0.80 + 0.20 * cellDepth[i];
        const kindName = kinds[cellKind[i]] || kinds[0];
        const [tr, tg, tb] = tints[kindName] || [1.06, 0.72, 1.02];

        const tick = Math.floor(t * 2.0 + (key % 997) / 97);
        const roll = hash3(key, tick, 7);

        if (flag === FLAG_EDGE) {
          const set = shade >= 0.5 ? EDGE_HEAVY : EDGE_LIGHT;
          const glyph = set[(key >>> 8) % set.length];
          ctx.fillStyle = roll < 0.06 ? JELLY_ACCENTS[key % JELLY_ACCENTS.length] : "rgba(146, 86, 134, 0.74)";
          ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
          continue;
        }

        let bgLevel;
        let glyph;
        // Boost pink/purple vividness slightly on internal gonad rings & radial markings while staying gray-pink
        let satR = tr;
        let satG = tg;
        let satB = tb;

        if (flag === FLAG_RIDGE) {
          bgLevel = 116;
          satR = tr * 1.06;
          satG = tg * 0.84;
          satB = tb * 1.05;
          glyph = RIDGE_GLYPHS[(key >>> 8) % RIDGE_GLYPHS.length];
        } else if (flag === FLAG_MARK) {
          bgLevel = 126;
          satR = tr * 1.08;
          satG = tg * 0.82;
          satB = tb * 1.02;
          glyph = MARK_GLYPHS[(key >>> 8) % MARK_GLYPHS.length];
        } else if (flag === FLAG_FIN) {
          bgLevel = 196 - shade * 58;
          glyph = FIN_GLYPHS[(key >>> 8) % FIN_GLYPHS.length];
        } else {
          bgLevel = 218 - shade * 92;
          const jitter = ((key >>> 4) % 3) - 1;
          glyph = SKIN_RAMP[clamp(Math.floor(shade * 8.99) + jitter, 0, SKIN_RAMP.length - 1)];
        }

        bgLevel *= dim;
        const r = clamp(Math.round(bgLevel * satR), 0, 255);
        const g = clamp(Math.round(bgLevel * satG), 0, 255);
        const b = clamp(Math.round(bgLevel * satB), 0, 255);
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.fillRect(x + 1, y + 1, cw - 1, ch - 1);

        let glyphColor;
        if (flag === FLAG_MARK) {
          glyphColor = "#fdf2f8";
        } else if (roll < 0.065) {
          glyphColor = JELLY_ACCENTS[key % JELLY_ACCENTS.length];
        } else if (roll < 0.11) {
          glyphColor = "#ffffff";
        } else if (bgLevel < 145) {
          glyphColor = "#fdf4ff";
        } else {
          glyphColor = "#3b1c38";
        }
        ctx.fillStyle = glyphColor;
        ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
      }
    }
  }

  class JellyfishEngine extends BaseLoopEngine {
    constructor(canvas, specs) {
      const world = new JellyWorld(specs);
      const renderer = new JellyRenderer(canvas);
      super(canvas, world, renderer);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. MANTA RAYS ENGINE ("mantas")
  // ═══════════════════════════════════════════════════════════════════════════

  const MANTA_NODES = 22;
  const MANTA_SHAPES = {
    giant_manta: {
      discNodes: 10, // ~42% disc, 58% whip tail
      wingSpan: 0.55,
      cephalic: true,
      hornLen: 0.23,
      roundedDisc: false,
      pattern: "manta_patches",
      palette: "slate_gray",
      tint: [0.43, 0.46, 0.51], // Charcoal / slate gray with stark white shoulder patches
    },
    spotted_eagle: {
      discNodes: 10,
      wingSpan: 0.50,
      cephalic: false,
      duckbill: true,
      roundedDisc: false,
      pattern: "white_dots",
      palette: "deep_blue",
      tint: [0.17, 0.29, 0.54], // Full deep navy blue spotted with bright white ASCII letter infills
    },
    leopard_ray: {
      discNodes: 12, // Rounded saucer disc (~52% of length)
      wingSpan: 0.40,
      cephalic: false,
      duckbill: false,
      roundedDisc: true, // Smooth oval/circular stingray silhouette
      pattern: "leopard_rosettes",
      palette: "brown_black",
      tint: [0.76, 0.57, 0.36], // Warm sandy-brown disc with charcoal-black leopard rosettes
    },
    reef_manta: {
      discNodes: 11,
      wingSpan: 0.50,
      cephalic: true,
      hornLen: 0.20,
      curvedWings: true,
      roundedDisc: false,
      pattern: "reef_chevron",
      palette: "steel_blue",
      tint: [0.32, 0.54, 0.76], // Lighter steel / cerulean ocean blue with dorsal V-chevron
    },
  };
  const MANTA_KINDS = Object.keys(MANTA_SHAPES);
  const MANTA_TINTS = {};
  for (const k of MANTA_KINDS) MANTA_TINTS[k] = MANTA_SHAPES[k].tint;

  const DEFAULT_MANTAS = [
    { kind: "giant_manta", size: 0.96 },
    { kind: "spotted_eagle", size: 0.88 },
    { kind: "reef_manta", size: 0.80 },
    { kind: "leopard_ray", size: 0.78 },
  ];

  class MantaWorld {
    constructor(specs = DEFAULT_MANTAS) {
      this.specs = specs;
      this.width = 0;
      this.height = 0;
      this.time = 0;
      this.mantas = [];
      this.fish = [];
      this.events = [];
      this.pointer = { x: 0, y: 0, active: false };
      this.tmp = { x: 0, y: 0 };
    }

    resize(width, height) {
      const first = this.width === 0;
      this.width = width;
      this.height = height;
      if (first || this.mantas.length === 0) {
        this.seed();
        return;
      }
      for (const f of this.fish) {
        f.x = clamp(f.x, 0, width);
        f.y = clamp(f.y, 0, height);
      }
    }

    seed() {
      const { width: W, height: H } = this;
      const minSide = Math.min(W, H) || 600;
      const baseLen = clamp(minSide * 0.39, 185, 345);
      const count = this.specs.length;

      this.mantas = [];
      for (let i = 0; i < count; i++) {
        const { kind, size } = this.specs[i];
        const length = baseLen * size;
        // Distinct orbital lanes so mantas don't crowd the same radius
        const orbitRadius = minSide * (0.21 + i * 0.068 + rand(-0.015, 0.015));
        const a = (i / count) * TAU + rand(-0.18, 0.18);
        const orbitDir = i % 2 === 0 ? 1 : -1;
        const x = W / 2 + Math.cos(a) * orbitRadius * (W / minSide) * 0.88;
        const y = H / 2 + Math.sin(a) * orbitRadius;
        const heading = a + (orbitDir * Math.PI) / 2;
        const nodes = new Float32Array(MANTA_NODES * 2);
        const seg = length / (MANTA_NODES - 1);
        for (let n = 0; n < MANTA_NODES; n++) {
          nodes[n * 2] = x - Math.cos(heading) * seg * n;
          nodes[n * 2 + 1] = y - Math.sin(heading) * seg * n;
        }
        this.mantas.push({
          id: i + 1,
          kind,
          length,
          nodes,
          heading,
          speed: 30,
          phase: rand(0, TAU),
          turn: 0,
          wander: 0,
          orbitDir,
          orbitRadius,
          depth: size,
        });
      }
      this.mantas.sort((a, b) => a.length - b.length);

      const fTotal = clamp(Math.round((W * H) / 4800), 80, 280);
      this.fish = [];
      for (let i = 0; i < fTotal; i++) {
        const dir = rand(0, TAU);
        const spd = rand(24, 42);
        this.fish.push({
          x: rand(0, W),
          y: rand(0, H),
          vx: Math.cos(dir) * spd,
          vy: Math.sin(dir) * spd,
          alarm: 0,
          alive: true,
          turn: 0,
          depth: rand(0.55, 1),
          escortId: i < 28 ? (i % count) : -1,
          escortSide: i % 2 === 0 ? 1 : -1,
          escortDist: rand(0.32, 0.62),
        });
      }
    }

    splash(x, y) {
      this.events.push({ kind: "splash", x, y });
      const r = 240;
      for (const f of this.fish) {
        const dx = f.x - x;
        const dy = f.y - y;
        const d = Math.hypot(dx, dy);
        if (d > r || d < 1e-3) continue;
        const k = (1 - d / r) * 260;
        f.vx += (dx / d) * k;
        f.vy += (dy / d) * k;
        f.alarm = 1;
      }
    }

    step(dt) {
      this.time += dt;
      this.stepMantas(dt);
      this.stepFish(dt);
    }

    stepMantas(dt) {
      const { mantas, pointer, width: W, height: H, time } = this;
      const minSide = Math.min(W, H) || 600;
      const cxW = W / 2;
      const cyW = H / 2;

      for (const m of mantas) {
        const L = m.length;
        const shape = MANTA_SHAPES[m.kind] || MANTA_SHAPES.giant_manta;
        const nodes = m.nodes;
        const hx = nodes[0];
        const hy = nodes[1];
        const fx0 = Math.cos(m.heading);
        const fy0 = Math.sin(m.heading);
        const nx0 = -fy0;
        const ny0 = fx0;

        let dx = fx0 * 1.25;
        let dy = fy0 * 1.25;
        m.wander = clamp(m.wander + (Math.random() - 0.5) * dt * 1.8, -0.75, 0.75);
        dx += Math.cos(m.heading + m.wander) * 0.34;
        dy += Math.sin(m.heading + m.wander) * 0.34;

        const rx = (hx - cxW) / (W / minSide);
        const ry = hy - cyW;
        const r = Math.hypot(rx, ry) || 1;
        const radius = m.orbitRadius * (1 + 0.15 * Math.sin(time * 0.045 + m.id * 1.3));
        const radial = clamp((radius - r) / radius, -1, 1);
        dx += ((-ry / r) * m.orbitDir + (rx / r) * radial * 0.80) * 0.54;
        dy += ((rx / r) * m.orbitDir + (ry / r) * radial * 0.80) * 0.54;

        if (pointer.active) {
          const pdx = hx - pointer.x;
          const pdy = hy - pointer.y;
          const pd = Math.hypot(pdx, pdy);
          if (pd < L * 0.55 + 50 && pd > 1e-3) {
            const pw = (1 - pd / (L * 0.55 + 50)) * 2.0;
            const side = pdx * nx0 + pdy * ny0 >= 0 ? 1 : -1;
            dx += (nx0 * side * 0.8 + (pdx / pd) * 0.4) * pw;
            dy += (ny0 * side * 0.8 + (pdy / pd) * 0.4) * pw;
          }
        }

        // Predictive CPA Path-Crossing Avoidance & Compact Elliptical Disc Box:
        // Anticipates path crossings early and steers tangentially (laterally) with gentle speed
        // staggering so wide-winged mantas glide past each other without interrupting paths!
        let speedMod = 1.0;
        let latSlide = 0;
        const myDiscX = nodes[6];
        const myDiscY = nodes[7];

        for (const other of mantas) {
          if (other === m) continue;
          const otherShape = MANTA_SHAPES[other.kind] || MANTA_SHAPES.giant_manta;
          const oDiscX = other.nodes[6];
          const oDiscY = other.nodes[7];

          const toX = oDiscX - myDiscX;
          const toY = oDiscY - myDiscY;
          const curDist = Math.hypot(toX, toY) || 1;

          const ovx = Math.cos(other.heading) * other.speed;
          const ovy = Math.sin(other.heading) * other.speed;
          const rvx = ovx - fx0 * m.speed;
          const rvy = ovy - fy0 * m.speed;
          const rv2 = rvx * rvx + rvy * rvy;
          const tCPA = rv2 > 1e-2 ? clamp(-(toX * rvx + toY * rvy) / rv2, 0, 4.5) : 0;
          const cpaX = toX + rvx * tCPA;
          const cpaY = toY + rvy * tCPA;
          const cpaDist = Math.hypot(cpaX, cpaY);
          const effDist = Math.min(curDist, cpaDist * 0.88 + curDist * 0.12);

          // Radar radius scaled to the combined wingspans so they curve smoothly before wings overlap
          const radarRange = (L * shape.wingSpan + other.length * otherShape.wingSpan) * 1.35;
          if (effDist < radarRange) {
            const ahead = (toX / curDist) * fx0 + (toY / curDist) * fy0;
            if (ahead > -0.30) {
              const prox = Math.pow(1 - effDist / radarRange, 1.25);
              const latOffset = -(cpaX * nx0 + cpaY * ny0);
              const passSide = Math.abs(latOffset) > L * 0.12
                ? (latOffset > 0 ? 1 : -1)
                : (m.id < other.id ? 1 : -1);
              const w = prox * 2.1 * (0.55 + 0.45 * Math.max(0, ahead));
              dx += nx0 * passSide * w;
              dy += ny0 * passSide * w;

              if (ahead > 0.15) {
                speedMod *= m.id < other.id ? 1 + 0.15 * prox : 1 - 0.13 * prox;
              }
            }
          }

          // Compact core collision box (inner body only, not outer wingtips) for soft lateral slide
          const coreRange = (L + other.length) * 0.28;
          if (curDist < coreRange && curDist > 1e-3) {
            const push = (1 - curDist / coreRange) * 16;
            const latProj = (-toX / curDist) * nx0 + (-toY / curDist) * ny0;
            const slideSign = Math.abs(latProj) > 0.08 ? Math.sign(latProj) : (m.id < other.id ? 1 : -1);
            latSlide += slideSign * push;
          }
        }

        const edgePad = 95;
        const over = Math.max(-hx + edgePad, hx - (W - edgePad), -hy + edgePad, hy - (H - edgePad));
        if (over > 0) {
          const w = clamp(over / (edgePad * 0.85), 0, 1) * 2.6;
          const toX = cxW - hx;
          const toY = cyW - hy;
          const d = Math.hypot(toX, toY) || 1;
          dx += (toX / d) * w;
          dy += (toY / d) * w;
        }

        const desired = Math.atan2(dy, dx);
        const maxTurn = 0.58 * dt;
        const turned = clamp(angleDiff(m.heading, desired), -maxTurn, maxTurn);
        m.heading += turned;
        m.turn += (turned / dt - m.turn) * Math.min(1, dt * 2.8);

        const flapThrust = 1 + 0.14 * Math.sin(m.phase * 2);
        const cruise = (27 + L * 0.034) * flapThrust * clamp(speedMod, 0.84, 1.18);
        m.speed += (cruise - m.speed) * Math.min(1, dt * 1.8);
        m.phase += dt * (2.05 + m.speed / 36);

        const fx = Math.cos(m.heading);
        const fy = Math.sin(m.heading);
        nodes[0] += (fx * m.speed - fy * latSlide) * dt;
        nodes[1] += (fy * m.speed + fx * latSlide) * dt;

        const seg = L / (MANTA_NODES - 1);
        const discNodes = (MANTA_SHAPES[m.kind] || MANTA_SHAPES.giant_manta).discNodes || 10;
        let prevAngle = m.heading + Math.PI;
        for (let k = 1; k < MANTA_NODES; k++) {
          const px = nodes[(k - 1) * 2];
          const py = nodes[(k - 1) * 2 + 1];
          const maxBend = k < discNodes ? 0.09 : 0.24;
          let angle = Math.atan2(nodes[k * 2 + 1] - py, nodes[k * 2] - px);
          angle = prevAngle + clamp(angleDiff(prevAngle, angle), -maxBend, maxBend);
          nodes[k * 2] = px + Math.cos(angle) * seg;
          nodes[k * 2 + 1] = py + Math.sin(angle) * seg;
          prevAngle = angle;
        }
      }
    }

    stepFish(dt) {
      const { fish, mantas, pointer, width: W, height: H, time, tmp: cur } = this;
      const calm = Math.exp(-dt * 0.8);
      for (const f of fish) {
        f.alarm *= calm;
        flowCurrent(f.x, f.y, time, cur);
        let ax = cur.x * 0.55 + (Math.random() - 0.5) * 35;
        let ay = cur.y * 0.55 + (Math.random() - 0.5) * 35 - f.vy * 0.5;

        if (f.escortId >= 0 && f.escortId < mantas.length && f.alarm < 0.3) {
          const m = mantas[f.escortId];
          const fx = Math.cos(m.heading);
          const fy = Math.sin(m.heading);
          const nx = -fy;
          const ny = fx;
          const tx = m.nodes[4] - fx * m.length * 0.12 + nx * f.escortSide * m.length * f.escortDist * 0.45;
          const ty = m.nodes[5] - fy * m.length * 0.12 + ny * f.escortSide * m.length * f.escortDist * 0.45;
          ax += (tx - f.x) * 1.8 + (fx * m.speed - f.vx) * 2.2;
          ay += (ty - f.y) * 1.8 + (fy * m.speed - f.vy) * 2.2;
        }

        if (pointer.active) {
          const dx = f.x - pointer.x;
          const dy = f.y - pointer.y;
          const d = Math.hypot(dx, dy);
          if (d < 140 && d > 1e-3) {
            const w = (1 - d / 140) ** 2;
            ax += (dx / d) * 900 * w;
            ay += (dy / d) * 900 * w;
            f.alarm = Math.max(f.alarm, w);
          }
        }

        const mPad = 36;
        if (f.x < mPad) ax += (mPad - f.x) * 6;
        else if (f.x > W - mPad) ax -= (f.x - (W - mPad)) * 6;
        if (f.y < mPad) ay += (mPad - f.y) * 6;
        else if (f.y > H - mPad) ay -= (f.y - (H - mPad)) * 6;

        const before = Math.atan2(f.vy, f.vx);
        f.vx += ax * dt;
        f.vy += ay * dt;
        const spd = Math.hypot(f.vx, f.vy) || 1;
        const maxSpd = 58 * (1 + f.alarm * 1.4);
        if (spd > maxSpd) {
          f.vx *= maxSpd / spd;
          f.vy *= maxSpd / spd;
        } else if (spd < 18) {
          f.vx *= 18 / spd;
          f.vy *= 18 / spd;
        }
        f.turn = angleDiff(before, Math.atan2(f.vy, f.vx)) / dt;
        f.x = clamp(f.x + f.vx * dt, -40, W + 40);
        f.y = clamp(f.y + f.vy * dt, -40, H + 40);
      }
    }
  }

  class MantaRenderer extends BaseAsciiRenderer {
    constructor(canvas) {
      super(canvas, MANTA_KINDS, MANTA_TINTS);
      this.ambientGlyph = "-";
      this.spine = new Float32Array(MANTA_NODES * 2);
      this.arc = new Float32Array(MANTA_NODES);
      this.arcTotal = 1;
      this.discArcTotal = 1;
      this.curManta = null;
      this.curShape = MANTA_SHAPES.giant_manta;
      this.wingSpanLeft = 0;
      this.wingSpanRight = 0;
    }

    render(world, dt) {
      const { ctx, dpr, cols, ch } = this;
      if (cols === 0) return;
      const t = world.time;

      this.consumeEvents(world);
      this.rasterizeMantas(world.mantas, t);
      this.depositWake(world);
      this.diffuse(dt);

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(this.bg, 0, 0);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      this.markAmbient(world.fish);
      this.drawDots();

      ctx.font = `600 ${Math.round(ch * 0.74)}px ${this.fontFamily}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      this.drawHeat();
      this.drawAmbient();
      this.drawCells(t);
    }

    depositWake(world) {
      const { energy } = this;
      for (const f of world.fish) {
        const i = this.cellIndex(f.x, f.y);
        if (i >= 0) energy[i] = Math.min(1.6, energy[i] + 0.01 + f.alarm * 0.025);
      }
      for (const m of world.mantas) {
        for (let k = MANTA_NODES - 7; k < MANTA_NODES; k++) {
          const i = this.cellIndex(m.nodes[k * 2], m.nodes[k * 2 + 1]);
          if (i >= 0) energy[i] = Math.min(1.6, energy[i] + 0.045);
        }
      }
      if (world.pointer.active) {
        this.stamp(energy, world.pointer.x, world.pointer.y, 1, 0.08);
      }
    }

    sampleManta(px, py) {
      const { spine, arc, curManta: m, curShape: shape } = this;
      const L = this.arcTotal;
      const discNodes = shape.discNodes || 10;

      // Smooth Disc Coordinate Frame from head (node 0) to pelvic tail base (node discNodes - 1)
      const hx = spine[0];
      const hy = spine[1];
      const bx = spine[(discNodes - 1) * 2];
      const by = spine[(discNodes - 1) * 2 + 1];
      const dx = bx - hx;
      const dy = by - hy;
      const discLen = Math.hypot(dx, dy) || 1;
      const ux = dx / discLen;
      const uy = dy / discLen;
      const nx = -uy;
      const ny = ux;

      const midIdx = Math.floor(discNodes / 2);
      const midV = (spine[midIdx * 2] - hx) * nx + (spine[midIdx * 2 + 1] - hy) * ny;

      const relX = px - hx;
      const relY = py - hy;
      const u = relX * ux + relY * uy;
      const sd = u / discLen; // 0 at head/mouth rim, < 0 in front of head, 1 at pelvic base of tail
      const spineCurve = 4 * clamp(sd, 0, 1) * (1 - clamp(sd, 0, 1)) * midV;
      const v = relX * nx + relY * ny - spineCurve;
      const a = Math.abs(v);
      const discSign = v >= 0 ? 1 : -1;

      this.hitDist = Math.hypot(u - clamp(u, -0.28 * discLen, discLen), a);
      this.hitS = clamp((sd + 0.25) * 0.40, 0, 1);
      this.hitV = v;

      // 1. MANTA RAY ICONIC CEPHALIC HORNS & WIDE CAVERNOUS MOUTH
      // Two long, pronounced paddle/horn lobes projecting far forward on either side of the wide open mouth!
      if (shape.cephalic && sd >= -0.28 && sd < 0.28) {
        const hornForward = shape.hornLen || 0.23; // Projects far in front of sd = 0!
        // As sd goes from +0.22 (shoulder base) to -hornForward (horn tip), the horns curve slightly inward like (  )
        const sHorn = clamp((0.22 - sd) / (0.22 + hornForward), 0, 1); // 0 at base, 1 at forward tip
        const hornCenter = L * (0.136 - 0.026 * Math.sin(sHorn * Math.PI * 0.88));
        const hornHalfW = L * 0.056 * (1 - 0.26 * Math.pow(sHorn, 1.4));
        const distFromHornAxis = Math.abs(a - hornCenter);

        if (sd >= -hornForward && sd <= 0.22 && distFromHornAxis <= hornHalfW) {
          const acrossHorn = distFromHornAxis / (hornHalfW || 1);
          // Rounded paddle tip at the front of the horn
          const tipEnd = -hornForward + 0.038 * acrossHorn * acrossHorn;
          if (sd >= tipEnd) {
            if (sd > 0.04 && sd < 0.14 && a > hornCenter + hornHalfW * 0.32) {
              // Lateral eyes on the outer base of the cephalic horns
              this.hitFlag = FLAG_EYE;
              this.hitShade = 0;
            } else {
              // Solid body-colored cephalic horns (no white in the mouth zone!)
              this.hitFlag = FLAG_BODY;
              this.hitShade = 0.74 - 0.18 * acrossHorn;
            }
            return true;
          }
        }
      }

      // 2. SPOTTED EAGLE RAY PROMINENT DUCK-BILL SNOUT
      if (shape.duckbill && sd >= -0.16 && sd < 0.22) {
        const sSnout = clamp((sd + 0.16) / 0.38, 0, 1); // 0 at snout tip, 1 at neck
        // Rounded duck-bill lobe that widens, then indents slightly at the neck before the wings
        const snoutW = L * 0.088 * Math.sin(Math.pow(sSnout, 0.65) * Math.PI * 0.88);
        if (a <= snoutW) {
          if (sd > 0.05 && sd < 0.13 && a > snoutW * 0.68) {
            this.hitFlag = FLAG_EYE;
            this.hitShade = 0;
          } else {
            this.hitFlag = a > snoutW * 0.78 ? FLAG_FIN : FLAG_BODY;
            this.hitShade = 0.66 - 0.2 * (a / (snoutW || 1));
          }
          return true;
        }
      }

      // 3. ROUNDED SAUCER DISC (Leopard Ray / Round Fantail Stingray)
      const baseSpan = discSign > 0 ? this.wingSpanRight : this.wingSpanLeft;
      if (shape.roundedDisc) {
        const rRaw = a / (baseSpan || 1);
        if (rRaw <= 1.05 && sd >= -0.04 && sd <= 1.04) {
          // Travelling ruffled wave around the circular stingray margin
          const ruffle = 0.035 * Math.sin(m.phase * 1.4 - sd * 4.8) * smoothstep(0.3, 0.9, rRaw);
          const curSpan = baseSpan * (1 + ruffle);
          const r = a / (curSpan || 1);
          if (r <= 1.0) {
            // Smooth oval/circular saucer boundary with slight rostral point at front
            const halfChord = 0.50 * Math.sqrt(Math.max(0, 1 - Math.pow(r, 1.85)));
            const rostralTip = r < 0.18 ? 0.045 * (1 - r / 0.18) : 0;
            const sdFront = 0.50 - halfChord - rostralTip;
            const sdBack = 0.50 + halfChord * 0.98;

            if (sd >= sdFront && sd <= sdBack) {
              const radialDist = Math.hypot((sd - 0.50) / 0.50, r);
              const flapSlope = Math.cos(m.phase * 1.4 - sd * 4.2 - r * 1.5);
              let shade = 0.62 - radialDist * 0.18 + flapSlope * 0.16 * r;
              let flag = FLAG_BODY;

              // Eyes & spiracles set back on top of the rounded disc
              const dEye = Math.hypot((sd - 0.24) * 4.2, (a / (L * 0.42) - 0.16) * 4.5);
              if (dEye < 0.20) {
                flag = FLAG_EYE;
                shade = 0;
              } else if (r < 0.045 && sd > 0.28 && sd < 0.92) {
                flag = FLAG_RIDGE;
                shade = 0.95;
              } else if (radialDist > 0.86) {
                flag = FLAG_FIN;
                shade = 0.38;
              } else {
                // Leopard rosette rings: dark core surrounded by a ring of bright white ASCII letter infills!
                const cellU = sd * 8.5;
                const cellV = v / (L * 0.048);
                const gu = Math.round(cellU);
                const gv = Math.round(cellV);
                const jx = gu + (hash3(gu, gv, m.id) - 0.5) * 0.36;
                const jy = gv + (hash3(gu, gv, m.id + 7) - 0.5) * 0.36;
                const dRosette = Math.hypot(cellU - jx, cellV - jy);
                if (dRosette <= 0.18) {
                  flag = FLAG_RIDGE;
                  shade = 0.95;
                } else if (dRosette < 0.49 && hash3(gu, gv, m.id + 19) > 0.12) {
                  flag = FLAG_WHITE_SPOT;
                  shade = 0.92;
                }
              }

              this.hitFlag = flag;
              this.hitShade = clamp(shade, 0.1, 0.98);
              return true;
            }
          }
        }
      } else {
        // 4. SWEPT FALCATE / CURVED PECTORAL WINGS (Giant Manta, Reef Manta, Spotted Eagle Ray)
        const rRaw = a / (baseSpan || 1);
        if (rRaw <= 1.06 && sd >= 0.04 && sd <= 1.04) {
          const flapPhase = m.phase - sd * 2.2 - rRaw * 1.6;
          const flap = Math.sin(flapPhase);
          const flapSlope = Math.cos(flapPhase);
          const spanScale = 1 - 0.10 * flap * flap * smoothstep(0.15, 0.9, rRaw);
          const curSpan = baseSpan * spanScale;
          const r = a / (curSpan || 1);

          if (r <= 1.0) {
            const tipShift = flap * 0.05 * r * r;
            // For cephalic mantas, the center mouth is deeply recessed between the two cephalic horns!
            const mouthRecess = shape.cephalic && a < L * 0.096
              ? 0.135 * Math.cos(((a / (L * 0.096)) * Math.PI) / 2)
              : 0;
            const startFront = (shape.cephalic ? 0.075 : 0.11) + mouthRecess;
            const tipS = (shape.curvedWings ? 0.64 : 0.70) + tipShift;
            const leadPow = shape.curvedWings ? 1.65 : 1.32;
            const sdFront = startFront + (tipS - startFront) * Math.pow(r, leadPow);
            const falcateArch = Math.sin(r * Math.PI) * (shape.curvedWings ? 0.10 : 0.15);
            const sdBack = 0.98 - (0.98 - (tipS + (shape.curvedWings ? 0.08 : 0.045))) * Math.pow(r, 0.92) - falcateArch;

            if (sd >= sdFront && sd <= sdBack) {
              const chord = Math.max(0.04, sdBack - sdFront);
              const sc = (sd - sdFront) / chord;
              const facing = (nx * -0.6 + ny * -0.8) * discSign * r;

              let shade = 0.62 - r * 0.10 + flapSlope * 0.18 * smoothstep(0.12, 0.85, r) + facing * 0.16;
              let flag = FLAG_BODY;

              if (r < 0.042 && sd > 0.16 && sd < 0.92) {
                flag = FLAG_RIDGE;
                shade = 0.96;
              } else if (
                shape.pattern === "manta_patches" &&
                sd > 0.24 &&
                sd < 0.48 &&
                r > 0.08 &&
                r < 0.36 &&
                sc > 0.20 &&
                sc < 0.70
              ) {
                // Giant Manta subtle lighter slate-gray shoulder shading (no stark white mouth/head zone!)
                flag = FLAG_BODY;
                shade = 0.32 + 0.14 * (r / 0.36);
              } else if (
                shape.pattern === "reef_chevron" &&
                ((sd > 0.24 && sd < 0.50 && r > 0.06 && r < 0.36 && Math.abs(sd - (0.25 + r * 0.58)) < 0.085) ||
                  (r > 0.62 && r < 0.78 && sc > 0.22 && sc < 0.68))
              ) {
                // Reef Manta lighter cerulean dorsal V-chevron shading
                flag = FLAG_BODY;
                shade = 0.28;
              } else if (
                shape.pattern === "white_dots" &&
                r < 0.88 &&
                sc > 0.09 &&
                sc < 0.91 &&
                sd > 0.11
              ) {
                // Spotted Eagle Ray: full deep-blue skin spotted with bright white ASCII dots!
                const cellU = sd * 10.5;
                const cellV = v / (L * 0.040);
                const gu = Math.round(cellU);
                const gv = Math.round(cellV);
                const jx = gu + (hash3(gu, gv, m.id) - 0.5) * 0.32;
                const jy = gv + (hash3(gu, gv, m.id + 5) - 0.5) * 0.32;
                const dSpot = Math.hypot(cellU - jx, cellV - jy);
                if (dSpot < 0.47 && hash3(gu, gv, m.id + 13) > 0.08) {
                  flag = FLAG_WHITE_SPOT;
                  shade = 0.92;
                }
              } else if (r > 0.84 || sc > 0.86) {
                flag = FLAG_FIN;
                shade = clamp(0.38 + flapSlope * 0.14, 0.15, 0.75);
              } else if (sc < 0.10) {
                // Crisp mouth & wing leading edge
                shade = Math.max(shade, 0.76);
              }

              this.hitFlag = flag;
              this.hitShade = clamp(shade, 0.1, 0.98);
              return true;
            }
          }
        }
      }

      // 5. Whip Tail (nodes discNodes - 2 .. MANTA_NODES - 1)
      let bestTail = Infinity;
      let tailS = 0;
      let tailSign = 1;
      const tailLen = Math.max(1, L - arc[discNodes - 2]);
      for (let k = discNodes - 2; k < MANTA_NODES - 1; k++) {
        const ax = spine[k * 2];
        const ay = spine[k * 2 + 1];
        const bx = spine[(k + 1) * 2];
        const by = spine[(k + 1) * 2 + 1];
        const abx = bx - ax;
        const aby = by - ay;
        const ab2 = abx * abx + aby * aby || 1e-6;
        const apx = px - ax;
        const apy = py - ay;
        const t = clamp((apx * abx + apy * aby) / ab2, 0, 1);
        const qx = ax + abx * t;
        const qy = ay + aby * t;
        const d2 = (px - qx) ** 2 + (py - qy) ** 2;
        if (d2 < bestTail) {
          bestTail = d2;
          tailS = clamp((arc[k] - arc[discNodes - 2] + Math.sqrt(ab2) * t) / tailLen, 0, 1);
          tailSign = abx * apy - aby * apx >= 0 ? 1 : -1;
        }
      }

      const dTail = Math.sqrt(bestTail);
      if (dTail < this.hitDist) this.hitDist = dTail;
      const tailW = L * 0.020 * Math.pow(1 - tailS, 1.15) + 1.5;
      if (dTail <= tailW) {
        this.hitDist = 0;
        this.hitS = 0.45 + tailS * 0.55;
        this.hitV = dTail * tailSign;
        this.hitFlag = tailS < 0.32 && dTail < tailW * 0.5 ? FLAG_RIDGE : FLAG_FIN;
        this.hitShade = 0.72 * (1 - tailS * 0.55);
        return true;
      }

      return false;
    }

    rasterizeMantas(mantas, t) {
      const { cellFlag, cellShade, cellKey, cellDepth, cellKind, spine, arc, cw, ch, cols, rows } = this;
      cellFlag.fill(0);

      for (const m of mantas) {
        this.curManta = m;
        this.curShape = MANTA_SHAPES[m.kind] || MANTA_SHAPES.giant_manta;
        const kindIndex = Math.max(0, MANTA_KINDS.indexOf(m.kind));
        const L = m.length;
        const N = MANTA_NODES;
        const n = m.nodes;

        for (let k = 0; k < N; k++) {
          const s = k / (N - 1);
          const a = Math.max(0, k - 1);
          const b = Math.min(N - 1, k + 1);
          let tx = n[a * 2] - n[b * 2];
          let ty = n[a * 2 + 1] - n[b * 2 + 1];
          const tl = Math.hypot(tx, ty) || 1;
          tx /= tl;
          ty /= tl;
          const amp = L * 0.028 * Math.pow(s, 2.2);
          const off = amp * Math.sin(m.phase - s * 4.5);
          spine[k * 2] = n[k * 2] - ty * off;
          spine[k * 2 + 1] = n[k * 2 + 1] + tx * off;
        }

        arc[0] = 0;
        for (let k = 1; k < N; k++) {
          arc[k] = arc[k - 1] + Math.hypot(spine[k * 2] - spine[(k - 1) * 2], spine[k * 2 + 1] - spine[(k - 1) * 2 + 1]);
        }
        this.arcTotal = arc[N - 1] || 1;
        const discNodes = this.curShape.discNodes || 10;
        this.discArcTotal = arc[discNodes - 1] || 1;

        const bank = clamp(m.turn * 0.45, -0.32, 0.32);
        const span = L * this.curShape.wingSpan;
        this.wingSpanRight = span * (1 - bank * 0.65);
        this.wingSpanLeft = span * (1 + bank * 0.65);

        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (let k = 0; k < N; k++) {
          minX = Math.min(minX, spine[k * 2]);
          maxX = Math.max(maxX, spine[k * 2]);
          minY = Math.min(minY, spine[k * 2 + 1]);
          maxY = Math.max(maxY, spine[k * 2 + 1]);
        }
        const reach = Math.max(this.wingSpanLeft, this.wingSpanRight) + L * 0.14 + 18;
        const c0 = Math.max(0, Math.floor((minX - reach) / cw));
        const c1 = Math.min(cols - 1, Math.floor((maxX + reach) / cw));
        const r0 = Math.max(0, Math.floor((minY - reach) / ch));
        const r1 = Math.min(rows - 1, Math.floor((maxY + reach) / ch));
        if (c0 > c1 || r0 > r1) continue;

        const skipBeyond = reach + Math.hypot(cw, ch);

        for (let r = r0; r <= r1; r++) {
          for (let c = c0; c <= c1; c++) {
            const x = c * cw;
            const y = r * ch;
            const centerHit = this.sampleManta(x + cw / 2, y + ch / 2);
            if (!centerHit && this.hitDist > skipBeyond) continue;
            const flag = this.hitFlag;
            const shade = this.hitShade;
            const s = this.hitS;
            const v = this.hitV;

            let hits = centerHit ? 1 : 0;
            for (let k = 0; k < SUBSAMPLES.length; k += 2) {
              if (this.sampleManta(x + SUBSAMPLES[k] * cw, y + SUBSAMPLES[k + 1] * ch)) hits++;
            }
            if (hits === 0) continue;
            const coverage = hits / 5;

            const i = r * cols + c;
            const key = (hash3(Math.round(s * 52), Math.round(v / (cw * 0.9)), m.id) * 4294967295) >>> 0;
            cellKey[i] = key;
            cellDepth[i] = m.depth;
            cellKind[i] = kindIndex;

            if (centerHit && coverage >= 0.6) {
              cellFlag[i] = flag;
              const flicker = (hash3(c, r, Math.floor(t * 6)) - 0.5) * 0.05;
              cellShade[i] = clamp(shade + flicker, 0, 1);
            } else {
              cellFlag[i] = FLAG_EDGE;
              cellShade[i] = coverage;
            }
          }
        }
      }
    }

    drawCells(t) {
      const { ctx, cols, rows, cw, ch, cellFlag, cellShade, cellKey, cellDepth, cellKind, kinds } = this;
      const SPOT_GLYPHS = "@Oo*8#0";
      const WHITE_PATCH_GLYPHS = ":;t%S";
      const n = cols * rows;
      for (let i = 0; i < n; i++) {
        const flag = cellFlag[i];
        if (!flag) continue;
        const col = i % cols;
        const row = (i / cols) | 0;
        const x = col * cw;
        const y = row * ch;
        const key = cellKey[i];
        const shade = cellShade[i];
        const dim = 0.84 + 0.16 * cellDepth[i];
        const kindName = kinds[cellKind[i]] || "giant_manta";
        const shape = MANTA_SHAPES[kindName] || MANTA_SHAPES.giant_manta;
        const isBrownLeopard = shape.palette === "brown_black";

        const tick = Math.floor(t * 2.4 + (key % 997) / 97);
        const roll = hash3(key, tick, 7);

        if (flag === FLAG_EDGE) {
          const set = shade >= 0.5 ? EDGE_HEAVY : EDGE_LIGHT;
          const glyph = set[(key >>> 8) % set.length];
          if (roll < 0.05) {
            ctx.fillStyle = ACCENTS[key % ACCENTS.length];
          } else if (isBrownLeopard) {
            ctx.fillStyle = "rgba(92, 64, 36, 0.78)";
          } else if (shape.palette === "slate_gray") {
            ctx.fillStyle = "rgba(71, 85, 105, 0.78)";
          } else {
            ctx.fillStyle = "rgba(30, 58, 102, 0.78)";
          }
          ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
          continue;
        }

        if (flag === FLAG_WHITE_PATCH) {
          // Bright crisp white dorsal shoulder patches (Giant Manta) & dorsal V-chevron (Reef Manta)
          const wLevel = Math.round((246 - shade * 28) * (0.93 + 0.07 * cellDepth[i]));
          ctx.fillStyle = `rgb(${wLevel - 3}, ${wLevel}, ${Math.min(255, wLevel + 4)})`;
          ctx.fillRect(x + 1, y + 1, cw - 1, ch - 1);
          const glyph = WHITE_PATCH_GLYPHS[(key >>> 6) % WHITE_PATCH_GLYPHS.length];
          ctx.fillStyle = shape.palette === "slate_gray" ? "#334155" : "#1e3a5f";
          ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
          continue;
        }

        if (flag === FLAG_WHITE_SPOT) {
          const gx = x + cw / 2;
          const gy = y + ch / 2 + 1;
          const glyph = SPOT_GLYPHS[(key >>> 5) % SPOT_GLYPHS.length];

          if (isBrownLeopard) {
            // Leopard Ray: charcoal-black leopard rosette rings on warm sandy-brown skin!
            const blk = Math.round(28 * dim);
            ctx.fillStyle = `rgb(${blk + 6},${blk + 2},${blk})`;
            ctx.fillRect(x + 1, y + 1, cw - 1, ch - 1);
            ctx.fillStyle = "#e2b887";
            ctx.fillText(glyph, gx, gy);
            continue;
          }

          // Spotted Eagle Ray: full deep-blue dorsal skin cell with pure BRIGHT WHITE (#ffffff) ASCII letter infill!
          const [tr, tg, tb] = shape.tint;
          const base = 178 * dim;
          const r = Math.min(255, Math.round(base * tr));
          const g = Math.min(255, Math.round(base * tg));
          const b = Math.min(255, Math.round(base * tb));
          ctx.fillStyle = `rgb(${r},${g},${b})`;
          ctx.fillRect(x + 1, y + 1, cw - 1, ch - 1);

          ctx.fillStyle = "#ffffff";
          ctx.fillText(glyph, gx - 0.35, gy);
          ctx.fillText(glyph, gx + 0.35, gy);
          continue;
        }

        // Species-specific dorsal shading for FLAG_BODY, FLAG_RIDGE, FLAG_FIN, FLAG_EYE
        const [tr, tg, tb] = shape.tint;
        let lum;
        let glyph;
        if (flag === FLAG_RIDGE) {
          lum = isBrownLeopard ? 52 : 110;
          glyph = RIDGE_GLYPHS[(key >>> 8) % RIDGE_GLYPHS.length];
        } else if (flag === FLAG_EYE) {
          lum = 44;
          glyph = "o";
        } else if (flag === FLAG_FIN) {
          lum = 228 - shade * 62;
          glyph = FIN_GLYPHS[(key >>> 8) % FIN_GLYPHS.length];
        } else {
          lum = 226 - shade * 86;
          const jitter = ((key >>> 4) % 3) - 1;
          glyph = SKIN_RAMP[clamp(Math.floor(shade * 8.99) + jitter, 0, SKIN_RAMP.length - 1)];
        }

        lum *= dim;
        const r = Math.min(255, Math.round(lum * tr));
        const g = Math.min(255, Math.round(lum * tg));
        const b = Math.min(255, Math.round(lum * tb));
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.fillRect(x + 1, y + 1, cw - 1, ch - 1);

        let glyphColor;
        if (flag === FLAG_EYE) {
          glyphColor = "#ffffff";
        } else if (roll < 0.025) {
          glyphColor = ACCENTS[key % ACCENTS.length];
        } else if (isBrownLeopard) {
          glyphColor = flag === FLAG_RIDGE
            ? "#d6a874"
            : `rgb(${Math.max(0, r - 48)},${Math.max(0, g - 38)},${Math.max(0, b - 24)})`;
        } else if (shape.palette === "slate_gray") {
          glyphColor = `rgb(${Math.min(255, r + 38)},${Math.min(255, g + 40)},${Math.min(255, b + 44)})`;
        } else if (flag === FLAG_RIDGE) {
          glyphColor = `rgb(${Math.min(255, r + 28)},${Math.min(255, g + 38)},${Math.min(255, b + 54)})`;
        } else {
          glyphColor = `rgb(${Math.min(255, r + 34)},${Math.min(255, g + 46)},${Math.min(255, b + 64)})`;
        }
        ctx.fillStyle = glyphColor;
        ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
      }
    }
  }

  class MantaEngine extends BaseLoopEngine {
    constructor(canvas, specs) {
      const world = new MantaWorld(specs);
      const renderer = new MantaRenderer(canvas);
      super(canvas, world, renderer);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 5. SEA TURTLES ENGINE ("turtles")
  //    Loggerhead, Green Sea Turtle, Olive Ridley, and Hawksbill Sea Turtle.
  //    Graceful gliding motion with rowing pectoral flippers, rear flippers,
  //    oval carapace with scute patterns, and distinct species palettes.
  // ═══════════════════════════════════════════════════════════════════════════

  const TURTLE_NODES = 16;
  const TURTLE_SHAPES = {
    loggerhead: {
      carapaceRatio: 0.62,
      shellWidth: 0.31, // Broad, sturdy heart carapace
      headScale: 0.12,
      beakSharp: false,
      flipperSpan: 0.49, // Balanced hydrofoil pectoral flippers
      palette: "reddish_brown",
      shellTint: [0.42, 0.18, 0.08], // Deep dark burnt terracotta shell
      skinTint: [0.90, 0.70, 0.40],  // Light warm golden-tan flippers & head
      tint: [0.42, 0.18, 0.08],
      scuteType: "loggerhead",
    },
    greenturtle: {
      carapaceRatio: 0.65,
      shellWidth: 0.29, // Smooth rounded teardrop oval
      headScale: 0.11,
      beakSharp: false,
      flipperSpan: 0.52, // Graceful oceanic flipper wings
      palette: "olive_green",
      shellTint: [0.15, 0.30, 0.12], // Deep dark forest / pine-olive shell
      skinTint: [0.55, 0.78, 0.45],  // Luminous light sage-jade flippers & head
      tint: [0.15, 0.30, 0.12],
      scuteType: "green",
    },
    olive_ridley: {
      carapaceRatio: 0.58,
      shellWidth: 0.33, // Broadest, nearly circular shell
      headScale: 0.11,
      beakSharp: false,
      flipperSpan: 0.46,
      palette: "slate_olive",
      shellTint: [0.22, 0.28, 0.22], // Deep dark charcoal-olive shell
      skinTint: [0.65, 0.74, 0.62],  // Pale light olive-slate flippers & head
      tint: [0.22, 0.28, 0.22],
      scuteType: "ridley",
    },
    hawksbill: {
      carapaceRatio: 0.64,
      shellWidth: 0.28, // Distinctive amber tortoiseshell with jagged posterior scutes
      headScale: 0.11,
      beakSharp: true,
      serratedMargin: true,
      flipperSpan: 0.49,
      palette: "tortoiseshell",
      shellTint: [0.34, 0.18, 0.06], // Deep dark mahogany tortoiseshell with amber scutes
      skinTint: [0.88, 0.70, 0.34],  // Bright golden-amber flippers & head
      tint: [0.34, 0.18, 0.06],
      scuteType: "hawksbill",
    },
  };
  const TURTLE_KINDS = Object.keys(TURTLE_SHAPES);
  const TURTLE_TINTS = {};
  for (const k of TURTLE_KINDS) TURTLE_TINTS[k] = TURTLE_SHAPES[k].tint;

  const DEFAULT_TURTLES = [
    { kind: "loggerhead", size: 0.94 },
    { kind: "greenturtle", size: 0.90 },
    { kind: "hawksbill", size: 0.84 },
    { kind: "olive_ridley", size: 0.78 },
  ];

  class TurtleWorld {
    constructor(specs = DEFAULT_TURTLES) {
      this.specs = specs;
      this.width = 0;
      this.height = 0;
      this.time = 0;
      this.turtles = [];
      this.fish = [];
      this.events = [];
      this.pointer = { x: 0, y: 0, active: false };
      this.tmp = { x: 0, y: 0 };
    }

    resize(width, height) {
      const first = this.width === 0;
      this.width = width;
      this.height = height;
      if (first || this.turtles.length === 0) {
        this.seed();
        return;
      }
      for (const f of this.fish) {
        f.x = clamp(f.x, 0, width);
        f.y = clamp(f.y, 0, height);
      }
    }

    seed() {
      const { width: W, height: H } = this;
      const minSide = Math.min(W, H) || 600;
      const baseLen = clamp(minSide * 0.28, 140, 220);
      const count = this.specs.length;

      // Clear, purposeful straight-line oceanic transect headings (NO CIRCLES!)
      const baseHeadings = [
        0.18,              // Swimming East-Northeast (~10 deg)
        Math.PI - 0.22,    // Swimming West-Northwest (~167 deg)
        Math.PI * 0.52,    // Swimming South-Southeast (~94 deg)
        -Math.PI * 0.48,   // Swimming North-Northwest (~-86 deg)
      ];

      this.turtles = [];
      for (let i = 0; i < count; i++) {
        const spec = this.specs[i];
        const L = baseLen * (spec.size || 1.0);

        // Distribute spawn positions cleanly across screen quadrants
        const qx = (i % 2 === 0 ? W * 0.26 : W * 0.74) + rand(-W * 0.08, W * 0.08);
        const qy = (i < 2 ? H * 0.28 : H * 0.72) + rand(-H * 0.08, H * 0.08);
        const heading = baseHeadings[i % baseHeadings.length] + rand(-0.12, 0.12);

        const nodes = new Float32Array(TURTLE_NODES * 2);
        const seg = L / (TURTLE_NODES - 1);
        for (let k = 0; k < TURTLE_NODES; k++) {
          nodes[k * 2] = qx - Math.cos(heading) * seg * k;
          nodes[k * 2 + 1] = qy - Math.sin(heading) * seg * k;
        }

        this.turtles.push({
          id: i,
          kind: spec.kind,
          length: L,
          nodes,
          heading,
          targetHeading: heading, // Locked onto straight cruising path
          turn: 0,
          isTurning: false,
          turnCooldown: 0,
          isWaiting: false,
          waitDuration: 0,
          yieldTargetId: -1,
          depth: rand(0.55, 0.95),
          phase: rand(0, TAU),
          strokeCycle: (i * (TAU / count)) + rand(0, 0.6), // Staggered swimming strokes!
          speed: 22,
          alarm: 0,
          fleeX: 0,
          fleeY: 0,
        });
      }

      // Small companion reef fish
      this.fish = [];
      const fishCount = clamp(Math.round((W * H) / 36000), 22, 55);
      for (let i = 0; i < fishCount; i++) {
        this.fish.push({
          x: rand(20, W - 20),
          y: rand(20, H - 20),
          vx: rand(-22, 22),
          vy: rand(-22, 22),
          size: rand(0.75, 1.3),
          depth: rand(0.35, 0.85),
          alarm: 0,
          turn: 0,
          escortId: i % this.turtles.length,
          escortSide: Math.random() < 0.5 ? -1 : 1,
          escortDist: rand(0.35, 0.85),
        });
      }
    }

    splash(x, y) {
      this.events.push({ kind: "pulse", x, y });
      for (const t of this.turtles) {
        const hx = t.nodes[0];
        const hy = t.nodes[1];
        const d = Math.hypot(hx - x, hy - y);
        if (d < t.length * 1.6 && d > 1e-3) {
          t.alarm = Math.max(t.alarm, clamp(1.4 - d / (t.length * 1.6), 0, 1.2));
          t.fleeX = x;
          t.fleeY = y;
        }
      }
    }

    step(dt) {
      this.time += dt;
      this.stepTurtles(dt);
      this.stepFish(dt);
    }

    stepTurtles(dt) {
      const { turtles, width: W, height: H, pointer } = this;
      const pad = 120; // Margin from screen boundaries for straight transect turns

      // ── 1. LONG-RANGE RECIPROCAL ENCOUNTER ADJUSTMENT ──
      // When two turtles are cruising directly towards each other on reciprocal courses,
      // gently bias both to starboard (their right) well in advance (300-480px apart),
      // so their tracks naturally separate and they glide past side-by-side with plenty of room!
      for (let i = 0; i < turtles.length; i++) {
        const t = turtles[i];
        if (t.isTurning || t.turnCooldown > 0) continue;
        const hx = t.nodes[0];
        const hy = t.nodes[1];
        const fx = Math.cos(t.heading);
        const fy = Math.sin(t.heading);

        for (let j = i + 1; j < turtles.length; j++) {
          const other = turtles[j];
          const ox = other.nodes[0];
          const oy = other.nodes[1];
          const dx = ox - hx;
          const dy = oy - hy;
          const dist = Math.hypot(dx, dy);

          if (dist > 220 && dist < 480) {
            const ofx = Math.cos(other.heading);
            const ofy = Math.sin(other.heading);
            const headingDot = fx * ofx + fy * ofy;
            // Swimming towards each other
            if (headingDot < -0.65) {
              const forwardDot = (dx * fx + dy * fy) / dist;
              if (forwardDot > 0.65) {
                // Both alter slightly to their right (starboard passing)
                t.targetHeading = t.heading + 0.20;
                t.isTurning = true;
                t.turnCooldown = 5.0;
                other.targetHeading = other.heading + 0.20;
                other.isTurning = true;
                other.turnCooldown = 5.0;
              }
            }
          }
        }
      }

      // ── 2. INDIVIDUAL TURTLE NAVIGATION & PROTOCOL ──
      for (let i = 0; i < turtles.length; i++) {
        const t = turtles[i];
        const nodes = t.nodes;
        const L = t.length;
        const hx = nodes[0];
        const hy = nodes[1];

        t.turnCooldown -= dt;

        // Boundary detection: When approaching an edge, initiate a wide, smooth turn towards ocean center
        const nearEdge = (hx < pad || hx > W - pad || hy < pad || hy > H - pad);
        if (nearEdge && t.turnCooldown <= 0 && !t.isTurning) {
          const targetX = W / 2 + rand(-W * 0.18, W * 0.18);
          const targetY = H / 2 + rand(-H * 0.18, H * 0.18);
          t.targetHeading = Math.atan2(targetY - hy, targetX - hx) + rand(-0.10, 0.10);
          t.isTurning = true;
          t.turnCooldown = 6.0; // Maintain the new straight transect for at least 6s
        }

        // Click splash fleeing response
        if (t.alarm > 0.02) {
          t.alarm *= Math.exp(-dt * 1.5);
          const fx = hx - t.fleeX;
          const fy = hy - t.fleeY;
          t.targetHeading = Math.atan2(fy, fx);
          t.isTurning = true;
          t.isWaiting = false;
        }

        // Pointer avoidance
        if (pointer.active) {
          const pdx = hx - pointer.x;
          const pdy = hy - pointer.y;
          const pd = Math.hypot(pdx, pdy);
          if (pd < L * 0.85 + 45 && pd > 1e-3) {
            t.targetHeading = Math.atan2(pdy, pdx);
            t.isTurning = true;
          }
        }

        // ── 3. WAIT-FOR-CLEARANCE COLLISION PROTOCOL ("Esperar hasta que tenga hueco") ──
        // Instead of swerving sideways (which causes drifting), if another turtle occupies
        // our forward corridor, STOP AND WAIT peacefully until the way is completely clear!
        let corridorBlocked = false;
        const fx = Math.cos(t.heading);
        const fy = Math.sin(t.heading);
        const nx = -fy;
        const ny = fx;

        // Forward corridor dimensions
        const corridorReach = L * 1.05 + 32;
        const corridorHalfWidth = L * 0.36 + 16;

        for (let j = 0; j < turtles.length; j++) {
          if (i === j) continue;
          const other = turtles[j];

          // Check sample points along other turtle: snout (0), mid-shell (6), rear-shell (12)
          for (const idx of [0, 6, 12]) {
            const px = other.nodes[idx * 2];
            const py = other.nodes[idx * 2 + 1];
            const dx = px - hx;
            const dy = py - hy;
            const fwd = dx * fx + dy * fy;
            const lat = Math.abs(dx * nx + dy * ny);

            if (fwd > 0 && fwd < corridorReach && lat < corridorHalfWidth) {
              const otherFx = Math.cos(other.heading);
              const otherFy = Math.sin(other.heading);
              const reciprocal = (fx * otherFx + fy * otherFy) < -0.3;

              if (reciprocal) {
                // Meeting head-on: higher ID yields and waits; lower ID has right-of-way
                if (t.id > other.id) {
                  corridorBlocked = true;
                  t.yieldTargetId = other.id;
                  break;
                }
              } else {
                // Crossing / following: if other already yielded to us, we proceed
                if (other.isWaiting && other.yieldTargetId === t.id) {
                  // Other turtle is waiting for us! We keep swimming
                } else if (t.id > other.id || fwd < corridorReach * 0.7) {
                  corridorBlocked = true;
                  t.yieldTargetId = other.id;
                  break;
                }
              }
            }
          }
          if (corridorBlocked) break;
        }

        t.isWaiting = corridorBlocked;

        if (t.isWaiting) {
          t.waitDuration += dt;
          // Failsafe: if waiting for over 5s, gently nudge course to find an open path
          if (t.waitDuration > 5.0) {
            t.waitDuration = 0;
            t.targetHeading = t.heading + (t.id % 2 === 0 ? 0.30 : -0.30);
            t.isTurning = true;
            t.turnCooldown = 5.0;
          }
        } else {
          t.waitDuration = 0;
          t.yieldTargetId = -1;
        }

        // ── 4. STRAIGHT-LINE HEADING TRACKING (NO DRIFTING!) ──
        // When waiting: DO NOT TURN! Hold the current heading stably.
        // When cruising: turns smoothly at a controlled, majestic rate (max ~18 deg/s)
        if (!t.isWaiting) {
          const diff = angleDiff(t.heading, t.targetHeading);
          if (Math.abs(diff) > 0.02) {
            const maxTurn = 0.32 * dt; // Majestic turn rate
            const step = clamp(diff, -maxTurn, maxTurn);
            t.heading += step;
            t.turn = step / dt;
          } else {
            t.heading = t.targetHeading;
            t.turn = 0;
            t.isTurning = false;
          }
        } else {
          t.turn = 0;
        }

        // ── 5. PHYSICAL ANIMAL LOCOMOTION & FLIPPER FLAPPING ──
        let thrustPower = 0;
        let isPowerStroke = false;

        if (!t.isWaiting) {
          // Normal swimming: rhythmic flipper flap (stretch wide on recovery, contract tight on power stroke)
          t.strokeCycle += dt * (2.1 + (t.alarm > 0.1 ? 1.4 : 0));
          const strokeSin = Math.sin(t.strokeCycle);
          isPowerStroke = strokeSin > 0;
          thrustPower = isPowerStroke ? Math.pow(strokeSin, 1.6) : 0;

          const baseGlideSpeed = 16 + L * 0.025;
          const peakThrustSpeed = baseGlideSpeed + 26 + (t.alarm > 0.1 ? 16 : 0);
          const targetSpeed = baseGlideSpeed + thrustPower * (peakThrustSpeed - baseGlideSpeed);
          const accelRate = isPowerStroke ? 3.8 : 1.3;
          t.speed += (targetSpeed - t.speed) * Math.min(1, dt * accelRate);
        } else {
          // Waiting for corridor to clear ("esperarse hasta que tenga hueco"):
          // Smoothly glide to a stop and maintain buoyant resting posture
          t.strokeCycle += dt * 0.28; // Calm gentle buoyant idle
          t.speed += (0 - t.speed) * Math.min(1, dt * 2.6);
          if (t.speed < 0.2) t.speed = 0;
        }

        // ── 6. STRICTLY FORWARD TANGENTIAL VELOCITY ──
        // Nodes only translate along the forward heading direction!
        const moveFx = Math.cos(t.heading);
        const moveFy = Math.sin(t.heading);
        nodes[0] += moveFx * t.speed * dt;
        nodes[1] += moveFy * t.speed * dt;

        // ── 7. KINEMATIC FOLLOW-THE-LEADER SPINE (ZERO LATERAL DRIFT!) ──
        // Every segment follows the path that the segment in front of it carved in the water.
        // Because each segment displacement is purely tangential to the water track,
        // lateral velocity is strictly 0: no sideways skidding or drifting!
        const seg = L / (TURTLE_NODES - 1);
        let prevAngle = t.heading + Math.PI;

        for (let k = 1; k < TURTLE_NODES; k++) {
          const px = nodes[(k - 1) * 2];
          const py = nodes[(k - 1) * 2 + 1];
          let angle = Math.atan2(nodes[k * 2 + 1] - py, nodes[k * 2] - px);

          // Head/neck (k=1): slight natural articulation
          // Carapace (k=2..12): stiff constraint (0.038 rad) keeps shell firm and straight,
          // while tracing the curve of the water without lateral drift!
          // Tail (k=13..15): trailing tail
          const maxBend = k <= 1 ? 0.15 : (k <= 12 ? 0.038 : 0.14);
          angle = prevAngle + clamp(angleDiff(prevAngle, angle), -maxBend, maxBend);

          nodes[k * 2] = px + Math.cos(angle) * seg;
          nodes[k * 2 + 1] = py + Math.sin(angle) * seg;
          prevAngle = angle;
        }
      }
    }

    stepFish(dt) {
      const { fish, turtles, pointer, width: W, height: H, time, tmp: cur } = this;
      const calm = Math.exp(-dt * 0.8);
      for (const f of fish) {
        f.alarm *= calm;
        flowCurrent(f.x, f.y, time, cur);
        let ax = cur.x * 0.5 + (Math.random() - 0.5) * 30;
        let ay = cur.y * 0.5 + (Math.random() - 0.5) * 30 - f.vy * 0.5;

        if (f.escortId >= 0 && f.escortId < turtles.length && f.alarm < 0.3) {
          const t = turtles[f.escortId];
          const fx = Math.cos(t.heading);
          const fy = Math.sin(t.heading);
          const nx = -fy;
          const ny = fx;
          const tx = t.nodes[6] - fx * t.length * 0.1 + nx * f.escortSide * t.length * f.escortDist * 0.4;
          const ty = t.nodes[7] - fy * t.length * 0.1 + ny * f.escortSide * t.length * f.escortDist * 0.4;
          ax += (tx - f.x) * 1.6 + (fx * t.speed - f.vx) * 2.0;
          ay += (ty - f.y) * 1.6 + (fy * t.speed - f.vy) * 2.0;
        }

        if (pointer.active) {
          const dx = f.x - pointer.x;
          const dy = f.y - pointer.y;
          const d = Math.hypot(dx, dy);
          if (d < 130 && d > 1e-3) {
            const w = (1 - d / 130) ** 2;
            ax += (dx / d) * 850 * w;
            ay += (dy / d) * 850 * w;
            f.alarm = Math.max(f.alarm, w);
          }
        }

        const mPad = 32;
        if (f.x < mPad) ax += (mPad - f.x) * 5;
        else if (f.x > W - mPad) ax -= (f.x - (W - mPad)) * 5;
        if (f.y < mPad) ay += (mPad - f.y) * 5;
        else if (f.y > H - mPad) ay -= (f.y - (H - mPad)) * 5;

        const before = Math.atan2(f.vy, f.vx);
        f.vx += ax * dt;
        f.vy += ay * dt;
        const spd = Math.hypot(f.vx, f.vy) || 1;
        const maxSpd = 55 * (1 + f.alarm * 1.3);
        if (spd > maxSpd) {
          f.vx *= maxSpd / spd;
          f.vy *= maxSpd / spd;
        } else if (spd < 16) {
          f.vx *= 16 / spd;
          f.vy *= 16 / spd;
        }
        f.turn = angleDiff(before, Math.atan2(f.vy, f.vx)) / dt;
        f.x = clamp(f.x + f.vx * dt, -30, W + 30);
        f.y = clamp(f.y + f.vy * dt, -30, H + 30);
      }
    }
  }

  class TurtleRenderer extends BaseAsciiRenderer {
    constructor(canvas) {
      super(canvas, TURTLE_KINDS, TURTLE_TINTS);
      this.ambientGlyph = "·";
      this.spine = new Float32Array(TURTLE_NODES * 2);
      this.arc = new Float32Array(TURTLE_NODES);
      this.arcTotal = 1;
      this.curTurtle = null;
      this.curShape = TURTLE_SHAPES.loggerhead;
    }

    render(world, dt) {
      const { ctx, dpr, cols, ch } = this;
      if (cols === 0) return;
      const t = world.time;

      this.consumeEvents(world);
      this.rasterizeTurtles(world.turtles, t);
      this.depositWake(world);
      this.diffuse(dt);

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(this.bg, 0, 0);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      this.markAmbient(world.fish);
      this.drawDots();

      ctx.font = `600 ${Math.round(ch * 0.74)}px ${this.fontFamily}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      this.drawHeat();
      this.drawAmbient();
      this.drawTurtleCells(t);
    }

    depositWake(world) {
      const { energy } = this;
      for (const f of world.fish) {
        const i = this.cellIndex(f.x, f.y);
        if (i >= 0) energy[i] = Math.min(1.5, energy[i] + 0.01 + f.alarm * 0.02);
      }
      for (const t of world.turtles) {
        const i = this.cellIndex(t.nodes[0], t.nodes[1]);
        if (i >= 0) energy[i] = Math.min(1.5, energy[i] + 0.035);

        // Power stroke deposits wake vortices at flipper tips
        const strokeSin = Math.sin(t.strokeCycle);
        if (strokeSin > 0.15) {
          const L = t.length;
          const fx = Math.cos(t.heading);
          const fy = Math.sin(t.heading);
          const nx = -fy;
          const ny = fx;
          const shape = TURTLE_SHAPES[t.kind] || TURTLE_SHAPES.loggerhead;
          const extension = 1.0 - 0.58 * Math.pow(strokeSin, 1.25);
          const span = L * (shape.flipperSpan || 0.49) * extension;
          const tipS = (0.22 + 0.10 + 0.28 * Math.pow(strokeSin, 1.15)) * L;

          // Left tip
          const lx = t.nodes[0] - fx * tipS + nx * span;
          const ly = t.nodes[1] - fy * tipS + ny * span;
          const li = this.cellIndex(lx, ly);
          if (li >= 0) energy[li] = Math.min(1.6, energy[li] + 0.045 * strokeSin);

          // Right tip
          const rx = t.nodes[0] - fx * tipS - nx * span;
          const ry = t.nodes[1] - fy * tipS - ny * span;
          const ri = this.cellIndex(rx, ry);
          if (ri >= 0) energy[ri] = Math.min(1.6, energy[ri] + 0.045 * strokeSin);
        }
      }
    }

    sampleTurtle(px, py) {
      const { spine, arc, curTurtle: t, curShape: shape } = this;
      const L = this.arcTotal;
      const N = TURTLE_NODES;

      let best = Infinity;
      let bestS = 0;
      let bestSign = 1;

      for (let k = 0; k < N - 1; k++) {
        const ax = spine[k * 2];
        const ay = spine[k * 2 + 1];
        const bx = spine[(k + 1) * 2];
        const by = spine[(k + 1) * 2 + 1];
        const abx = bx - ax;
        const aby = by - ay;
        const ab2 = abx * abx + aby * aby || 1e-6;
        const apx = px - ax;
        const apy = py - ay;
        const param = clamp((apx * abx + apy * aby) / ab2, 0, 1);
        const qx = ax + abx * param;
        const qy = ay + aby * param;
        const d2 = (px - qx) ** 2 + (py - qy) ** 2;
        if (d2 < best) {
          best = d2;
          const sAlong = (arc[k] + Math.sqrt(ab2) * param) / this.arcTotal;
          bestS = clamp(sAlong, 0, 1);
          const cross = abx * apy - aby * apx;
          bestSign = cross >= 0 ? 1 : -1;
        }
      }

      const dist = Math.sqrt(best);
      this.hitDist = dist;
      this.hitS = bestS;
      this.hitV = dist * bestSign;

      const s = bestS;
      const a = dist;

      // ── 1. HEAD & BEAK (s from 0 to 0.18, lighter skin tint) ──
      if (s <= 0.18) {
        const headEnd = 0.13;
        if (s <= headEnd) {
          const pHead = s / headEnd; // 0 at snout tip, 1 at skull base
          let headW;
          if (shape.beakSharp) {
            headW = L * 0.075 * Math.sqrt(pHead) * (1 - 0.15 * pHead);
          } else {
            headW = L * (shape.headScale || 0.11) * Math.sin(Math.pow(pHead, 0.62) * Math.PI * 0.88);
          }
          if (a <= headW) {
            if (s >= 0.040 && s <= 0.078 && a >= headW * 0.58) {
              this.hitFlag = FLAG_EYE;
              this.hitShade = 0;
            } else {
              this.hitFlag = FLAG_MARK; // Head (lighter skin tint!)
              this.hitShade = 0.74 - 0.22 * (a / (headW || 1));
            }
            return true;
          }
        }
        // Neck connecting head to shell
        const neckW = L * 0.065;
        if (s > 0.09 && s <= 0.18 && a <= neckW) {
          this.hitFlag = FLAG_MARK; // Neck (lighter skin tint!)
          this.hitShade = 0.62;
          return true;
        }
      }

      // ── 2. CARAPACE / SHELL (s from 0.18 to 0.78, narrow streamlined dark dome) ──
      const shellStart = 0.18;
      const shellEnd = 0.78;
      if (s >= shellStart && s <= shellEnd) {
        const pShell = (s - shellStart) / (shellEnd - shellStart); // 0 at anterior nuchal notch, 1 at posterior
        // Broad, natural carapace dome
        const maxShellW = L * (shape.shellWidth || 0.30);

        let shellProf;
        if (shape.scuteType === "ridley") {
          shellProf = Math.sin(Math.pow(pShell, 0.72) * Math.PI);
        } else if (shape.scuteType === "loggerhead") {
          shellProf = Math.sin(Math.pow(pShell, 0.65) * Math.PI) * (1 - 0.18 * pShell);
        } else {
          // Green / Hawksbill: elegant elongated teardrop oval
          shellProf = Math.sin(Math.pow(pShell, 0.74) * Math.PI) * (1 - 0.14 * pShell);
        }

        let serration = 0;
        if (shape.serratedMargin && pShell > 0.65) {
          serration = 0.03 * Math.sin(pShell * 36) * ((pShell - 0.65) / 0.35);
        }

        const halfW = maxShellW * (shellProf + serration);
        if (a <= halfW) {
          const rShell = a / (halfW || 1); // 0 at spine ridge, 1 at outer rim

          // Vertebral ridge (keel)
          if (rShell < 0.10) {
            this.hitFlag = FLAG_RIDGE;
            this.hitShade = 0.95;
            return true;
          }

          // Marginal scutes rim
          if (rShell > 0.85) {
            this.hitFlag = FLAG_RIDGE;
            this.hitShade = 0.65;
            return true;
          }

          // Scute seams
          const scuteU = pShell * 4.6;
          const scuteV = rShell * 2.6;
          const du = Math.abs(scuteU - Math.round(scuteU));
          const dv = Math.abs(scuteV - Math.round(scuteV));
          if (Math.min(du, dv) < 0.09) {
            this.hitFlag = FLAG_RIDGE;
            this.hitShade = 0.85;
            return true;
          }

          // Hawksbill golden tortoiseshell marbling
          if (shape.scuteType === "hawksbill" && hash3(Math.round(scuteU), Math.round(scuteV), t.id) > 0.30) {
            this.hitFlag = FLAG_WHITE_SPOT;
            this.hitShade = 0.92;
            return true;
          }

          // Carapace body (uses dark shellTint!)
          this.hitFlag = FLAG_BODY;
          this.hitShade = 0.72 - rShell * 0.22;
          return true;
        }
      }

      // ── 3. ARTICULATED FRONT FLIPPERS (PECTORAL WINGS - Estiramiento y Encogimiento) ──
      const sShoulder = 0.22;
      const strokeSin = Math.sin(t.strokeCycle);
      const strokeCos = Math.cos(t.strokeCycle);
      const aMin = L * 0.08;

      // When strokeSin < 0 (recovery): flippers reach forward and STRETCH wide out (estirarse)!
      // When strokeSin > 0 (power stroke): flippers sweep back and CONTRACT tight (encogerse)!
      let extension;
      let strokeSweep;
      if (strokeSin < 0) {
        // Recovery / Reach: fully stretched out to the sides and reached forward
        const extProg = -strokeSin; // 0 to 1
        extension = 1.0 + 0.20 * extProg; // Expands up to 1.20x base span!
        strokeSweep = -0.15 * extProg;    // Reaches forward towards head (s -> 0.14)
      } else {
        // Power stroke: pulls back and contracts tight against the carapace flanks
        const pullProg = strokeSin; // 0 to 1
        extension = 1.0 - 0.58 * Math.pow(pullProg, 1.25); // Contracts down to 0.42x base span!
        strokeSweep = 0.28 * Math.pow(pullProg, 1.15);     // Sweeps back along shell (s -> 0.52)
      }

      // Banking into turns: outer flipper extends wider, inner flipper tucks/brakes
      const bank = clamp(t.turn * 1.1, -0.35, 0.35) * bestSign;
      const baseSpan = L * (shape.flipperSpan || 0.49);
      const curSpan = baseSpan * extension * (1 + bank * 0.35);
      const aMax = aMin + curSpan;

      if (a >= aMin && a <= aMax) {
        const spanProg = (a - aMin) / curSpan; // 0 at shoulder, 1 at wingtip

        // Natural hydrofoil backward sweep + stroke sweep
        const baseSweep = 0.10 * Math.pow(spanProg, 1.3);
        const sweepAmp = strokeSweep * Math.pow(spanProg, 1.1);

        // Blade lag: flexible wingtip flexes with water resistance
        const bladeLag = -0.06 * strokeCos * Math.pow(spanProg, 1.4);

        const flipperAxisS = sShoulder + baseSweep + sweepAmp + bladeLag;

        // Hydrodynamic tapered blade chord
        const flipperChord = 0.046 + 0.050 * Math.sin(spanProg * Math.PI) * (1 - 0.20 * spanProg);
        const ds = Math.abs(s - flipperAxisS);

        if (ds <= flipperChord) {
          this.hitFlag = FLAG_FIN; // Flippers (uses lighter skinTint!)
          // Dynamic shading: highlights the leading edge and blade curvature
          const edgeShade = 1 - (ds / flipperChord);
          this.hitShade = 0.60 + edgeShade * 0.18 - spanProg * 0.15 + strokeCos * 0.10 * spanProg;
          return true;
        }
      }

      // ── 4. REAR FLIPPERS (PELVIC STEERING RUDDERS) ──
      const rearRootS = 0.70;
      const rearMinA = L * 0.05;
      const rearMaxA = L * 0.28;
      if (a >= rearMinA && a <= rearMaxA && s >= 0.62 && s <= 0.94) {
        const rearSpanProg = (a - rearMinA) / (rearMaxA - rearMinA);
        // Tilts dynamically into turns like an airplane rudder!
        const rudderAngle = -t.turn * 0.45 * bestSign;
        const rearAxisS = rearRootS + rearSpanProg * 0.14 + rudderAngle * 0.08;
        const rearChord = 0.080 * (1 - 0.35 * rearSpanProg) + 0.02;
        if (Math.abs(s - rearAxisS) <= rearChord) {
          this.hitFlag = FLAG_FIN; // Rear flipper paddles (lighter skinTint)
          this.hitShade = 0.58 - rearSpanProg * 0.18;
          return true;
        }
      }

      // ── 5. SHORT TAIL ──
      if (s >= 0.76 && s <= 0.90) {
        const tailProg = (s - 0.76) / 0.14;
        const tailW = L * 0.030 * (1 - tailProg);
        if (a <= tailW) {
          this.hitFlag = FLAG_MARK; // Tail (lighter skinTint)
          this.hitShade = 0.55;
          return true;
        }
      }

      return false;
    }

    rasterizeTurtles(turtles, t) {
      const { cellFlag, cellShade, cellKey, cellDepth, cellKind, cols, rows, cw, ch, kinds } = this;
      cellFlag.fill(0);

      for (let mIdx = 0; mIdx < turtles.length; mIdx++) {
        const turtle = turtles[mIdx];
        this.curTurtle = turtle;
        const kindIndex = Math.max(0, kinds.indexOf(turtle.kind));
        this.curShape = TURTLE_SHAPES[turtle.kind] || TURTLE_SHAPES.loggerhead;

        const L = turtle.length;
        const spine = this.spine;
        const nodes = turtle.nodes;
        for (let k = 0; k < TURTLE_NODES * 2; k++) spine[k] = nodes[k];

        let acc = 0;
        this.arc[0] = 0;
        for (let k = 0; k < TURTLE_NODES - 1; k++) {
          const dx = spine[(k + 1) * 2] - spine[k * 2];
          const dy = spine[(k + 1) * 2 + 1] - spine[k * 2 + 1];
          acc += Math.hypot(dx, dy);
          this.arc[k + 1] = acc;
        }
        this.arcTotal = acc || turtle.length;

        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        for (let k = 0; k < TURTLE_NODES; k++) {
          minX = Math.min(minX, spine[k * 2]);
          maxX = Math.max(maxX, spine[k * 2]);
          minY = Math.min(minY, spine[k * 2 + 1]);
          maxY = Math.max(maxY, spine[k * 2 + 1]);
        }
        const reach = L * ((this.curShape.flipperSpan || 0.52) * 1.45 + 0.12) + 24;
        const c0 = Math.max(0, Math.floor((minX - reach) / cw));
        const c1 = Math.min(cols - 1, Math.floor((maxX + reach) / cw));
        const r0 = Math.max(0, Math.floor((minY - reach) / ch));
        const r1 = Math.min(rows - 1, Math.floor((maxY + reach) / ch));
        if (c0 > c1 || r0 > r1) continue;

        const skipBeyond = reach + Math.hypot(cw, ch);

        for (let r = r0; r <= r1; r++) {
          for (let c = c0; c <= c1; c++) {
            const x = c * cw;
            const y = r * ch;
            const centerHit = this.sampleTurtle(x + cw / 2, y + ch / 2);
            if (!centerHit && this.hitDist > skipBeyond) continue;
            const flag = this.hitFlag;
            const shade = this.hitShade;
            const s = this.hitS;
            const v = this.hitV;

            let hits = centerHit ? 1 : 0;
            for (let k = 0; k < SUBSAMPLES.length; k += 2) {
              if (this.sampleTurtle(x + SUBSAMPLES[k] * cw, y + SUBSAMPLES[k + 1] * ch)) hits++;
            }
            if (hits === 0) continue;
            const coverage = hits / 5;

            const i = r * cols + c;
            const key = (hash3(Math.round(s * 52), Math.round(v / (cw * 0.9)), turtle.id) * 4294967295) >>> 0;
            cellKey[i] = key;
            cellDepth[i] = turtle.depth;
            cellKind[i] = kindIndex;

            if (centerHit && coverage >= 0.6) {
              cellFlag[i] = flag;
              const flicker = (hash3(c, r, Math.floor(t * 6)) - 0.5) * 0.05;
              cellShade[i] = clamp(shade + flicker, 0, 1);
            } else {
              cellFlag[i] = FLAG_EDGE;
              cellShade[i] = coverage;
            }
          }
        }
      }
    }

    drawTurtleCells(t) {
      const { ctx, cols, rows, cw, ch, cellFlag, cellShade, cellKey, cellDepth, cellKind, kinds } = this;
      const HAWKSBILL_MARBLE_GLYPHS = "%#*@S";
      const n = cols * rows;

      for (let i = 0; i < n; i++) {
        const flag = cellFlag[i];
        if (!flag) continue;
        const col = i % cols;
        const row = (i / cols) | 0;
        const x = col * cw;
        const y = row * ch;
        const key = cellKey[i];
        const shade = cellShade[i];
        const dim = 0.85 + 0.15 * cellDepth[i];
        const kindName = kinds[cellKind[i]] || "loggerhead";
        const shape = TURTLE_SHAPES[kindName] || TURTLE_SHAPES.loggerhead;

        if (flag === FLAG_EDGE) {
          const set = shade >= 0.5 ? EDGE_HEAVY : EDGE_LIGHT;
          const glyph = set[(key >>> 8) % set.length];
          const [sr, sg, sb] = shape.skinTint || shape.tint;
          ctx.fillStyle = `rgba(${Math.round(45 * sr)}, ${Math.round(50 * sg)}, ${Math.round(55 * sb)}, 0.65)`;
          ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
          continue;
        }

        if (flag === FLAG_WHITE_SPOT) {
          // Hawksbill golden tortoiseshell scute infill
          const lum = Math.round(225 * dim);
          ctx.fillStyle = `rgb(${Math.min(255, Math.round(lum * 1.15))}, ${Math.min(255, Math.round(lum * 0.82))}, ${Math.round(lum * 0.28)})`;
          ctx.fillRect(x + 1, y + 1, cw - 1, ch - 1);
          const glyph = HAWKSBILL_MARBLE_GLYPHS[(key >>> 5) % HAWKSBILL_MARBLE_GLYPHS.length];
          ctx.fillStyle = "#3e2205";
          ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
          continue;
        }

        let lum;
        let glyph;
        let tr, tg, tb;

        if (flag === FLAG_EYE) {
          lum = 22;
          glyph = "o";
          [tr, tg, tb] = [1, 1, 1];
        } else if (flag === FLAG_RIDGE) {
          // Dark scute seams & vertebral keel
          lum = 42 * dim;
          glyph = RIDGE_GLYPHS[(key >>> 8) % RIDGE_GLYPHS.length];
          [tr, tg, tb] = shape.shellTint || shape.tint;
        } else if (flag === FLAG_BODY) {
          // ── CARAPACE / SHELL (Distinctly darker armored dome as requested!) ──
          lum = (122 - shade * 38) * dim;
          const jitter = ((key >>> 4) % 3) - 1;
          glyph = SKIN_RAMP[clamp(Math.floor(shade * 8.99) + jitter, 0, SKIN_RAMP.length - 1)];
          [tr, tg, tb] = shape.shellTint || shape.tint;
        } else {
          // ── APPENDAGES: LARGE PROMINENT FLIPPERS & HEAD (Lighter, bright, highly recognizable!) ──
          lum = (222 - shade * 32) * dim;
          if (flag === FLAG_FIN) {
            const FLIP_GLYPHS = "%;tS~";
            glyph = FLIP_GLYPHS[(key >>> 8) % FLIP_GLYPHS.length];
          } else {
            const jitter = ((key >>> 4) % 3) - 1;
            glyph = SKIN_RAMP[clamp(Math.floor(shade * 8.99) + jitter, 0, SKIN_RAMP.length - 1)];
          }
          [tr, tg, tb] = shape.skinTint || shape.tint;
        }

        const r = clamp(Math.round(lum * tr), 0, 255);
        const g = clamp(Math.round(lum * tg), 0, 255);
        const b = clamp(Math.round(lum * tb), 0, 255);
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.fillRect(x + 1, y + 1, cw - 1, ch - 1);

        let glyphColor;
        if (flag === FLAG_EYE) {
          glyphColor = "#ffffff";
        } else if (flag === FLAG_RIDGE) {
          glyphColor = "#fef08a"; // Soft golden scute seam line
        } else if (flag === FLAG_BODY) {
          // Subtle warm texture on dark shell
          glyphColor = `rgb(${Math.min(255, r + 55)}, ${Math.min(255, g + 55)}, ${Math.min(255, b + 45)})`;
        } else {
          // High contrast dark slate glyph text on lighter flippers & head
          glyphColor = `rgb(${Math.max(0, Math.round(r * 0.40))}, ${Math.max(0, Math.round(g * 0.40))}, ${Math.max(0, Math.round(b * 0.35))})`;
        }

        ctx.fillStyle = glyphColor;
        ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
      }
    }
  }

  class TurtleEngine extends BaseLoopEngine {
    constructor(canvas, specs) {
      const world = new TurtleWorld(specs);
      const renderer = new TurtleRenderer(canvas);
      super(canvas, world, renderer);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. PERMANENT SEA WAVES ENGINE ("waves" / "sea_waves")
  //    Gentle, perpetual ocean swell rolling fluently from top to bottom (up -> down).
  //    Features multi-harmonic lateral distortion along the X axis so waves are
  //    not straight or identical across X, but curve, undulate, ebb, and swell
  //    organically across the sea surface. Deep blue ocean styling.
  // ═══════════════════════════════════════════════════════════════════════════

  const SEA_PALETTES = ["deep_blue", "navy_swell", "cobalt_crest", "foam_cyan"];
  const SEA_TINTS = {
    deep_blue:    [0.12, 0.28, 0.62], // Deep navy/sapphire swell
    navy_swell:   [0.18, 0.38, 0.74], // Mid-ocean cobalt swell
    cobalt_crest: [0.26, 0.52, 0.88], // Lighter blue wave face
    foam_cyan:    [0.60, 0.82, 0.98], // Crisp light cyan crest foam
  };

  const SEA_CREST_GLYPHS  = "~^≈*#@S%";
  const SEA_FACE_GLYPHS   = "~=-~·^";
  const SEA_TROUGH_GLYPHS = "·°·.";

  class SeaWaveWorld {
    constructor() {
      this.width = 0;
      this.height = 0;
      this.cw = 11;
      this.ch = 15;
      this.cols = 0;
      this.rows = 0;
      this.time = 0;

      // Downward flow speed (px/s, slow and relaxing)
      this.flowSpeed = 28;
      this.wavelength = 135;

      // Interactive splashes that radiate outward and displace passing waves
      this.ripples = [];
      this.events = [];
      this.pointer = { x: 0, y: 0, active: false };

      // Drifting foam specks that float along with the swell
      this.foamSpecks = [];
    }

    resize(width, height, cw = 11, ch = 15) {
      const first = this.width === 0;
      this.width = width;
      this.height = height;
      this.cw = cw || clamp(Math.round(width / 120), 9, 13);
      this.ch = ch || Math.round(this.cw * 1.38);
      this.cols = Math.ceil(width / this.cw);
      this.rows = Math.ceil(height / this.ch);

      const minSide = Math.min(width, height) || 700;
      this.wavelength = clamp(minSide * 0.18, 120, 165);

      if (first || this.foamSpecks.length === 0) {
        this.seedFoamSpecks();
      }
    }

    seedFoamSpecks() {
      this.foamSpecks = [];
      const count = clamp(Math.round((this.width * this.height) / 14000), 40, 95);
      for (let i = 0; i < count; i++) {
        this.foamSpecks.push({
          x: rand(0, this.width),
          y: rand(0, this.height),
          speedY: rand(24, 38),
          driftX: rand(-3.5, 3.5),
          size: rand(0.6, 1.3),
          phase: rand(0, TAU),
        });
      }
    }

    // User clicking splashes the water, creating an expanding radial ripple
    splash(x, y) {
      if (this.ripples.length >= 8) {
        this.ripples.shift();
      }
      this.ripples.push({
        x,
        y,
        radius: 0,
        maxRadius: clamp(Math.min(this.width, this.height) * 0.44, 230, 380),
        speed: 85,
        amp: 1.0,
        age: 0,
      });
      this.events.push({ kind: "pulse", x, y });
    }

    step(dt) {
      this.time += dt;
      const { width: W, height: H } = this;
      if (!W || !H) return;

      // Advance user click ripples
      for (let i = this.ripples.length - 1; i >= 0; i--) {
        const rip = this.ripples[i];
        rip.age += dt;
        rip.radius += rip.speed * dt;
        rip.amp = clamp(1 - (rip.radius / rip.maxRadius) ** 1.6, 0, 1);
        if (rip.radius >= rip.maxRadius || rip.amp <= 0.02) {
          this.ripples.splice(i, 1);
        }
      }

      // Drift foam specks downward along with the rolling swell
      for (const f of this.foamSpecks) {
        f.y += f.speedY * dt;
        f.x += (f.driftX + Math.sin(this.time * 0.8 + f.phase) * 6) * dt;
        if (f.y > H + 20) {
          f.y = -20;
          f.x = rand(0, W);
        }
        if (f.x < -20) f.x = W + 20;
        else if (f.x > W + 20) f.x = -20;
      }
    }

    // Compute the permanent sea wave elevation at (x, y) with organic lateral X distortion
    sampleElevation(x, y) {
      const t = this.time;
      const W = this.width || 1200;

      // ── ORGANIC LATERAL DISTORTION ALONG THE X AXIS ──
      // 1. Broad ocean swell curvature (long wavelength ~0.8*W):
      //    Waves bow gently, creating wide crescent swell curves across X
      const swell1 = Math.sin((x / W) * TAU * 1.25 + t * 0.14) * 58;

      // 2. Mid-frequency sinuous undulations:
      //    Prevents the wave lines from being uniform or parallel across X
      const swell2 = Math.sin(x * 0.012 - t * 0.22 + y * 0.002) * 28;
      const swell3 = Math.cos(x * 0.024 + t * 0.16) * 16;

      // 3. Fine wave-edge harmonic ripple:
      const swell4 = Math.sin(x * 0.048 - t * 0.36 + y * 0.006) * 8;

      const totalDistortion = swell1 + swell2 + swell3 + swell4;

      // ── PRIMARY DOWNWARD WAVE SWELL (Top -> Bottom, +Y) ──
      const waveTravelY = y + totalDistortion - t * this.flowSpeed;
      const k1 = TAU / this.wavelength;
      const phase1 = waveTravelY * k1;
      // Stokes/trochoid profile: sharper crests, wider flat troughs
      const crest1 = Math.pow(Math.max(0, (Math.cos(phase1) + 1) * 0.5), 1.75);

      // ── SECONDARY CROSS-SWELL (Slightly angled at ~14 degrees) ──
      // Creates beautiful natural wave interference and shifting crest heights
      const diagY = y * 0.97 + x * 0.24;
      const diagDistort = Math.cos(x * 0.011 + t * 0.20) * 18;
      const k2 = TAU / (this.wavelength * 1.28);
      const phase2 = (diagY + diagDistort - t * (this.flowSpeed * 0.86)) * k2;
      const crest2 = Math.pow(Math.max(0, (Math.cos(phase2) + 1) * 0.5), 2.1);

      // Combine swells
      let elevation = crest1 * 0.70 + crest2 * 0.30;

      // ── INTERACTIVE RIPPLE DISPLACEMENT ──
      for (let i = 0; i < this.ripples.length; i++) {
        const rip = this.ripples[i];
        const dx = x - rip.x;
        const dy = y - rip.y;
        const dist = Math.hypot(dx, dy);
        const diff = dist - rip.radius;
        if (Math.abs(diff) < 52) {
          const ripK = TAU / 38;
          const ripPhase = diff * ripK;
          const ripEnv = Math.cos((diff / 52) * Math.PI * 0.5) ** 2;
          const rippleMod = Math.cos(ripPhase) * ripEnv * rip.amp * 0.55;
          elevation = clamp(elevation + rippleMod, 0, 1.2);
        }
      }

      return clamp(elevation, 0, 1.0);
    }
  }

  class SeaWaveRenderer extends BaseAsciiRenderer {
    constructor(canvas) {
      super(canvas, SEA_PALETTES, SEA_TINTS);
      this.ambientGlyph = "·";
    }

    render(world, dt) {
      const { ctx, dpr, cols, ch } = this;
      if (cols === 0) return;
      const t = world.time;

      this.consumeEvents(world);
      this.diffuse(dt);

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(this.bg, 0, 0);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      this.drawDots();

      ctx.font = `600 ${Math.round(ch * 0.74)}px ${this.fontFamily}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      this.drawSeaWaves(world, t);
      this.drawFoamSpecks(world, t);
      this.drawRipples(world, t);
    }

    drawSeaWaves(world, t) {
      const { ctx, cols, rows, cw, ch } = this;
      const tick = Math.floor(t * 0.85);

      for (let r = 0; r < rows; r++) {
        const y = (r + 0.5) * ch;
        for (let c = 0; c < cols; c++) {
          const x = (c + 0.5) * cw;
          const elev = world.sampleElevation(x, y);

          const px = c * cw;
          const py = r * ch;
          const key = (hash3(c, r, 17) * 4294967295) >>> 0;

          if (elev > 0.74) {
            // ── PEAK ROLLING WAVE CREST & FOAM (Soft luminous blue block, gentle opacity) ──
            const crestNorm = clamp((elev - 0.74) / 0.26, 0, 1);
            // Soft translucent blue with gentle opacity (0.28 to 0.55) so it blends whiter and seamlessly into #fafbfe
            const blockAlpha = (0.26 + crestNorm * 0.28).toFixed(3);
            ctx.fillStyle = `rgba(56, 120, 195, ${blockAlpha})`;
            ctx.fillRect(px + 1, py + 1, cw - 1, ch - 1);

            let glyph;
            let glyphColor;
            if (crestNorm > 0.55) {
              glyph = SEA_CREST_GLYPHS[(key >>> 5) % SEA_CREST_GLYPHS.length];
              glyphColor = "#ffffff";
            } else {
              glyph = SEA_FACE_GLYPHS[(key >>> 4) % SEA_FACE_GLYPHS.length];
              glyphColor = "#0f2b5c";
            }

            ctx.fillStyle = glyphColor;
            ctx.fillText(glyph, px + cw / 2, py + ch / 2 + 1);
          } else if (elev > 0.36) {
            // ── SLOPING WAVE FACE (Light, delicate translucent blue glyphs) ──
            const slopeNorm = (elev - 0.36) / 0.34;
            const alpha = clamp(0.18 + slopeNorm * 0.32, 0.16, 0.50);
            ctx.fillStyle = `rgba(45, 95, 165, ${alpha.toFixed(3)})`;
            const glyph = SEA_FACE_GLYPHS[((key >>> 3) + tick) % SEA_FACE_GLYPHS.length];
            ctx.fillText(glyph, px + cw / 2, py + ch / 2 + 1);
          } else {
            // ── TRANQUIL DEEP TROUGH (Soft subtle pastel-navy specks) ──
            if (((c + r) & 1) === 0) {
              const shimmer = 0.12 + 0.08 * Math.sin(t * 0.7 + (key % 23));
              ctx.fillStyle = `rgba(70, 115, 175, ${shimmer.toFixed(3)})`;
              const glyph = SEA_TROUGH_GLYPHS[(key >>> 2) % SEA_TROUGH_GLYPHS.length];
              ctx.fillText(glyph, px + cw / 2, py + ch / 2 + 1);
            }
          }
        }
      }
    }

    drawFoamSpecks(world, t) {
      const { ctx } = this;
      for (const f of world.foamSpecks) {
        const elev = world.sampleElevation(f.x, f.y);
        // Foam specks glow with soft delicate blue-white opacity
        const alpha = clamp(0.25 + elev * 0.40, 0.20, 0.65);
        ctx.fillStyle = elev > 0.65 ? `rgba(240, 249, 255, ${alpha.toFixed(3)})` : `rgba(45, 95, 165, ${alpha.toFixed(3)})`;
        const glyph = elev > 0.65 ? "*" : "·";
        ctx.fillText(glyph, f.x, f.y);
      }
    }

    // ── CLICK SPLASH RIPPLES ──
    drawRipples(world, t) {
      const { ctx, cw } = this;
      for (const rip of world.ripples) {
        if (rip.radius < 4 || rip.amp <= 0.04) continue;
        const alpha = clamp(rip.amp * 0.45, 0.05, 0.50).toFixed(3);
        ctx.fillStyle = `rgba(56, 120, 195, ${alpha})`;
        const R = rip.radius;
        const segCount = clamp(Math.round((R * TAU) / (cw * 2.5)), 8, 36);

        for (let s = 0; s < segCount; s++) {
          const theta = (s / segCount) * TAU;
          const px = rip.x + Math.cos(theta) * R;
          const py = rip.y + Math.sin(theta) * R;
          if (px < -20 || px > world.width + 20 || py < -20 || py > world.height + 20) continue;
          const glyph = Math.abs(Math.sin(theta)) > 0.6 ? "~" : (Math.cos(theta) >= 0 ? ")" : "(");
          ctx.fillText(glyph, px, py);
        }
      }
    }
  }

  class SeaWaveEngine extends BaseLoopEngine {
    constructor(canvas) {
      const world = new SeaWaveWorld();
      const renderer = new SeaWaveRenderer(canvas);
      super(canvas, world, renderer);
    }
  }

  // Alias for backward compatibility
  const SoundWaveWorld = SeaWaveWorld;
  const SoundWaveRenderer = SeaWaveRenderer;
  const SoundWaveEngine = SeaWaveEngine;

  // ── GLOBAL EXPORTS & THEME SWITCHER ──────────────────────────────────────

  window.JellyfishEngine = JellyfishEngine;
  window.MantaEngine = MantaEngine;
  window.TurtleEngine = TurtleEngine;
  window.SeaWaveEngine = SeaWaveEngine;
  window.SoundWaveEngine = SoundWaveEngine;

  const THEME_CREDITS = {
    sharks: "ASCII Sharks by stackedlol",
    turtles: "ASCII Sea Turtles • Loggerhead, Green, Olive Ridley, Hawksbill",
    jellyfish: "ASCII Jellyfish • Inspired by stackedlol",
    mantas: "ASCII Manta Rays • Inspired by stackedlol",
    waves: "ASCII Permanent Sea Waves • Undulating Ocean Swell",
  };

  let activeEngine = null;
  let activeThemeName = null;

  window.initBackgroundCanvas = function (canvas, initialTheme) {
    const params = new URLSearchParams(window.location.search);
    const theme = initialTheme || params.get("theme") || "sharks";
    window.setBackgroundTheme(theme, canvas);
  };

  window.setBackgroundTheme = function (themeName, canvasEl) {
    const mapped =
      themeName === "sound_waves" || themeName === "sea_waves"
        ? "waves"
        : themeName === "turtle" || themeName === "tortuga" || themeName === "tortugas"
        ? "turtles"
        : themeName;
    const normalized = [
      "sharks",
      "turtles",
      "jellyfish",
      "mantas",
      "waves",
    ].includes(mapped)
      ? mapped
      : "sharks";
    const canvas = canvasEl || document.getElementById("shark-canvas");
    if (!canvas) return;
    if (activeEngine && activeThemeName === normalized) return;

    if (activeEngine && typeof activeEngine.destroy === "function") {
      activeEngine.destroy();
      activeEngine = null;
    }

    activeThemeName = normalized;
    if (normalized === "turtles") {
      activeEngine = new TurtleEngine(canvas);
    } else if (normalized === "jellyfish") {
      activeEngine = new JellyfishEngine(canvas);
    } else if (normalized === "mantas") {
      activeEngine = new MantaEngine(canvas);
    } else if (normalized === "waves") {
      activeEngine = new SeaWaveEngine(canvas);
    } else {
      activeEngine = new window.OceanEngine(canvas, [
        { kind: "hammerhead", size: 1.0 },
        { kind: "classic", size: 0.88 },
        { kind: "thresher", size: 0.92 },
        { kind: "mako", size: 0.78 },
      ]);
    }
    window.activeEngine = activeEngine;

    const creditSpan = document.querySelector(".repo-credit span");
    if (creditSpan && THEME_CREDITS[normalized]) {
      creditSpan.textContent = THEME_CREDITS[normalized];
    }
  };

  window.getBackgroundTheme = function () {
    return activeThemeName || "sharks";
  };
})();
