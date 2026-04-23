/**
 * J.A.R.V.I.S — Interface Web avec Orbe Three.js
 *
 * Se connecte au backend Python via WebSocket (ws://localhost:8765),
 * recoit les changements d'etat et pilote l'orbe en consequence.
 *
 * Etats: "idle" | "listening" | "thinking" | "speaking"
 */

import { createOrb, type OrbState } from "./orb";
import { injectVisionButton, captureFrame } from "./screen_capture";
import "./style.css";

// ── Config ────────────────────────────────────────────────────────────────────
const WS_HOST = window.location.hostname || "localhost";
const WS_SCHEME = window.location.protocol === "https:" ? "wss" : "ws";
const WS_URL = `${WS_SCHEME}://${WS_HOST}:8765`;
const RECONNECT_INTERVAL_MS = 2_000;
const WS_TOKEN_STORAGE_KEY = "jarvis_ws_token";

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

// ── DOM refs ──────────────────────────────────────────────────────────────────
const canvas = document.getElementById("orb-canvas") as HTMLCanvasElement;
const statusEl = document.getElementById("status-text") as HTMLDivElement;
const errorEl = document.getElementById("error-text") as HTMLDivElement;
const badgeEl = document.getElementById("connection-badge") as HTMLDivElement;
const badgeLabelEl = document.getElementById(
  "connection-label"
) as HTMLSpanElement;
const muteButtonEl = document.getElementById("mute-button") as HTMLButtonElement;

// ── Orb ───────────────────────────────────────────────────────────────────────
const orb = createOrb(canvas);

// ── State labels (French) ────────────────────────────────────────────────────
const STATE_LABELS: Record<OrbState, string> = {
  idle: "",
  listening: "ecoute...",
  thinking: "reflexion...",
  speaking: "",
};

function applyState(state: OrbState): void {
  orb.setState(state);
  statusEl.textContent = STATE_LABELS[state];
}

function setMuted(muted: boolean): void {
  muteButtonEl.classList.toggle("is-muted", muted);
  muteButtonEl.setAttribute("aria-pressed", String(muted));
  muteButtonEl.textContent = muted ? "unmute" : "mute";
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
  muteButtonEl.disabled = !ok;
}

// ── WebSocket with auto-reconnect ─────────────────────────────────────────────
let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let authToken = getStoredToken();

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

  ws.addEventListener("message", async (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data as string) as {
        state?: string;
        action?: string;
        muted?: boolean;
        volume?: number;
        id?: string;
      };

      if (data.action === "request_screen_capture") {
        const frame = await captureFrame();
        if (frame && ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: "screen_frame",
            id: data.id,
            data: frame,
          }));
        } else if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: "screen_frame",
            id: data.id,
            error: "no_stream",
          }));
        }
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
      if (data.action === "set_volume" && typeof data.volume === "number") {
        orb.setVolume(data.volume);
        return;
      }
      if (data.state) {
        applyState(data.state as OrbState);
      }
      if (typeof data.volume === "number") {
        orb.setVolume(data.volume);
      }
      if (typeof data.muted === "boolean") {
        setMuted(data.muted);
      }
    } catch {
      // ignore malformed messages
    }
  });

  ws.addEventListener("close", () => {
    setConnected(false);
    applyState("idle");
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

// ── Events ──────────────────────────────────────────────────────────────────
muteButtonEl.addEventListener("click", () => {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  // Envoi du signal stop au backend
  ws.send(JSON.stringify({ type: "stop_audio" }));

  // Feedback immédiat sur l'orbe
  applyState("idle");
});

// ── Boot ──────────────────────────────────────────────────────────────────────
setConnected(false);
applyState("idle");
setMuted(false);
injectVisionButton();
connect();

// Silence unused-import warning for showError
void showError;
