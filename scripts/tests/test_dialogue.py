"""Tests de dialogue (sans dépendance réseau).

Ils vérifient que les briques de conversation — clarification, détection
de transcription bancale, niveaux de risque, registre appris, fenêtre de
conversation continue — se comportent comme attendu.

Lance-les depuis la racine du projet :

    python3 -m pytest scripts/tests/test_dialogue.py -q

Ou directement :

    python3 scripts/tests/test_dialogue.py
"""
import os
import sys
import time

# Permet d'importer `PHOEBUS` même en exécution directe.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_clarify_transcription_incertaine():
    from PHOEBUS.clarify import transcription_incertaine
    assert transcription_incertaine("") is True
    assert transcription_incertaine("...") is True
    assert transcription_incertaine("zz") is True
    assert transcription_incertaine("bo") is True
    # Une phrase utile ne doit PAS être marquée incertaine.
    assert transcription_incertaine("allume la lumière du salon") is False
    assert transcription_incertaine("quel temps fait-il à Amilly") is False


def test_clarify_demande_ambigue():
    from PHOEBUS.clarify import demande_ambigue, question_pour_clarifier
    assert demande_ambigue("allume") is True
    assert demande_ambigue("éteins") is True
    assert demande_ambigue("ouvre") is True
    assert demande_ambigue("fais ça") is True
    assert demande_ambigue("allume la lumière du salon") is False
    # La question générée est non vide.
    assert len(question_pour_clarifier("allume")) > 3


def test_risk_levels():
    import PHOEBUS.security as security

    original_config = security.DEVICE_CONFIG
    try:
        security.DEVICE_CONFIG = {}
        assert security.risk_level_for("ha_lumiere") == "low"
        assert security.risk_level_for("ha_thermostat") == "medium"
        assert security.risk_level_for("ha_alarme") == "high"
        assert security.risk_level_for("agent_natif") == "high"
        # Fallback pour action inconnue.
        assert security.risk_level_for("un_truc_inexistant") == "low"
    finally:
        security.DEVICE_CONFIG = original_config


def test_conversation_window():
    import PHOEBUS.state as st
    st.end_conversation()
    assert st.is_in_conversation() is False
    st.extend_conversation(2)
    assert st.is_in_conversation() is True
    time.sleep(2.1)
    assert st.is_in_conversation() is False


def test_registre_detection():
    from PHOEBUS.memory import detecter_registre
    assert detecter_registre("tu peux allumer la lumière ?") == "tu"
    assert detecter_registre("pouvez-vous me dire l'heure ?") == "vous"
    assert detecter_registre("bref, salut") is None


def test_skill_registry():
    from PHOEBUS.skills import skill, get_skill, list_skills

    @skill("__test_demo", risk="medium", help="démo")
    async def _h(d):
        return None

    assert get_skill("__test_demo") is not None
    assert get_skill("__test_demo").risk == "medium"
    assert "__test_demo" in list_skills()


def test_naturaliser_markdown():
    from PHOEBUS.text_shaping import naturaliser
    assert "**" not in naturaliser("c'est **très** bien")
    assert "`" not in naturaliser("voici `code` ici")
    # Le contenu reste.
    assert "très" in naturaliser("c'est **très** bien")


def test_naturaliser_abreviations():
    from PHOEBUS.text_shaping import naturaliser
    assert "Monsieur Favi" in naturaliser("M. Favi est là")
    assert "par exemple" in naturaliser("p. ex. ceci").lower()
    assert "c'est-à-dire" in naturaliser("c.-à-d. ceci")


def test_naturaliser_unites():
    from PHOEBUS.text_shaping import naturaliser
    assert "degrés" in naturaliser("Il fait 25°C")
    assert "pour cent" in naturaliser("à 80%")
    assert "euros" in naturaliser("ça fait 12€")
    assert "kilomètres" in naturaliser("100 km à faire")


def test_naturaliser_respiration():
    from PHOEBUS.text_shaping import naturaliser
    # Ajoute une virgule après "donc" suivi d'un espace+minuscule.
    out = naturaliser("donc voici la réponse")
    assert "donc," in out.lower()


def test_naturaliser_idempotent():
    from PHOEBUS.text_shaping import naturaliser
    t = "M. Favi, donc il fait 20°C **aujourd'hui**."
    assert naturaliser(naturaliser(t)) == naturaliser(t)


def test_intent_fast_path():
    from PHOEBUS.intent import detect
    # Commandes reconnues
    r = detect("PHOEBUS, allume la lumière du salon")
    assert r is not None and r.name == "allumer" and '"salon"' in r.reply
    r = detect("éteins la cuisine")
    assert r is not None and r.name == "eteindre"
    r = detect("mets le thermostat à 21")
    assert r is not None and r.name == "thermostat" and "21" in r.reply
    r = detect("quelle heure est-il")
    assert r is not None and r.name == "heure"
    # Non reconnu → None → retombe sur LLM
    assert detect("raconte-moi une blague") is None
    assert detect("comment tu te sens aujourd'hui") is None


def test_sentence_splitter():
    from PHOEBUS.sentence_splitter import split, split_streaming
    r = split("Bonjour Floriace. Comment allez-vous ?")
    assert len(r) == 2
    # Abréviations ne coupent pas (M. Favi reste dans la 1re phrase).
    r = split("M. Favi est arrivé. Il a apporté des croissants !")
    assert len(r) == 2 and "M. Favi" in r[0]
    # Streaming : fragment sans terminateur → reste en buffer
    sentences, buf = split_streaming("Bonjour Floriace. Je m'appe")
    assert sentences == ["Bonjour Floriace."]
    assert buf.strip().startswith("Je m")


def test_correction_detection():
    from PHOEBUS.memory_unified import looks_like_correction
    assert looks_like_correction("Non, je voulais dire Lyon")
    assert looks_like_correction("tu te trompes")
    assert not looks_like_correction("merci PHOEBUS")
    assert not looks_like_correction("allume le salon")


def test_response_cache_key_stability():
    from PHOEBUS.response_cache import _cache_key
    # Même texte, même voix → même clé (déterministe).
    k1 = _cache_key("Bonjour Floriace.", "fr-FR-Remy", "auto")
    k2 = _cache_key("Bonjour Floriace.", "fr-FR-Remy", "auto")
    assert k1 == k2
    # Voix différente → clé différente.
    k3 = _cache_key("Bonjour Floriace.", "fr-FR-Henri", "auto")
    assert k1 != k3


def test_brain_router_profiles_and_ranking():
    from PHOEBUS.brain_router import build_profile, rank_provider_names

    p = build_profile("donne-moi les dernières nouvelles sur X", streaming=False)
    assert p.needs_realtime is True
    assert p.preferred_provider == "grok"
    assert rank_provider_names(
        p,
        available=["gemini", "groq", "grok", "ollama"],
        order=["gemini", "groq", "grok", "ollama"],
        mode="balanced",
        metrics={},
    )[0] == "grok"

    p = build_profile("bonjour", streaming=True)
    assert p.priority == "fast"
    assert rank_provider_names(
        p,
        available=["gemini", "groq", "ollama"],
        order=["gemini", "groq", "ollama"],
        mode="speed",
        metrics={},
    )[0] == "groq"


# ── Exécution directe ─────────────────────────────────────────────────────

def _run_all():
    tests = [
        test_clarify_transcription_incertaine,
        test_clarify_demande_ambigue,
        test_risk_levels,
        test_conversation_window,
        test_registre_detection,
        test_skill_registry,
        test_naturaliser_markdown,
        test_naturaliser_abreviations,
        test_naturaliser_unites,
        test_naturaliser_respiration,
        test_naturaliser_idempotent,
        test_intent_fast_path,
        test_sentence_splitter,
        test_correction_detection,
        test_response_cache_key_stability,
        test_brain_router_profiles_and_ranking,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK   {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__} : {e}")
        except Exception as e:
            failed += 1
            print(f"ERR  {fn.__name__} : {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passent.")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
