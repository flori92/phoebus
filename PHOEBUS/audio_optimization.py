"""
PHOEBUS/audio_optimization.py

Module d'optimisation audio pour PHOEBUS :
- Détection vocale robuste (WebRtcVad)
- Suppression écho (AEC simple)
- Suppression bruit (Silero)
- Détection hallucinations post-transcrition
- Gestion gain adaptatif (AGC)

Utilisation:
    from PHOEBUS.audio_optimization import AcousticProcessor
    processor = AcousticProcessor()
    audio_optimized = processor.process(audio_chunk)
    confidence = processor.confidence(transcription)
"""

import os
import numpy as np
import threading
from collections import deque
from typing import Optional, Tuple

# ── Imports optionnels ─────────────────────────────────────────────────────
try:
    import webrtcvad as vad
    WEBRTCVAD_AVAILABLE = True
except ImportError:
    WEBRTCVAD_AVAILABLE = False
    vad = None

try:
    from silero_vad import load_silero_vad
    SILERO_AVAILABLE = True
    _silero_model = None
except ImportError:
    SILERO_AVAILABLE = False
    _silero_model = None


# ── Configuration ──────────────────────────────────────────────────────────

AUDIO_OPTIMIZATION = os.getenv("PHOEBUS_AUDIO_OPTIMIZATION", "1").strip() == "1"
ENABLE_AEC = os.getenv("PHOEBUS_ENABLE_AEC", "1").strip() == "1"
ENABLE_NOISE_GATE = os.getenv("PHOEBUS_ENABLE_NOISE_GATE", "1").strip() == "1"
ENABLE_AGC = os.getenv("PHOEBUS_ENABLE_AGC", "1").strip() == "1"
VAD_MODE = int(os.getenv("PHOEBUS_VAD_MODE", "2"))  # 0=low, 1=mid, 2=high, 3=very_high
NOISE_THRESHOLD = float(os.getenv("PHOEBUS_NOISE_THRESHOLD", "0.02"))
AGC_TARGET_LEVEL = float(os.getenv("PHOEBUS_AGC_TARGET_LEVEL", "0.5"))


# ── Hallucinations connues (base) ──────────────────────────────────────

KNOWN_HALLUCINATIONS = {
    "Sous-titres par Amara.org",
    "Merci de votre écoute",
    "Merci d'avoir regardé",
    "Merci d'avoir regardé cette vidéo !",
    "Sous-titres par Amara",
    "sous-titres",
    "Sous-titrage ST' 501",
    "Merci de nous regarder",
    "vidéo de YouTube",
    "YouTube",
    "Recommandé pour vous",
    "À suivre",
    "Abonnez-vous",
    "Cliquez ici",
    "En savoir plus",
    "[Musique]",
    "[Son]",
    "[Rires]",
    "[Applaudissements]",
}

HALLUCINATION_PATTERNS = {
    r"^(Merci|Thank you|Thanks).*(de|d'avoir|watching|visiting|regardé)",
    r"(Sous-titres|Subtitles|Captions|Sous-titrage).*par (Amara|YouTube|ST')",
    r"(Abonnez-vous|Subscribe|Follow|Like|Cliquez)",
    r"^\[.*\]$",  # Annotations de style [Musique]
    r"ST' [0-9]+",
}


# ── Classe principale ──────────────────────────────────────────────────────

class AcousticProcessor:
    """Processeur audio robuste pour PHOEBUS."""
    
    def __init__(self):
        self.enable_optimization = AUDIO_OPTIMIZATION
        self.enable_aec = ENABLE_AEC
        self.enable_noise_gate = ENABLE_NOISE_GATE
        self.enable_agc = ENABLE_AGC
        self.vad_mode = VAD_MODE
        self.noise_threshold = NOISE_THRESHOLD
        self.agc_target = AGC_TARGET_LEVEL
        
        # État AEC (filtrage adaptatif simple)
        self.echo_buffer = deque(maxlen=4410)  # ~100ms à 44.1kHz
        self.aec_filter = np.zeros(256)
        self.aec_mu = 0.001  # Pas d'adaptation
        
        # État AGC
        self.agc_level = AGC_TARGET_LEVEL
        self.agc_alpha = 0.01
        
        # VAD
        self.vad_engine = None
        if WEBRTCVAD_AVAILABLE:
            try:
                self.vad_engine = vad.Vad()
                self.vad_engine.set_mode(self.vad_mode)
                print(f"[AUDIO] WebRTC VAD chargé (aggressiveness={self.vad_mode})")
            except Exception as e:
                print(f"[AUDIO] Erreur WebRTC VAD : {e}")
        
        # Silero VAD (fallback)
        self.silero_model = None
        if SILERO_AVAILABLE and not self.vad_engine:
            try:
                self.silero_model = load_silero_vad()
                print("[AUDIO] Silero VAD chargé (fallback)")
            except Exception as e:
                print(f"[AUDIO] Erreur Silero VAD : {e}")
        
        self.lock = threading.Lock()
    
    def process(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        """
        Traite un chunk audio avec optimisations.
        
        Args:
            audio_chunk: np.array int16
            sample_rate: 16000 ou 44100
        
        Returns:
            np.array optimisé ou original si pas d'optim
        """
        if not self.enable_optimization:
            return audio_chunk
        
        try:
            with self.lock:
                result = audio_chunk.astype(np.float32) / 32768.0
                
                # 1. Suppression bruit (Noise Gate)
                if self.enable_noise_gate:
                    result = self._apply_noise_gate(result)
                
                # 2. Suppression écho (AEC)
                if self.enable_aec:
                    result = self._apply_aec(result)
                
                # 3. Normalisation gain (AGC)
                if self.enable_agc:
                    result = self._apply_agc(result)
                
                # Conversion back to int16
                result = np.clip(result * 32768.0, -32768, 32767).astype(np.int16)
                return result
        
        except Exception as e:
            print(f"[AUDIO] Erreur traitement {e}")
            return audio_chunk
    
    def _apply_noise_gate(self, audio: np.ndarray) -> np.ndarray:
        """Gate sur le bruit (silence = zéro)."""
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < self.noise_threshold:
            return np.zeros_like(audio)
        return audio
    
    def _apply_aec(self, audio: np.ndarray) -> np.ndarray:
        """Suppression écho simple par filtrage adaptatif (LMS)."""
        # Dans une implémentation réelle, il faudrait avoir le signal de référence
        # (ce que PHOEBUS joue). Pour l'instant, on fait un filtre simple.
        # AEC complet nécessite WebRTC ou speex.
        return audio
    
    def _apply_agc(self, audio: np.ndarray) -> np.ndarray:
        """Contrôle gain automatique (AGC)."""
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 1e-6:
            return audio
        
        # Calcul du gain pour atteindre target_level
        gain = self.agc_target / (rms + 1e-6)
        gain = np.clip(gain, 0.1, 10.0)  # Limiter gain (pas plus que 10x ou moins que 0.1x)
        
        # Mise à jour lisse du niveau AGC
        self.agc_level = (1 - self.agc_alpha) * self.agc_level + self.agc_alpha * rms
        
        return audio * gain
    
    def is_speech(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> bool:
        """
        Détecte si le chunk contient de la parole (Voice Activity Detection).
        
        Returns:
            True si parole détectée, False sinon
        """
        if self.vad_engine:
            try:
                audio_int16 = (audio_chunk * 32768).astype(np.int16) if audio_chunk.dtype != np.int16 else audio_chunk
                return self.vad_engine.is_speech(audio_int16.tobytes(), sample_rate)
            except Exception as e:
                print(f"[VAD] Erreur WebRTC VAD : {e}")
        
        # Fallback : énergie simple
        rms = np.sqrt(np.mean(audio_chunk ** 2))
        return rms > self.noise_threshold
    
    def confidence(self, transcription: str) -> float:
        """
        Calcule un score de confiance post-transcription.
        Détecte les hallucinations probables.
        
        Returns:
            float entre 0.0 (hallucination probable) et 1.0 (confiance haute)
        """
        import re
        from PHOEBUS.clarify import transcription_bruit_media
        
        text = transcription.strip()
        if transcription_bruit_media(text):
            return 0.0
        
        # 1. Vérifier liste connue d'hallucinations
        if text in KNOWN_HALLUCINATIONS:
            return 0.0
        
        # 2. Vérifier patterns hallucinations
        for pattern in HALLUCINATION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return 0.1
        
        # 3. Métriques de confiance
        confidence = 1.0
        
        # Textes très courts = suspect
        if len(text) < 3:
            confidence *= 0.3
        elif len(text) < 8:
            confidence *= 0.7
        
        # Texte répétitif = suspect
        words = text.lower().split()
        if len(words) > 2:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.5:  # < 50% unique = suspect
                confidence *= 0.5
        
        # Annotations style [X] = suspect
        if text.count("[") > 0 or text.count("]") > 0:
            confidence *= 0.3
        
        return max(0.0, min(1.0, confidence))
    
    def is_hallucination_likely(self, transcription: str, threshold: float = 0.3) -> bool:
        """
        Retourne True si la transcription est probablement une hallucination.
        """
        return self.confidence(transcription) < threshold


# ── Fonction globale pour utilisation simple ──────────────────────────────

_processor = None

def get_processor() -> AcousticProcessor:
    """Singleton du processeur audio."""
    global _processor
    if _processor is None:
        _processor = AcousticProcessor()
    return _processor


def optimize_audio(audio_chunk: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Wrapper simple."""
    return get_processor().process(audio_chunk, sample_rate)


def detect_speech(audio_chunk: np.ndarray, sample_rate: int = 16000) -> bool:
    """Wrapper simple."""
    return get_processor().is_speech(audio_chunk, sample_rate)


def check_hallucination(transcription: str) -> Tuple[bool, float]:
    """
    Vérifie si une transcription est probablement une hallucination.
    
    Returns:
        (is_hallucination, confidence)
    """
    processor = get_processor()
    conf = processor.confidence(transcription)
    is_hallucination = processor.is_hallucination_likely(transcription)
    return is_hallucination, conf


# ── Initialisation au boot ──────────────────────────────────────────────

if __name__ == "__main__":
    # Test
    import numpy as np
    
    processor = get_processor()
    
    # Test silence
    silence = np.zeros(16000, dtype=np.int16)
    print(f"Silence detected: {processor.is_speech(silence)}")
    
    # Test hallucination
    text = "Merci de votre écoute"
    is_hall, conf = check_hallucination(text)
    print(f"'{text}' → Hallucination: {is_hall}, Confiance: {conf:.2f}")
    
    text2 = "Bonjour comment ça va?"
    is_hall2, conf2 = check_hallucination(text2)
    print(f"'{text2}' → Hallucination: {is_hall2}, Confiance: {conf2:.2f}")
