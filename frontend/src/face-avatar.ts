/**
 * JARVIS — Face Avatar.
 *
 * Portrait animé à partir de PNG en niveaux de gris, synchronisé avec le
 * backend via WebSocket. Motion layers pour donner l'impression d'un visage
 * vivant :
 *   - respiration continue (léger scale sinusoïdal)
 *   - saccades aléatoires (micro-translations type mouvement oculaire)
 *   - head-bobble pendant la parole (rotation de ±0.6°)
 *   - pulse d'échelle corrélé au volume pendant la parole
 *   - halo multicouche coloré par état, volume-réactif
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

const ASSETS_PATH = "/jarvis-face";

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

// ── Réglages ───────────────────────────────────────────────────────────────

// Cadence maximale de changement de bouche (Hz équivalent : ~12).
const MOUTH_MIN_FRAME_MS = 80;
// Lissage exponentiel du volume pour éviter la vibration de lèvre.
const VOLUME_SMOOTHING = 0.35;

// Blinks : durée humaine ~130 ms, intervalle 3–6.5 s (raccourci quand thinking).
const BLINK_DURATION_MS = 130;
const BLINK_MIN_INTERVAL_MS = 3000;
const BLINK_MAX_INTERVAL_MS = 6500;
const BLINK_THINKING_FACTOR = 0.5; // clignements 2× plus fréquents en reflexion

// Saccades oculaires (on simule par un micro-shift du visage entier,
// puisqu'on n'a pas de calque "yeux" séparé).
const SACCADE_MIN_INTERVAL_MS = 1400;
const SACCADE_MAX_INTERVAL_MS = 3800;
const SACCADE_AMPLITUDE_PX = 4;
const SACCADE_DURATION_MS = 180;

// Respiration continue : cycle lent, amplitude ~0.6% d'échelle.
const BREATH_PERIOD_MS = 4200;
const BREATH_AMPLITUDE = 0.006;

// Head-bobble pendant la parole : petite rotation oscillatoire.
const BOBBLE_PERIOD_MS = 1500;
const BOBBLE_AMPLITUDE_DEG = 0.6;

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

function mouthFrameForVolume(v: number): FrameKey {
  if (v < 0.14) return "mouth0";
  if (v < 0.38) return "mouth1";
  if (v < 0.68) return "mouth2";
  return "mouth3";
}

// ── Création ───────────────────────────────────────────────────────────────

export function createFaceAvatar(container: HTMLElement): FaceAvatar {
  // Wrapper principal + halo layers
  const wrap = document.createElement("div");
  wrap.className = "face-avatar";
  wrap.dataset.state = "idle";
  container.appendChild(wrap);

  // Couche d'aura tournante (conic gradient animé en CSS).
  const aura = document.createElement("div");
  aura.className = "face-aura";
  wrap.appendChild(aura);

  // Deux couches image : base (expression, cross-fade doux) et top (bouche/blink, coupure franche).
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

  // ── Préchargement / disponibilité des frames ─────────────────────────────
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

  // ── Boucle d'animation (respiration, bobble, saccades, halo) ───────────
  const startTs = performance.now();
  function animate(now: number): void {
    if (destroyed) return;
    const t = now - startTs;

    // Respiration : scale sinusoïdal doux, toujours actif.
    const breath =
      1 + Math.sin((t / BREATH_PERIOD_MS) * Math.PI * 2) * BREATH_AMPLITUDE;

    // Head-bobble pendant la parole, modulé par le volume.
    let bobble = 0;
    if (currentState === "speaking") {
      const activity = Math.max(0.15, smoothedVolume);
      bobble =
        Math.sin((t / BOBBLE_PERIOD_MS) * Math.PI * 2) *
        BOBBLE_AMPLITUDE_DEG *
        activity;
    }

    // Pulse d'échelle fine corrélé au volume pendant la parole.
    const speakPulse =
      currentState === "speaking" ? 1 + smoothedVolume * 0.018 : 1;

    // Saccade : interpolation vers la cible sur SACCADE_DURATION_MS.
    if (saccadeStart > 0) {
      const p = Math.min(1, (now - saccadeStart) / SACCADE_DURATION_MS);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - p, 3);
      saccadeX = saccadeX * (1 - eased) + saccadeTargetX * eased;
      saccadeY = saccadeY * (1 - eased) + saccadeTargetY * eased;
      if (p >= 1) saccadeStart = 0;
    }

    const scale = breath * speakPulse;
    wrap.style.transform = `translate(calc(-50% + ${saccadeX}px), calc(-50% + ${saccadeY}px)) scale(${scale}) rotate(${bobble}deg)`;

    // Halo : on expose volume + activité au CSS via custom properties.
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

    rafHandle = requestAnimationFrame(animate);
  }

  // ── Saccades programmées ────────────────────────────────────────────────
  function scheduleSaccade(): void {
    if (destroyed) return;
    const delay = randInt(SACCADE_MIN_INTERVAL_MS, SACCADE_MAX_INTERVAL_MS);
    saccadeTimer = setTimeout(() => {
      if (destroyed) return;
      // Cible : mouvement plus ample en idle (regarde autour), plus réduit en speaking.
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

  // ── API publique ────────────────────────────────────────────────────────
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
