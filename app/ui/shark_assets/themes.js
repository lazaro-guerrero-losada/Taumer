// ASCII Ambient Background Engines for Taumer — Light Mode
// Shares the exact monochrome slate palette, 5-point subsample rasterizer,
// wake diffusion grid, and ASCII glyph ramps from ASCII Sharks.
// Themes:
//   1. "sharks"    — ASCII Sharks (window.OceanEngine in sharks.js)
//   2. "jellyfish" — Pulsing Jellyfish (Deep Sea Zen)
//   3. "bacteria"  — Petri Dish / Bacteria Colony (Microscopic World + Mitosis)
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
  // 2. CONWAY'S GAME OF LIFE ENGINE ("bacteria" / "game_of_life")
  //    John Horton Conway (1970) — B3/S23 Cellular Automaton
  // ═══════════════════════════════════════════════════════════════════════════

  const LIFE_STRAINS = ["cobalt_slate", "teal_slate", "violet_slate", "amber_slate"];
  const LIFE_TINTS = {
    cobalt_slate: [0.54, 0.65, 0.84], // Deep blueprint slate-blue
    teal_slate:   [0.44, 0.72, 0.71], // Crisp bioluminescent slate-teal
    violet_slate: [0.68, 0.55, 0.82], // Dusty amethyst-indigo slate
    amber_slate:  [0.82, 0.56, 0.54], // Warm terracotta-rose slate
  };

  // Classic 1970 John Horton Conway patterns (ASCII art bitmaps)
  const LIFE_PATTERNS = {
    glider: [
      ".O.",
      "..O",
      "OOO",
    ],
    lwss: [
      ".OOOO",
      "O...O",
      "....O",
      "O..O.",
    ],
    mwss: [
      "...O..",
      ".O...O",
      "O.....",
      "O....O",
      "OOOOO.",
    ],
    r_pentomino: [
      ".OO",
      "OO.",
      ".O.",
    ],
    acorn: [
      ".O.....",
      "...O...",
      "OO..OOO",
    ],
    diehard: [
      "......O.",
      "OO......",
      ".O...OOO",
    ],
    pulsar: [
      "..OOO...OOO..",
      ".............",
      "O....O.O....O",
      "O....O.O....O",
      "O....O.O....O",
      "..OOO...OOO..",
      ".............",
      "..OOO...OOO..",
      "O....O.O....O",
      "O....O.O....O",
      "O....O.O....O",
      ".............",
      "..OOO...OOO..",
    ],
    koks_galaxy: [
      "OOOOOO.OO",
      "OOOOOO.OO",
      ".......OO",
      "OO.....OO",
      "OO.....OO",
      "OO.....OO",
      "OO.......",
      "OO.OOOOOO",
      "OO.OOOOOO",
    ],
    pentadecathlon: [
      "..O....O..",
      "OO.OOOO.OO",
      "..O....O..",
    ],
    gosper_gun: [
      "........................O...........",
      "......................O.O...........",
      "............OO......OO............OO",
      "...........O...O....OO............OO",
      "OO........O.....O...OO..............",
      "OO........O...O.OO....O.O...........",
      "..........O.....O.......O...........",
      "...........O...O....................",
      "............OO......................",
    ],
  };

  const LIFE_BIRTH_GLYPHS = "@*+O";
  const LIFE_ACTIVE_GLYPHS = "#8X%S@";
  const LIFE_MATURE_GLYPHS = "S%t;:";
  const LIFE_GHOST_GLYPHS = ":;.·";

  class BacteriaWorld {
    constructor() {
      this.width = 0;
      this.height = 0;
      this.cw = 12;
      this.ch = 18;
      this.cols = 0;
      this.rows = 0;
      this.time = 0;
      this.genInterval = 0.44; // Calm, relaxing slow-motion evolution cadence
      this.generation = 0;
      this.directorTimer = 0;

      // ── PROGRESSIVE POPULATION EBB & FLOW (EXPANSION & CONTRACTION) ──
      // In Conway's Game of Life, life propagates and moves across space through oscillators,
      // moving gliders and spaceships (LWSS/MWSS/HWSS), and dynamic methuselah reactions.
      // When density reaches max threshold (~6.8%), the environment gently inverts to "shrink":
      // births become slightly harder (probabilistic) and over-dense clusters thin out,
      // creating a very slow, calm, relaxing contraction until reaching min threshold (~1.6%).
      // In both phases, gliders and moving spaceships continuously traverse the open space,
      // and static frozen blocks slowly dissolve or re-awaken into gliders so the screen never stagnates!
      this.ecoPhase = "grow"; // "grow" or "shrink"
      this.maxDensityThreshold = 0.068; // Lower ceiling for spacious airy canvas (~6.8%)
      this.minDensityThreshold = 0.016; // Lower floor (~1.6%)

      this.alive = new Uint8Array(0);
      this.nextAlive = new Uint8Array(0);
      this.age = new Uint16Array(0);
      this.strain = new Uint8Array(0);
      this.fade = new Float32Array(0);
      this.neighbors = new Uint8Array(0);
      this.cellGrowth = new Float32Array(0); // [0..1] continuous growth/bloom progress
      this.cellTimer = new Float32Array(0);  // per-cell staggered evolution clock

      this.liveCount = 0;
      this.birthsLastStep = 0;
      this.activeCount = 0;
      this.stagnantSteps = 0;
      this.clickCycle = 0;
      this.nextStrainCycle = 0;
      this.lastPointerCell = -1;
      this.pointerTrailCooldown = 0;

      this.ambientNodes = [];
      this.events = [];
      this.pointer = { x: 0, y: 0, active: false };
    }

    resize(width, height, cw = 12, ch = 18) {
      this.width = width;
      this.height = height;
      this.cw = cw || clamp(Math.round(width / 124), 8, 13);
      this.ch = ch || Math.round(this.cw * 1.45);
      const newCols = Math.ceil(width / this.cw);
      const newRows = Math.ceil(height / this.ch);

      if (newCols !== this.cols || newRows !== this.rows || this.alive.length === 0) {
        this.cols = newCols;
        this.rows = newRows;
        const n = newCols * newRows;
        this.alive = new Uint8Array(n);
        this.nextAlive = new Uint8Array(n);
        this.age = new Uint16Array(n);
        this.strain = new Uint8Array(n);
        this.fade = new Float32Array(n);
        this.neighbors = new Uint8Array(n);
        this.cellGrowth = new Float32Array(n);
        this.cellTimer = new Float32Array(n);

        // Stagger each cell's evolution timer smoothly across the grid
        // so every cell evolves at a different time but at the exact same slow-motion speed!
        for (let r = 0; r < newRows; r++) {
          for (let c = 0; c < newCols; c++) {
            const i = r * newCols + c;
            const phase = ((c * 0.082 + r * 0.126 + hash3(c, r, 29) * 0.35) % 1.0 + 1.0) % 1.0;
            this.cellTimer[i] = phase * this.genInterval;
            this.cellGrowth[i] = 0.0;
          }
        }
        this.seedEcosystem(true);
      }
    }

    wrapCol(c) {
      const { cols } = this;
      return ((c % cols) + cols) % cols;
    }

    wrapRow(r) {
      const { rows } = this;
      return ((r % rows) + rows) % rows;
    }

    clearDisk(c0, r0, radius) {
      const { cols, rows, alive, age, fade, cellGrowth } = this;
      if (!cols || !rows) return;
      const r2 = radius * radius;
      for (let dr = -radius; dr <= radius; dr++) {
        for (let dc = -radius; dc <= radius; dc++) {
          if (dc * dc + dr * dr > r2) continue;
          const c = this.wrapCol(c0 + dc);
          const r = this.wrapRow(r0 + dr);
          const i = r * cols + c;
          if (alive[i]) {
            alive[i] = 0;
            age[i] = 0;
            fade[i] = 0.35;
            if (cellGrowth) cellGrowth[i] = 0.0;
          }
        }
      }
    }

    stampPattern(patternName, c0, r0, strainId = 0, flipX = false, flipY = false, transpose = false) {
      const rowsData = LIFE_PATTERNS[patternName];
      if (!rowsData || !this.cols || !this.rows) return;
      const pH = rowsData.length;
      const pW = rowsData[0].length;
      const { cols, alive, age, strain, fade, cellGrowth } = this;

      for (let pr = 0; pr < pH; pr++) {
        const line = rowsData[pr];
        for (let pc = 0; pc < pW; pc++) {
          if (line[pc] !== "O") continue;
          let dc = flipX ? pW - 1 - pc : pc;
          let dr = flipY ? pH - 1 - pr : pr;
          dc -= Math.floor(pW / 2);
          dr -= Math.floor(pH / 2);
          if (transpose) {
            const tmp = dc;
            dc = dr;
            dr = tmp;
          }
          const c = this.wrapCol(c0 + dc);
          const r = this.wrapRow(r0 + dr);
          const idx = r * cols + c;
          alive[idx] = 1;
          age[idx] = 1;
          strain[idx] = strainId & 3;
          fade[idx] = 1.0;
          if (cellGrowth) cellGrowth[idx] = 1.0;
        }
      }
    }

    seedEcosystem(fullReset = true) {
      const { cols, rows, cw, ch } = this;
      if (!cols || !rows) return;
      if (fullReset) {
        this.alive.fill(0);
        this.nextAlive.fill(0);
        this.age.fill(0);
        this.fade.fill(0);
        if (this.cellGrowth) this.cellGrowth.fill(0);
      }

      // Airy, open initial ecosystem: dynamic moving gliders and spaceships + oscillators
      // leaving spacious negative room across the canvas
      // 1. Moving gliders traveling across quadrants
      this.stampPattern("glider", Math.round(cols * 0.22), Math.round(rows * 0.24), 0, false, false, false);
      this.stampPattern("glider", Math.round(cols * 0.78), Math.round(rows * 0.72), 1, true, true, false);
      this.stampPattern("glider", Math.round(cols * 0.76), Math.round(rows * 0.22), 2, true, false, false);

      // 2. Moving lightweight spaceships (LWSS) traveling horizontally
      this.stampPattern("lwss", Math.round(cols * 0.18), Math.round(rows * 0.65), 3, false, false, false);

      // 3. Evolving methuselah that naturally produces gliders and active motion
      this.stampPattern("r_pentomino", Math.round(cols * 0.50), Math.round(rows * 0.38), 0, false, false, false);

      // Subtle background coordinate markers for ambient depth
      this.ambientNodes = [];
      const aCount = clamp(Math.round((cols * rows) / 110), 35, 95);
      for (let i = 0; i < aCount; i++) {
        this.ambientNodes.push({
          x: rand(0, cols * cw),
          y: rand(0, rows * ch),
          alive: true,
          depth: rand(0.56, 0.92),
          turn: 0,
          alarm: 0,
        });
      }

      if (fullReset) {
        for (let i = 0; i < this.alive.length; i++) {
          if (this.alive[i]) {
            this.cellGrowth[i] = 1.0;
            this.fade[i] = 1.0;
          }
        }
      }
      this.updateNeighborCounts();
      this.events.push({ kind: "pulse", x: (cols * cw) * 0.5, y: (rows * ch) * 0.5 });
    }

    findOpenSpot() {
      const { cols, rows, alive } = this;
      let bestC = Math.floor(cols * 0.5);
      let bestR = Math.floor(rows * 0.5);
      let bestScore = Infinity;

      for (let attempt = 0; attempt < 12; attempt++) {
        const c0 = Math.floor(rand(cols * 0.12, cols * 0.88));
        const r0 = Math.floor(rand(rows * 0.14, rows * 0.86));
        let count = 0;
        for (let dr = -8; dr <= 8; dr += 2) {
          for (let dc = -8; dc <= 8; dc += 2) {
            const c = this.wrapCol(c0 + dc);
            const r = this.wrapRow(r0 + dr);
            if (alive[r * cols + c]) count++;
          }
        }
        if (count < bestScore) {
          bestScore = count;
          bestC = c0;
          bestR = r0;
          if (count === 0) break;
        }
      }
      return { c: bestC, r: bestR };
    }

    spawnColonyAtGrid(c0, r0, burstKind = -1) {
      const { cw, ch } = this;
      const sId = (this.nextStrainCycle++) & 3;
      const mode = burstKind >= 0 ? burstKind % 5 : (this.clickCycle++) % 5;

      // Clear a small breathing pocket so the new population can flourish
      this.clearDisk(c0, r0, 6);

      if (mode === 0) {
        // Dynamic Glider Fleet (3 gliders traveling in formation)
        this.stampPattern("glider", c0, r0, sId, false, false);
        this.stampPattern("glider", c0 - 5, r0 + 4, (sId + 1) & 3, false, false);
        this.stampPattern("glider", c0 + 5, r0 - 4, (sId + 2) & 3, true, true);
      } else if (mode === 1) {
        // Lightweight spaceship (LWSS) moving across screen + Escort Glider
        this.stampPattern("lwss", c0, r0, sId, Math.random() < 0.5, false);
        this.stampPattern("glider", c0 + 7, r0 + 5, (sId + 1) & 3, false, false);
      } else if (mode === 2) {
        // R-Pentomino core (famous dynamic methuselah that naturally produces gliders)
        this.stampPattern("r_pentomino", c0, r0, sId, Math.random() < 0.5, Math.random() < 0.5);
      } else if (mode === 3) {
        // Medium spaceship (MWSS) + Cross Glider
        this.stampPattern("mwss", c0, r0, sId, Math.random() < 0.5, false);
        this.stampPattern("glider", c0 - 6, r0 - 5, (sId + 2) & 3, false, true);
      } else {
        // Kok's Galaxy oscillator + Outward Glider
        this.stampPattern("koks_galaxy", c0, r0, sId);
        this.stampPattern("glider", c0 + 8, r0 + 7, (sId + 3) & 3, false, false);
      }

      this.updateNeighborCounts();
      const px = (c0 + 0.5) * cw;
      const py = (r0 + 0.5) * ch;
      this.events.push({ kind: "divide", x: px, y: py });
      this.events.push({ kind: "splash", x: px, y: py });
    }

      this.updateNeighborCounts();
      const px = (c0 + 0.5) * cw;
      const py = (r0 + 0.5) * ch;
      this.events.push({ kind: "divide", x: px, y: py });
      this.events.push({ kind: "splash", x: px, y: py });
    }

    // Triggered when the user clicks/taps on a spot in the window!
    splash(x, y) {
      if (!this.cols || !this.rows) return;
      const c0 = clamp(Math.floor(x / this.cw), 0, this.cols - 1);
      const r0 = clamp(Math.floor(y / this.ch), 0, this.rows - 1);
      this.spawnColonyAtGrid(c0, r0);
    }

    updateNeighborCounts() {
      const { cols, rows, alive, neighbors } = this;
      for (let r = 0; r < rows; r++) {
        const rUp = ((r - 1 + rows) % rows) * cols;
        const rMid = r * cols;
        const rDn = ((r + 1) % rows) * cols;
        for (let c = 0; c < cols; c++) {
          const cL = (c - 1 + cols) % cols;
          const cR = (c + 1) % cols;
          neighbors[rMid + c] =
            alive[rUp + cL] + alive[rUp + c] + alive[rUp + cR] +
            alive[rMid + cL] +                 alive[rMid + cR] +
            alive[rDn + cL] + alive[rDn + c] + alive[rDn + cR];
        }
      }
    }

    // Conway's Game of Life laws:
    // Cells evolve according to their 8 neighbors:
    // - Underpopulation: < 2 neighbors dies
    // - Survival: 2 or 3 neighbors lives
    // - Overpopulation: > 3 neighbors dies
    // - Reproduction: exactly 3 neighbors creates a new living cell
    // Gliders and spaceships travel across empty space.
    // In shrink phase, parameters modulate gently and slowly to create a relaxed, gradual contraction.
    step(dt) {
      this.time += dt;
      const { cols, rows, alive, nextAlive, age, strain, fade, cellGrowth, cellTimer, neighbors, genInterval } = this;
      if (!cols || !rows) return;

      const n = cols * rows;
      const growSpeed = 1 / (genInterval * 0.48);
      const fadeSpeed = 1 / (genInterval * 0.75);
      const ghostDecay = Math.exp(-dt * 1.5);

      let liveTotal = 0;
      let births = 0;
      let activeMoving = 0;

      // Smooth 60 FPS continuous visual interpolation of cell sizes
      for (let i = 0; i < n; i++) {
        if (alive[i]) {
          cellGrowth[i] = Math.min(1.0, cellGrowth[i] + dt * growSpeed);
          liveTotal++;
          if (age[i] <= 4) activeMoving++;
        } else {
          cellGrowth[i] = Math.max(0.0, cellGrowth[i] - dt * fadeSpeed);
          if (fade[i] > 0.005) {
            fade[i] *= ghostDecay;
            if (fade[i] < 0.01) fade[i] = 0;
          }
        }
      }

      this.liveCount = liveTotal;
      const density = liveTotal / n;

      // ── PROGRESSIVE DENSITY OSCILLATION & PHASE INVERSION ──
      // When population expands to upper threshold, gently invert to "shrink"
      if (this.ecoPhase === "grow" && density >= this.maxDensityThreshold) {
        this.ecoPhase = "shrink";
      }
      // When population has contracted down very slowly and calmly, gently invert back to "grow"
      else if (this.ecoPhase === "shrink" && density <= this.minDensityThreshold) {
        this.ecoPhase = "grow";
        const spot = this.findOpenSpot();
        this.spawnColonyAtGrid(spot.c, spot.r);
      }

      // Parameters invert very gently during shrink phase
      // (Survival strictness 0.78 and birth 0.65 means population decreases very slowly and calmly)
      const isShrink = this.ecoPhase === "shrink";
      const survivalStrictness = isShrink ? 0.78 : 1.0;
      const birthProbability = isShrink ? 0.65 : 1.0;

      // Pre-calculate neighbor counts from current alive buffer
      for (let r = 0; r < rows; r++) {
        const rUp = ((r - 1 + rows) % rows) * cols;
        const rMid = r * cols;
        const rDn = ((r + 1) % rows) * cols;
        for (let c = 0; c < cols; c++) {
          const cL = (c - 1 + cols) % cols;
          const cR = (c + 1) % cols;
          neighbors[rMid + c] =
            alive[rUp + cL] + alive[rUp + c] + alive[rUp + cR] +
            alive[rMid + cL] +                 alive[rMid + cR] +
            alive[rDn + cL] + alive[rDn + c] + alive[rDn + cR];
        }
      }

      // Staggered clock evolution: each cell evaluates its Conway neighbor rule
      for (let i = 0; i < n; i++) {
        cellTimer[i] += dt;
        if (cellTimer[i] < genInterval) continue;
        cellTimer[i] -= genInterval;

        const count = neighbors[i];
        const wasAlive = alive[i];

        if (wasAlive) {
          let survives = false;
          if (count === 2) {
            survives = true;
          } else if (count === 3) {
            survives = !isShrink || hash3(i, Math.floor(this.time * 1.5), 19) < survivalStrictness;
          }

          if (survives) {
            nextAlive[i] = 1;
            age[i] = Math.min(60000, age[i] + 1);
            fade[i] = 1.0;
          } else {
            // Underpopulation (<2) or overpopulation (>3)
            nextAlive[i] = 0;
            age[i] = 0;
            fade[i] = 0.85;
          }
        } else {
          // Reproduction: exactly 3 living neighbors produces a cell!
          if (count === 3 && (!isShrink || hash3(i, Math.floor(this.time * 1.5), 31) < birthProbability)) {
            nextAlive[i] = 1;
            age[i] = 1;
            fade[i] = 1.0;
            births++;

            const c = i % cols;
            const r = (i / cols) | 0;
            const rUp = ((r - 1 + rows) % rows) * cols;
            const rMid = r * cols;
            const rDn = ((r + 1) % rows) * cols;
            const cL = (c - 1 + cols) % cols;
            const cR = (c + 1) % cols;
            const nbIdx = [
              rUp + cL, rUp + c, rUp + cR,
              rMid + cL,         rMid + cR,
              rDn + cL, rDn + c, rDn + cR,
            ];
            let s0 = -1, s1 = -1, s2 = -1;
            for (let k = 0; k < 8; k++) {
              const ni = nbIdx[k];
              if (alive[ni]) {
                if (s0 < 0) s0 = strain[ni];
                else if (s1 < 0) s1 = strain[ni];
                else { s2 = strain[ni]; break; }
              }
            }
            if (s0 === s1 || s0 === s2) strain[i] = s0 >= 0 ? s0 & 3 : 0;
            else if (s1 === s2 && s1 >= 0) strain[i] = s1 & 3;
            else strain[i] = Math.max(0, s0) & 3;
          } else {
            nextAlive[i] = 0;
          }
        }
      }

      // Synchronize buffer states
      for (let i = 0; i < n; i++) {
        alive[i] = nextAlive[i];
      }

      this.birthsLastStep = births;
      this.activeCount = activeMoving;

      // ── PERPETUAL ECOSYSTEM DIRECTOR ──
      // Prevents static locked blocks from freezing forever and keeps active gliders moving across space
      this.directorTimer += dt;
      if (this.directorTimer >= 1.4) {
        this.directorTimer = 0;
        this.generation++;
        const minEmergencyLive = Math.max(12, Math.round(n * 0.003));

        if (liveTotal < minEmergencyLive) {
          this.ecoPhase = "grow";
          this.seedEcosystem(false);
          this.stagnantSteps = 0;
          return;
        }

        // Dissolve or perturb very old immortal static blocks (still-lifes like 2x2 blocks or beehives)
        // so that isolated blocks do not sit idle forever on the workbench!
        for (let i = 0; i < n; i++) {
          if (alive[i] && age[i] > 32) {
            const h = hash3(i, this.generation, 43);
            if (isShrink ? h < 0.08 : h < 0.035) {
              // Gently dissolve static block
              alive[i] = 0;
              nextAlive[i] = 0;
              age[i] = 0;
              fade[i] = 0.45;
            } else if (h > 0.985 && density < this.maxDensityThreshold * 0.8) {
              // Perturb block into a moving glider
              const c = i % cols;
              const r = (i / cols) | 0;
              this.stampPattern("glider", c, r, (strain[i] + 1) & 3, Math.random() < 0.5, Math.random() < 0.5);
            }
          }
        }

        if (births < 3 || activeMoving < 10) {
          this.stagnantSteps++;
        } else {
          this.stagnantSteps = Math.max(0, this.stagnantSteps - 1);
        }

        // If the window gets quiet or empty in one area, launch a moving glider across open space
        if (this.ecoPhase === "grow" && (this.stagnantSteps >= 5 || (this.generation % 20 === 0 && activeMoving < 18)) && density < this.maxDensityThreshold * 0.7) {
          this.stagnantSteps = 0;
          const spot = this.findOpenSpot();
          this.stampPattern("glider", spot.c, spot.r, (this.nextStrainCycle++) & 3, Math.random() < 0.5, Math.random() < 0.5);
        }
      }
    }
  }

  class BacteriaRenderer extends BaseAsciiRenderer {
    constructor(canvas) {
      super(canvas, LIFE_STRAINS, LIFE_TINTS);
      this.ambientGlyph = "·";
    }

    resize(width, height, dpr) {
      const prevCols = this.cols;
      const prevRows = this.rows;
      this.width = width;
      this.height = height;
      this.dpr = dpr;
      // Slightly squarer ASCII grid cells so Pulsars, Galaxies, and Gliders have balanced geometry
      this.cw = clamp(Math.round(width / 112), 10, 14);
      this.ch = Math.round(this.cw * 1.18);
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

    render(world, dt) {
      const { ctx, dpr, cols, ch } = this;
      if (cols === 0) return;
      const t = world.time;

      this.consumeEvents(world);
      this.rasterizeLife(world, t);
      this.depositWake(world);
      this.diffuse(dt);

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(this.bg, 0, 0);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      this.markAmbient(world.ambientNodes);
      this.drawDots();

      ctx.font = `600 ${Math.round(ch * 0.74)}px ${this.fontFamily}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      this.drawHeat();
      this.drawAmbient(["·", "+"]);
      this.drawLifeCells(world, t);
    }

    depositWake(world) {
      const { energy } = this;
      const { alive, age } = world;
      const n = Math.min(energy.length, alive.length);
      for (let i = 0; i < n; i++) {
        if (alive[i] && age[i] === 1) {
          // Newly born cells emit a soft wake into the diffusion field
          energy[i] = Math.min(1.3, energy[i] + 0.045);
        }
      }
    }

    rasterizeLife(world, t) {
      const { cellFlag, cellShade, cellKey, cellDepth, cellKind, cols, rows } = this;
      const { alive, age, strain, fade, neighbors } = world;
      cellFlag.fill(0);

      const n = Math.min(cols * rows, alive.length);
      for (let i = 0; i < n; i++) {
        const c = i % cols;
        const r = (i / cols) | 0;
        const sId = strain[i] & 3;
        cellKind[i] = sId;
        cellKey[i] = (hash3(c, r, sId + 11) * 4294967295) >>> 0;

        if (alive[i]) {
          const a = age[i];
          const nb = neighbors[i];
          cellDepth[i] = a <= 4 ? 1.0 : 0.86;
          if (a === 1) {
            cellFlag[i] = FLAG_RIDGE; // Newly born cell
            cellShade[i] = 0.92;
          } else if (a <= 5) {
            cellFlag[i] = FLAG_BODY; // Active glider / oscillator / expanding wave
            cellShade[i] = clamp(0.58 + nb * 0.07, 0.35, 0.95);
          } else {
            cellFlag[i] = FLAG_FIN; // Mature still-life / gun structure
            cellShade[i] = clamp(0.38 + nb * 0.06, 0.25, 0.78);
          }
        } else if (fade[i] > 0.08) {
          // Ghost trail of recently died cell
          cellFlag[i] = FLAG_EDGE;
          cellShade[i] = fade[i];
          cellDepth[i] = 0.75;
        }
      }
    }

    drawLifeCells(world, t) {
      const {
        ctx,
        cols,
        rows,
        cw,
        ch,
        cellFlag,
        cellShade,
        cellKey,
        cellKind,
        kinds,
        tints,
      } = this;
      const n = cols * rows;
      const tick = Math.floor(t * 0.9);

      for (let i = 0; i < n; i++) {
        const flag = cellFlag[i];
        if (!flag) continue;

        const col = i % cols;
        const row = (i / cols) | 0;
        const x = col * cw;
        const y = row * ch;
        const key = cellKey[i];
        const shade = cellShade[i];
        const kindName = kinds[cellKind[i]] || kinds[0];
        const [tr, tg, tb] = tints[kindName] || [0.54, 0.65, 0.84];

        if (flag === FLAG_EDGE) {
          // Soft fading ghost trail left behind moving gliders & oscillators
          const alpha = clamp(shade * 0.42, 0.05, 0.34);
          const rr = clamp(Math.round(244 - (1 - tr) * 85), 140, 242);
          const gg = clamp(Math.round(246 - (1 - tg) * 85), 145, 244);
          const bb = clamp(Math.round(250 - (1 - tb) * 85), 150, 248);
          ctx.fillStyle = `rgba(${rr}, ${gg}, ${bb}, ${(alpha * 0.65).toFixed(3)})`;
          ctx.fillRect(x + 1, y + 1, cw - 1, ch - 1);

          const gIdx = clamp(Math.floor((1 - shade) * LIFE_GHOST_GLYPHS.length), 0, LIFE_GHOST_GLYPHS.length - 1);
          ctx.fillStyle = `rgba(100, 116, 139, ${(alpha * 1.35).toFixed(3)})`;
          ctx.fillText(LIFE_GHOST_GLYPHS[gIdx], x + cw / 2, y + ch / 2 + 1);
          continue;
        }

        let r, g, b, glyph, glyphColor;
        const roll = hash3(key, tick, 13);

        if (flag === FLAG_RIDGE) {
          // Newly born cell (age === 1): vivid tinted slate block + bright crisp glyph
          r = clamp(Math.round(236 - (1 - tr) * 195), 75, 225);
          g = clamp(Math.round(238 - (1 - tg) * 195), 80, 228);
          b = clamp(Math.round(244 - (1 - tb) * 195), 90, 236);
          glyph = LIFE_BIRTH_GLYPHS[(key >>> 6) % LIFE_BIRTH_GLYPHS.length];
          glyphColor = "#ffffff";
        } else if (flag === FLAG_BODY) {
          // Active young cell (age 2..5: gliders, spaceships, oscillators)
          const depth = 165 + shade * 45;
          r = clamp(Math.round(242 - (1 - tr) * depth), 85, 228);
          g = clamp(Math.round(244 - (1 - tg) * depth), 90, 230);
          b = clamp(Math.round(248 - (1 - tb) * depth), 95, 238);
          glyph = LIFE_ACTIVE_GLYPHS[(key >>> 5) % LIFE_ACTIVE_GLYPHS.length];
          glyphColor = roll < 0.14 ? "#ffffff" : "#1e293b";
        } else {
          // Mature stable cell (age > 5: blocks, beehives, glider gun stations)
          const depth = 115 + shade * 40;
          r = clamp(Math.round(245 - (1 - tr) * depth), 135, 234);
          g = clamp(Math.round(246 - (1 - tg) * depth), 140, 236);
          b = clamp(Math.round(250 - (1 - tb) * depth), 148, 242);
          glyph = LIFE_MATURE_GLYPHS[(key >>> 4) % LIFE_MATURE_GLYPHS.length];
          glyphColor = "#334155";
        }

        const growth = world.cellGrowth ? world.cellGrowth[i] : 1.0;
        if (growth < 0.04) continue;

        const curW = Math.max(2, (cw - 1) * growth);
        const curH = Math.max(2, (ch - 1) * growth);
        const padX = (cw - 1 - curW) * 0.5;
        const padY = (ch - 1 - curH) * 0.5;

        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.fillRect(x + 1 + padX, y + 1 + padY, curW, curH);

        if (growth > 0.38) {
          ctx.save();
          ctx.globalAlpha = clamp((growth - 0.38) / 0.62, 0, 1);
          ctx.fillStyle = glyphColor;
          ctx.fillText(glyph, x + cw / 2, y + ch / 2 + 1);
          ctx.restore();
        }
      }
    }
  }

  class BacteriaEngine extends BaseLoopEngine {
    constructor(canvas, specs) {
      const world = new BacteriaWorld(specs);
      const renderer = new BacteriaRenderer(canvas);
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
  // 4. PERMANENT SEA WAVES ENGINE ("waves" / "sea_waves")
  //    Gentle, perpetual ocean swell rolling fluently from top to bottom (up -> down).
  //    Features multi-harmonic lateral distortion along the X axis so waves are
  //    not straight or identical across X, but curve, undulate, ebb, and swell
  //    organically across the sea surface. Pure monochrome/gray-slate ASCII styling.
  // ═══════════════════════════════════════════════════════════════════════════

  const SEA_PALETTES = ["ocean_slate", "mist_slate", "deep_slate", "foam_slate"];
  const SEA_TINTS = {
    ocean_slate: [0.92, 0.95, 0.99], // Clean neutral slate-sea tint
    mist_slate:  [0.90, 0.94, 0.98], // Soft sea-mist tint
    deep_slate:  [0.88, 0.92, 0.97], // Deep ocean swell tint
    foam_slate:  [0.95, 0.96, 1.00], // Crisp crest foam tint
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

      // Advance ripples
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
            // ── PEAK ROLLING WAVE CREST & FOAM ──
            const crestNorm = clamp((elev - 0.74) / 0.26, 0, 1);
            // Soft slate-gray crest block fading into #fafbfe at edges
            const lum = 246 - Math.round(crestNorm * 68); // ~178 (slate) to 246
            ctx.fillStyle = `rgb(${lum - 4}, ${lum}, ${lum + 8})`;
            ctx.fillRect(px + 1, py + 1, cw - 1, ch - 1);

            let glyph;
            let glyphColor;
            if (crestNorm > 0.55) {
              glyph = SEA_CREST_GLYPHS[(key >>> 5) % SEA_CREST_GLYPHS.length];
              glyphColor = crestNorm > 0.82 ? "#f8fafc" : "#1e293b";
            } else {
              glyph = SEA_FACE_GLYPHS[(key >>> 4) % SEA_FACE_GLYPHS.length];
              glyphColor = "#334155";
            }

            ctx.fillStyle = glyphColor;
            ctx.fillText(glyph, px + cw / 2, py + ch / 2 + 1);
          } else if (elev > 0.36) {
            // ── SLOPING WAVE FACE (Gentle undulating slate glyphs) ──
            const slopeNorm = (elev - 0.36) / 0.34;
            const alpha = clamp(0.22 + slopeNorm * 0.48, 0.20, 0.70);
            ctx.fillStyle = `rgba(51, 65, 85, ${alpha.toFixed(3)})`;
            const glyph = SEA_FACE_GLYPHS[((key >>> 3) + tick) % SEA_FACE_GLYPHS.length];
            ctx.fillText(glyph, px + cw / 2, py + ch / 2 + 1);
          } else {
            // ── TRANQUIL DEEP TROUGH (Subtle resting water specks) ──
            if (((c + r) & 1) === 0) {
              const shimmer = 0.16 + 0.08 * Math.sin(t * 0.7 + (key % 23));
              ctx.fillStyle = `rgba(100, 116, 139, ${shimmer.toFixed(3)})`;
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
        // Foam specks glow brighter as they ride along the crests
        const alpha = clamp(0.35 + elev * 0.55, 0.30, 0.90);
        ctx.fillStyle = `rgba(30, 41, 59, ${alpha.toFixed(3)})`;
        const glyph = elev > 0.65 ? "*" : "·";
        ctx.fillText(glyph, f.x, f.y);
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
  window.BacteriaEngine = BacteriaEngine;
  window.MantaEngine = MantaEngine;
  window.SeaWaveEngine = SeaWaveEngine;
  window.SoundWaveEngine = SoundWaveEngine;

  const THEME_CREDITS = {
    sharks: "ASCII Sharks by stackedlol",
    jellyfish: "ASCII Jellyfish • Inspired by stackedlol",
    bacteria: "ASCII Game of Life • John Horton Conway (1970)",
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
      themeName === "game_of_life"
        ? "bacteria"
        : themeName === "sound_waves" || themeName === "sea_waves"
        ? "waves"
        : themeName;
    const normalized = [
      "sharks",
      "jellyfish",
      "bacteria",
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
    if (normalized === "jellyfish") {
      activeEngine = new JellyfishEngine(canvas);
    } else if (normalized === "bacteria") {
      activeEngine = new BacteriaEngine(canvas);
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

    const creditSpan = document.querySelector(".repo-credit span");
    if (creditSpan && THEME_CREDITS[normalized]) {
      creditSpan.textContent = THEME_CREDITS[normalized];
    }
  };

  window.getBackgroundTheme = function () {
    return activeThemeName || "sharks";
  };
})();
