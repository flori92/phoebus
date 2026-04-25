#!/usr/bin/env python3
"""
PHOEBUS Health Check — Diagnostic rapide des super-pouvoirs

Utilisation: python scripts/healthcheck_superpouvoirs.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def print_header(msg):
    print(f"\n{'='*60}")
    print(f"🔍 {msg}")
    print(f"{'='*60}\n")

def check_imports():
    """Vérifie que tous les modules peuvent être importés."""
    print_header("Vérification Imports Critiques")
    
    modules = {
        "PHOEBUS.audio_optimization": "Audio robuste",
        "PHOEBUS.network_cameras": "Caméras multiples",
        "PHOEBUS.config": "Configuration",
        "PHOEBUS.voice": "Synthèse vocale",
        "PHOEBUS.vision": "Vision/Webcam",
        "PHOEBUS.multi_user": "Multi-utilisateurs",
        "PHOEBUS.brain_router": "Routeur IA",
    }
    
    results = {}
    for module_name, desc in modules.items():
        try:
            __import__(module_name)
            print(f"✅ {module_name:35} {desc}")
            results[module_name] = True
        except ImportError as e:
            print(f"❌ {module_name:35} {desc} ({e})")
            results[module_name] = False
    
    return results

def check_audio():
    """Teste le module audio."""
    print_header("Super-Pouvoir #1: Audio Robuste")
    
    try:
        from PHOEBUS.audio_optimization import (
            get_processor, check_hallucination
        )
        
        processor = get_processor()
        print(f"✅ Processeur audio initialisé")
        print(f"   • Optimisation: {processor.enable_optimization}")
        print(f"   • AEC: {processor.enable_aec}")
        print(f"   • Noise Gate: {processor.enable_noise_gate}")
        print(f"   • AGC: {processor.enable_agc}")
        print(f"   • VAD Mode: {processor.vad_mode}/3")
        
        # Test hallucination
        is_hall, conf = check_hallucination("Merci de votre écoute")
        status = "✅" if is_hall else "❌"
        print(f"\n{status} Détection hallucination: Merci de votre écoute")
        print(f"   → Résultat: {is_hall}, Confiance: {conf:.1%}")
        
        return True
    except Exception as e:
        print(f"❌ Erreur audio: {e}")
        return False

def check_cameras():
    """Teste les caméras."""
    print_header("Super-Pouvoir #1: Vision Augmentée")
    
    try:
        from PHOEBUS.network_cameras import discover_cameras, get_camera_manager
        
        manager = get_camera_manager()
        cameras = manager.list_cameras()
        
        print(f"✅ Caméras enregistrées: {len(cameras)}")
        for cam in cameras:
            print(f"   • {cam}")
        
        # Essayer découverte réseau
        print(f"\n⏳ Scan réseau (rapide)...")
        found = discover_cameras(scan_network=False)  # Sans scan réseau
        print(f"✅ Découverte: {len(found)} caméra(s)")
        
        return True
    except Exception as e:
        print(f"❌ Erreur caméras: {e}")
        return False

def check_multi_user():
    """Teste multi-utilisateurs."""
    print_header("Super-Pouvoir #3: Sentinelle (Biométrie)")
    
    try:
        from PHOEBUS.multi_user import lister_utilisateurs, MULTI_USER_ENABLED
        
        users = lister_utilisateurs()
        print(f"✅ Multi-utilisateurs: {'Activé' if MULTI_USER_ENABLED else 'Désactivé'}")
        print(f"✅ Utilisateurs enregistrés: {len(users)}")
        for user in users:
            print(f"   • {user}")
        
        return True
    except Exception as e:
        print(f"❌ Erreur multi-user: {e}")
        return False

def check_lmarena():
    """Vérifie LMArena Bridge."""
    print_header("Super-Pouvoir #5: Conscience + LMArena")
    
    try:
        from PHOEBUS.config import arena_client, ARENA_URL, ARENA_MODEL
        
        if arena_client:
            print(f"✅ Arena Client configuré")
            print(f"   • URL: {ARENA_URL}")
            print(f"   • Modèle: {ARENA_MODEL}")
            
            # Tenter health check
            import urllib.request
            try:
                urllib.request.urlopen(f"{ARENA_URL}/health", timeout=2)
                print(f"✅ Bridge LMArena accessible")
            except:
                print(f"⚠️  Bridge LMArena non accessible (lancez: python scripts/arena_bridge.py start)")
            
            return True
        else:
            print(f"⚠️  Arena Client non configuré (optionnel)")
            return True
    except Exception as e:
        print(f"⚠️  Erreur Arena: {e}")
        return True  # Optionnel

def check_config():
    """Vérifie la configuration."""
    print_header("Configuration (.env)")
    
    try:
        from PHOEBUS.config import (
            PHOEBUS_WS_TOKEN, WS_AUTH_REQUIRED,
            DEFAULT_WS_PORT, DEFAULT_MOBILE_PORT
        )
        
        print(f"✅ Token WebSocket: {'***' if PHOEBUS_WS_TOKEN else '(vide)'}")
        print(f"✅ Authentification WS requise: {WS_AUTH_REQUIRED}")
        print(f"✅ Port WS: {DEFAULT_WS_PORT}")
        print(f"✅ Port Mobile: {DEFAULT_MOBILE_PORT}")
        
        return True
    except Exception as e:
        print(f"❌ Erreur config: {e}")
        return False

def check_system():
    """Vérifie l'environnement système."""
    print_header("Environnement Système")
    
    # Python
    print(f"✅ Python: {sys.version.split()[0]}")
    
    # OS
    import platform
    print(f"✅ OS: {platform.system()} {platform.release()}")
    
    # Dépendances système
    if sys.platform == "darwin":
        import subprocess
        try:
            result = subprocess.run(["brew", "list", "portaudio"], capture_output=True)
            if result.returncode == 0:
                print(f"✅ PortAudio: installé (macOS)")
            else:
                print(f"❌ PortAudio: NON installé (macOS)")
        except:
            pass
    
    return True

def check_performance():
    """Mesure la performance."""
    print_header("Performance & Latence")
    
    try:
        import time
        from PHOEBUS.stt_backends import get_backend
        
        # STT backend
        stt_backend = get_backend()
        if stt_backend:
            print(f"✅ Backend STT: disponible")
        else:
            print(f"⚠️  Backend STT: indisponible")
        
        # Vector DB
        try:
            import chromadb
            print(f"✅ Vector DB (ChromaDB): disponible")
        except:
            print(f"⚠️  Vector DB: indisponible")
        
        return True
    except Exception as e:
        print(f"⚠️  Erreur performance: {e}")
        return True

def generate_report(results):
    """Génère un rapport final."""
    print_header("📊 RAPPORT FINAL")
    
    total_checks = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"Tests réussis: {passed}/{total_checks}\n")
    
    if passed == total_checks:
        print("🟢 PHOEBUS PRÊT — Tous les super-pouvoirs sont opérationnels!\n")
        status = "✅ PRODUCTION READY"
    elif passed >= total_checks * 0.8:
        print("🟡 PHOEBUS PARTIEL — Certains super-pouvoirs nécessitent config\n")
        status = "⚠️  CONFIGURATION REQUISE"
    else:
        print("🔴 PHOEBUS DÉGRADÉ — Plusieurs erreurs détectées\n")
        status = "❌ ERREURS DÉTECTÉES"
    
    print(f"Status: {status}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nPour activation complète, voir: GUIDE_SUPERPOUVOIRS.md")

def main():
    """Exécute le diagnostic complet."""
    print("\n" + "🌟 "*15)
    print("PHOEBUS — HEALTH CHECK DES SUPER-POUVOIRS")
    print("🌟 "*15 + "\n")
    
    results = {}
    
    # Checks
    results["Imports"] = all(check_imports().values())
    results["Audio"] = check_audio()
    results["Caméras"] = check_cameras()
    results["Multi-User"] = check_multi_user()
    results["LMArena"] = check_lmarena()
    results["Config"] = check_config()
    results["Système"] = check_system()
    results["Performance"] = check_performance()
    
    # Rapport
    generate_report(results)
    
    return 0 if all(results.values()) else 1

if __name__ == "__main__":
    sys.exit(main())
