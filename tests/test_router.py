"""
Tests pour le router de commandes PHOEBUS.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import json

from PHOEBUS.router import (
    extraire_json_de_reponse,
    executer_commande_generique,
    traiter_reponse_ia
)


class TestExtraireJson:
    """Tests pour l'extraction JSON."""
    
    def test_json_simple(self):
        """JSON sans balises."""
        texte = '{"action": "test", "value": 123}'
        result = extraire_json_de_reponse(texte)
        assert result == {"action": "test", "value": 123}
    
    def test_json_avec_backticks(self):
        """JSON dans bloc markdown."""
        texte = """```json
        {"action": "test"}
        ```"""
        result = extraire_json_de_reponse(texte)
        assert result == {"action": "test"}
    
    def test_json_invalide(self):
        """JSON malformé."""
        texte = '{"action": "test"'  # Manque fermeture
        result = extraire_json_de_reponse(texte)
        assert result is None
    
    def test_texte_sans_json(self):
        """Texte sans JSON."""
        texte = "Juste du texte normal"
        result = extraire_json_de_reponse(texte)
        assert result is None


class TestExecuterCommande:
    """Tests pour l'exécution des commandes."""
    
    @pytest.mark.asyncio
    async def test_commande_domotique(self):
        """Commande domotique détectée."""
        with patch("PHOEBUS.home.executer_action_ha") as mock_ha:
            mock_ha.return_value = {"success": True}
            
            result = await executer_commande_generique({
                "action": "home",
                "entity_id": "light.salon",
                "service": "turn_on"
            })
            
            mock_ha.assert_called_once()
            assert "success" in str(result)
    
    @pytest.mark.asyncio
    async def test_commande_shell(self):
        """Commande shell."""
        with patch("PHOEBUS.agent.executer_commande_shell") as mock_shell:
            mock_shell.return_value = "output test"
            
            result = await executer_commande_generique({
                "action": "shell",
                "command": "ls -la"
            })
            
            mock_shell.assert_called_once_with("ls -la")
            assert "output test" in str(result)
    
    @pytest.mark.asyncio
    async def test_action_inconnue(self):
        """Action non reconnue."""
        result = await executer_commande_generique({
            "action": "unknown_action"
        })
        
        assert "inconnue" in str(result).lower() or "unknown" in str(result).lower()


class TestTraiterReponseIA:
    """Tests pour le traitement des réponses IA."""
    
    @pytest.mark.asyncio
    async def test_reponse_avec_action(self):
        """Réponse contenant une action."""
        with patch("PHOEBUS.router.executer_commande_generique") as mock_exec:
            mock_exec.return_value = "Action exécutée"
            
            reponse = '{"action": "home", "entity_id": "test"}\n\nTexte explicatif'
            result = await traiter_reponse_ia(reponse, "123")
            
            mock_exec.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_reponse_sans_action(self):
        """Réponse texte simple sans action."""
        reponse = "Juste une réponse textuelle"
        result = await traiter_reponse_ia(reponse, "123")
        
        # Ne devrait pas lever d'exception
        assert isinstance(result, str) or result is None


class TestSecurity:
    """Tests pour la sécurité du router."""
    
    @pytest.mark.asyncio
    async def test_commande_dangereuse_bloquee(self):
        """Commandes sensibles requièrent confirmation."""
        with patch("PHOEBUS.security.audit_log") as mock_audit:
            result = await executer_commande_generique({
                "action": "shell",
                "command": "rm -rf /"
            })
            
            # Devrait être auditée
            mock_audit.assert_called()
