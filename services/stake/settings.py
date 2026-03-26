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
    """LLM parser configuration for extracting race data from raw Stake.com text.

    Uses cheap fast model (flash-lite) for high-volume parsing.
    """

    model: str = Field(
        default="google/gemini-3.1-flash-lite-preview",
        description="OpenRouter model for parse step (cheap, high-volume)"
    )
    temperature: float = Field(
        default=0.0,
        description="LLM temperature for parsing (low for deterministic extraction)"
    )
    max_tokens: int = Field(
        default=4000,
        description="Max tokens for parse response"
    )


class ResearchSettings(BaseModel):
    """Research agent LLM config — cheap model for data gathering."""

    model: str = Field(
        default="google/gemini-3.1-flash-lite-preview",
        description="OpenRouter model for research (cheap, high-volume)"
    )
    temperature: float = Field(
        default=0.3,
        description="LLM temperature for research"
    )
    max_tokens: int = Field(
        default=4000,
        description="Max tokens for research response"
    )
    provider: str = Field(
        default="online",
        description="Search provider: 'online' (OpenRouter online model) or 'searxng' per D-05/SEARCH-02"
    )
    searxng_url: str = Field(
        default="http://46.30.43.46:8888/search",
        description="SearXNG endpoint URL (used when provider='searxng')"
    )


class AnalysisSettings(BaseModel):
    """Analysis/aggregation LLM config — expensive model, use sparingly."""

    model: str = Field(
        default="google/gemini-3.1-pro-preview",
        description="OpenRouter model for analysis aggregation (expensive, use sparingly)"
    )
    temperature: float = Field(
        default=0.7,
        description="LLM temperature for analysis"
    )
    max_tokens: int = Field(
        default=8000,
        description="Max tokens for analysis response"
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


class SizingSettings(BaseModel):
    """Bet sizing configuration.

    Controls Kelly criterion parameters, portfolio caps, and minimum bet sizes.
    Per BET-02 through BET-05 requirements.
    """

    kelly_multiplier: float = Field(
        default=0.25,
        description="Kelly fraction multiplier (0.25 = quarter-Kelly) per BET-02"
    )
    per_bet_cap_pct: float = Field(
        default=0.03,
        description="Max single bet as fraction of bankroll (3%) per BET-03"
    )
    max_total_exposure_pct: float = Field(
        default=0.05,
        description="Max total race exposure as fraction of bankroll (5%) per BET-04"
    )
    max_win_bets: int = Field(
        default=2,
        description="Max win bets per race per BET-04"
    )
    skip_overround_threshold: float = Field(
        default=15.0,
        description="Pre-analysis skip if overround margin exceeds this % per BET-05/D-06"
    )
    min_bet_usdt: float = Field(
        default=1.0,
        description="Minimum bet size in USDT — bets below this are rounded up or skipped"
    )
    sparsity_discount: float = Field(
        default=0.5,
        description="Sizing multiplier when research data is sparse per ANALYSIS-04/D-11"
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
    research: ResearchSettings = Field(default_factory=ResearchSettings)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    sizing: SizingSettings = Field(default_factory=SizingSettings)
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
