"""Configuration loader with Azure Key Vault + env var fallback."""
import logging
from functools import lru_cache
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.core.exceptions import ResourceNotFoundError, ClientAuthenticationError
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # ===== Key Vault =====
    azure_key_vault_url: Optional[str] = None
    use_key_vault: bool = False
    
    # ===== LLM =====
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_temperature: float = 0.2
    
    # ===== GitHub =====
    github_token: str = ""
    github_webhook_secret: str = ""
    
    # ===== App =====
    log_level: str = "INFO"
    max_iterations: int = 15
    max_diff_chars: int = 30000
    
    # ===== Safety =====
    allowed_repos: str = ""  # Comma-separated list; empty = allow all
    require_label: str = ""  # Only review PRs with this label (empty = always)
    default_dry_run: bool = False
    
    # ===== Caching =====
    cache_backend: str = "memory"  # 'memory' or 'redis'
    redis_url: str = ""
    cache_max_size: int = 1000
    
    # Per-tool TTLs (seconds)
    cache_ttl_pr_metadata: int = 300        # 5 min — PR state changes
    cache_ttl_pr_diff: int = 600            # 10 min — diffs stable per commit
    cache_ttl_pr_files: int = 600           # 10 min
    cache_ttl_file_content: int = 3600      # 1 hour — file at specific ref
    
    enable_tool_cache: bool = True
    
    @property
    def allowed_repos_set(self) -> set[str]:
        return {r.strip() for r in self.allowed_repos.split(",") if r.strip()}


class KeyVaultLoader:
    """Lazy loader for Azure Key Vault secrets with caching."""
    
    SECRET_MAPPING = {
        "openai_api_key": "openai-api-key",
        "github_token": "github-token",
        "github_webhook_secret": "github-webhook-secret",
    }
    
    def __init__(self, vault_url: str):
        self.vault_url = vault_url
        self._client: Optional[SecretClient] = None
        self._cache: dict[str, str] = {}
    
    @property
    def client(self) -> SecretClient:
        if self._client is None:
            logger.info(f"Initializing Key Vault client for {self.vault_url}")
            credential = DefaultAzureCredential(
                exclude_interactive_browser_credential=True,
            )
            self._client = SecretClient(
                vault_url=self.vault_url,
                credential=credential,
            )
        return self._client
    
    def get_secret(self, setting_name: str, default: str = "") -> str:
        if setting_name in self._cache:
            return self._cache[setting_name]
        
        secret_name = self.SECRET_MAPPING.get(setting_name)
        if not secret_name:
            return default
        
        try:
            secret = self.client.get_secret(secret_name)
            value = secret.value or default
            self._cache[setting_name] = value
            logger.info(f"Loaded secret '{secret_name}' from Key Vault")
            return value
        except ResourceNotFoundError:
            logger.warning(f"Secret '{secret_name}' not found")
            return default
        except ClientAuthenticationError as e:
            logger.error(f"Key Vault auth failed: {e}")
            raise


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build Settings, optionally pulling from Azure Key Vault."""
    settings = Settings()
    
    if settings.use_key_vault and settings.azure_key_vault_url:
        logger.info("Loading configuration from Azure Key Vault")
        loader = KeyVaultLoader(settings.azure_key_vault_url)
        for setting_name in KeyVaultLoader.SECRET_MAPPING:
            kv_value = loader.get_secret(setting_name, default="")
            if kv_value:
                setattr(settings, setting_name, kv_value)
    else:
        logger.info("Loading configuration from environment variables")
    
    # Validate required settings
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required")
    if not settings.github_token:
        raise ValueError("GITHUB_TOKEN is required")
    
    return settings
