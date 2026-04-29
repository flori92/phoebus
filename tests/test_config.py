"""
Tests pour la configuration Pydantic.
"""

import pytest
from unittest.mock import patch

from PHOEBUS.config_pydantic import (
    LLMConfig,
    ServerConfig,
    PhoebusConfig,
    get_config,
    reload_config,
)
from PHOEBUS.brain_router import build_profile, rank_provider_names


class TestLLMConfig:
    """Tests pour la configuration LLM."""

    def test_llm_config_empty(self):
        """Config LLM sans clés API."""
        with patch.dict("os.environ", {}, clear=True):
            config = LLMConfig()
        assert config.gemini_api_key is None
        assert config.groq_api_key is None

    def test_llm_config_with_keys(self):
        """Config LLM avec clés."""
        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "test-key",
                "GROQ_API_KEY": "  spaced-key  ",
                "XAI_API_KEY": "xai-key",
            },
            clear=False,
        ):
            config = LLMConfig()
            assert config.gemini_api_key == "test-key"
            assert config.groq_api_key == "spaced-key"  # Stripped
            assert config.xai_api_key == "xai-key"


class TestServerConfig:
    """Tests pour la configuration serveur."""

    def test_default_values(self):
        """Valeurs par défaut."""
        config = ServerConfig()
        assert config.ws_port == 8765
        assert config.mobile_port == 8080
        assert config.ws_auth_required is False

    def test_invalid_port(self):
        """Port hors range."""
        with pytest.raises(ValueError):
            ServerConfig(ws_port=100)


class TestPhoebusConfig:
    """Tests pour la configuration globale."""

    def test_is_production_development(self):
        """Détection environnement dev."""
        config = PhoebusConfig(server=ServerConfig(), _env_file=None)
        assert config.is_production is False

    def test_is_production_true(self):
        """Détection environnement prod."""
        config = PhoebusConfig(
            server=ServerConfig(ws_auth_required=True), _env_file=None
        )
        assert config.is_production is True

    def test_get_available_providers(self):
        """Liste des providers disponibles."""
        with patch.dict("os.environ", {}, clear=True):
            llm_config = LLMConfig(gemini_api_key="key1", groq_api_key="key2", xai_api_key="key3")
            config = PhoebusConfig(
                llm=llm_config,
                server=ServerConfig(),
                _env_file=None,
            )
        providers = config.get_available_llm_providers()
        assert "gemini" in providers
        assert "groq" in providers
        assert "grok" in providers
        assert "mistral" not in providers


class TestConfigSingleton:
    """Tests pour le pattern singleton."""

    def test_singleton_instance(self):
        """Même instance retournée."""
        reload_config()  # Reset
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_reload_creates_new_instance(self):
        """Reload crée nouvelle instance."""
        config1 = get_config()
        config2 = reload_config()
        assert config1 is not config2


def test_brain_router_priorise_local_first(monkeypatch):
    monkeypatch.setenv("PHOEBUS_BRAIN_MODE", "local_first")
    monkeypatch.setenv("PHOEBUS_LOCAL_FIRST", "1")

    profile = build_profile("raconte une blague courte")
    order = rank_provider_names(
        profile,
        available=["gemini", "groq", "ollama"],
        order=["gemini", "groq", "ollama"],
        metrics={},
    )

    assert order[0] == "ollama"


def test_brain_router_ne_sacrifie_pas_les_requetes_profondes_au_local(monkeypatch):
    monkeypatch.setenv("PHOEBUS_BRAIN_MODE", "local_first")
    monkeypatch.setenv("PHOEBUS_LOCAL_FIRST", "1")

    profile = build_profile("analyse et optimise l'architecture de Phoebus")
    order = rank_provider_names(
        profile,
        available=["gemini", "groq", "ollama"],
        order=["gemini", "groq", "ollama"],
        metrics={},
    )

    assert profile.priority == "smart"
    assert order[0] == "gemini"


def test_brain_router_garde_preferred_provider_pour_temps_reel(monkeypatch):
    monkeypatch.setenv("PHOEBUS_BRAIN_MODE", "local_first")
    monkeypatch.setenv("PHOEBUS_LOCAL_FIRST", "1")

    profile = build_profile("donne-moi la météo aujourd'hui")
    order = rank_provider_names(
        profile,
        available=["arena", "groq", "ollama"],
        order=["groq", "arena", "ollama"],
        metrics={},
    )

    assert profile.needs_realtime is True
    assert order[0] == "arena"


def test_brain_router_priorise_arena_pour_x_sans_cle_dediee(monkeypatch):
    monkeypatch.setenv("PHOEBUS_BRAIN_MODE", "balanced")
    monkeypatch.setenv("PHOEBUS_LOCAL_FIRST", "0")

    profile = build_profile("résume les tendances sur X autour de l'IA")
    order = rank_provider_names(
        profile,
        available=["gemini", "arena", "groq"],
        order=["gemini", "groq", "arena"],
        metrics={},
    )

    assert profile.preferred_provider == "grok"
    assert order[0] == "arena"


def test_brain_router_priorise_grok_quand_disponible(monkeypatch):
    monkeypatch.setenv("PHOEBUS_BRAIN_MODE", "balanced")
    monkeypatch.setenv("PHOEBUS_LOCAL_FIRST", "0")

    profile = build_profile("résume les tendances sur X autour de l'IA")
    order = rank_provider_names(
        profile,
        available=["gemini", "grok", "arena", "groq"],
        order=["gemini", "groq", "arena", "grok"],
        metrics={},
    )

    assert profile.preferred_provider == "grok"
    assert order[0] == "grok"
