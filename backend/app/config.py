from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    gnani_api_key: SecretStr | None = None
    gnani_base_url: str = "https://api.vachana.ai"
    prisma_model: str = "prisma-v3.0"
    prisma_format: str = "codemix"
    timbre_model: str = "timbre-v3.0"
    timbre_voice: str = "Lakshmi"
    timbre_speed: float = 0.95
    http_timeout_s: float = 30.0

    # V2 live call (WebRTC). STUN works on most home/LAN networks; add TURN for strict NATs.
    ice_stun_urls: str = "stun:stun.l.google.com:19302,stun:stun1.l.google.com:19302"
    ice_turn_url: str | None = None
    ice_turn_username: str | None = None
    ice_turn_credential: SecretStr | None = None
    public_base_url: str | None = None  # e.g. https://192.168.1.7:8443 ; default: derived from the request

    @property
    def key_configured(self) -> bool:
        k = self.gnani_api_key.get_secret_value() if self.gnani_api_key else ""
        return bool(k) and k != "your-gnani-api-key-here"


@lru_cache
def get_settings() -> Settings:
    return Settings()
