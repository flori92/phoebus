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
const WS_TOKEN_STORAGE_KEY = "jarvis_ws_token";

function getStoredToken() {
  const params = new URLSearchParams(window.location.search);
  const tokenFromUrl = (params.get("token") || "").trim();
  if (tokenFromUrl) {
    localStorage.setItem(WS_TOKEN_STORAGE_KEY, tokenFromUrl);
    return tokenFromUrl;
  }
  return (localStorage.getItem(WS_TOKEN_STORAGE_KEY) || "").trim();
}

function requestToken() {
  const token = window.prompt("Token JARVIS", getStoredToken()) || "";
  const trimmed = token.trim();
  if (trimmed) {
    localStorage.setItem(WS_TOKEN_STORAGE_KEY, trimmed);
  }
  return trimmed;
}

// ── DOM Refs ────────────────────────────────────────────────────────────────
const badgeEl      = document.getElementById("connection-badge");
const badgeLabelEl = document.getElementById("connection-label");
const statusEl     = document.getElementById("status-text");
const userTextEl   = document.getElementById("user-text");
const jarvisTextEl = document.getElementById("jarvis-text");
const micBtn       = document.getElementById("mic-btn");
const micIcon      = micBtn.querySelector(".mic-icon");
const stopIcon     = micBtn.querySelector(".stop-icon");
const micLabelEl   = document.getElementById("mic-label");
const stopJarvisBtn= document.getElementById("stop-jarvis-btn");
const avatarEl     = document.getElementById("avatar-face");

// ── ORB 3D ──────────────────────────────────────────────────────────────────
let orb = null;
if (typeof createOrb === "function") {
  const canvas = document.getElementById("orb-canvas");
  if (canvas) {
    orb = createOrb(canvas);
  }
}

// ── HTTPS Warning ───────────────────────────────────────────────────────────
if (window.location.protocol !== "https:" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") {
  const warning = document.getElementById("https-warning");
  if (warning) {
    warning.style.display = "block";
    const closeBtn = document.getElementById("close-warning-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        warning.style.display = "none";
      });
    }
  }
}

// ── État de l'application ───────────────────────────────────────────────────
let currentState = "idle";
let ws           = null;
let isListening  = false;
let reconnectTimer = null;
let authToken = getStoredToken();
const faceRoot = document.documentElement;
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
const FACE_FRAME_URLS = {
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

class FaceAvatar {
  constructor(imageEl) {
    this.imageEl = imageEl;
    this.state = "idle";
    this.mood = "neutral";
    this.activeFrame = null;
    this.targetVolume = 0;
    this.smoothedVolume = 0;
    this.lastVolumeAt = 0;
    this.blinking = false;
    this.blinkTimer = null;
    this.blinkHoldTimer = null;
    this.mouthTimer = null;

    this.preloadFrames();
    this.applyFrame("neutral");
    this.scheduleBlink();
  }

  setState(state) {
    this.state = state;

    if (state === "speaking") {
      this.stopBlink();
      this.startMouthLoop();
    } else {
      this.stopMouthLoop();
      this.targetVolume = 0;
      this.smoothedVolume = 0;
      this.scheduleBlink();
    }

    this.updateFrame();
  }

  setMood(mood) {
    this.mood = mood;
    this.updateFrame();
  }

  setVolume(volume) {
    this.targetVolume = clamp(volume || 0, 0, 1);
    this.lastVolumeAt = Date.now();

    if (this.state === "speaking" && !this.mouthTimer) {
      this.startMouthLoop();
    }
  }

  preloadFrames() {
    Object.values(FACE_FRAME_URLS).forEach((url) => {
      const image = new Image();
      image.decoding = "async";
      image.src = url;
    });
  }

  applyFrame(frame) {
    if (!this.imageEl) {
      return;
    }
    if (this.activeFrame !== frame) {
      this.imageEl.src = FACE_FRAME_URLS[frame];
    }
    this.activeFrame = frame;
    this.imageEl.dataset.frame = frame;
    document.body.dataset.jarvisFrame = frame;
  }

  resolveIdleFrame() {
    if (this.state === "thinking") {
      return "thinking";
    }

    if (this.state === "listening") {
      switch (this.mood) {
        case "warm":
        case "joy":
          return "smile";
        case "serious":
          return "serious";
        case "alert":
          return "alert";
        default:
          return "neutral";
      }
    }

    switch (this.mood) {
      case "warm":
      case "joy":
        return "smile";
      case "alert":
        return "alert";
      case "serious":
        return "serious";
      default:
        return "neutral";
    }
  }

  resolveSpeakingFrame() {
    if (this.smoothedVolume >= 0.58) {
      return "speak-open";
    }
    if (this.smoothedVolume >= 0.34) {
      return "speak-oh";
    }
    if (this.smoothedVolume >= 0.14) {
      return "speak-light";
    }
    return this.resolveIdleFrame();
  }

  updateFrame() {
    if (this.blinking && this.state !== "speaking") {
      this.applyFrame("blink");
      return;
    }

    if (this.state === "speaking") {
      this.applyFrame(this.resolveSpeakingFrame());
      return;
    }

    this.applyFrame(this.resolveIdleFrame());
  }

  startMouthLoop() {
    if (this.mouthTimer) {
      return;
    }

    const cadenceMs = Math.round(1000 / 12);
    this.mouthTimer = window.setInterval(() => {
      if (Date.now() - this.lastVolumeAt > cadenceMs * 1.5) {
        this.targetVolume *= 0.72;
        if (this.targetVolume < 0.01) {
          this.targetVolume = 0;
        }
      }

      this.smoothedVolume += (this.targetVolume - this.smoothedVolume) * 0.38;
      if (this.smoothedVolume < 0.01) {
        this.smoothedVolume = 0;
      }

      this.updateFrame();
    }, cadenceMs);
  }

  stopMouthLoop() {
    if (this.mouthTimer) {
      clearInterval(this.mouthTimer);
      this.mouthTimer = null;
    }
  }

  scheduleBlink() {
    this.clearBlinkTimers();

    if (this.state === "speaking") {
      return;
    }

    this.blinkTimer = setTimeout(
      () => this.playBlinkSequence(),
      this.state === "thinking" ? rand(2200, 4200) : rand(2800, 5200)
    );
  }

  stopBlink() {
    this.clearBlinkTimers();
    this.blinking = false;
  }

  playBlinkSequence() {
    this.blinking = true;
    this.updateFrame();

    this.blinkHoldTimer = setTimeout(() => {
      this.blinking = false;
      this.updateFrame();

      if (Math.random() < 0.22) {
        this.blinkTimer = setTimeout(() => {
          this.blinking = true;
          this.updateFrame();
          this.blinkHoldTimer = setTimeout(() => {
            this.blinking = false;
            this.updateFrame();
            this.scheduleBlink();
          }, rand(70, 105));
        }, rand(70, 135));
        return;
      }

      this.scheduleBlink();
    }, rand(92, 132));
  }

  clearBlinkTimers() {
    if (this.blinkTimer) {
      clearTimeout(this.blinkTimer);
      this.blinkTimer = null;
    }
    if (this.blinkHoldTimer) {
      clearTimeout(this.blinkHoldTimer);
      this.blinkHoldTimer = null;
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
const faceAvatar = new FaceAvatar(avatarEl);

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

  faceRoot.style.setProperty("--jarvis-gaze-x", `${currentGaze.x.toFixed(2)}px`);
  faceRoot.style.setProperty("--jarvis-gaze-y", `${currentGaze.y.toFixed(2)}px`);
  faceRoot.style.setProperty("--jarvis-eye-open", eyeOpen.toFixed(3));
  faceRoot.style.setProperty("--jarvis-eye-wide", eyeWide.toFixed(3));
  faceRoot.style.setProperty("--jarvis-mouth-open", mouthOpen.toFixed(3));
  faceRoot.style.setProperty("--jarvis-mouth-width", mouthWidth.toFixed(3));
  faceRoot.style.setProperty("--jarvis-mouth-skew", mouthSkew.toFixed(3));
  faceRoot.style.setProperty("--jarvis-mouth-lift", mouthLift.toFixed(3));
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
  document.body.dataset.jarvisMood = currentMood;
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
  faceRoot.style.setProperty("--jarvis-voice", currentVoiceLevel.toFixed(3));
  renderFace();
}

// ── Gestion des états ───────────────────────────────────────────────────────
const STATE_LABELS = {
  idle:      "en attente",
  listening: "je vous écoute...",
  thinking:  "en réflexion...",
  speaking:  "jarvis répond...",
};

function applyState(state) {
  // Retirer l'ancien état du body
  document.body.classList.remove(
    "state-idle", "state-listening", "state-thinking", "state-speaking"
  );
  document.body.classList.add(`state-${state}`);
  document.body.dataset.jarvisState = state;
  currentState = state;
  statusEl.textContent = STATE_LABELS[state] || state;
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
    stopJarvisBtn.style.display = "flex";
  } else {
    stopJarvisBtn.style.display = "none";
  }

  // Icône microphone
  if (state === "listening") {
    micIcon.style.display = "none";
    stopIcon.style.display = "block";
    micLabelEl.textContent = "APPUYER POUR ARRÊTER";
  } else {
    micIcon.style.display = "block";
    stopIcon.style.display = "none";
    micLabelEl.textContent = "APPUYER POUR PARLER";
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

// Écouteur pour le bouton stop JARVIS
stopJarvisBtn.addEventListener("click", () => {
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
setConnected(false);

// ── WebSocket ───────────────────────────────────────────────────────────────
// ── Streaming Audio Player ────────────────────────────────────────────────
class StreamingAudioPlayer {
  constructor() {
    this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    this.nextStartTime = 0;
    this.activeId = null;
  }

  async playChunk(base64Data, utteranceId) {
    if (this.activeId !== utteranceId) {
      this.activeId = utteranceId;
      this.nextStartTime = this.audioCtx.currentTime + 0.1;
      applyState("speaking");
    }

    const binary = atob(base64Data);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);

    try {
      const audioBuffer = await this.audioCtx.decodeAudioData(bytes.buffer);
      const source = this.audioCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.audioCtx.destination);

      const startTime = Math.max(this.audioCtx.currentTime, this.nextStartTime);
      source.start(startTime);
      this.nextStartTime = startTime + audioBuffer.duration;

      source.onended = () => {
        if (this.audioCtx.currentTime >= this.nextStartTime - 0.1) {
          applyState("idle");
          setVoiceLevel(0);
        }
      };

      // Animation bouche simplifiée pendant le streaming
      const vol = 0.4 + 0.3 * Math.sin(Date.now() / 50);
      setVoiceLevel(vol);

    } catch (e) {
      console.error("[STREAM] Erreur décodage chunk :", e);
    }
  }

  stop() {
    this.activeId = null;
    this.nextStartTime = 0;
  }
}

const streamingPlayer = new StreamingAudioPlayer();

function connectWS() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }

  ws = new WebSocket(WS_URL);

  ws.addEventListener("open", () => {
    console.log("[WS] Connecté à", WS_URL);
    setConnected(true);
    ws.send(JSON.stringify({
      type: "auth",
      token: authToken,
      client_type: "mobile",
      client_name: navigator.userAgent.slice(0, 80),
    }));
  });

  ws.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(event.data);

      if (data.action === "auth_ok") {
        return;
      }
      if (data.action === "auth_required") {
        authToken = requestToken();
        if (!authToken) {
          setConnected(false);
          return;
        }
        ws.send(JSON.stringify({
          type: "auth",
          token: authToken,
          client_type: "mobile",
          client_name: navigator.userAgent.slice(0, 80),
        }));
        return;
      }
      if (data.action === "auth_failed") {
        localStorage.removeItem(WS_TOKEN_STORAGE_KEY);
        authToken = requestToken();
        if (!authToken) {
          setConnected(false);
          return;
        }
        ws.send(JSON.stringify({
          type: "auth",
          token: authToken,
          client_type: "mobile",
          client_name: navigator.userAgent.slice(0, 80),
        }));
        return;
      }

      if (data.action === "jarvis_expression" && data.text) {
        consumeExpressionText(data.text, { id: data.id });
        return;
      }

      if (data.action === "jarvis_lipsync" && Array.isArray(data.frames)) {
        rememberPendingLipsync(data.frames, data.id);
        if (data.id && data.id === activeSpeechId && currentState === "speaking") {
          const activeFrames = consumePendingLipsync(data.id);
          if (activeFrames && activeFrames.length) {
            startTimedLipsync(activeFrames, data.id);
          }
        }
        return;
      }

      // État de l'orbe (envoyé par le backend lors de ses propres actions)
      if (data.action === "set_state" && data.state) {
        // Ignorer les états de microphone local du PC ("listening", "active") car le mobile gère son propre micro
        if (data.state === "listening" || data.state === "active") return;
        // Si le mobile est en train d'écouter, on ne le force pas en idle non plus
        if (data.state === "idle" && isListening) return;

        // On ignore l'état "speaking" du PC uniquement si on utilise le TTS local (SpeechSynthesis).
        // Mais maintenant on joue l'audio distant, donc on peut accepter l'état speaking, bien qu'on l'applique localement au lancement de l'audio.
        if (data.state !== "speaking") {
          applyState(data.state);
        }
      }

      if (data.action === "jarvis_audio_chunk" && data.audio_b64) {
        streamingPlayer.playChunk(data.audio_b64, data.id);
        return;
      }

      // Réponse textuelle de JARVIS destinée au mobile avec audio distant (même voix que web)
      if (data.action === "jarvis_audio" && data.audio_b64) {
        afficherReponseJarvis(data.text);
        jouerAudioBase64(data.audio_b64, { id: data.id, text: data.text });
      }
      // Fallback ancienne méthode (sans audio)
      else if (data.action === "jarvis_response" && data.text) {
        afficherReponseJarvis(data.text);
        parleSynthese(data.text, { id: data.id, text: data.text });
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
  jarvisTextEl.textContent = "";
}

function afficherReponseJarvis(text) {
  const textePropre = cleanSpeechText(text);
  jarvisTextEl.textContent = textePropre || text;
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

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.lang           = SPEECH_LANG;
  recognition.continuous     = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.addEventListener("start", () => {
    isListening = true;
    applyState("listening");
    userTextEl.textContent  = "";
    jarvisTextEl.textContent = "";
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
    }
  });

  recognition.addEventListener("end", () => {
    isListening = false;
    const texteCapture = userTextEl.textContent.replace(/^"|"$/g, "").trim();
    console.log("[STT] Fin écoute. Texte :", texteCapture);

    if (texteCapture) {
      applyState("thinking");
      const envoyé = sendCommand(texteCapture);
      if (!envoyé) {
        applyState("idle");
        userTextEl.textContent = "⚠ Non connecté à JARVIS";
      }
    } else {
      applyState("idle");
    }
  });

  recognition.addEventListener("error", (event) => {
    console.warn("[STT] Erreur :", event.error);
    isListening = false;
    applyState("idle");

    if (event.error === "not-allowed") {
      userTextEl.textContent =
        "⚠ Micro non autorisé. Activez le dans chrome://flags";
    } else if (event.error === "no-speech") {
      userTextEl.textContent = "";
    } else {
      userTextEl.textContent = `⚠ Erreur micro : ${event.error}`;
    }
  });

} else {
  // SpeechRecognition non supporté
  micBtn.disabled = true;
  statusEl.textContent = "micro non supporté sur ce navigateur";
  console.error("[STT] SpeechRecognition non disponible.");
}

// ── Bouton microphone ───────────────────────────────────────────────────────
micBtn.addEventListener("click", () => {
  if (!recognition) return;

  // Bloquer si JARVIS pense ou parle
  if (currentState === "thinking" || currentState === "speaking") return;

  if (isListening) {
    // Arrêter l'écoute
    recognition.stop();
  } else {
    // Annuler TTS en cours si nécessaire
    window.speechSynthesis.cancel();
    try {
      recognition.start();
    } catch (e) {
      console.warn("[STT] Impossible de démarrer :", e);
    }
  }
});

// ── Démarrage ───────────────────────────────────────────────────────────────
connectWS();
console.log("[JARVIS MOBILE] Interface initialisée. WebSocket :", WS_URL);
