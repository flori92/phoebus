"""
Configuration PHOEBUS avec validation Pydantic.
Remplace progressivement la config legacy.
"""
from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings
from typing import Optional, List
from pathlib import Path


class LLMConfig(BaseSettings):
    """Configuration des providers LLM."""
    model_config = ConfigDict(env_prefix="")
    
    gemini_api_key: Optional[str] = Field(default=None, description="Clé API Gemini")
    groq_api_key: Optional[str] = Field(default=None, description="Clé API Groq")
    mistral_api_key: Optional[str] = Field(default=None, description="Clé API Mistral")
    openai_api_key: Optional[str] = Field(default=None, description="Clé API OpenAI")
    xai_api_key: Optional[str] = Field(default=None, description="Clé API xAI/Grok")
    kimi_api_key: Optional[str] = Field(default=None, description="Clé API Kimi")
    
    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class ServerConfig(BaseSettings):
    """Configuration du serveur WebSocket/HTTP."""
    model_config = ConfigDict(env_prefix="PHOEBUS_")
    
    ws_token: str = Field(
        default="CHANGE_ME",
        min_length=8,
        description="Token d'authentification WebSocket"
    )
    ws_port: int = Field(default=8765, ge=1024, le=65535)
    mobile_port: int = Field(default=8080, ge=1024, le=65535)
    ws_auth_required: bool = Field(default=True)
    
    @field_validator("ws_token")
    @classmethod
    def validate_token_not_default(cls, v):
        forbidden = {"CHANGE_ME", "VOTRE_TOKEN_ICI", "CHANGE_MOI_IMMEDIATEMENT"}
        if v in forbidden:
            raise ValueError(f"Token par défaut non sécurisé: {v}")
        return v


class HomeAssistantConfig(BaseSettings):
    """Configuration Home Assistant."""
    model_config = ConfigDict(env_prefix="")
    
    home_assistant_url: Optional[str] = Field(default=None)
    home_assistant_token: Optional[str] = Field(default=None)
    
    @field_validator("home_assistant_url")
    @classmethod
    def validate_url(cls, v):
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("URL HA doit commencer par http:// ou https://")
        return v


class AudioConfig(BaseSettings):
    """Configuration audio/VAD."""
    model_config = ConfigDict(env_prefix="PHOEBUS_")
    
    wake_enabled: bool = Field(default=True)
    vad_mode: int = Field(default=2, ge=0, le=3, description="Mode VAD (0-3)")
    multi_user: bool = Field(default=False)
    audio_threshold: float = Field(default=0.02, ge=0.0, le=1.0)


class PhoebusConfig(BaseSettings):
    """Configuration globale PHOEBUS."""
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    llm: LLMConfig = Field(default_factory=LLMConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    home_assistant: HomeAssistantConfig = Field(default_factory=HomeAssistantConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    
    base_dir: Path = Field(default=Path(__file__).parent.parent)
    
    @property
    def is_production(self) -> bool:
        """Vérifie si on est en production."""
        token = self.server.ws_token.strip().lower()
        return token not in {"change_me", "test"} and not token.startswith("test")
    
    def get_available_llm_providers(self) -> List[str]:
        """Liste les providers LLM configurés."""
        providers = []
        if self.llm.gemini_api_key:
            providers.append("gemini")
        if self.llm.groq_api_key:
            providers.append("groq")
        if self.llm.mistral_api_key:
            providers.append("mistral")
        if self.llm.openai_api_key:
            providers.append("openai")
        return providers


# Instance globale (lazy loading)
_config_instance: Optional[PhoebusConfig] = None


def get_config() -> PhoebusConfig:
    """Retourne l'instance singleton de configuration."""
    global _config_instance
    if _config_instance is None:
        _config_instance = PhoebusConfig()
    return _config_instance


def reload_config() -> PhoebusConfig:
    """Force le rechargement de la configuration."""
    global _config_instance
    _config_instance = PhoebusConfig()
    return _config_instance
