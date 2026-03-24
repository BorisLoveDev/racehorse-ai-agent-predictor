"""
Stake Advisor Bot configuration.
Uses Pydantic Settings with STAKE_ prefix and __ nested delimiter.

IMPORTANT: Nested config classes extend BaseModel (not BaseSettings).
This is required for env_nested_delimiter="__" to work correctly —
if nested classes were BaseSettings, each would try to load env vars
independently instead of delegating to the parent's prefix/delimiter.
With BaseModel, STAKE_PARSER__MODEL correctly populates parser.model.
"""

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ParserSettings(BaseModel):
    """LLM parser configuration for extracting race data from raw Stake.com text."""

    model: str = Field(
        default="google/gemini-2.0-flash-001",
        description="OpenRouter model for parse step"
    )
    temperature: float = Field(
        default=0.0,
        description="LLM temperature for parsing (low for deterministic extraction)"
    )
    max_tokens: int = Field(
        default=4000,
        description="Max tokens for parse response"
    )


class RedisSettings(BaseModel):
    """Redis configuration for FSM state persistence (aiogram)."""

    url: str = Field(
        default="redis://redis:6379",
        description="Redis URL for FSM storage"
    )
    state_ttl: int = Field(
        default=86400,
        description="FSM state TTL in seconds (24h)"
    )
    data_ttl: int = Field(
        default=86400,
        description="FSM data TTL in seconds (24h)"
    )


class BankrollSettings(BaseModel):
    """Bankroll management defaults."""

    default_stake_pct: float = Field(
        default=0.02,
        description="Default stake as fraction of bankroll (2%)"
    )


class AuditSettings(BaseModel):
    """Audit log configuration."""

    log_path: str = Field(
        default="data/stake_audit.jsonl",
        description="Path to JSONL audit log file"
    )


class StakeSettings(BaseSettings):
    """Main settings for the Stake Advisor Bot service.

    Loads from environment variables with STAKE_ prefix.
    Nested settings use __ as delimiter (e.g., STAKE_PARSER__MODEL).
    """

    model_config = SettingsConfigDict(
        env_prefix="STAKE_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore"
    )

    parser: ParserSettings = Field(default_factory=ParserSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    bankroll: BankrollSettings = Field(default_factory=BankrollSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)

    database_path: str = Field(
        default="races.db",
        description="SQLite database path"
    )
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key"
    )
    telegram_bot_token: str = Field(
        default="",
        description="Telegram bot token"
    )
    telegram_chat_id: str = Field(
        default="",
        description="Telegram chat ID"
    )


@lru_cache()
def get_stake_settings() -> StakeSettings:
    """Return singleton StakeSettings instance."""
    return StakeSettings()
