"""Moteur de proactivité de JARVIS.

Jarvis vérifie périodiquement un ensemble de règles et peut prendre la
parole de lui-même quand une condition est remplie (rappels, silence trop
long avec conversation ouverte, etc.). Chaque règle est une coroutine
indépendante pour que les nouvelles extensions soient faciles à brancher.

Les règles actuelles sont volontairement prudentes pour éviter le
harcèlement : Jarvis n'intervient que quand une conversation est active
OU quand il a une info objectivement utile.
"""
import asyncio
import time

import jarvis.state as state


_RULES = []


def rule(fn):
    """Décorateur pour enregistrer une coroutine de règle proactive.

    Le callable reçoit `parler` (coroutine de TTS) et est rappelé tick
    après tick — il doit se limiter tout seul (ex: drapeau interne).
    """
    _RULES.append(fn)
    return fn


# ── Règles par défaut ──────────────────────────────────────────────────────

@rule
async def _silence_ping(parler):
    """Après 40s de silence dans une conversation active, un 'je suis là'
    discret. Une seule fois par période de silence."""
    if not state.is_in_conversation():
        return
    s = state.seconds_since_user_activity()
    if s is None:
        return
    if 40 <= s < 90 and not state.silence_ping_sent:
        state.silence_ping_sent = True
        await parler("Je vous écoute toujours, Monsieur.")


@rule
async def _silence_timeout(parler):
    """Après 2 minutes sans rien, on clôt la conversation gracieusement."""
    if not state.is_in_conversation():
        return
    s = state.seconds_since_user_activity()
    if s is None:
        return
    if s > 120:
        state.end_conversation()


# ── Boucle ────────────────────────────────────────────────────────────────

async def loop(parler, tick_seconds: float = 5.0):
    """Boucle infinie à lancer en tâche asyncio au démarrage du serveur."""
    while True:
        for fn in list(_RULES):
            try:
                await fn(parler)
            except Exception as e:
                print(f"[PROACTIVE] Règle {getattr(fn, '__name__', '?')} erreur : {e}")
        await asyncio.sleep(tick_seconds)


def register_rule(fn):
    """Variante non-décorateur pour enregistrer une règle dynamiquement."""
    _RULES.append(fn)
    return fn
