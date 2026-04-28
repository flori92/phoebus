"""
Configuration pytest pour PHOEBUS.
"""
import pytest
from unittest.mock import MagicMock, patch
import os
import sys

# Ajouter le dossier racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_env_vars():
    """Fixture pour variables d'environnement de test."""
    env = {
        "GEMINI_API_KEY": "test-gemini-key",
        "GROQ_API_KEY": "test-groq-key",
        "MISTRAL_API_KEY": "test-mistral-key",
        "PHOEBUS_WS_TOKEN": "test-token",
        "HOME_ASSISTANT_URL": "http://test.local:8123",
        "HOME_ASSISTANT_TOKEN": "test-ha-token",
    }
    with patch.dict(os.environ, env, clear=False):
        yield env


@pytest.fixture
def mock_genai_client():
    """Mock pour le client Gemini."""
    client = MagicMock()
    response = MagicMock()
    response.text = "Réponse test"
    client.models.generate_content.return_value = response
    return client


@pytest.fixture
def mock_state():
    """Mock pour l'état global."""
    with patch("PHOEBUS.state") as mock:
        mock.CONNECTED_CLIENTS = set()
        mock.interface_deja_connectee = False
        yield mock
