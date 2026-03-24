"""
Unit tests for StakeSettings configuration class.
Tests default values, env var overrides, and singleton pattern.
"""

import os
import pytest


def test_default_parser_model():
    """StakeSettings().parser.model returns default gemini model."""
    # Clear any lingering env vars
    os.environ.pop("STAKE_PARSER__MODEL", None)
    from services.stake.settings import StakeSettings
    s = StakeSettings()
    assert s.parser.model == "google/gemini-2.0-flash-001"


def test_parser_model_env_override(monkeypatch):
    """STAKE_PARSER__MODEL env var overrides parser.model."""
    monkeypatch.setenv("STAKE_PARSER__MODEL", "test-model")
    from services.stake.settings import StakeSettings
    s = StakeSettings()
    assert s.parser.model == "test-model"


def test_default_redis_url():
    """StakeSettings().redis.url returns default redis URL."""
    os.environ.pop("STAKE_REDIS__URL", None)
    from services.stake.settings import StakeSettings
    s = StakeSettings()
    assert s.redis.url == "redis://redis:6379"


def test_default_stake_pct():
    """StakeSettings().bankroll.default_stake_pct returns 0.02."""
    os.environ.pop("STAKE_BANKROLL__DEFAULT_STAKE_PCT", None)
    from services.stake.settings import StakeSettings
    s = StakeSettings()
    assert s.bankroll.default_stake_pct == 0.02


def test_default_audit_log_path():
    """StakeSettings().audit.log_path returns default path."""
    os.environ.pop("STAKE_AUDIT__LOG_PATH", None)
    from services.stake.settings import StakeSettings
    s = StakeSettings()
    assert s.audit.log_path == "data/stake_audit.jsonl"


def test_get_stake_settings_returns_instance():
    """get_stake_settings() returns a StakeSettings instance."""
    from services.stake.settings import StakeSettings, get_stake_settings
    result = get_stake_settings()
    assert isinstance(result, StakeSettings)


def test_nested_classes_are_not_base_settings():
    """Nested config classes must be BaseModel, not BaseSettings."""
    from pydantic import BaseModel
    from pydantic_settings import BaseSettings
    from services.stake.settings import (
        ParserSettings,
        RedisSettings,
        BankrollSettings,
        AuditSettings,
        StakeSettings,
    )
    assert issubclass(ParserSettings, BaseModel)
    assert issubclass(RedisSettings, BaseModel)
    assert issubclass(BankrollSettings, BaseModel)
    assert issubclass(AuditSettings, BaseModel)
    # Only root class is BaseSettings
    assert issubclass(StakeSettings, BaseSettings)
    # Nested classes must NOT be BaseSettings directly
    assert not issubclass(ParserSettings, BaseSettings)
    assert not issubclass(RedisSettings, BaseSettings)
    assert not issubclass(BankrollSettings, BaseSettings)
    assert not issubclass(AuditSettings, BaseSettings)


def test_stake_env_prefix():
    """StakeSettings uses STAKE_ env prefix."""
    from services.stake.settings import StakeSettings
    config = StakeSettings.model_config
    assert config.get("env_prefix") == "STAKE_"


def test_nested_delimiter():
    """StakeSettings uses __ as nested delimiter."""
    from services.stake.settings import StakeSettings
    config = StakeSettings.model_config
    assert config.get("env_nested_delimiter") == "__"
