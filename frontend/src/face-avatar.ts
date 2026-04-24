/**
 * PHOEBUS — Face Avatar.
 *
 * Portrait animé synchronisé avec le backend via WebSocket, composé de
 * plusieurs couches de motion pour donner l'impression d'un visage vivant :
 *   - respiration continue (scale sinusoïdal)
 *   - saccades aléatoires (micro-translations type mouvement oculaire)
 *   - head-bobble pendant la parole (rotation ±0.6°)
 *   - pulse d'échelle corrélé au volume pendant la parole
 *   - parallaxe souris avec légère inclinaison 3D (perspective)
 *   - reflet lumineux qui orbite en synchronisation avec l'aura du halo
 *   - particules qui voyagent de l'anneau neural vers la bouche en speaking
 *
 * Signaux consommés :
 *   setState()    — idle | listening | thinking | speaking
 *   setVolume(v)  — 0..1, piloté par le backend pendant la TTS
 */

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

export interface FaceAvatar {
  setState(s: AvatarState): void;
  setVolume(v: number): void;
  destroy(): void;
}

// ── Assets ─────────────────────────────────────────────────────────────────

const ASSETS_PATH = "/phoebus-face";

const FRAMES = {
  base: `${ASSETS_PATH}/base-neutral.png`,
  thinking: `${ASSETS_PATH}/expr-thinking.png`,
  attentive: `${ASSETS_PATH}/expr-attentive.png`,
  smile: `${ASSETS_PATH}/expr-smile.png`,
  mouth0: `${ASSETS_PATH}/mouth-00-closed.png`,
  mouth1: `${ASSETS_PATH}/mouth-01-slightly.png`,
  mouth2: `${ASSETS_PATH}/mouth-02-oh.png`,
  mouth3: `${ASSETS_PATH}/mouth-03-wide.png`,
  eyesClosed: `${ASSETS_PATH}/eyes-closed.png`,
} as const;

type FrameKey = keyof typeof FRAMES;

// Couleurs d'aura par état, en rgb() — alignées sur les valeurs CSS
// --aura-core de style.css pour que particules et halo aient le même ton.
const AURA_COLOR_BY_STATE: Record<AvatarState, string> = {
  idle: "76, 168, 232",
  listening: "34, 197, 94",
  thinking: "139, 92, 246",
  speaking: "251, 191, 36",
};

// ── Réglages ───────────────────────────────────────────────────────────────

const MOUTH_MIN_FRAME_MS = 80;
const VOLUME_SMOOTHING = 0.35;

const BLINK_DURATION_MS = 130;
const BLINK_MIN_INTERVAL_MS = 3000;
const BLINK_MAX_INTERVAL_MS = 6500;
const BLINK_THINKING_FACTOR = 0.5;

const SACCADE_MIN_INTERVAL_MS = 1400;
const SACCADE_MAX_INTERVAL_MS = 3800;
const SACCADE_AMPLITUDE_PX = 4;
const SACCADE_DURATION_MS = 180;

const BREATH_PERIOD_MS = 4200;
const BREATH_AMPLITUDE = 0.006;

const BOBBLE_PERIOD_MS = 1500;
const BOBBLE_AMPLITUDE_DEG = 0.6;

// Parallaxe souris : amplitude max et lissage.
const PARALLAX_AMOUNT_PX = 14;
const TILT_AMOUNT_DEG = 4.5;
const PARALLAX_LERP = 0.09; // interpolation par frame vers la cible

// Aura : même période que la CSS (18 s) pour que la lumière du reflet
// suive visiblement la zone la plus brillante du conic-gradient.
const AURA_PERIOD_MS = 18000;

// Particules parole → bouche.
const PARTICLE_POOL_SIZE = 56;
const PARTICLE_SPAWN_BASE_MS = 160; // intervalle au repos vocal
const PARTICLE_SPAWN_MIN_MS = 45;   // intervalle au pic vocal
const PARTICLE_LIFETIME_MIN_MS = 650;
const PARTICLE_LIFETIME_MAX_MS = 1150;

// Accessibilité : on dégrade fort si l'utilisateur a demandé
// "prefers-reduced-motion".
const REDUCED_MOTION =
  typeof window !== "undefined" &&
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ── Utilitaires ────────────────────────────────────────────────────────────

function preload(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(img);
    img.src = src;
  });
}

function randInt(min: number, max: number): number {
  return Math.floor(min + Math.random() * (max - min));
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function mouthFrameForVolume(v: number): FrameKey {
  if (v < 0.14) return "mouth0";
  if (v < 0.38) return "mouth1";
  if (v < 0.68) return "mouth2";
  return "mouth3";
}

// ── Particules ─────────────────────────────────────────────────────────────

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  targetX: number;
  targetY: number;
  lifetime: number;
  born: number;
  size: number;
  active: boolean;
}

function makeParticlePool(): Particle[] {
  const pool: Particle[] = [];
  for (let i = 0; i < PARTICLE_POOL_SIZE; i++) {
    pool.push({
      x: 0, y: 0, vx: 0, vy: 0,
      targetX: 0, targetY: 0,
      lifetime: 0, born: 0, size: 0,
      active: false,
    });
  }
  return pool;
}

// ── Création ───────────────────────────────────────────────────────────────

export function createFaceAvatar(container: HTMLElement): FaceAvatar {
  // ── DOM ─────────────────────────────────────────────────────────────────
  const wrap = document.createElement("div");
  wrap.className = "face-avatar";
  wrap.dataset.state = "idle";
  container.appendChild(wrap);

  const aura = document.createElement("div");
  aura.className = "face-aura";
  wrap.appendChild(aura);

  const layerBottom = document.createElement("img");
  const layerTop = document.createElement("img");
  layerBottom.className = "face-layer face-layer-bottom";
  layerTop.className = "face-layer face-layer-top";
  layerBottom.draggable = false;
  layerTop.draggable = false;
  layerBottom.alt = "";
  layerTop.alt = "";
  wrap.appendChild(layerBottom);
  wrap.appendChild(layerTop);

  // Reflet rim-light qui orbite au-dessus du portrait.
  const highlight = document.createElement("div");
  highlight.className = "face-highlight";
  wrap.appendChild(highlight);

  // Canvas pour les particules parole → bouche.
  const particleCanvas = document.createElement("canvas");
  particleCanvas.className = "face-particles";
  wrap.appendChild(particleCanvas);
  const pctx = particleCanvas.getContext("2d");

  // ── Préchargement ──────────────────────────────────────────────────────
  const available: Partial<Record<FrameKey, boolean>> = {};
  const loadPromises: Promise<void>[] = [];
  (Object.keys(FRAMES) as FrameKey[]).forEach((key) => {
    const p = preload(FRAMES[key]).then((img) => {
      available[key] = img.complete && img.naturalWidth > 0;
    });
    loadPromises.push(p);
  });

  function resolveFrame(key: FrameKey): string {
    if (available[key]) return FRAMES[key];
    return FRAMES.base;
  }

  // ── État interne ─────────────────────────────────────────────────────────
  let currentState: AvatarState = "idle";
  let smoothedVolume = 0;
  let currentMouthKey: FrameKey = "mouth0";
  let lastMouthChange = 0;
  let blinking = false;
  let blinkTimer: ReturnType<typeof setTimeout> | null = null;
  let saccadeTimer: ReturnType<typeof setTimeout> | null = null;
  let saccadeX = 0;
  let saccadeY = 0;
  let saccadeTargetX = 0;
  let saccadeTargetY = 0;
  let saccadeStart = 0;
  let rafHandle = 0;
  let destroyed = false;

  // Parallaxe souris
  let mouseNormX = 0; // -1..+1
  let mouseNormY = 0;
  let parallaxX = 0;
  let parallaxY = 0;
  let tiltX = 0;
  let tiltY = 0;

  // Particules
  const particles = makeParticlePool();
  let lastParticleSpawn = 0;
  let cachedRect: DOMRect | null = null;
  let dpr = Math.max(1, window.devicePixelRatio || 1);

  function restFrameForState(s: AvatarState): FrameKey {
    switch (s) {
      case "thinking":
        return available.thinking ? "thinking" : "base";
      case "listening":
        return available.attentive ? "attentive" : "base";
      case "speaking":
      case "idle":
      default:
        return "base";
    }
  }

  function render(): void {
    if (destroyed) return;

    const restSrc = resolveFrame(restFrameForState(currentState));
    if (!layerBottom.src.endsWith(restSrc)) {
      layerBottom.src = restSrc;
    }

    if (blinking && available.eyesClosed) {
      layerTop.src = FRAMES.eyesClosed;
      layerTop.style.opacity = "1";
      return;
    }

    if (currentState === "speaking") {
      const src = resolveFrame(currentMouthKey);
      if (!layerTop.src.endsWith(src)) {
        layerTop.src = src;
      }
      layerTop.style.opacity = "1";
      return;
    }

    layerTop.style.opacity = "0";
  }

  // ── Canvas sizing ───────────────────────────────────────────────────────
  function resizeCanvas(): void {
    if (!pctx) return;
    const rect = wrap.getBoundingClientRect();
    cachedRect = rect;
    const w = Math.max(1, Math.floor(rect.width * dpr));
    const h = Math.max(1, Math.floor(rect.height * dpr));
    if (particleCanvas.width !== w) particleCanvas.width = w;
    if (particleCanvas.height !== h) particleCanvas.height = h;
    pctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  const resizeObs = new ResizeObserver(resizeCanvas);
  resizeObs.observe(wrap);
  resizeCanvas();

  // ── Mouse parallax ──────────────────────────────────────────────────────
  function onMouseMove(e: MouseEvent): void {
    const cx = window.innerWidth / 2;
    const cy = window.innerHeight / 2;
    mouseNormX = Math.max(-1, Math.min(1, (e.clientX - cx) / cx));
    mouseNormY = Math.max(-1, Math.min(1, (e.clientY - cy) / cy));
  }
  if (!REDUCED_MOTION) {
    window.addEventListener("mousemove", onMouseMove, { passive: true });
  }

  // ── Boucle d'animation (60 Hz) ──────────────────────────────────────────
  const startTs = performance.now();

  function animate(now: number): void {
    if (destroyed) return;
    const t = now - startTs;

    // ── Respiration + bobble + pulse échelle ──────────────────────────────
    const breath = REDUCED_MOTION
      ? 1
      : 1 + Math.sin((t / BREATH_PERIOD_MS) * Math.PI * 2) * BREATH_AMPLITUDE;

    let bobble = 0;
    if (currentState === "speaking" && !REDUCED_MOTION) {
      const activity = Math.max(0.15, smoothedVolume);
      bobble =
        Math.sin((t / BOBBLE_PERIOD_MS) * Math.PI * 2) *
        BOBBLE_AMPLITUDE_DEG *
        activity;
    }

    const speakPulse =
      currentState === "speaking" ? 1 + smoothedVolume * 0.018 : 1;

    // ── Saccades ──────────────────────────────────────────────────────────
    if (saccadeStart > 0 && !REDUCED_MOTION) {
      const p = Math.min(1, (now - saccadeStart) / SACCADE_DURATION_MS);
      const eased = 1 - Math.pow(1 - p, 3);
      saccadeX = saccadeX * (1 - eased) + saccadeTargetX * eased;
      saccadeY = saccadeY * (1 - eased) + saccadeTargetY * eased;
      if (p >= 1) saccadeStart = 0;
    }

    // ── Parallaxe souris (lerp vers la cible) ─────────────────────────────
    if (!REDUCED_MOTION) {
      parallaxX = lerp(parallaxX, mouseNormX * PARALLAX_AMOUNT_PX, PARALLAX_LERP);
      parallaxY = lerp(parallaxY, mouseNormY * PARALLAX_AMOUNT_PX, PARALLAX_LERP);
      // Inclinaison 3D : "tilt toward" — la tête penche vers le curseur.
      tiltX = lerp(tiltX, mouseNormX * TILT_AMOUNT_DEG, PARALLAX_LERP);
      tiltY = lerp(tiltY, -mouseNormY * TILT_AMOUNT_DEG, PARALLAX_LERP);
    }

    const totalX = saccadeX + parallaxX;
    const totalY = saccadeY + parallaxY;
    const scale = breath * speakPulse;

    wrap.style.transform =
      `translate(calc(-50% + ${totalX.toFixed(2)}px), calc(-50% + ${totalY.toFixed(2)}px)) ` +
      `rotateX(${tiltY.toFixed(2)}deg) rotateY(${tiltX.toFixed(2)}deg) ` +
      `scale(${scale.toFixed(4)}) rotate(${bobble.toFixed(2)}deg)`;

    // ── Volume + activity exposés aux CSS variables ───────────────────────
    const activityLevel =
      currentState === "speaking"
        ? smoothedVolume
        : currentState === "thinking"
          ? 0.35
          : currentState === "listening"
            ? 0.25
            : 0.12;
    wrap.style.setProperty("--vol", smoothedVolume.toFixed(3));
    wrap.style.setProperty("--activity", activityLevel.toFixed(3));

    // ── Reflet lumineux : position sur un cercle, même phase que l'aura ──
    const auraAngle = (t / AURA_PERIOD_MS) * Math.PI * 2;
    const hlX = 50 + Math.cos(auraAngle) * 34;
    const hlY = 50 + Math.sin(auraAngle) * 34;
    const hlIntensity = 0.15 + activityLevel * 0.55;
    wrap.style.setProperty("--hl-x", `${hlX.toFixed(1)}%`);
    wrap.style.setProperty("--hl-y", `${hlY.toFixed(1)}%`);
    wrap.style.setProperty("--hl-intensity", hlIntensity.toFixed(3));

    // ── Particules ────────────────────────────────────────────────────────
    updateParticles(now);
    drawParticles(now);

    rafHandle = requestAnimationFrame(animate);
  }

  // ── Particules : spawn, update, draw ────────────────────────────────────
  function spawnParticleIfDue(now: number): void {
    if (currentState !== "speaking") return;
    if (!cachedRect) return;

    // Cadence modulée par le volume : plus c'est fort, plus c'est dense.
    const interval = lerp(
      PARTICLE_SPAWN_BASE_MS,
      PARTICLE_SPAWN_MIN_MS,
      Math.min(1, smoothedVolume * 1.6),
    );
    if (now - lastParticleSpawn < interval) return;

    // Trouve un slot libre.
    let slot: Particle | null = null;
    for (let i = 0; i < particles.length; i++) {
      if (!particles[i].active) {
        slot = particles[i];
        break;
      }
    }
    if (!slot) return;

    const w = cachedRect.width;
    const h = cachedRect.height;
    const cx = w / 2;
    const cy = h / 2;

    // Naissance : sur un cercle situé à la couronne neurale (hors du visage).
    const angle = Math.random() * Math.PI * 2;
    const startRadius = Math.min(w, h) * 0.55;
    slot.x = cx + Math.cos(angle) * startRadius;
    slot.y = cy + Math.sin(angle) * startRadius;

    // Cible : zone bouche (~68 % de la hauteur) avec léger jitter.
    slot.targetX = cx + (Math.random() - 0.5) * w * 0.08;
    slot.targetY = h * 0.68 + (Math.random() - 0.5) * h * 0.04;

    // Vitesse initiale dirigée vers la cible.
    const dx = slot.targetX - slot.x;
    const dy = slot.targetY - slot.y;
    const len = Math.max(1, Math.hypot(dx, dy));
    const speed = 1.2 + Math.random() * 1.8;
    slot.vx = (dx / len) * speed;
    slot.vy = (dy / len) * speed;

    slot.lifetime = PARTICLE_LIFETIME_MIN_MS +
      Math.random() * (PARTICLE_LIFETIME_MAX_MS - PARTICLE_LIFETIME_MIN_MS);
    slot.born = now;
    slot.size = 1.3 + Math.random() * 2.1;
    slot.active = true;

    lastParticleSpawn = now;
  }

  function updateParticles(now: number): void {
    spawnParticleIfDue(now);

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      if (!p.active) continue;

      const age = now - p.born;
      if (age >= p.lifetime) {
        p.active = false;
        continue;
      }

      const dx = p.targetX - p.x;
      const dy = p.targetY - p.y;
      const len = Math.hypot(dx, dy);
      if (len < 3) {
        p.active = false;
        continue;
      }

      // Attraction + damping (Euler simple).
      const pull = 0.07;
      p.vx += (dx / len) * pull;
      p.vy += (dy / len) * pull;
      p.vx *= 0.93;
      p.vy *= 0.93;
      p.x += p.vx;
      p.y += p.vy;
    }
  }

  function drawParticles(now: number): void {
    if (!pctx || !cachedRect) return;
    pctx.clearRect(0, 0, cachedRect.width, cachedRect.height);

    if (currentState !== "speaking") return;

    const baseColor = AURA_COLOR_BY_STATE[currentState];
    pctx.globalCompositeOperation = "screen";

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      if (!p.active) continue;

      const age = now - p.born;
      const lifePct = age / p.lifetime; // 0..1
      // Enveloppe d'intensité : fade in rapide, plateau, fade out doux.
      const alpha =
        lifePct < 0.15
          ? (lifePct / 0.15) * 0.85
          : (1 - lifePct) * 0.85;

      pctx.shadowColor = `rgba(${baseColor}, ${alpha.toFixed(3)})`;
      pctx.shadowBlur = p.size * 4;
      pctx.fillStyle = `rgba(${baseColor}, ${alpha.toFixed(3)})`;
      pctx.beginPath();
      pctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      pctx.fill();
    }
    pctx.shadowBlur = 0;
    pctx.globalCompositeOperation = "source-over";
  }

  // ── Saccades programmées ────────────────────────────────────────────────
  function scheduleSaccade(): void {
    if (destroyed || REDUCED_MOTION) return;
    const delay = randInt(SACCADE_MIN_INTERVAL_MS, SACCADE_MAX_INTERVAL_MS);
    saccadeTimer = setTimeout(() => {
      if (destroyed) return;
      const amplitude =
        currentState === "speaking"
          ? SACCADE_AMPLITUDE_PX * 0.4
          : SACCADE_AMPLITUDE_PX;
      saccadeTargetX = (Math.random() - 0.5) * 2 * amplitude;
      saccadeTargetY = (Math.random() - 0.5) * 2 * amplitude;
      saccadeStart = performance.now();
      scheduleSaccade();
    }, delay);
  }

  // ── Clignements ─────────────────────────────────────────────────────────
  function scheduleNextBlink(): void {
    if (destroyed) return;
    const factor = currentState === "thinking" ? BLINK_THINKING_FACTOR : 1;
    const delay = Math.floor(
      randInt(BLINK_MIN_INTERVAL_MS, BLINK_MAX_INTERVAL_MS) * factor,
    );
    blinkTimer = setTimeout(() => {
      if (destroyed) return;
      blinking = true;
      render();
      setTimeout(() => {
        blinking = false;
        render();
        scheduleNextBlink();
      }, BLINK_DURATION_MS);
    }, delay);
  }

  // ── API publique ─────────────────────────────────────────────────────────
  const api: FaceAvatar = {
    setState(s) {
      if (currentState === s) return;
      currentState = s;
      wrap.dataset.state = s;
      if (s !== "speaking") {
        smoothedVolume = 0;
        currentMouthKey = "mouth0";
      }
      render();
    },

    setVolume(v) {
      const clamped = Math.max(0, Math.min(1, v));
      smoothedVolume =
        smoothedVolume * (1 - VOLUME_SMOOTHING) + clamped * VOLUME_SMOOTHING;

      if (currentState !== "speaking") return;

      const now = performance.now();
      if (now - lastMouthChange < MOUTH_MIN_FRAME_MS) return;

      const newKey = mouthFrameForVolume(smoothedVolume);
      if (newKey !== currentMouthKey) {
        currentMouthKey = newKey;
        lastMouthChange = now;
        render();
      }
    },

    destroy() {
      destroyed = true;
      if (blinkTimer) clearTimeout(blinkTimer);
      if (saccadeTimer) clearTimeout(saccadeTimer);
      if (rafHandle) cancelAnimationFrame(rafHandle);
      window.removeEventListener("mousemove", onMouseMove);
      resizeObs.disconnect();
      wrap.remove();
    },
  };

  // ── Démarrage ────────────────────────────────────────────────────────────
  Promise.all(loadPromises).then(() => {
    if (destroyed) return;
    render();
    scheduleNextBlink();
    scheduleSaccade();
    rafHandle = requestAnimationFrame(animate);
  });

  return api;
}
