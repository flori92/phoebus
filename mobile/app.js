/**
 * J.A.R.V.I.S — Interface Mobile
 *
 * Se connecte au backend Python via WebSocket dynamiquement (même IP que le serveur HTTP).
 * Utilise Web Speech API pour STT (voix → texte) et SpeechSynthesis pour TTS (texte → voix).
 *
 * États: "idle" | "listening" | "thinking" | "speaking"
 */

// ── Config ─────────────────────────────────────────────────────────────────
const WS_SCHEME = window.location.protocol === "https:" ? "wss" : "ws";
const WS_URL = `${WS_SCHEME}://${window.location.hostname}:8765`;
const RECONNECT_DELAY_MS = 2500;
const SPEECH_LANG = "fr-FR";
const BROWSER_STT_ENABLED = false;
const WAKE_WORD_RE = /\b(?:phoebus|phébus|fébus|febus|feubus|rebus)\b/i;
const CONFIRMATION_RE = /\b(?:confirme|je confirme|ok confirme|oui confirme|valide|vas[- ]?y|exécute|execute|annule|annuler|stop|laisse tomber|oublie|non)\b/i;

// ── DOM Refs ────────────────────────────────────────────────────────────────
const badgeEl      = document.getElementById("connection-badge");
const badgeLabelEl = document.getElementById("connection-label");
const statusEl     = document.getElementById("status-text");
const userTextEl   = document.getElementById("user-text");
const PHOEBUSTextEl = document.getElementById("PHOEBUS-text");
const micBtn       = document.getElementById("mic-btn");
const micIcon      = micBtn.querySelector(".mic-icon");
const stopIcon     = micBtn.querySelector(".stop-icon");
const micLabelEl   = document.getElementById("mic-label");
const stopPHOEBUSBtn= document.getElementById("stop-PHOEBUS-btn");
const avatarCoreEl = document.getElementById("avatar-core");
const avatarFallbackEl = document.getElementById("avatar-face-fallback");
const avatarReflectiveVideoEl = document.getElementById("avatar-video-reflective");
const avatarExpressiveVideoEl = document.getElementById("avatar-video-expressive");

// ── ORB 3D ──────────────────────────────────────────────────────────────────
let orb = null;
if (typeof createOrb === "function") {
  const canvas = document.getElementById("orb-canvas");
  if (canvas) {
    orb = createOrb(canvas);
  }
}

// Le micro permanent est porte par le backend. Le navigateur reste une voie
// best-effort, sans alerte visible si sa permission est refusee.
const browserMicWarning = document.getElementById("https-warning");
if (browserMicWarning) {
  browserMicWarning.style.display = "none";
}

// ── État de l'application ───────────────────────────────────────────────────
let currentState = "idle";
let ws           = null;
let isListening  = false;
let reconnectTimer = null;
const faceRoot = document.documentElement;
const PAIR_DEVICE_ID_KEY = "PHOEBUS_PAIR_DEVICE_ID";
const PAIR_SECRET_KEY = "PHOEBUS_PAIR_SECRET";

function removeLegacyTokenFromUrl() {
  const params = new URLSearchParams(window.location.search);
  if (params.has("token")) {
    params.delete("token");
    const nextSearch = params.toString();
    const nextUrl = window.location.pathname + (nextSearch ? `?${nextSearch}` : "") + window.location.hash;
    window.history.replaceState({}, document.title, nextUrl);
  }
  Object.keys(window.localStorage)
    .filter((key) => key.includes("PHOEBUS") && key.includes("TOKEN"))
    .forEach((key) => window.localStorage.removeItem(key));
}

removeLegacyTokenFromUrl();
const MOOD_PRESETS = {
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
const AVATAR_FALLBACK_URLS = {
  neutral: "avatar/neutral.png",
  "speak-light": "avatar/speak-light.png",
  "speak-oh": "avatar/speak-oh.png",
  "speak-open": "avatar/speak-open.png",
  thinking: "avatar/thinking.png",
  blink: "avatar/blink.png",
  smile: "avatar/smile.png",
  alert: "avatar/alert.png",
  serious: "avatar/serious.png",
};
const AVATAR_CLIP_URLS = {
  reflective: "avatar/reflective.mp4",
  expressive: "avatar/expressive.mp4",
  none: "",
};
const AVATAR_POSTER_URLS = {
  reflective: "avatar/neutral.png",
  expressive: "avatar/smile.png",
  none: "avatar/neutral.png",
};
const AVATAR_CLIP_KEYS = ["reflective", "expressive", "none"];

function resolveAvatarPalette(state, mood) {
  let palette = {
    accentRgb: "88, 202, 255",
    softRgb: "197, 241, 255",
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

function resolveAvatarClip(state, _mood) {
  if (state === "speaking") {
    return "expressive";
  }
  // Quand il ne parle pas, afficher l'image fixe
  return "none";
}

function resolveFallbackFrame(state, mood) {
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

class FaceAvatar {
  constructor(media) {
    this.media = media;
    this.state = "idle";
    this.mood = "neutral";
    this.activeClip = "reflective";
    this.readyClips = new Set(["none"]);
    this.failedClips = new Set();

    this.configureVideo("reflective", media.reflectiveVideoEl);
    this.configureVideo("expressive", media.expressiveVideoEl);
    this.updateMedia();

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        this.ensurePlayback();
      }
    });
    window.addEventListener("pointerdown", () => {
      this.ensurePlayback();
    }, { once: true, passive: true });
  }

  setState(state) {
    this.state = state;
    this.updateMedia();
  }

  setMood(mood) {
    this.mood = mood;
    this.updateMedia();
  }

  setVolume(_volume) {
    this.ensurePlayback();
  }

  configureVideo(clip, videoEl) {
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

    const markReady = () => {
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

  getVideoEl(clip) {
    if (clip === "expressive") return this.media.expressiveVideoEl;
    return this.media.reflectiveVideoEl; // Fallback pour none/reflective
  }

  ensurePlayback() {
    AVATAR_CLIP_KEYS.forEach((clip) => {
      if (clip === "none") return;
      const playPromise = this.getVideoEl(clip).play();
      if (playPromise) {
        playPromise.catch(() => {});
      }
    });
  }

  updateMedia() {
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
let currentMood = "neutral";
let currentVoiceLevel = 0;
let currentGaze = { x: 0, y: 0 };
let currentViseme = { open: 0.01, width: 1, skew: 0, lift: 0 };
let gazeTimer = null;
let visemeTimer = null;
let moodResetTimer = null;
let pendingExpressionTimer = null;
let timedLipsyncTimers = [];
let pendingExpressionId = "";
let pendingLipsyncById = new Map();
let activeSpeechId = "";
let lastExpressionText = "";
let lastExpressionAt = 0;
let lastExpressionId = "";
const faceAvatar = new FaceAvatar({
  coreEl: avatarCoreEl,
  fallbackEl: avatarFallbackEl,
  reflectiveVideoEl: avatarReflectiveVideoEl,
  expressiveVideoEl: avatarExpressiveVideoEl,
});

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function rand(min, max) {
  return min + Math.random() * (max - min);
}

function cleanSpeechText(text) {
  return String(text || "")
    .replace(/\{[^}]*\}/gs, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeSpeech(text) {
  return cleanSpeechText(text)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function inferMood(text) {
  const normalized = normalizeSpeech(text);

  if (/\b(alerte|attention|urgence|urgent|alarme|fuite|fumee|intrusion|erreur|impossible|probleme|danger)\b/.test(normalized)) {
    return "alert";
  }
  if (/\b(parfait|excellent|super|felicitations|bravo|bonne nouvelle)\b/.test(normalized)) {
    return "joy";
  }
  if (/\b(bien sur|pas de souci|pas d inquietude|ne t inquiete pas|je m en occupe|avec plaisir)\b/.test(normalized)) {
    return "warm";
  }
  if (/\b(c est fait|termine|effectue|active|desactive|regle|configure|pret)\b/.test(normalized)) {
    return "confident";
  }
  if (/\b(analyse|verification|resume|diagnostic|securite|architecture|hypothese|risque)\b/.test(normalized)) {
    return "serious";
  }
  return "neutral";
}

function getRestViseme() {
  return currentState === "speaking"
    ? { open: 0.07, width: 1, skew: 0, lift: 0 }
    : { open: 0.01, width: 1, skew: 0, lift: 0 };
}

function renderFace() {
  const preset = MOOD_PRESETS[currentMood];
  const palette = resolveAvatarPalette(currentState, currentMood);
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
  const listenEnergy = currentState === "listening" ? currentVoiceLevel : 0; // Réagit aussi à MA voix quand je parle
  const totalVoice = voiceEnergy + listenEnergy;
  
  const avatarEnergy = clamp(stateEnergy + moodEnergy + totalVoice * 0.8, 0.24, 1.5);
  const avatarPresence = clamp(0.92 + avatarEnergy * 0.15, 0.92, 1.1);
  const shellShiftX = currentGaze.x * (currentState === "thinking" ? 1.45 : 1.05);
  const shellShiftY = currentGaze.y * (currentState === "thinking" ? 1.2 : 0.82);
  const shellScale = clamp(1 + avatarEnergy * 0.05 + totalVoice * 0.15, 1.01, 1.25); // Onde de choc vocale intense
  const shellTilt = clamp(
    currentGaze.x * (currentState === "thinking" ? 0.72 : 0.48),
    -4.2,
    4.2
  );
  const saturation = clamp(
    1.08 + avatarEnergy * 0.3 + (currentMood === "joy" ? 0.1 : 0),
    1.08,
    1.6
  );
  const contrast = clamp(1.08 + avatarEnergy * 0.2, 1.08, 1.4);
  const brightness = clamp(1.02 + avatarEnergy * 0.2 + totalVoice * 0.5, 1.02, 1.8); // Flash de lumière sur la voix
  const haloOpacity = clamp(0.56 + avatarEnergy * 0.4, 0.56, 1.0);
  const scanOpacity = clamp(0.34 + avatarEnergy * 0.4, 0.34, 0.9);
  const neuralOpacity = clamp(0.28 + avatarEnergy * 0.5, 0.28, 1.0);
  const ringOpacity = clamp(0.16 + avatarEnergy * 0.4, 0.16, 0.9);
  const opacity = clamp(0.86 + avatarPresence * 0.16, 0.9, 1);
  const neuralSpeed =
    currentState === "speaking"
      ? 3.8
      : currentState === "thinking"
        ? 4.6
        : currentState === "listening"
          ? 5.2
          : 6.8;

  faceRoot.style.setProperty("--PHOEBUS-gaze-x", `${currentGaze.x.toFixed(2)}px`);
  faceRoot.style.setProperty("--PHOEBUS-gaze-y", `${currentGaze.y.toFixed(2)}px`);
  faceRoot.style.setProperty("--PHOEBUS-eye-open", eyeOpen.toFixed(3));
  faceRoot.style.setProperty("--PHOEBUS-eye-wide", eyeWide.toFixed(3));
  faceRoot.style.setProperty("--PHOEBUS-mouth-open", mouthOpen.toFixed(3));
  faceRoot.style.setProperty("--PHOEBUS-mouth-width", mouthWidth.toFixed(3));
  faceRoot.style.setProperty("--PHOEBUS-mouth-skew", mouthSkew.toFixed(3));
  faceRoot.style.setProperty("--PHOEBUS-mouth-lift", mouthLift.toFixed(3));
  faceRoot.style.setProperty("--avatar-energy", avatarEnergy.toFixed(3));
  faceRoot.style.setProperty("--avatar-presence", avatarPresence.toFixed(3));
  faceRoot.style.setProperty("--avatar-shift-x", `${shellShiftX.toFixed(2)}px`);
  faceRoot.style.setProperty("--avatar-shift-y", `${shellShiftY.toFixed(2)}px`);
  faceRoot.style.setProperty("--avatar-scale", shellScale.toFixed(3));
  faceRoot.style.setProperty("--avatar-tilt", `${shellTilt.toFixed(2)}deg`);
  faceRoot.style.setProperty("--avatar-opacity", opacity.toFixed(3));
  faceRoot.style.setProperty("--avatar-saturation", saturation.toFixed(3));
  faceRoot.style.setProperty("--avatar-contrast", contrast.toFixed(3));
  faceRoot.style.setProperty("--avatar-brightness", brightness.toFixed(3));
  faceRoot.style.setProperty("--avatar-halo-opacity", haloOpacity.toFixed(3));
  faceRoot.style.setProperty("--avatar-scan-opacity", scanOpacity.toFixed(3));
  faceRoot.style.setProperty("--avatar-neural-opacity", neuralOpacity.toFixed(3));
  faceRoot.style.setProperty("--avatar-ring-opacity", ringOpacity.toFixed(3));
  faceRoot.style.setProperty("--avatar-neural-speed", `${neuralSpeed.toFixed(2)}s`);
  faceRoot.style.setProperty("--avatar-accent-rgb", palette.accentRgb);
  faceRoot.style.setProperty("--avatar-soft-rgb", palette.softRgb);
  faceRoot.style.setProperty("--avatar-hot-rgb", palette.hotRgb);
  document.body.dataset.PHOEBUSMood = currentMood;
}

function scheduleMoodReset(ms = 3600) {
  if (moodResetTimer) {
    clearTimeout(moodResetTimer);
  }
  moodResetTimer = setTimeout(() => {
    currentMood = currentState === "thinking" ? "serious" : "neutral";
    faceAvatar.setMood(currentMood);
    renderFace();
  }, ms);
}

function cancelPendingExpressionFallback() {
  if (pendingExpressionTimer) {
    clearTimeout(pendingExpressionTimer);
    pendingExpressionTimer = null;
  }
  pendingExpressionId = "";
}

function cancelTimedLipsync() {
  for (const timer of timedLipsyncTimers) {
    clearTimeout(timer);
  }
  timedLipsyncTimers = [];
}

function setCurrentViseme(state) {
  currentViseme = state;
  renderFace();
}

function stopVisemeSequence() {
  cancelPendingExpressionFallback();
  cancelTimedLipsync();
  if (visemeTimer) {
    clearTimeout(visemeTimer);
    visemeTimer = null;
  }
  setCurrentViseme(getRestViseme());
}

function tokenizeSpeech(text) {
  const normalized = normalizeSpeech(text).replace(/[^a-z\s]/g, " ");
  const words = normalized.split(/\s+/).filter(Boolean);
  const tokens = [];

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

function visemeForToken(token) {
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

function buildVisemeFrames(text) {
  return tokenizeSpeech(text)
    .slice(0, 72)
    .map((token) => visemeForToken(token));
}

function startVisemeSequence(text) {
  const frames = buildVisemeFrames(text);
  stopVisemeSequence();

  if (!frames.length) {
    return;
  }

  let index = 0;
  const step = () => {
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

function scheduleExpressionFallback(text, utteranceId) {
  cancelPendingExpressionFallback();
  pendingExpressionId = utteranceId || "";
  pendingExpressionTimer = setTimeout(() => {
    pendingExpressionTimer = null;
    pendingExpressionId = "";
    startVisemeSequence(text);
  }, 180);
}

function startTimedLipsync(frames, utteranceId) {
  if (!Array.isArray(frames) || !frames.length) {
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

function rememberPendingLipsync(frames, utteranceId) {
  if (!utteranceId || !Array.isArray(frames) || !frames.length) {
    return;
  }
  pendingLipsyncById.set(utteranceId, frames);
  if (pendingLipsyncById.size > 8) {
    const oldestKey = pendingLipsyncById.keys().next().value;
    pendingLipsyncById.delete(oldestKey);
  }
}

function consumePendingLipsync(utteranceId) {
  if (!utteranceId || !pendingLipsyncById.has(utteranceId)) {
    return null;
  }
  const frames = pendingLipsyncById.get(utteranceId);
  pendingLipsyncById.delete(utteranceId);
  return frames || null;
}

function startSpeechAnimation(speechMeta = {}) {
  const utteranceId = speechMeta.id || "";
  const text = cleanSpeechText(speechMeta.text || "");

  activeSpeechId = utteranceId;
  if (text) {
    consumeExpressionText(text, { id: utteranceId });
  }

  const frames = consumePendingLipsync(utteranceId);
  if (frames && frames.length) {
    startTimedLipsync(frames, utteranceId);
    return;
  }
  if (text) {
    startVisemeSequence(text);
  }
}

function consumeExpressionText(text, options = {}) {
  const cleaned = cleanSpeechText(text);
  if (!cleaned) {
    return;
  }

  const now = Date.now();
  if (options.id && options.id === lastExpressionId) {
    return;
  }
  if (!options.id && cleaned === lastExpressionText && now - lastExpressionAt < 1500) {
    return;
  }
  lastExpressionText = cleaned;
  lastExpressionAt = now;
  lastExpressionId = options.id || "";

  currentMood = inferMood(cleaned);
  faceAvatar.setMood(currentMood);
  renderFace();
  if (options.animateMouth) {
    startVisemeSequence(cleaned);
  } else if (options.scheduleFallback) {
    scheduleExpressionFallback(cleaned, options.id);
  }
  scheduleMoodReset(clamp(cleaned.length * 38, 2800, 6400));
}

function scheduleGazeLoop() {
  if (gazeTimer) {
    clearTimeout(gazeTimer);
    gazeTimer = null;
  }

  const tick = () => {
    let maxX = 3.4;
    let maxY = 1.8;
    let minDelay = 1500;
    let maxDelay = 2800;

    if (currentState === "thinking") {
      maxX = 6;
      maxY = 3.2;
      minDelay = 800;
      maxDelay = 1500;
    } else if (currentState === "listening") {
      maxX = 4.4;
      maxY = 2.3;
      minDelay = 1000;
      maxDelay = 1800;
    } else if (currentState === "speaking") {
      maxX = 3.6;
      maxY = 2;
      minDelay = 700;
      maxDelay = 1300;
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

function setVoiceLevel(level) {
  const baseline = currentState === "speaking" ? 0.08 : 0;
  currentVoiceLevel = Math.max(baseline, Math.min(1, level || 0));
  faceAvatar.setVolume(Math.max(0, Math.min(1, level || 0)));
  faceRoot.style.setProperty("--PHOEBUS-voice", currentVoiceLevel.toFixed(3));
  renderFace();
}

// ── Gestion des états ───────────────────────────────────────────────────────
const STATE_LABELS = {
  idle:      "en attente",
  listening: "je vous écoute...",
  thinking:  "en réflexion...",
  speaking:  "PHOEBUS répond...",
  proactive: "PHOEBUS observe...",
};

function applyState(state) {
  // Retirer l'ancien état du body
  document.body.classList.remove(
    "state-idle", "state-listening", "state-thinking", "state-speaking", "state-proactive"
  );
  document.body.classList.add(`state-${state}`);
  document.body.dataset.PHOEBUSState = state;
  currentState = state;
  statusEl.textContent = STATE_LABELS[state] || state;

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
    activeSpeechId = "";
    stopVisemeSequence();
  } else {
    currentViseme = getRestViseme();
    renderFace();
  }

  setVoiceLevel(0);
  scheduleGazeLoop();

  // Affichage du bouton Stop global seulement si ca parle
  if (state === "speaking") {
    stopPHOEBUSBtn.style.display = "flex";
  } else {
    stopPHOEBUSBtn.style.display = "none";
  }

  if (micLabelEl) {
    micLabelEl.textContent = "ECOUTE CONTINUE";
  }

  // Mettre à jour l'état de l'orbe 3D
  if (orb) {
    orb.setState(state);
  }
}

renderFace();
applyState("idle");

let currentAudio = null;
let fakeVolumeInterval = null;

// Écouteur pour le bouton stop PHOEBUS
stopPHOEBUSBtn.addEventListener("click", () => {
  window.speechSynthesis.cancel(); // Stoppe l'audio mobile (fallback)
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "stop_audio" })); // Stoppe l'audio PC
  }
  applyState("idle");
});

// ── Badge de connexion ──────────────────────────────────────────────────────
function setConnected(ok) {
  badgeEl.classList.toggle("connected", ok);
  badgeEl.classList.toggle("disconnected", !ok);
  badgeLabelEl.textContent = ok ? "connecté" : "reconnexion...";
}

function setAuthFailed() {
  setConnected(false);
  badgeLabelEl.textContent = "connexion refusée";
  userTextEl.textContent = "⚠ Connexion refusée par le backend.";
}
setConnected(false);

// ── WebSocket ───────────────────────────────────────────────────────────────
// ── Streaming Audio Player ────────────────────────────────────────────────
class StreamingAudioPlayer {
  constructor() {
    this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    this.nextStartTime = 0;
    this.activeId = null;
    this.sources = new Set();
  }

  async playChunk(base64Data, utteranceId) {
    if (this.activeId !== utteranceId) {
      this.stop(); // On arrête le flux précédent
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

      // Animation bouche simplifiée
      const vol = 0.4 + 0.3 * Math.sin(Date.now() / 50);
      setVoiceLevel(vol);

    } catch (e) {
      console.error("[STREAM] Erreur décodage chunk :", e);
    }
  }

  stop() {
    this.sources.forEach(s => {
      try { s.stop(); } catch(e) {}
    });
    this.sources.clear();
    this.activeId = null;
    this.nextStartTime = 0;
  }
}

const streamingPlayer = new StreamingAudioPlayer();

// ── Caméra du téléphone (servie à PHOEBUS sur demande WebSocket) ─────────
//
// Quand le backend envoie {"action":"request_phone_camera","id":..,"facing":..},
// on capture une frame via getUserMedia + canvas, on encode en JPEG base64
// et on renvoie {"action":"phone_camera_result","id":..,"image":..}.
//
// Première utilisation : iOS/Android demande la permission caméra. Une fois
// accordée, les captures suivantes sont instantanées.
let _phoebusCamStream = null;

async function capturerCameraTelephone(reqId, facing) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("getUserMedia non supporté sur ce navigateur");
    }
    // Réutilise le stream s'il est déjà ouvert ; sinon en ouvre un.
    if (!_phoebusCamStream || !_phoebusCamStream.active) {
      const constraints = {
        video: {
          facingMode: facing === "user" ? "user" : { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      };
      _phoebusCamStream = await navigator.mediaDevices.getUserMedia(constraints);
    }

    const track = _phoebusCamStream.getVideoTracks()[0];
    if (!track) throw new Error("Aucun flux vidéo disponible");

    // Capture via ImageCapture si dispo (plus précis), sinon via <video> + canvas.
    let blob;
    if (typeof ImageCapture !== "undefined") {
      const ic = new ImageCapture(track);
      blob = await ic.takePhoto({ imageHeight: 720, imageWidth: 1280 }).catch(
        async () => {
          // Certains devices ne supportent pas takePhoto → fallback grabFrame.
          const frame = await ic.grabFrame();
          const cv = document.createElement("canvas");
          cv.width = frame.width;
          cv.height = frame.height;
          cv.getContext("2d").drawImage(frame, 0, 0);
          return await new Promise((res) =>
            cv.toBlob((b) => res(b), "image/jpeg", 0.85)
          );
        }
      );
    } else {
      const video = document.createElement("video");
      video.srcObject = _phoebusCamStream;
      video.muted = true;
      video.playsInline = true;
      await video.play();
      // Petit délai pour laisser l'autoexposition se stabiliser.
      await new Promise((r) => setTimeout(r, 250));
      const cv = document.createElement("canvas");
      cv.width = video.videoWidth;
      cv.height = video.videoHeight;
      cv.getContext("2d").drawImage(video, 0, 0);
      video.pause();
      blob = await new Promise((res) =>
        cv.toBlob((b) => res(b), "image/jpeg", 0.85)
      );
    }

    if (!blob) throw new Error("Échec encodage JPEG");

    const dataUrl = await new Promise((res) => {
      const fr = new FileReader();
      fr.onloadend = () => res(fr.result);
      fr.readAsDataURL(blob);
    });
    // dataUrl = "data:image/jpeg;base64,XXXX". Le backend supporte les deux
    // formats (avec ou sans le préfixe).
    ws.send(
      JSON.stringify({
        action: "phone_camera_result",
        id: reqId,
        image: dataUrl,
      })
    );
  } catch (err) {
    console.error("[CAM] Erreur capture :", err);
    // On répond quand même pour débloquer la Future côté backend.
    try {
      ws.send(
        JSON.stringify({
          action: "phone_camera_result",
          id: reqId,
          image: "",
          error: String(err && err.message ? err.message : err),
        })
      );
    } catch (_) {}
  }
}

// ── Contrôle du téléphone par PHOEBUS (Tier 1 — Web APIs) ────────────────
//
// Le backend envoie {"action":"phone_command","id":..,"command":"vibrate",...}
// On exécute la commande via les Web APIs du navigateur et on répond
// {"action":"phone_command_result","id":..,...}.

let _phoneTorchStream = null;
let _phoneTorchState = false;
let _phoneAlarmOscillator = null;

function _phoneReply(reqId, payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    action: "phone_command_result",
    id: reqId,
    ...payload,
  }));
}

async function handlePhoneCommand(data) {
  const reqId = data.id;
  const cmd = (data.command || "").toLowerCase();

  try {
    switch (cmd) {
      case "vibrate":
        await _phoneVibrate(reqId, data);
        break;
      case "torch":
        await _phoneTorch(reqId, data);
        break;
      case "gps":
        await _phoneGps(reqId, data);
        break;
      case "clipboard_read":
        await _phoneClipboardRead(reqId, data);
        break;
      case "clipboard_write":
        await _phoneClipboardWrite(reqId, data);
        break;
      case "alarm":
        await _phoneAlarm(reqId, data);
        break;
      case "notification":
        await _phoneNotification(reqId, data);
        break;
      case "battery":
        await _phoneBattery(reqId, data);
        break;
      case "info":
        await _phoneInfo(reqId, data);
        break;
      case "open_app":
        await _phoneOpenApp(reqId, data);
        break;
      case "open_url":
        await _phoneOpenUrl(reqId, data);
        break;
      case "share_text":
        await _phoneShareText(reqId, data);
        break;
      default:
        _phoneReply(reqId, { error: `Commande inconnue: ${cmd}` });
    }
  } catch (err) {
    console.error(`[PHONE] Erreur ${cmd}:`, err);
    _phoneReply(reqId, { error: String(err.message || err) });
  }
}

// ── Vibration ──
async function _phoneVibrate(reqId, data) {
  const pattern = data.pattern || [200, 100, 200, 100, 400];
  if (navigator.vibrate) {
    navigator.vibrate(pattern);
    _phoneReply(reqId, { ok: true });
  } else {
    _phoneReply(reqId, { error: "Vibration API non supportée" });
  }
}

// ── Lampe torche (via MediaStream torch constraint) ──
async function _phoneTorch(reqId, data) {
  const desired = data.state || "toggle";

  try {
    if (!_phoneTorchStream || !_phoneTorchStream.active) {
      _phoneTorchStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
    }

    const track = _phoneTorchStream.getVideoTracks()[0];
    if (!track) throw new Error("Pas de piste vidéo");

    const caps = track.getCapabilities ? track.getCapabilities() : {};
    if (!caps.torch) {
      throw new Error("Lampe torche non supportée sur ce navigateur/appareil");
    }

    let newState;
    if (desired === "toggle") {
      newState = !_phoneTorchState;
    } else {
      newState = desired !== "off";
    }

    await track.applyConstraints({ advanced: [{ torch: newState }] });
    _phoneTorchState = newState;
    _phoneReply(reqId, { ok: true, torch_state: newState ? "on" : "off" });
  } catch (err) {
    _phoneReply(reqId, { error: String(err.message || err) });
  }
}

// ── GPS ──
async function _phoneGps(reqId, _data) {
  if (!navigator.geolocation) {
    _phoneReply(reqId, { error: "Geolocation API non disponible" });
    return;
  }

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      _phoneReply(reqId, {
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
        accuracy: Math.round(pos.coords.accuracy),
        altitude: pos.coords.altitude,
        speed: pos.coords.speed,
        heading: pos.coords.heading,
      });
    },
    (err) => {
      _phoneReply(reqId, { error: `GPS: ${err.message} (code ${err.code})` });
    },
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
  );
}

// ── Clipboard lecture ──
async function _phoneClipboardRead(reqId, _data) {
  try {
    if (!navigator.clipboard || !navigator.clipboard.readText) {
      throw new Error("Clipboard API non disponible");
    }
    const text = await navigator.clipboard.readText();
    _phoneReply(reqId, { text: text || "" });
  } catch (err) {
    _phoneReply(reqId, { error: String(err.message || err) });
  }
}

// ── Clipboard écriture ──
async function _phoneClipboardWrite(reqId, data) {
  try {
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      throw new Error("Clipboard API non disponible");
    }
    await navigator.clipboard.writeText(data.text || "");
    _phoneReply(reqId, { ok: true });
  } catch (err) {
    _phoneReply(reqId, { error: String(err.message || err) });
  }
}

// ── Alarme sonore (Web Audio API — génère un son fort) ──
async function _phoneAlarm(reqId, data) {
  const duration = Math.min(data.duration || 5, 30); // max 30s

  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();

    // Créer un oscillateur à fréquence variable (sirène)
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.connect(gain);
    gain.connect(ctx.destination);

    // Son sirène : alternance 800Hz ↔ 1200Hz
    osc.type = "square";
    osc.frequency.setValueAtTime(800, ctx.currentTime);
    const steps = duration * 4; // 4 transitions par seconde
    for (let i = 0; i < steps; i++) {
      const t = ctx.currentTime + i * 0.25;
      osc.frequency.setValueAtTime(i % 2 === 0 ? 800 : 1200, t);
    }

    gain.gain.setValueAtTime(0.8, ctx.currentTime);
    gain.gain.setValueAtTime(0, ctx.currentTime + duration);

    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + duration);

    _phoneAlarmOscillator = { osc, ctx };

    // Vibrer aussi pendant l'alarme
    if (navigator.vibrate) {
      const vibePattern = [];
      for (let i = 0; i < duration * 2; i++) {
        vibePattern.push(400, 100);
      }
      navigator.vibrate(vibePattern);
    }

    osc.onended = () => {
      ctx.close().catch(() => {});
      _phoneAlarmOscillator = null;
    };

    _phoneReply(reqId, { ok: true, duration });
  } catch (err) {
    _phoneReply(reqId, { error: String(err.message || err) });
  }
}

// ── Notification locale ──
async function _phoneNotification(reqId, data) {
  const title = data.title || "PHOEBUS";
  const message = data.message || "";

  try {
    if (!("Notification" in window)) {
      throw new Error("Notifications non supportées");
    }

    if (Notification.permission === "denied") {
      throw new Error("Notifications bloquées par l'utilisateur");
    }

    if (Notification.permission !== "granted") {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") {
        throw new Error("Permission notifications refusée");
      }
    }

    new Notification(title, {
      body: message,
      icon: "phoebus-face.png",
      vibrate: [200, 100, 200],
      tag: "phoebus-notification",
    });

    _phoneReply(reqId, { ok: true });
  } catch (err) {
    _phoneReply(reqId, { error: String(err.message || err) });
  }
}

// ── Batterie ──
async function _phoneBattery(reqId, _data) {
  try {
    if (!navigator.getBattery) {
      _phoneReply(reqId, { error: "Battery API non disponible" });
      return;
    }
    const battery = await navigator.getBattery();
    _phoneReply(reqId, {
      level: Math.round(battery.level * 100),
      charging: battery.charging,
      chargingTime: battery.chargingTime,
      dischargingTime: battery.dischargingTime,
    });
  } catch (err) {
    _phoneReply(reqId, { error: String(err.message || err) });
  }
}

// ── Infos de l'appareil ──
async function _phoneInfo(reqId, _data) {
  _phoneReply(reqId, {
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    language: navigator.language,
    screen: `${screen.width}x${screen.height}`,
    online: navigator.onLine,
    cookieEnabled: navigator.cookieEnabled,
    maxTouchPoints: navigator.maxTouchPoints || 0,
  });
}

// ── Ouverture d'apps via URL schemes (iOS/Android natif) ──
const APP_URL_SCHEMES = {
  // Streaming & Media
  netflix:       "nflx://",
  "prime video": "aiv://",
  prime:         "aiv://",
  "disney+":     "disneyplus://",
  disney:        "disneyplus://",
  youtube:       "youtube://",
  twitch:        "twitch://",
  spotify:       "spotify://",
  "apple music": "music://",
  musique:       "music://",
  podcasts:      "podcasts://",
  // Social
  instagram:     "instagram://",
  tiktok:        "snssdk1128://",
  twitter:       "twitter://",
  x:             "twitter://",
  snapchat:      "snapchat://",
  facebook:      "fb://",
  linkedin:      "linkedin://",
  reddit:        "reddit://",
  // Messaging
  whatsapp:      "whatsapp://",
  telegram:      "tg://",
  messenger:     "fb-messenger://",
  signal:        "sgnl://",
  discord:       "discord://",
  // Utilities
  maps:          "maps://",
  "google maps": "comgooglemaps://",
  waze:          "waze://",
  uber:          "uber://",
  safari:        "x-web-search://",
  chrome:        "googlechrome://",
  mail:          "mailto:",
  "app store":   "itms-apps://",
  parametres:    "App-prefs://",
  reglages:      "App-prefs://",
  settings:      "App-prefs://",
  camera:        "camera://",
  photos:        "photos-redirect://",
  fichiers:      "shareddocuments://",
  notes:         "mobilenotes://",
  rappels:       "x-apple-reminderkit://",
  calendrier:    "calshow://",
  calculatrice:  "calc://",
  horloge:       "clock-worldclock://",
  sante:         "x-apple-health://",
  wallet:        "shoebox://",
  telephone:     "tel://",
  // Finance
  paypal:        "paypal://",
  revolut:       "revolut://",
  // Raccourcis Apple
  raccourcis:    "shortcuts://",
  shortcuts:     "shortcuts://",
};

async function _phoneOpenApp(reqId, data) {
  const appName = (data.app || data.name || "").toLowerCase().trim();
  if (!appName) {
    _phoneReply(reqId, { error: "Aucun nom d'app fourni" });
    return;
  }

  // Chercher le URL scheme
  let scheme = APP_URL_SCHEMES[appName];
  
  // Recherche partielle
  if (!scheme) {
    for (const [key, url] of Object.entries(APP_URL_SCHEMES)) {
      if (key.includes(appName) || appName.includes(key)) {
        scheme = url;
        break;
      }
    }
  }

  if (!scheme) {
    // Fallback : recherche dans l'App Store / Play Store
    const searchUrl = /iphone|ipad|ios/i.test(navigator.userAgent)
      ? `https://apps.apple.com/search?term=${encodeURIComponent(appName)}`
      : `https://play.google.com/store/search?q=${encodeURIComponent(appName)}`;
    window.open(searchUrl, "_blank");
    _phoneReply(reqId, { ok: true, method: "store_search", app: appName });
    return;
  }

  try {
    window.location.href = scheme;
    _phoneReply(reqId, { ok: true, method: "url_scheme", app: appName, scheme });
  } catch (err) {
    _phoneReply(reqId, { error: String(err.message || err) });
  }
}

async function _phoneOpenUrl(reqId, data) {
  const url = (data.url || "").trim();
  if (!url) {
    _phoneReply(reqId, { error: "Aucune URL fournie" });
    return;
  }
  try {
    window.open(url, "_blank");
    _phoneReply(reqId, { ok: true, url });
  } catch (err) {
    _phoneReply(reqId, { error: String(err.message || err) });
  }
}

async function _phoneShareText(reqId, data) {
  const text = data.text || "";
  const title = data.title || "PHOEBUS";
  try {
    if (navigator.share) {
      await navigator.share({ title, text });
      _phoneReply(reqId, { ok: true });
    } else {
      _phoneReply(reqId, { error: "Web Share API non supportée" });
    }
  } catch (err) {
    _phoneReply(reqId, { error: String(err.message || err) });
  }
}

function connectWS() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }

  ws = new WebSocket(WS_URL);

  ws.addEventListener("open", () => {
    console.log("[WS] Connecté à", WS_URL);
    setConnected(true);
    ws.send(JSON.stringify({
      type: "auth",
      client_type: "mobile",
      client_name: navigator.userAgent.slice(0, 80),
      pair_device_id: window.localStorage.getItem(PAIR_DEVICE_ID_KEY) || "",
      pair_secret: window.localStorage.getItem(PAIR_SECRET_KEY) || "",
    }));
  });

  ws.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(event.data);

      if (data.action === "reload_ui") {
        console.log("[SYSTEM] Synchro moteur... rechargement.");
        setTimeout(() => window.location.reload(), 300);
        return;
      }

      if (data.action === "auth_ok") {
        if (data.pair_device_id && data.pair_secret) {
          window.localStorage.setItem(PAIR_DEVICE_ID_KEY, data.pair_device_id);
          window.localStorage.setItem(PAIR_SECRET_KEY, data.pair_secret);
        }
        setConnected(true);
        userTextEl.textContent = "";
        return;
      }

      if (data.action === "auth_failed") {
        setAuthFailed();
        return;
      }

      if (data.action === "PHOEBUS_expression" && data.text) {
        consumeExpressionText(data.text, { id: data.id });
        return;
      }

      if (data.action === "PHOEBUS_lipsync" && Array.isArray(data.frames)) {
        rememberPendingLipsync(data.frames, data.id);
        if (data.id && data.id === activeSpeechId && currentState === "speaking") {
          const activeFrames = consumePendingLipsync(data.id);
          if (activeFrames && activeFrames.length) {
            startTimedLipsync(activeFrames, data.id);
          }
        }
        return;
      }

      if (data.action === "user_transcript" && data.text) {
        afficherTexteUtilisateur(data.text);
        return;
      }

      // État de l'orbe (envoyé par le backend lors de ses propres actions)
      if (data.action === "set_state" && data.state) {
        if (data.state !== "speaking") {
          applyState(data.state);
        }
      }

      if (data.action === "PHOEBUS_audio_chunk" && data.audio_b64) {
        streamingPlayer.playChunk(data.audio_b64, data.id);
        return;
      }

      // Réponse textuelle de PHOEBUS destinée au mobile avec audio distant (même voix que web)
      if (data.action === "PHOEBUS_audio" && data.audio_b64) {
        afficherReponsePHOEBUS(data.text);
        jouerAudioBase64(data.audio_b64, { id: data.id, text: data.text });
      }
      // Fallback ancienne méthode (sans audio)
      else if (data.action === "PHOEBUS_response" && data.text) {
        afficherReponsePHOEBUS(data.text);
        parleSynthese(data.text, { id: data.id, text: data.text });
      }
      else if (data.action === "request_phone_camera" && data.id) {
        // Le backend nous demande une frame caméra (PHOEBUS veut voir).
        capturerCameraTelephone(data.id, data.facing || "environment").catch(
          (err) => console.error("[CAM] Capture KO :", err)
        );
      }
      // ── Commandes de contrôle du téléphone (Tier 1) ──────────────────
      else if (data.action === "phone_command" && data.id) {
        handlePhoneCommand(data).catch(
          (err) => console.error("[PHONE] Commande KO :", err)
        );
      }
    } catch (e) {
      console.error("[WS] Erreur parsing message :", e);
    }
  });

  ws.addEventListener("close", () => {
    console.log("[WS] Déconnecté. Reconnexion dans", RECONNECT_DELAY_MS, "ms...");
    setConnected(false);
    applyState("idle");
    scheduleReconnect();
  });

  ws.addEventListener("error", () => {
    setConnected(false);
  });
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWS();
  }, RECONNECT_DELAY_MS);
}

function sendCommand(text) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.warn("[WS] WebSocket non connecté, commande ignorée.");
    return false;
  }
  ws.send(JSON.stringify({ type: "mobile_command", text }));
  return true;
}

// ── Affichage dialogue ──────────────────────────────────────────────────────
function afficherTexteUtilisateur(text) {
  userTextEl.textContent = `"${text}"`;
  PHOEBUSTextEl.textContent = "";
}

function afficherReponsePHOEBUS(text) {
  const textePropre = cleanSpeechText(text);
  PHOEBUSTextEl.textContent = textePropre || text;
}

function jouerAudioBase64(base64) {
  if (currentAudio) {
    currentAudio.pause();
  }
  window.speechSynthesis.cancel();

  applyState("speaking");

  currentAudio = new Audio("data:audio/mp3;base64," + base64);
  currentAudio.play().catch(e => console.error("[AUDIO] Erreur lecture :", e));

  // Fake volume for ORB
  if (fakeVolumeInterval) clearInterval(fakeVolumeInterval);
  fakeVolumeInterval = setInterval(() => {
    const t = Date.now() / 50;
    const vol = Math.max(0.1, Math.min(1.0, 0.4 + 0.3 * Math.sin(t) + 0.2 * Math.sin(t * 0.5) + (Math.random() * 0.2 - 0.1)));
    if (orb) {
      orb.setVolume(vol);
    }
    setVoiceLevel(vol);
  }, 50);

  currentAudio.addEventListener("ended", () => {
    applyState("idle");
    if (fakeVolumeInterval) {
      clearInterval(fakeVolumeInterval);
      fakeVolumeInterval = null;
    }
    if (orb) orb.setVolume(0);
    setVoiceLevel(0);
    currentAudio = null;
  });

  currentAudio.addEventListener("pause", () => {
    if (currentState === "speaking") {
      applyState("idle");
    }
    if (fakeVolumeInterval) {
      clearInterval(fakeVolumeInterval);
      fakeVolumeInterval = null;
    }
    if (orb) orb.setVolume(0);
    setVoiceLevel(0);
  });
}

// ── TTS Web (Speech Synthesis) ──────────────────────────────────────────────
let synthVoice = null;

function chargerVoix() {
  const voices = window.speechSynthesis.getVoices();
  // Chercher une voix française de bonne qualité
  synthVoice =
    voices.find(v => v.lang === "fr-FR" && v.name.includes("Google")) ||
    voices.find(v => v.lang === "fr-FR") ||
    voices.find(v => v.lang.startsWith("fr")) ||
    null;
  console.log("[TTS] Voix sélectionnée :", synthVoice?.name || "par défaut");
}

window.speechSynthesis.addEventListener("voiceschanged", chargerVoix);
chargerVoix();

function parleSynthese(texte) {
  // Annuler toute synthèse en cours
  window.speechSynthesis.cancel();

  const textePropre = cleanSpeechText(texte);

  if (!textePropre) return;

  applyState("speaking");
  consumeExpressionText(textePropre);
  setVoiceLevel(0.12);

  const utterance = new SpeechSynthesisUtterance(textePropre);
  utterance.lang = SPEECH_LANG;
  utterance.rate = 0.95;
  utterance.pitch = 0.9;
  utterance.volume = 1.0;

  if (synthVoice) {
    utterance.voice = synthVoice;
  }

  utterance.addEventListener("end", () => {
    applyState("idle");
    setVoiceLevel(0);
  });

  utterance.addEventListener("error", (e) => {
    console.warn("[TTS] Erreur synthèse :", e.error);
    applyState("idle");
    setVoiceLevel(0);
  });

  window.speechSynthesis.speak(utterance);
}

// ── STT Web Speech API ──────────────────────────────────────────────────────
const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

let recognition = null;
let recognitionHadError = false;
let autoListenEnabled = true;
let restartListenTimer = null;
let dispatchCommandTimer = null;
let capturedFinalText = "";
let suppressNextEndDispatch = false;
let browserMicRetryAfter = 0;
let browserSpeechBlocked = false;
let browserSpeechBlockedLogged = false;

function shouldDispatchVoiceCommand(text) {
  const value = (text || "").trim();
  return WAKE_WORD_RE.test(value) || CONFIRMATION_RE.test(value);
}

function canAutoListen() {
  return (
    autoListenEnabled &&
    recognition &&
    !browserSpeechBlocked &&
    ws &&
    ws.readyState === WebSocket.OPEN &&
    Date.now() >= browserMicRetryAfter &&
    currentState !== "thinking" &&
    currentState !== "speaking"
  );
}

function startRecognition(reason = "auto") {
  if (!recognition || isListening || !canAutoListen()) return;
  window.speechSynthesis.cancel();
  try {
    recognition.start();
    console.log("[STT] Démarrage micro :", reason);
  } catch (e) {
    const name = e && e.name ? e.name : "";
    if (name === "NotAllowedError" || name === "SecurityError") {
      blockBrowserSpeech("start-denied");
      return;
    }
    console.warn("[STT] Impossible de démarrer :", e);
    scheduleListenRestart(1200);
  }
}

function scheduleListenRestart(delay = 650) {
  if (browserSpeechBlocked) return;
  if (restartListenTimer) clearTimeout(restartListenTimer);
  restartListenTimer = setTimeout(() => {
    restartListenTimer = null;
    if (!autoListenEnabled || !recognition) return;
    if (!canAutoListen()) {
      scheduleListenRestart(1000);
      return;
    }
    startRecognition("restart");
  }, delay);
}

function blockBrowserSpeech(reason = "permission-denied") {
  browserSpeechBlocked = true;
  autoListenEnabled = false;
  browserMicRetryAfter = Number.MAX_SAFE_INTEGER;
  if (restartListenTimer) {
    clearTimeout(restartListenTimer);
    restartListenTimer = null;
  }
  if (!browserSpeechBlockedLogged) {
    browserSpeechBlockedLogged = true;
    console.info("[STT] Micro navigateur indisponible, écoute backend conservée :", reason);
  }
  isListening = false;
  recognitionHadError = false;
  userTextEl.textContent = "";
  statusEl.textContent = "en attente";
  applyState("idle");
}

function dispatchCapturedText(text) {
  const command = (text || "").replace(/^"|"$/g, "").trim();
  capturedFinalText = "";
  if (!command) {
    applyState("idle");
    scheduleListenRestart(400);
    return;
  }

  if (!shouldDispatchVoiceCommand(command)) {
    console.log("[STT] Phrase ignorée sans mot de réveil :", command);
    userTextEl.textContent = "";
    applyState("idle");
    scheduleListenRestart(300);
    return;
  }

  console.log("[STT] Commande envoyée :", command);
  userTextEl.textContent = `"${command}"`;
  applyState("thinking");
  if (isListening) {
    suppressNextEndDispatch = true;
    try { recognition.stop(); } catch (_) {}
  }
  const envoyé = sendCommand(command);
  if (!envoyé) {
    applyState("idle");
    userTextEl.textContent = "⚠ Non connecté à PHOEBUS";
  }
  scheduleListenRestart(2200);
}

if (BROWSER_STT_ENABLED && SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.lang           = SPEECH_LANG;
  recognition.continuous     = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.addEventListener("start", () => {
    isListening = true;
    recognitionHadError = false;
    capturedFinalText = "";
    // Interruption : si on commence à parler, PHOEBUS se tait
    streamingPlayer.stop();
    cancelTimedLipsync();

    applyState("listening");
    userTextEl.textContent  = "";
    PHOEBUSTextEl.textContent = "";
    if (micLabelEl) micLabelEl.textContent = "ECOUTE CONTINUE";
    console.log("[STT] Écoute démarrée.");
  });

  recognition.addEventListener("result", (event) => {
    let interim   = "";
    let final_txt = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        final_txt += transcript;
      } else {
        interim += transcript;
      }
    }

    // Affichage en temps réel des résultats intermédiaires
    userTextEl.textContent = `"${final_txt || interim}"`;

    if (final_txt) {
      console.log("[STT] Résultat final :", final_txt);
      capturedFinalText = `${capturedFinalText} ${final_txt}`.trim();
      if (dispatchCommandTimer) clearTimeout(dispatchCommandTimer);
      dispatchCommandTimer = setTimeout(() => {
        dispatchCommandTimer = null;
        dispatchCapturedText(capturedFinalText);
      }, 850);
    }
  });

  recognition.addEventListener("end", () => {
    isListening = false;
    if (micLabelEl) micLabelEl.textContent = "ECOUTE CONTINUE";
    if (suppressNextEndDispatch) {
      suppressNextEndDispatch = false;
      scheduleListenRestart(900);
      return;
    }
    if (recognitionHadError) {
      recognitionHadError = false;
      scheduleListenRestart(900);
      return;
    }
    const texteCapture = capturedFinalText || userTextEl.textContent.replace(/^"|"$/g, "").trim();
    console.log("[STT] Fin écoute. Texte :", texteCapture);

    if (texteCapture) {
      dispatchCapturedText(texteCapture);
    } else {
      applyState("idle");
      scheduleListenRestart(450);
    }
  });

  recognition.addEventListener("error", (event) => {
    isListening = false;
    recognitionHadError = true;
    applyState("idle");

    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      blockBrowserSpeech(event.error);
    } else if (event.error === "no-speech") {
      userTextEl.textContent = "";
      scheduleListenRestart(500);
    } else {
      console.warn("[STT] Erreur :", event.error);
      userTextEl.textContent = "";
      statusEl.textContent = "en attente";
      scheduleListenRestart(1200);
    }
  });

} else {
  if (micBtn) micBtn.disabled = true;
  statusEl.textContent = "en attente";
  console.info("[STT] Reconnaissance navigateur désactivée : le backend est la source vocale unique.");
}

// ── Relance micro best-effort. Le bouton est masque, conserve seulement
//    comme cible technique pour les plateformes qui exigent un geste humain.
micBtn.addEventListener("click", () => {
  if (!BROWSER_STT_ENABLED) return;
  if (!recognition) return;

  autoListenEnabled = true;
  browserSpeechBlocked = false;
  browserMicRetryAfter = 0;
  if (currentState === "thinking" || currentState === "speaking") {
    scheduleListenRestart(800);
    return;
  }
  startRecognition("manual");
});

// ── Démarrage ───────────────────────────────────────────────────────────────
connectWS();
if (BROWSER_STT_ENABLED) {
  scheduleListenRestart(900);
}
console.log("[PHOEBUS MOBILE] Interface initialisée. WebSocket :", WS_URL);
