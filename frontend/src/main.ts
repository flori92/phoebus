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

type JarvisMood =
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

// ── Config ────────────────────────────────────────────────────────────────────
const WS_HOST = window.location.hostname || "localhost";
const WS_SCHEME = window.location.protocol === "https:" ? "wss" : "ws";
const WS_URL = `${WS_SCHEME}://${WS_HOST}:8765`;
const RECONNECT_INTERVAL_MS = 2_000;
const WS_TOKEN_STORAGE_KEY = "jarvis_ws_token";
const FACE_ROOT = document.documentElement;
const MOOD_PRESETS: Record<JarvisMood, MoodPreset> = {
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
  const provided = window.prompt("Token JARVIS", current)?.trim() ?? "";
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

function cleanSpeechText(text: string): string {
  return text.replace(/\{[^}]*\}/gs, " ").replace(/\s+/g, " ").trim();
}

function normalizeSpeech(text: string): string {
  return cleanSpeechText(text)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function inferMood(text: string): JarvisMood {
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

function renderFace(): void {
  const preset = MOOD_PRESETS[currentMood];
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

  FACE_ROOT.style.setProperty("--jarvis-gaze-x", `${currentGaze.x.toFixed(2)}px`);
  FACE_ROOT.style.setProperty("--jarvis-gaze-y", `${currentGaze.y.toFixed(2)}px`);
  FACE_ROOT.style.setProperty("--jarvis-eye-open", eyeOpen.toFixed(3));
  FACE_ROOT.style.setProperty("--jarvis-eye-wide", eyeWide.toFixed(3));
  FACE_ROOT.style.setProperty("--jarvis-mouth-open", mouthOpen.toFixed(3));
  FACE_ROOT.style.setProperty("--jarvis-mouth-width", mouthWidth.toFixed(3));
  FACE_ROOT.style.setProperty("--jarvis-mouth-skew", mouthSkew.toFixed(3));
  FACE_ROOT.style.setProperty("--jarvis-mouth-lift", mouthLift.toFixed(3));
  document.body.dataset.jarvisMood = currentMood;
}

function scheduleMoodReset(ms = 3_600): void {
  if (moodResetTimer) {
    clearTimeout(moodResetTimer);
  }
  moodResetTimer = setTimeout(() => {
    currentMood = currentState === "thinking" ? "serious" : "neutral";
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
    let maxX = 2.4;
    let maxY = 1.4;
    let minDelay = 1_800;
    let maxDelay = 3_200;

    if (currentState === "thinking") {
      maxX = 4.8;
      maxY = 2.8;
      minDelay = 1_100;
      maxDelay = 2_000;
    } else if (currentState === "listening") {
      maxX = 3.2;
      maxY = 1.7;
      minDelay = 1_300;
      maxDelay = 2_400;
    } else if (currentState === "speaking") {
      maxX = 2.2;
      maxY = 1.2;
      minDelay = 900;
      maxDelay = 1_800;
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
const statusEl = document.getElementById("status-text") as HTMLDivElement;
const errorEl = document.getElementById("error-text") as HTMLDivElement;
const badgeEl = document.getElementById("connection-badge") as HTMLDivElement;
const badgeLabelEl = document.getElementById(
  "connection-label"
) as HTMLSpanElement;

// ── Orb ───────────────────────────────────────────────────────────────────────
const orb = createOrb(canvas);

// ── State labels (French) ────────────────────────────────────────────────────
const STATE_LABELS: Record<OrbState, string> = {
  idle: "",
  listening: "ecoute...",
  thinking: "reflexion...",
  speaking: "",
};
let currentState: OrbState = "idle";
let currentMood: JarvisMood = "neutral";
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
  FACE_ROOT.style.setProperty("--jarvis-voice", currentVoiceLevel.toFixed(3));
  renderFace();
}

function applyState(state: OrbState): void {
  currentState = state;
  orb.setState(state);
  statusEl.textContent = STATE_LABELS[state];
  document.body.dataset.jarvisState = state;

  if (state === "listening") {
    currentMood = "alert";
  } else if (state === "thinking") {
    currentMood = "serious";
  } else if (state === "idle" && currentMood !== "warm" && currentMood !== "joy") {
    currentMood = "neutral";
  }

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
      if (data.action === "jarvis_expression" && data.text) {
        consumeExpressionText(data.text, { scheduleFallback: true, id: data.id });
        return;
      }
      if (data.action === "jarvis_lipsync" && Array.isArray(data.frames)) {
        startTimedLipsync(data.frames, data.id);
        return;
      }
      if (data.action === "set_volume" && typeof data.volume === "number") {
        orb.setVolume(data.volume);
        setVoiceLevel(data.volume);
        return;
      }
      if (data.state) {
        applyState(data.state as OrbState);
      }
      if (typeof data.volume === "number") {
        orb.setVolume(data.volume);
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

// Silence unused-import warning for showError
void showError;
