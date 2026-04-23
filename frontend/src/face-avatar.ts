/**
 * JARVIS — Face Avatar.
 *
 * Affiche un portrait animé à partir d'un jeu de PNG en niveaux de gris,
 * synchronisé avec les événements WebSocket du backend :
 *   - state: idle | listening | thinking | speaking  → expression de base
 *   - set_volume (0..1)                              → forme de la bouche
 *
 * Aucune modification côté serveur : on réutilise les signaux que le backend
 * envoie déjà pour piloter l'orbe (volume durant la TTS).
 *
 * Les images attendues dans /jarvis-face/ :
 *   base-neutral.png       : visage neutre, bouche fermée (état idle/listening)
 *   expr-thinking.png      : visage pensif / yeux mi-clos (état thinking)
 *   expr-attentive.png     : visage attentif (optionnel — fallback base)
 *   expr-smile.png         : sourire subtil (optionnel — fallback base)
 *   mouth-00-closed.png    : bouche fermée pendant la parole
 *   mouth-01-slightly.png  : bouche légèrement entrouverte
 *   mouth-02-oh.png        : bouche arrondie "oh"
 *   mouth-03-wide.png      : bouche grande ouverte
 *   eyes-closed.png        : frame de clignement (optionnel — fallback base)
 *
 * Les images manquantes retombent silencieusement sur `base-neutral.png`.
 */

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

export interface FaceAvatar {
  setState(s: AvatarState): void;
  setVolume(v: number): void;
  destroy(): void;
}

// ── Config ─────────────────────────────────────────────────────────────────

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

// ── Anti-flicker : on limite la cadence de changement de bouche à ~12 Hz,
// en dessous la lèvre « vibre » sur les micro-variations d'amplitude. ──────
const MOUTH_MIN_FRAME_MS = 80;

// Lissage exponentiel du volume — évite les sautes sur un unique pic.
const VOLUME_SMOOTHING = 0.35;

// ── Seuils de bouche (volume lissé → frame) ────────────────────────────────
// Adaptés au flux `set_volume` du backend qui oscille ~[0.1, 1.0] en parole.
function mouthFrameForVolume(v: number): FrameKey {
  if (v < 0.14) return "mouth0";
  if (v < 0.38) return "mouth1";
  if (v < 0.68) return "mouth2";
  return "mouth3";
}

// ── Blinks : moment naturels, durée humaine (~120 ms), 3–6 s entre deux. ──
const BLINK_MIN_INTERVAL_MS = 3000;
const BLINK_MAX_INTERVAL_MS = 6500;
const BLINK_DURATION_MS = 130;

// ── Utilitaires ────────────────────────────────────────────────────────────

function preload(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(img); // on tolère l'absence, on utilisera la base
    img.src = src;
  });
}

function randInt(min: number, max: number): number {
  return Math.floor(min + Math.random() * (max - min));
}

// ── Création ───────────────────────────────────────────────────────────────

export function createFaceAvatar(container: HTMLElement): FaceAvatar {
  // Wrapper
  const wrap = document.createElement("div");
  wrap.className = "face-avatar";
  container.appendChild(wrap);

  // Deux couches pour permettre un cross-fade doux entre expressions
  // (les coupures rapides de bouche se font sur la couche "top" directement).
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

  // Préchargement : on vérifie quelles frames existent réellement.
  const available: Partial<Record<FrameKey, boolean>> = {};
  const loadPromises: Promise<void>[] = [];
  (Object.keys(FRAMES) as FrameKey[]).forEach((key) => {
    const p = preload(FRAMES[key]).then((img) => {
      available[key] = img.complete && img.naturalWidth > 0;
    });
    loadPromises.push(p);
  });

  // Résolution d'une clé de frame avec repli sur la base si absente.
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
  let destroyed = false;

  // Frame "de repos" par état (hors blink, hors parole).
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

  // Composition : définit la source réellement affichée pour chaque couche.
  // `bottom` = expression de repos (change rarement, cross-fade doux)
  // `top`    = mouth pendant parole OU blink (change souvent, coupure franche)
  function render(): void {
    if (destroyed) return;

    // ── Bottom layer : expression de repos actuelle ──────────────────────
    const restSrc = resolveFrame(restFrameForState(currentState));
    if (layerBottom.src.slice(-restSrc.length) !== restSrc) {
      layerBottom.src = restSrc;
    }

    // ── Top layer : prioritairement blink, sinon parole, sinon rien ──────
    if (blinking && available.eyesClosed) {
      layerTop.src = FRAMES.eyesClosed;
      layerTop.style.opacity = "1";
      return;
    }

    if (currentState === "speaking") {
      const key = currentMouthKey;
      const src = resolveFrame(key);
      if (layerTop.src.slice(-src.length) !== src) {
        layerTop.src = src;
      }
      layerTop.style.opacity = "1";
      return;
    }

    // Ni parole ni blink → on masque la couche top pour ne voir que le repos.
    layerTop.style.opacity = "0";
  }

  // ── Boucle de clignement ─────────────────────────────────────────────────
  function scheduleNextBlink(): void {
    if (destroyed) return;
    const delay = randInt(BLINK_MIN_INTERVAL_MS, BLINK_MAX_INTERVAL_MS);
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
      // On reset le volume si on sort de speaking pour ne pas garder
      // une bouche ouverte figée.
      if (s !== "speaking") {
        smoothedVolume = 0;
        currentMouthKey = "mouth0";
      }
      render();
    },

    setVolume(v) {
      const clamped = Math.max(0, Math.min(1, v));
      smoothedVolume = smoothedVolume * (1 - VOLUME_SMOOTHING) + clamped * VOLUME_SMOOTHING;

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
      wrap.remove();
    },
  };

  // Démarrage : on attend le préchargement puis on lance les animations.
  Promise.all(loadPromises).then(() => {
    if (destroyed) return;
    render();
    scheduleNextBlink();
  });

  return api;
}
