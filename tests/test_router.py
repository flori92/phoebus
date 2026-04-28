"""Tests pour le routeur central PHOEBUS."""

import json
from unittest.mock import AsyncMock, patch

import pytest

import PHOEBUS.state as state
from PHOEBUS.router import (
    executer_commande_generique,
    extraire_json_de_reponse,
    route_request,
    traiter_reponse_ia,
)


class TestExtraireJson:
    def test_json_simple(self):
        texte = '{"action": "test", "value": 123}'
        assert extraire_json_de_reponse(texte) == {"action": "test", "value": 123}

    def test_json_avec_backticks(self):
        texte = """```json
        {"action": "test"}
        ```"""
        assert extraire_json_de_reponse(texte) == {"action": "test"}

    def test_json_avec_accolades_dans_string(self):
        texte = '{"action": "note", "text": "a {b} c"}'
        assert extraire_json_de_reponse(texte) == {"action": "note", "text": "a {b} c"}

    def test_json_invalide(self):
        assert extraire_json_de_reponse('{"action": "test"') is None

    def test_texte_sans_json(self):
        assert extraire_json_de_reponse("Juste du texte normal") is None


class TestExecuterCommandeGenerique:
    @pytest.mark.asyncio
    async def test_commande_texte_passe_par_route_request(self):
        with (
            patch("PHOEBUS.router.route_request", new_callable=AsyncMock) as mock_route,
            patch("PHOEBUS.router.traiter_reponse_ia", new_callable=AsyncMock) as mock_traiter,
            patch("PHOEBUS.router._parler_safe", new_callable=AsyncMock),
        ):
            mock_route.return_value = "Réponse test"
            mock_traiter.return_value = False

            result = await executer_commande_generique("bonjour", source="test")

        assert result == "Réponse test"
        mock_route.assert_awaited_once()
        mock_traiter.assert_awaited_once_with("Réponse test")

    @pytest.mark.asyncio
    async def test_fast_path_heure_repond_sans_llm(self):
        with patch("PHOEBUS.router._parler_safe", new_callable=AsyncMock):
            result = await executer_commande_generique("quelle heure est-il", source="test")

        assert "Il est" in result

    @pytest.mark.asyncio
    async def test_media_naturel_execute_recommandation_vod(self):
        with (
            patch("PHOEBUS.media.open_uri") as mock_open,
            patch("PHOEBUS.media._search_suggestions", return_value=["The Nice Guys", "Intouchables"]),
            patch("PHOEBUS.actions.parler", new_callable=AsyncMock) as mock_parler,
            patch("PHOEBUS.router.stocker_souvenir"),
        ):
            result = await executer_commande_generique("je veux regarder un film comique", source="test")

        assert result == "Action exécutée, Monsieur."
        assert "justwatch.com" in mock_open.call_args.args[0]
        mock_parler.assert_awaited_once()
        assert "Propositions rapides" in mock_parler.await_args.args[0]

    @pytest.mark.asyncio
    async def test_recherche_naturelle_passe_par_objectif_web(self):
        rep = await route_request("trouve-moi un bon casque bluetooth", source="test")

        payload = json.loads(rep)
        assert payload == {
            "action": "recherche_web",
            "query": "trouve-moi un bon casque bluetooth",
        }

    @pytest.mark.asyncio
    async def test_action_naturelle_passe_par_planificateur(self):
        rep = await route_request("je veux installer VLC sur mon Mac", source="test")

        payload = json.loads(rep)
        assert payload == {
            "action": "agent_planifie",
            "instruction": "je veux installer VLC sur mon Mac",
        }

    @pytest.mark.asyncio
    async def test_reponse_incapable_bascule_sur_fallback(self):
        with patch("PHOEBUS.router.demander_ia", new_callable=AsyncMock) as mock_ia:
            mock_ia.return_value = "Je ne peux pas accéder à cette information."

            rep = await route_request("explique moi la virtualisation", source="test")

        payload = json.loads(rep)
        assert payload == {
            "action": "knowledge_query",
            "question": "explique moi la virtualisation",
        }

    @pytest.mark.asyncio
    async def test_reponse_vide_reste_silencieuse(self):
        with (
            patch("PHOEBUS.router.route_request", new_callable=AsyncMock) as mock_route,
            patch("PHOEBUS.router._parler_safe", new_callable=AsyncMock) as mock_parler,
        ):
            mock_route.return_value = ""

            result = await executer_commande_generique("sous-titres", source="test")

        assert result == ""
        mock_parler.assert_not_awaited()


class TestTraiterReponseIA:
    @pytest.mark.asyncio
    async def test_reponse_avec_action_execute_action_low_risk(self):
        reponse = '{"action": "system_lock"}\n\nTexte explicatif'

        with (
            patch("PHOEBUS.actions.executer_une_action", new_callable=AsyncMock) as mock_action,
            patch("PHOEBUS.router.stocker_souvenir"),
        ):
            result = await traiter_reponse_ia(reponse)

        assert result is True
        mock_action.assert_awaited_once_with({"action": "system_lock"})

    @pytest.mark.asyncio
    async def test_reponse_sans_action_est_parlee(self):
        reponse = "Juste une réponse textuelle"

        with (
            patch("PHOEBUS.router.parler", new_callable=AsyncMock) as mock_parler,
            patch("PHOEBUS.router.stocker_souvenir"),
        ):
            result = await traiter_reponse_ia(reponse)

        assert result is True
        mock_parler.assert_awaited_once_with(reponse)

    @pytest.mark.asyncio
    async def test_action_high_risk_demande_confirmation(self):
        state.PENDING_CONFIRMATION = None
        reponse = '{"action": "system_empty_trash"}'

        try:
            with (
                patch("PHOEBUS.router.parler", new_callable=AsyncMock) as mock_parler,
                patch("PHOEBUS.router.audit_log") as mock_audit,
                patch("PHOEBUS.router.stocker_souvenir"),
            ):
                result = await traiter_reponse_ia(reponse)

            assert result is True
            assert state.PENDING_CONFIRMATION == {"action": "system_empty_trash"}
            mock_parler.assert_awaited_once()
            mock_audit.assert_called_once()
        finally:
            state.PENDING_CONFIRMATION = None
