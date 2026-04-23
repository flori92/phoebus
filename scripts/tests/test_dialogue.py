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

# Permet d'importer `jarvis` même en exécution directe.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_clarify_transcription_incertaine():
    from jarvis.clarify import transcription_incertaine
    assert transcription_incertaine("") is True
    assert transcription_incertaine("...") is True
    assert transcription_incertaine("zz") is True
    assert transcription_incertaine("bo") is True
    # Une phrase utile ne doit PAS être marquée incertaine.
    assert transcription_incertaine("allume la lumière du salon") is False
    assert transcription_incertaine("quel temps fait-il à Amilly") is False


def test_clarify_demande_ambigue():
    from jarvis.clarify import demande_ambigue, question_pour_clarifier
    assert demande_ambigue("allume") is True
    assert demande_ambigue("éteins") is True
    assert demande_ambigue("ouvre") is True
    assert demande_ambigue("fais ça") is True
    assert demande_ambigue("allume la lumière du salon") is False
    # La question générée est non vide.
    assert len(question_pour_clarifier("allume")) > 3


def test_risk_levels():
    from jarvis.security import risk_level_for
    assert risk_level_for("ha_lumiere") == "low"
    assert risk_level_for("ha_thermostat") == "medium"
    assert risk_level_for("ha_alarme") == "high"
    assert risk_level_for("agent_natif") == "high"
    # Fallback pour action inconnue.
    assert risk_level_for("un_truc_inexistant") == "low"


def test_conversation_window():
    import jarvis.state as st
    st.end_conversation()
    assert st.is_in_conversation() is False
    st.extend_conversation(2)
    assert st.is_in_conversation() is True
    time.sleep(2.1)
    assert st.is_in_conversation() is False


def test_registre_detection():
    from jarvis.memory import detecter_registre
    assert detecter_registre("tu peux allumer la lumière ?") == "tu"
    assert detecter_registre("pouvez-vous me dire l'heure ?") == "vous"
    assert detecter_registre("bref, salut") is None


def test_skill_registry():
    from jarvis.skills import skill, get_skill, list_skills

    @skill("__test_demo", risk="medium", help="démo")
    async def _h(d):
        return None

    assert get_skill("__test_demo") is not None
    assert get_skill("__test_demo").risk == "medium"
    assert "__test_demo" in list_skills()


def test_naturaliser_markdown():
    from jarvis.text_shaping import naturaliser
    assert "**" not in naturaliser("c'est **très** bien")
    assert "`" not in naturaliser("voici `code` ici")
    # Le contenu reste.
    assert "très" in naturaliser("c'est **très** bien")


def test_naturaliser_abreviations():
    from jarvis.text_shaping import naturaliser
    assert "Monsieur Favi" in naturaliser("M. Favi est là")
    assert "par exemple" in naturaliser("p. ex. ceci").lower()
    assert "c'est-à-dire" in naturaliser("c.-à-d. ceci")


def test_naturaliser_unites():
    from jarvis.text_shaping import naturaliser
    assert "degrés" in naturaliser("Il fait 25°C")
    assert "pour cent" in naturaliser("à 80%")
    assert "euros" in naturaliser("ça fait 12€")
    assert "kilomètres" in naturaliser("100 km à faire")


def test_naturaliser_respiration():
    from jarvis.text_shaping import naturaliser
    # Ajoute une virgule après "donc" suivi d'un espace+minuscule.
    out = naturaliser("donc voici la réponse")
    assert "donc," in out.lower()


def test_naturaliser_idempotent():
    from jarvis.text_shaping import naturaliser
    t = "M. Favi, donc il fait 20°C **aujourd'hui**."
    assert naturaliser(naturaliser(t)) == naturaliser(t)


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
