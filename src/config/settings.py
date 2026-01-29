"""
Centralized configuration for the Horse Racing Betting Agent System.
Uses Pydantic Settings with environment variable support.
"""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TimingSettings(BaseSettings):
    """Timing configuration for race monitoring and analysis."""

    minutes_before_race: int = Field(
        default=3,
        description="Trigger AI analysis N minutes before race starts"
    )
    result_wait_minutes: int = Field(
        default=15,
        description="Wait N minutes after race for results to appear"
    )
    result_max_retries: int = Field(
        default=5,
        description="Maximum retry attempts when fetching results"
    )
    result_retry_interval: int = Field(
        default=180,
        description="Seconds between result fetch retries"
    )
    monitor_poll_interval: int = Field(
        default=60,
        description="Seconds between race monitoring checks"
    )


class BettingSettings(BaseSettings):
    """Betting configuration and constraints."""

    default_bet_amount: float = Field(
        default=100.0,
        description="Default budget per race (not real money, for tracking)"
    )
    min_confidence_to_bet: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score required to place bet"
    )
    max_bet_amount: float = Field(
        default=500.0,
        description="Maximum bet amount per race"
    )
    enable_exotic_bets: bool = Field(
        default=True,
        description="Enable exotic bets (Exacta, Trifecta, First4, QPS)"
    )


class GeminiAgentSettings(BaseSettings):
    """Gemini agent configuration."""

    model_id: str = Field(
        default="google/gemini-3-flash-preview",
        description="Gemini model ID via OpenRouter"
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8000)
    enable_web_search: bool = Field(default=True)


class GrokAgentSettings(BaseSettings):
    """Grok agent configuration."""

    model_id: str = Field(
        default="x-ai/grok-4.1-fast",
        description="Grok model ID via OpenRouter"
    )
    reasoning_effort: str = Field(
        default="high",
        description="Reasoning effort level for Grok"
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8000)
    enable_web_search: bool = Field(default=True)


class ResearchAgentSettings(BaseSettings):
    """Research agent configuration - runs before betting agents to gather info."""

    model_id: str = Field(
        default="google/gemini-3-flash-preview",
        description="Model for research agent (query generation, summarization)"
    )
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000)
    enabled: bool = Field(
        default=True,
        description="Enable research agent to pre-fetch search results"
    )
    top_horses_to_research: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of top horses to research"
    )
    include_jockeys: bool = Field(
        default=True,
        description="Include jockey research queries"
    )
    include_trainers: bool = Field(
        default=True,
        description="Include trainer research queries"
    )


class AgentsSettings(BaseSettings):
    """Agent configuration container."""

    gemini: GeminiAgentSettings = Field(default_factory=GeminiAgentSettings)
    grok: GrokAgentSettings = Field(default_factory=GrokAgentSettings)
    research: ResearchAgentSettings = Field(default_factory=ResearchAgentSettings)
    parallel_execution: bool = Field(
        default=True,
        description="Run both agents in parallel"
    )


class WebSearchSettings(BaseSettings):
    """Web search configuration."""

    engine: str = Field(
        default="searxng",
        description="Search engine: 'searxng' (recommended) or 'duckduckgo'"
    )
    searxng_url: str = Field(
        default="http://localhost:8080",
        description="SearXNG instance URL"
    )
    mode: str = Field(
        default="raw",
        description="Search mode: 'off' (disabled), 'raw' (snippets only), 'lite' (LLM extracts), 'deep' (full research)"
    )
    enabled: bool = Field(
        default=True,
        description="Enable web search for additional context"
    )
    max_results_per_query: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum results per search query"
    )
    max_queries_per_race: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum total queries per race analysis"
    )
    deep_mode_max_sites: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum sites to visit in deep mode"
    )
    enable_cache: bool = Field(
        default=True,
        description="Cache search results to avoid duplicates"
    )
    cache_ttl_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Cache time-to-live in seconds"
    )


class APIKeysSettings(BaseSettings):
    """API keys and credentials."""

    openrouter_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="OpenRouter API key for LLM access"
    )
    telegram_bot_token: SecretStr = Field(
        default=SecretStr(""),
        description="Telegram bot token for notifications"
    )
    telegram_chat_id: str = Field(
        default="",
        description="Telegram chat ID to send notifications"
    )


class RedisSettings(BaseSettings):
    """Redis configuration for pub/sub messaging."""

    host: str = Field(default="localhost")
    port: int = Field(default=6379)
    db: int = Field(default=0)
    password: str = Field(default="")


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    path: str = Field(
        default="races.db",
        description="Path to SQLite database file"
    )


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="RACEHORSE_",
        env_nested_delimiter="__",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Sub-settings
    timing: TimingSettings = Field(default_factory=TimingSettings)
    betting: BettingSettings = Field(default_factory=BettingSettings)
    agents: AgentsSettings = Field(default_factory=AgentsSettings)
    api_keys: APIKeysSettings = Field(default_factory=APIKeysSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    web_search: WebSearchSettings = Field(default_factory=WebSearchSettings)

    # Source timezone (TabTouch's timezone - don't change)
    source_timezone: str = Field(
        default="Australia/Perth",
        description="TabTouch operates in Perth timezone"
    )

    # Client timezone for display
    client_timezone: str = Field(
        default="Asia/Kuala_Lumpur",
        description="User's local timezone for display"
    )

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
