/**
 * J.A.R.V.I.S — Interface Web avec Orbe Three.js
 *
 * Se connecte au backend Python via WebSocket (ws://localhost:8765),
 * recoit les changements d'etat et pilote l'orbe en consequence.
 *
 * Etats: "idle" | "listening" | "thinking" | "speaking"
 */

import { createOrb, type OrbState } from "./orb";
import "./style.css";

type PHOEBUSMood =
  | "neutral"
  | "warm"
  | "joy"
  | "confident"
  | "alert"
  | "serious";

type MoodPreset = {
  eyeOpen: number;
  eyeWide: number;
  mouthBase: number;
  mouthWidth: number;
  mouthSkew: number;
  mouthLift: number;
};

type VisemeState = {
  open: number;
  width: number;
  skew: number;
  lift: number;
};

type VisemeFrame = VisemeState & {
  hold: number;
};

type TimedLipsyncFrame = VisemeState & {
  time_ms: number;
  duration_ms: number;
};

type AvatarFallbackFrameKey =
  | "neutral"
  | "speak-light"
  | "speak-oh"
  | "speak-open"
  | "thinking"
  | "blink"
  | "smile"
  | "alert"
  | "serious";

type AvatarClipKey = "reflective" | "expressive" | "none";

type AvatarVisualPalette = {
  accentRgb: string;
  softRgb: string;
  hotRgb: string;
};

type AvatarMediaElements = {
  coreEl: HTMLDivElement;
  fallbackEl: HTMLImageElement;
  reflectiveVideoEl: HTMLVideoElement;
  expressiveVideoEl: HTMLVideoElement;
};

// ── Solar Helpers (PHOEBUS) ─────────────────────────────────────────────────
function getSolarRgb() {
  const date = new Date();
  const hour = date.getHours() + date.getMinutes() / 60;

  const night = { r: 10, g: 17, b: 40 };
  const dawn = { r: 62, g: 31, b: 71 };
  const sunrise = { r: 255, g: 140, b: 66 };
  const noon = { r: 255, g: 255, b: 230 };
  const afternoon = { r: 255, g: 202, b: 58 };
  const sunset = { r: 255, g: 63, b: 0 };
  const twilight = { r: 42, g: 27, b: 61 };

  let k1, k2, ratio;
  if (hour < 5) { k1 = night; k2 = dawn; ratio = hour / 5; }
  else if (hour < 7) { k1 = dawn; k2 = sunrise; ratio = (hour - 5) / 2; }
  else if (hour < 12) { k1 = sunrise; k2 = noon; ratio = (hour - 7) / 5; }
  else if (hour < 17) { k1 = noon; k2 = afternoon; ratio = (hour - 12) / 5; }
  else if (hour < 19) { k1 = afternoon; k2 = sunset; ratio = (hour - 17) / 2; }
  else if (hour < 21) { k1 = sunset; k2 = twilight; ratio = (hour - 19) / 2; }
  else { k1 = twilight; k2 = night; ratio = (hour - 21) / 3; }

  const r = Math.round(k1.r + (k2.r - k1.r) * ratio);
  const g = Math.round(k1.g + (k2.g - k1.g) * ratio);
  const b = Math.round(k1.b + (k2.b - k1.b) * ratio);

  return `${r}, ${g}, ${b}`;
}

// ── Config ────────────────────────────────────────────────────────────────────
const WS_HOST = window.location.hostname || "localhost";
const WS_SCHEME = window.location.protocol === "https:" ? "wss" : "ws";
const WS_URL = `${WS_SCHEME}://${WS_HOST}:8765`;
const RECONNECT_INTERVAL_MS = 2_000;
const WS_TOKEN_STORAGE_KEY = "PHOEBUS_ws_token";
const FACE_ROOT = document.documentElement;
const MOOD_PRESETS: Record<PHOEBUSMood, MoodPreset> = {
  neutral: {
    eyeOpen: 1,
    eyeWide: 0,
    mouthBase: 0.04,
    mouthWidth: 1,
    mouthSkew: 0,
    mouthLift: 0,
  },
  warm: {
    eyeOpen: 0.98,
    eyeWide: 0.06,
    mouthBase: 0.05,
    mouthWidth: 1.04,
    mouthSkew: 0.02,
    mouthLift: 0.03,
  },
  joy: {
    eyeOpen: 0.92,
    eyeWide: 0.18,
    mouthBase: 0.06,
    mouthWidth: 1.1,
    mouthSkew: 0.02,
    mouthLift: 0.07,
  },
  confident: {
    eyeOpen: 0.94,
    eyeWide: 0.04,
    mouthBase: 0.04,
    mouthWidth: 1.03,
    mouthSkew: 0.05,
    mouthLift: 0.02,
  },
  alert: {
    eyeOpen: 1.14,
    eyeWide: 0.22,
    mouthBase: 0.02,
    mouthWidth: 0.95,
    mouthSkew: 0,
    mouthLift: -0.02,
  },
  serious: {
    eyeOpen: 0.86,
    eyeWide: -0.02,
    mouthBase: 0.02,
    mouthWidth: 0.92,
    mouthSkew: -0.03,
    mouthLift: -0.01,
  },
};
const PHONEME_CLUSTERS = [
  "eaux",
  "eau",
  "oin",
  "ion",
  "ain",
  "ein",
  "ien",
  "ou",
  "on",
  "an",
  "en",
  "in",
  "ai",
  "ei",
  "au",
  "eu",
  "oeu",
  "oe",
  "oi",
  "ui",
  "ch",
  "gn",
  "ph",
];
const AVATAR_FALLBACK_URLS: Record<AvatarFallbackFrameKey, string> = {
  neutral: "/avatar/neutral.png",
  "speak-light": "/avatar/speak-light.png",
  "speak-oh": "/avatar/speak-oh.png",
  "speak-open": "/avatar/speak-open.png",
  thinking: "/avatar/thinking.png",
  blink: "/avatar/blink.png",
  smile: "/avatar/smile.png",
  alert: "/avatar/alert.png",
  serious: "/avatar/serious.png",
};
const AVATAR_CLIP_URLS: Record<AvatarClipKey, string> = {
  reflective: "/avatar/reflective.mp4",
  expressive: "/avatar/expressive.mp4",
  none: "",
};
const AVATAR_POSTER_URLS: Record<AvatarClipKey, string> = {
  reflective: "/avatar/neutral.png",
  expressive: "/avatar/smile.png",
  none: "/avatar/neutral.png",
};
const AVATAR_CLIP_KEYS: AvatarClipKey[] = ["reflective", "expressive", "none"];

function resolveAvatarPalette(state: OrbState, mood: PHOEBUSMood): AvatarVisualPalette {
  const solarRgb = getSolarRgb();
  
  let palette: AvatarVisualPalette = {
    accentRgb: solarRgb,
    softRgb: solarRgb, // Will be lightened/shifted if needed
    hotRgb: "255, 219, 134",
  };

  switch (mood) {
    case "warm":
    case "joy":
      palette = {
        accentRgb: "96, 221, 255",
        softRgb: "214, 247, 255",
        hotRgb: "255, 210, 150",
      };
      break;
    case "alert":
      palette = {
        accentRgb: "255, 126, 126",
        softRgb: "255, 220, 220",
        hotRgb: "174, 235, 255",
      };
      break;
    case "serious":
      palette = {
        accentRgb: "119, 176, 255",
        softRgb: "211, 231, 255",
        hotRgb: "255, 203, 126",
      };
      break;
    case "confident":
      palette = {
        accentRgb: "124, 214, 255",
        softRgb: "220, 246, 255",
        hotRgb: "255, 232, 176",
      };
      break;
    default:
      break;
  }

  switch (state) {
    case "listening":
      return {
        accentRgb: "86, 231, 152",
        softRgb: "205, 255, 228",
        hotRgb: palette.hotRgb,
      };
    case "thinking":
      return {
        accentRgb: "255, 186, 95",
        softRgb: "255, 233, 170",
        hotRgb: "150, 224, 255",
      };
    case "speaking":
      return {
        accentRgb: "102, 214, 255",
        softRgb: "220, 246, 255",
        hotRgb: mood === "alert" ? "255, 150, 132" : palette.hotRgb,
      };
    default:
      return palette;
  }
}

function resolveAvatarClip(state: OrbState, _mood: PHOEBUSMood): AvatarClipKey {
  if (state === "thinking") {
    return "reflective";
  }
  if (state === "speaking") {
    return "expressive";
  }
  // En écoute ou au repos, on ne veut aucune vidéo (bouche fermée statique)
  return "none";
}

function resolveFallbackFrame(state: OrbState, mood: PHOEBUSMood): AvatarFallbackFrameKey {
  if (state === "thinking") {
    return "thinking";
  }

  if (state === "speaking") {
    if (mood === "warm" || mood === "joy") {
      return "smile";
    }
    if (mood === "alert") {
      return "alert";
    }
    if (mood === "serious") {
      return "serious";
    }
    return "speak-open";
  }

  if (state === "listening") {
    if (mood === "warm" || mood === "joy") {
      return "smile";
    }
    if (mood === "serious") {
      return "serious";
    }
    return "alert";
  }

  if (mood === "warm" || mood === "joy") {
    return "smile";
  }
  if (mood === "alert") {
    return "alert";
  }
  if (mood === "serious") {
    return "serious";
  }
  return "neutral";
}

function getStoredToken(): string {
  const params = new URLSearchParams(window.location.search);
  const tokenFromUrl = params.get("token")?.trim() ?? "";
  if (tokenFromUrl) {
    localStorage.setItem(WS_TOKEN_STORAGE_KEY, tokenFromUrl);
    return tokenFromUrl;
  }
  return localStorage.getItem(WS_TOKEN_STORAGE_KEY)?.trim() ?? "";
}

function requestToken(): string {
  const current = getStoredToken();
  const provided = window.prompt("Token PHOEBUS", current)?.trim() ?? "";
  if (provided) {
    localStorage.setItem(WS_TOKEN_STORAGE_KEY, provided);
  }
  return provided;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function rand(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

class FaceAvatar {
  private state: OrbState = "idle";
  private mood: PHOEBUSMood = "neutral";
  private activeClip: AvatarClipKey = "reflective";
  private readyClips = new Set<AvatarClipKey>();
  private failedClips = new Set<AvatarClipKey>();

  constructor(private readonly media: AvatarMediaElements) {
    this.readyClips.add("none"); // Le mode sans vidéo est toujours prêt
    this.configureVideo("reflective", media.reflectiveVideoEl);
    this.configureVideo("expressive", media.expressiveVideoEl);
    this.updateMedia();

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        this.ensurePlayback();
      }
    });
    window.addEventListener(
      "pointerdown",
      () => {
        this.ensurePlayback();
      },
      { once: true, passive: true }
    );
  }

  setState(state: OrbState): void {
    this.state = state;
    this.updateMedia();
  }

  setMood(mood: PHOEBUSMood): void {
    this.mood = mood;
    this.updateMedia();
  }

  setVolume(_volume: number): void {
    this.ensurePlayback();
  }

  private configureVideo(clip: AvatarClipKey, videoEl: HTMLVideoElement): void {
    videoEl.muted = true;
    videoEl.defaultMuted = true;
    videoEl.autoplay = true;
    videoEl.loop = true;
    videoEl.playsInline = true;
    videoEl.preload = "auto";
    videoEl.tabIndex = -1;
    videoEl.poster = AVATAR_POSTER_URLS[clip];
    videoEl.setAttribute("playsinline", "");
    videoEl.setAttribute("webkit-playsinline", "");
    videoEl.setAttribute("muted", "");
    videoEl.setAttribute("loop", "");
    videoEl.setAttribute("autoplay", "");
    if (!videoEl.getAttribute("src")) {
      videoEl.src = AVATAR_CLIP_URLS[clip];
    }

    const markReady = (): void => {
      this.readyClips.add(clip);
      this.failedClips.delete(clip);
      if (this.activeClip === clip) {
        this.updateMedia();
      }
      this.ensurePlayback();
    };

    videoEl.addEventListener("loadeddata", markReady);
    videoEl.addEventListener("canplay", markReady);
    videoEl.addEventListener("playing", markReady);
    videoEl.addEventListener("error", () => {
      this.failedClips.add(clip);
      this.readyClips.delete(clip);
      if (this.activeClip === clip) {
        this.updateMedia();
      }
    });

    videoEl.load();
  }

  private getVideoEl(clip: AvatarClipKey): HTMLVideoElement {
    if (clip === "expressive") return this.media.expressiveVideoEl;
    return this.media.reflectiveVideoEl; // Fallback pour none/reflective
  }

  private ensurePlayback(): void {
    for (const clip of AVATAR_CLIP_KEYS) {
      if (clip === "none") continue;
      const playPromise = this.getVideoEl(clip).play();
      if (playPromise) {
        playPromise.catch(() => {});
      }
    }
  }

  private updateMedia(): void {
    const nextClip = resolveAvatarClip(this.state, this.mood);
    const fallbackFrame = resolveFallbackFrame(this.state, this.mood);
    const showFallback =
      this.failedClips.has(nextClip) || !this.readyClips.has(nextClip);

    this.activeClip = nextClip;
    this.media.coreEl.dataset.PHOEBUSClip = nextClip;
    this.media.coreEl.dataset.videoFallback = showFallback ? "true" : "false";
    document.body.dataset.PHOEBUSClip = nextClip;

    this.media.fallbackEl.src = AVATAR_FALLBACK_URLS[fallbackFrame];
    this.media.fallbackEl.dataset.fallbackFrame = fallbackFrame;
    this.media.reflectiveVideoEl.dataset.active = String(nextClip === "reflective");
    this.media.expressiveVideoEl.dataset.active = String(nextClip === "expressive");

    if (!showFallback && nextClip !== "none") {
      this.ensurePlayback();
    }
  }
}

function cleanSpeechText(text: string): string {
  return text.replace(/\{[^}]*\}/gs, " ").replace(/\s+/g, " ").trim();
}

function normalizeSpeech(text: string): string {
  return cleanSpeechText(text)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function inferMood(text: string): PHOEBUSMood {
  const normalized = normalizeSpeech(text);

  if (
    /\b(alerte|attention|urgence|urgent|alarme|fuite|fumee|intrusion|erreur|impossible|probleme|danger)\b/.test(
      normalized
    )
  ) {
    return "alert";
  }
  if (/\b(parfait|excellent|super|felicitations|bravo|bonne nouvelle)\b/.test(normalized)) {
    return "joy";
  }
  if (
    /\b(bien sur|pas de souci|pas d inquietude|ne t inquiete pas|je m en occupe|avec plaisir)\b/.test(
      normalized
    )
  ) {
    return "warm";
  }
  if (
    /\b(c est fait|termine|effectue|active|desactive|regle|configure|pret)\b/.test(
      normalized
    )
  ) {
    return "confident";
  }
  if (
    /\b(analyse|verification|resume|diagnostic|securite|architecture|hypothese|risque)\b/.test(
      normalized
    )
  ) {
    return "serious";
  }
  return "neutral";
}

function getRestViseme(): VisemeState {
  return currentState === "speaking"
    ? { open: 0.07, width: 1, skew: 0, lift: 0 }
    : { open: 0.01, width: 1, skew: 0, lift: 0 };
}

function getSolarIntensity() {
  const date = new Date();
  const hour = date.getHours() + date.getMinutes() / 60;
  // Intensity: 0.4 at night, 1.3 at noon
  // Use a simple sine-like curve or similar
  const intensity = 0.85 + 0.45 * Math.cos(((hour - 12) * Math.PI) / 12);
  return intensity.toFixed(3);
}

function renderFace(): void {
  const preset = MOOD_PRESETS[currentMood];
  const palette = resolveAvatarPalette(currentState, currentMood);
  const solarIntensity = getSolarIntensity();
  const eyeOpen = clamp(
    preset.eyeOpen +
      (currentState === "listening" ? 0.06 : 0) +
      (currentState === "thinking" ? -0.04 : 0),
    0.72,
    1.24
  );
  const eyeWide = clamp(
    preset.eyeWide +
      (currentState === "listening" ? 0.08 : 0) +
      (currentState === "thinking" ? 0.03 : 0),
    -0.05,
    0.34
  );
  const mouthOpen = clamp(
    preset.mouthBase +
      currentViseme.open +
      (currentState === "speaking" ? currentVoiceLevel * 0.14 : 0),
    0,
    0.58
  );
  const mouthWidth = clamp(preset.mouthWidth * currentViseme.width, 0.84, 1.22);
  const mouthSkew = clamp(preset.mouthSkew + currentViseme.skew, -0.18, 0.18);
  const mouthLift = clamp(preset.mouthLift + currentViseme.lift, -0.08, 0.18);
  const stateEnergy =
    currentState === "speaking"
      ? 0.9
      : currentState === "thinking"
        ? 0.72
        : currentState === "listening"
          ? 0.62
          : 0.38;
  const moodEnergy =
    currentMood === "joy"
      ? 0.2
      : currentMood === "warm"
        ? 0.14
        : currentMood === "alert"
          ? 0.24
          : currentMood === "serious"
            ? 0.1
            : currentMood === "confident"
              ? 0.08
              : 0;
  const voiceEnergy = currentState === "speaking" ? currentVoiceLevel : 0;
  const avatarEnergy = clamp(stateEnergy + moodEnergy + voiceEnergy * 0.42, 0.24, 1.2);
  const avatarPresence = clamp(0.92 + avatarEnergy * 0.12, 0.92, 1.04);
  const shellShiftX = currentGaze.x * (currentState === "thinking" ? 1.45 : 1.05);
  const shellShiftY = currentGaze.y * (currentState === "thinking" ? 1.2 : 0.82);
  const shellScale = clamp(1 + avatarEnergy * 0.04 + voiceEnergy * 0.05, 1.01, 1.09);
  const shellTilt = clamp(
    currentGaze.x * (currentState === "thinking" ? 0.72 : 0.48),
    -4.2,
    4.2
  );
  const saturation = clamp(
    1.08 + avatarEnergy * 0.24 + (currentMood === "joy" ? 0.05 : 0),
    1.08,
    1.44
  );
  const contrast = clamp(1.08 + avatarEnergy * 0.16, 1.08, 1.3);
  const brightness = clamp(1.02 + avatarEnergy * 0.16 + voiceEnergy * 0.06, 1.02, 1.28);
  const haloOpacity = clamp(0.56 + avatarEnergy * 0.26, 0.56, 0.92);
  const scanOpacity = clamp(0.34 + avatarEnergy * 0.32, 0.34, 0.84);
  const neuralOpacity = clamp(0.28 + avatarEnergy * 0.44, 0.28, 0.92);
  const ringOpacity = clamp(0.16 + avatarEnergy * 0.34, 0.16, 0.78);
  const opacity = clamp(0.86 + avatarPresence * 0.16, 0.9, 1);
  const neuralSpeed =
    currentState === "speaking"
      ? 3.8
      : currentState === "thinking"
        ? 4.6
        : currentState === "listening"
          ? 5.2
          : 6.8;

  FACE_ROOT.style.setProperty("--PHOEBUS-solar-intensity", solarIntensity);
  FACE_ROOT.style.setProperty("--PHOEBUS-gaze-x", `${currentGaze.x.toFixed(2)}px`);
  FACE_ROOT.style.setProperty("--PHOEBUS-gaze-y", `${currentGaze.y.toFixed(2)}px`);
  FACE_ROOT.style.setProperty("--PHOEBUS-eye-open", eyeOpen.toFixed(3));
  FACE_ROOT.style.setProperty("--PHOEBUS-eye-wide", eyeWide.toFixed(3));
  FACE_ROOT.style.setProperty("--PHOEBUS-mouth-open", mouthOpen.toFixed(3));
  FACE_ROOT.style.setProperty("--PHOEBUS-mouth-width", mouthWidth.toFixed(3));
  FACE_ROOT.style.setProperty("--PHOEBUS-mouth-skew", mouthSkew.toFixed(3));
  FACE_ROOT.style.setProperty("--PHOEBUS-mouth-lift", mouthLift.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-energy", avatarEnergy.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-presence", avatarPresence.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-shift-x", `${shellShiftX.toFixed(2)}px`);
  FACE_ROOT.style.setProperty("--avatar-shift-y", `${shellShiftY.toFixed(2)}px`);
  FACE_ROOT.style.setProperty("--avatar-scale", shellScale.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-tilt", `${shellTilt.toFixed(2)}deg`);
  FACE_ROOT.style.setProperty("--avatar-opacity", opacity.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-saturation", saturation.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-contrast", contrast.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-brightness", brightness.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-halo-opacity", haloOpacity.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-scan-opacity", scanOpacity.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-neural-opacity", neuralOpacity.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-ring-opacity", ringOpacity.toFixed(3));
  FACE_ROOT.style.setProperty("--avatar-neural-speed", `${neuralSpeed.toFixed(2)}s`);
  FACE_ROOT.style.setProperty("--avatar-accent-rgb", palette.accentRgb);
  FACE_ROOT.style.setProperty("--avatar-soft-rgb", palette.softRgb);
  FACE_ROOT.style.setProperty("--avatar-hot-rgb", palette.hotRgb);
  document.body.dataset.PHOEBUSMood = currentMood;
}

function scheduleMoodReset(ms = 3_600): void {
  if (moodResetTimer) {
    clearTimeout(moodResetTimer);
  }
  moodResetTimer = setTimeout(() => {
    currentMood = currentState === "thinking" ? "serious" : "neutral";
    faceAvatar.setMood(currentMood);
    renderFace();
  }, ms);
}

function cancelPendingExpressionFallback(): void {
  if (pendingExpressionTimer) {
    clearTimeout(pendingExpressionTimer);
    pendingExpressionTimer = null;
  }
  pendingExpressionId = "";
}

function cancelTimedLipsync(): void {
  for (const timer of timedLipsyncTimers) {
    clearTimeout(timer);
  }
  timedLipsyncTimers = [];
}

function setCurrentViseme(state: VisemeState): void {
  currentViseme = state;
  renderFace();
}

function stopVisemeSequence(): void {
  cancelPendingExpressionFallback();
  cancelTimedLipsync();
  if (visemeTimer) {
    clearTimeout(visemeTimer);
    visemeTimer = null;
  }
  setCurrentViseme(getRestViseme());
}

function tokenizeSpeech(text: string): string[] {
  const normalized = normalizeSpeech(text).replace(/[^a-z\s]/g, " ");
  const words = normalized.split(/\s+/).filter(Boolean);
  const tokens: string[] = [];

  for (const word of words) {
    let index = 0;
    while (index < word.length) {
      const cluster = PHONEME_CLUSTERS.find((item) => word.startsWith(item, index));
      if (cluster) {
        tokens.push(cluster);
        index += cluster.length;
      } else {
        tokens.push(word[index]);
        index += 1;
      }
    }
    tokens.push(" ");
  }

  return tokens;
}

function visemeForToken(token: string): VisemeFrame {
  if (token === " ") {
    return { ...getRestViseme(), hold: 60 };
  }
  if (/^[mbp]$/.test(token)) {
    return { open: 0, width: 0.98, skew: 0, lift: 0.02, hold: 70 };
  }
  if (/^(f|v|ph)$/.test(token)) {
    return { open: 0.12, width: 1.01, skew: 0.02, lift: 0.01, hold: 78 };
  }
  if (/^(ou|o|on|au|eu|u)$/.test(token)) {
    return { open: 0.24, width: 0.88, skew: 0, lift: 0, hold: 105 };
  }
  if (/^(a|an|en|eau|ain|ein)$/.test(token)) {
    return { open: 0.36, width: 1.14, skew: 0, lift: 0.02, hold: 96 };
  }
  if (/^(e|i|y|ai|ei|ui|ien|oi)$/.test(token)) {
    return { open: 0.2, width: 1.12, skew: 0.02, lift: 0.05, hold: 86 };
  }
  return { open: 0.16, width: 1.02, skew: 0, lift: 0, hold: 72 };
}

function buildVisemeFrames(text: string): VisemeFrame[] {
  return tokenizeSpeech(text)
    .slice(0, 72)
    .map((token) => visemeForToken(token));
}

function startVisemeSequence(text: string): void {
  const frames = buildVisemeFrames(text);
  stopVisemeSequence();

  if (!frames.length) {
    return;
  }

  let index = 0;
  const step = (): void => {
    const frame = frames[index];
    setCurrentViseme({
      open: frame.open,
      width: frame.width,
      skew: frame.skew,
      lift: frame.lift,
    });
    index += 1;

    if (index < frames.length) {
      visemeTimer = setTimeout(step, frame.hold);
      return;
    }

    visemeTimer = setTimeout(() => {
      visemeTimer = null;
      setCurrentViseme(getRestViseme());
    }, 90);
  };

  step();
}

function scheduleExpressionFallback(text: string, utteranceId?: string): void {
  cancelPendingExpressionFallback();
  pendingExpressionId = utteranceId ?? "";
  pendingExpressionTimer = setTimeout(() => {
    pendingExpressionTimer = null;
    pendingExpressionId = "";
    startVisemeSequence(text);
  }, 180);
}

function startTimedLipsync(frames: TimedLipsyncFrame[], utteranceId?: string): void {
  if (!frames.length) {
    return;
  }

  if (utteranceId && pendingExpressionId && pendingExpressionId !== utteranceId) {
    return;
  }

  stopVisemeSequence();
  const sortedFrames = [...frames].sort((a, b) => a.time_ms - b.time_ms);

  for (const frame of sortedFrames) {
    const timer = setTimeout(() => {
      setCurrentViseme({
        open: frame.open,
        width: frame.width,
        skew: frame.skew,
        lift: frame.lift,
      });
    }, Math.max(0, frame.time_ms));
    timedLipsyncTimers.push(timer);
  }

  const lastFrame = sortedFrames[sortedFrames.length - 1];
  const resetTimer = setTimeout(() => {
    timedLipsyncTimers = timedLipsyncTimers.filter((timer) => timer !== resetTimer);
    setCurrentViseme(getRestViseme());
  }, Math.max(0, lastFrame.time_ms + lastFrame.duration_ms + 40));
  timedLipsyncTimers.push(resetTimer);
}

function consumeExpressionText(
  text: string,
  options: { animateMouth?: boolean; scheduleFallback?: boolean; id?: string } = {}
): void {
  const cleaned = cleanSpeechText(text);
  if (!cleaned) {
    return;
  }

  const now = Date.now();
  if (options.id && options.id === lastExpressionId) {
    return;
  }
  if (!options.id && cleaned === lastExpressionText && now - lastExpressionAt < 1_500) {
    return;
  }
  lastExpressionText = cleaned;
  lastExpressionAt = now;
  lastExpressionId = options.id ?? "";

  currentMood = inferMood(cleaned);
  faceAvatar.setMood(currentMood);
  renderFace();
  if (options.animateMouth) {
    startVisemeSequence(cleaned);
  } else if (options.scheduleFallback) {
    scheduleExpressionFallback(cleaned, options.id);
  }
  scheduleMoodReset(clamp(cleaned.length * 38, 2_800, 6_400));
}

function scheduleGazeLoop(): void {
  if (gazeTimer) {
    clearTimeout(gazeTimer);
    gazeTimer = null;
  }

  const tick = (): void => {
    let maxX = 3.4;
    let maxY = 1.8;
    let minDelay = 1_500;
    let maxDelay = 2_800;

    if (currentState === "thinking") {
      maxX = 6;
      maxY = 3.2;
      minDelay = 800;
      maxDelay = 1_500;
    } else if (currentState === "listening") {
      maxX = 4.4;
      maxY = 2.3;
      minDelay = 1_000;
      maxDelay = 1_800;
    } else if (currentState === "speaking") {
      maxX = 3.6;
      maxY = 2;
      minDelay = 700;
      maxDelay = 1_300;
    }

    currentGaze = {
      x: rand(-maxX, maxX),
      y: rand(-maxY, maxY),
    };
    renderFace();
    gazeTimer = setTimeout(tick, rand(minDelay, maxDelay));
  };

  gazeTimer = setTimeout(tick, 450);
}

// ── DOM refs ──────────────────────────────────────────────────────────────────
const canvas = document.getElementById("orb-canvas") as HTMLCanvasElement;
const avatarCoreEl = document.getElementById("avatar-core") as HTMLDivElement;
const avatarFallbackEl = document.getElementById(
  "avatar-face-fallback"
) as HTMLImageElement;
const avatarReflectiveVideoEl = document.getElementById(
  "avatar-video-reflective"
) as HTMLVideoElement;
const avatarExpressiveVideoEl = document.getElementById(
  "avatar-video-expressive"
) as HTMLVideoElement;
const statusEl = document.getElementById("status-text") as HTMLDivElement;
const errorEl = document.getElementById("error-text") as HTMLDivElement;
const badgeEl = document.getElementById("connection-badge") as HTMLDivElement;
const badgeLabelEl = document.getElementById(
  "connection-label"
) as HTMLSpanElement;
const faceAvatar = new FaceAvatar({
  coreEl: avatarCoreEl,
  fallbackEl: avatarFallbackEl,
  reflectiveVideoEl: avatarReflectiveVideoEl,
  expressiveVideoEl: avatarExpressiveVideoEl,
});
document.body.classList.add("has-face-avatar");

// ── Orb ───────────────────────────────────────────────────────────────────────
const orb = createOrb(canvas);

// ── State labels (French) ────────────────────────────────────────────────────
const STATE_LABELS: Record<OrbState, string> = {
  idle: "",
  listening: "écoute...",
  thinking: "PHOEBUS réfléchit...",
  speaking: "PHOEBUS répond...",
  proactive: "PHOEBUS observe...",
};
let currentState: OrbState = "idle";
let currentMood: PHOEBUSMood = "neutral";
let currentVoiceLevel = 0;
let currentGaze = { x: 0, y: 0 };
let currentViseme: VisemeState = getRestViseme();
let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let gazeTimer: ReturnType<typeof setTimeout> | null = null;
let visemeTimer: ReturnType<typeof setTimeout> | null = null;
let moodResetTimer: ReturnType<typeof setTimeout> | null = null;
let pendingExpressionTimer: ReturnType<typeof setTimeout> | null = null;
let timedLipsyncTimers: ReturnType<typeof setTimeout>[] = [];
let pendingExpressionId = "";
let authToken = getStoredToken();
let lastExpressionText = "";
let lastExpressionAt = 0;
let lastExpressionId = "";

function setVoiceLevel(level: number): void {
  const baseline = currentState === "speaking" ? 0.08 : 0;
  currentVoiceLevel = Math.max(baseline, Math.min(1, level || 0));
  faceAvatar.setVolume(Math.max(0, Math.min(1, level || 0)));
  FACE_ROOT.style.setProperty("--PHOEBUS-voice", currentVoiceLevel.toFixed(3));
  renderFace();
}

function applyState(state: OrbState): void {
  currentState = state;
  orb.setState(state);
  if (faceAvatar) faceAvatar.setState(state);
  // On expose l'état sur body pour que la CSS puisse teinter l'orbe
  // et l'aura sans JS additionnel.
  document.body.dataset.state = state;
  statusEl.textContent = STATE_LABELS[state];
  document.body.dataset.PHOEBUSState = state;

  // Toggle de la classe proactivite pour l'effet 'Neural Pulse'
  document.body.classList.toggle("is-proactive", state === "proactive");

  if (state === "listening") {
    currentMood = "alert";
  } else if (state === "thinking") {
    currentMood = "serious";
  } else if (state === "idle" && currentMood !== "warm" && currentMood !== "joy") {
    currentMood = "neutral";
  }

  faceAvatar.setMood(currentMood);
  faceAvatar.setState(state);

  if (state !== "speaking") {
    stopVisemeSequence();
  } else {
    currentViseme = getRestViseme();
    renderFace();
  }

  setVoiceLevel(0);
  scheduleGazeLoop();
}

// ── Error toast ───────────────────────────────────────────────────────────────
let errorTimer: ReturnType<typeof setTimeout> | null = null;

function showError(msg: string): void {
  errorEl.textContent = msg;
  errorEl.style.opacity = "1";
  if (errorTimer) clearTimeout(errorTimer);
  errorTimer = setTimeout(() => {
    errorEl.style.opacity = "0";
  }, 4_000);
}

// ── Connection badge ──────────────────────────────────────────────────────────
function setConnected(ok: boolean): void {
  badgeEl.classList.toggle("connected", ok);
  badgeEl.classList.toggle("disconnected", !ok);
  badgeLabelEl.textContent = ok ? "connecte" : "reconnexion";
}

function sendAuth(): void {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(
    JSON.stringify({
      type: "auth",
      token: authToken,
      client_type: "web",
      client_name: window.navigator.userAgent.slice(0, 80),
    })
  );
}

// ── Streaming Audio Player ────────────────────────────────────────────────────
class StreamingAudioPlayer {
  private audioCtx: AudioContext;
  private nextStartTime: number = 0;
  private activeId: string | null = null;
  private sources: Set<AudioBufferSourceNode> = new Set();

  constructor() {
    this.audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
  }

  async playChunk(base64Data: string, utteranceId: string): Promise<void> {
    if (this.activeId !== utteranceId) {
      this.stop();
      this.activeId = utteranceId;
      this.nextStartTime = this.audioCtx.currentTime + 0.05;
      applyState("speaking");
    }

    const binary = atob(base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

    try {
      const audioBuffer = await this.audioCtx.decodeAudioData(bytes.buffer);
      const source = this.audioCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.audioCtx.destination);

      const startTime = Math.max(this.audioCtx.currentTime, this.nextStartTime);
      source.start(startTime);
      this.nextStartTime = startTime + audioBuffer.duration;

      this.sources.add(source);
      source.onended = () => {
        this.sources.delete(source);
        if (this.audioCtx.currentTime >= this.nextStartTime - 0.1 && this.sources.size === 0) {
          applyState("idle");
          setVoiceLevel(0);
        }
      };
      
      const vol = 0.4 + 0.3 * Math.sin(Date.now() / 50);
      setVoiceLevel(vol);
    } catch (e) {
      console.error("[STREAM] Error decoding chunk", e);
    }
  }

  stop(): void {
    this.sources.forEach(s => {
      try { s.stop(); } catch(e) {}
    });
    this.sources.clear();
    this.activeId = null;
    this.nextStartTime = 0;
  }
}

const streamingPlayer = new StreamingAudioPlayer();

// ── WebSocket with auto-reconnect ─────────────────────────────────────────────
function connect(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  ws = new WebSocket(WS_URL);

  ws.addEventListener("open", () => {
    setConnected(true);
    sendAuth();
  });

  ws.addEventListener("message", (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data as string) as {
        state?: string;
        action?: string;
        muted?: boolean;
        volume?: number;
        id?: string;
        text?: string;
        backend?: string;
        frames?: TimedLipsyncFrame[];
      };

      if (data.action === "request_screen_capture") {
        return;
      }
      if (data.action === "auth_ok") {
        return;
      }
      if (data.action === "auth_required") {
        authToken = requestToken();
        if (!authToken) {
          showError("Token requis");
          return;
        }
        sendAuth();
        return;
      }
      if (data.action === "auth_failed") {
        localStorage.removeItem(WS_TOKEN_STORAGE_KEY);
        authToken = "";
        showError("Token invalide");
        setConnected(false);
        authToken = requestToken();
        if (authToken) sendAuth();
        return;
      }

      if (data.action === "demo") {
        orb.triggerDemo();
        return;
      }
      if (data.action === "metamorphose") {
        const shape = (data as any).shape || "sphere";
        const colors = (data as any).colors || [];
        orb.setTheme(shape as any, colors);
        return;
      }
      if (data.action === "PHOEBUS_expression" && data.text) {
        consumeExpressionText(data.text, { scheduleFallback: true, id: data.id });
        return;
      }
      if (data.action === "PHOEBUS_lipsync" && Array.isArray(data.frames)) {
        startTimedLipsync(data.frames, data.id);
        return;
      }
      if (data.action === "PHOEBUS_audio_chunk" && data.id && data.text) {
        streamingPlayer.playChunk(data.text, data.id);
        return;
      }
      if (data.action === "set_volume" && typeof data.volume === "number") {
        orb.setVolume(data.volume);
        if (faceAvatar) faceAvatar.setVolume(data.volume);
        setVoiceLevel(data.volume);
        return;
      }
      if (data.state) {
        applyState(data.state as OrbState);
      }
      if (typeof data.volume === "number") {
        orb.setVolume(data.volume);
        if (faceAvatar) faceAvatar.setVolume(data.volume);
        setVoiceLevel(data.volume);
      }
    } catch {
      // ignore malformed messages
    }
  });

  ws.addEventListener("close", () => {
    setConnected(false);
    applyState("idle");
    setVoiceLevel(0);
    scheduleReconnect();
  });

  ws.addEventListener("error", () => {
    setConnected(false);
  });
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, RECONNECT_INTERVAL_MS);
}

// ── Boot ──────────────────────────────────────────────────────────────────────
setConnected(false);
renderFace();
applyState("idle");
connect();

// Mise à jour périodique de la palette solaire (chaque minute)
setInterval(() => {
  renderFace();
}, 60_000);

// Silence unused-import warning for showError
void showError;
