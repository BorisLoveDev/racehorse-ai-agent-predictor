"""
Pydantic models for structured bet outputs from AI agents.
All bet types follow TabTouch betting conventions.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class WinBet(BaseModel):
    """Bet on a horse to win (1st place)."""

    horse_number: int = Field(..., ge=1, description="Horse number")
    amount: float = Field(..., gt=0, description="Bet amount")
    reasoning: str = Field(default="", description="Why this bet")

    @field_validator("horse_number")
    @classmethod
    def validate_horse_number(cls, v: int) -> int:
        if v < 1 or v > 30:
            raise ValueError("Horse number must be between 1 and 30")
        return v


class PlaceBet(BaseModel):
    """Bet on a horse to place (1st, 2nd, or 3rd)."""

    horse_number: int = Field(..., ge=1, description="Horse number")
    amount: float = Field(..., gt=0, description="Bet amount")
    reasoning: str = Field(default="", description="Why this bet")

    @field_validator("horse_number")
    @classmethod
    def validate_horse_number(cls, v: int) -> int:
        if v < 1 or v > 30:
            raise ValueError("Horse number must be between 1 and 30")
        return v


class ExactaBet(BaseModel):
    """Bet on exact 1st and 2nd finish order."""

    first: int = Field(..., ge=1, description="Horse to finish 1st")
    second: int = Field(..., ge=1, description="Horse to finish 2nd")
    amount: float = Field(..., gt=0, description="Bet amount")
    reasoning: str = Field(default="", description="Why this bet")

    @field_validator("first", "second")
    @classmethod
    def validate_horse_numbers(cls, v: int) -> int:
        if v < 1 or v > 30:
            raise ValueError("Horse number must be between 1 and 30")
        return v

    def model_post_init(self, __context) -> None:
        """Validate that first and second are different."""
        if self.first == self.second:
            raise ValueError("First and second horses must be different")


class QuinellaBet(BaseModel):
    """Bet on two horses to finish 1st and 2nd in any order."""

    horses: list[int] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Two horses (any order)"
    )
    amount: float = Field(..., gt=0, description="Bet amount")
    reasoning: str = Field(default="", description="Why this bet")

    @field_validator("horses")
    @classmethod
    def validate_horses(cls, v: list[int]) -> list[int]:
        if len(v) != 2:
            raise ValueError("Quinella requires exactly 2 horses")
        if v[0] == v[1]:
            raise ValueError("Horses must be different")
        for horse in v:
            if horse < 1 or horse > 30:
                raise ValueError("Horse numbers must be between 1 and 30")
        return sorted(v)  # Sort for consistency


class TrifectaBet(BaseModel):
    """Bet on exact 1st, 2nd, and 3rd finish order."""

    first: int = Field(..., ge=1, description="Horse to finish 1st")
    second: int = Field(..., ge=1, description="Horse to finish 2nd")
    third: int = Field(..., ge=1, description="Horse to finish 3rd")
    amount: float = Field(..., gt=0, description="Bet amount")
    reasoning: str = Field(default="", description="Why this bet")

    @field_validator("first", "second", "third")
    @classmethod
    def validate_horse_numbers(cls, v: int) -> int:
        if v < 1 or v > 30:
            raise ValueError("Horse number must be between 1 and 30")
        return v

    def model_post_init(self, __context) -> None:
        """Validate all horses are different."""
        horses = [self.first, self.second, self.third]
        if len(set(horses)) != 3:
            raise ValueError("All three horses must be different")


class First4Bet(BaseModel):
    """Bet on exact 1st, 2nd, 3rd, and 4th finish order."""

    horses: list[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Four horses in exact finish order"
    )
    amount: float = Field(..., gt=0, description="Bet amount")
    reasoning: str = Field(default="", description="Why this bet")

    @field_validator("horses")
    @classmethod
    def validate_horses(cls, v: list[int]) -> list[int]:
        if len(v) != 4:
            raise ValueError("First4 requires exactly 4 horses")
        if len(set(v)) != 4:
            raise ValueError("All four horses must be different")
        for horse in v:
            if horse < 1 or horse > 30:
                raise ValueError("Horse numbers must be between 1 and 30")
        return v


class QPSBet(BaseModel):
    """
    Quinella Place Special - select 2-4 horses, any 2 to finish in top 3.
    """

    horses: list[int] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="2-4 horses, any 2 must finish in top 3"
    )
    amount: float = Field(..., gt=0, description="Bet amount")
    reasoning: str = Field(default="", description="Why this bet")

    @field_validator("horses")
    @classmethod
    def validate_horses(cls, v: list[int]) -> list[int]:
        if len(v) < 2 or len(v) > 4:
            raise ValueError("QPS requires 2-4 horses")
        if len(set(v)) != len(v):
            raise ValueError("All horses must be different")
        for horse in v:
            if horse < 1 or horse > 30:
                raise ValueError("Horse numbers must be between 1 and 30")
        return sorted(v)  # Sort for consistency


class StructuredBetOutput(BaseModel):
    """
    Complete structured output from AI agent analysis.
    This is the schema used with llm.with_structured_output().
    """

    # Race identification
    race_url: str = Field(..., description="TabTouch race URL")
    race_location: str = Field(..., description="Race location/track")
    race_number: int = Field(..., ge=1, description="Race number")

    # Analysis summary
    analysis_summary: str = Field(
        ...,
        min_length=50,
        description="Brief summary of key analysis findings"
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence in predictions (0-1)"
    )

    # Bet recommendations (all optional)
    win_bet: Optional[WinBet] = Field(
        default=None,
        description="Win bet recommendation"
    )
    place_bet: Optional[PlaceBet] = Field(
        default=None,
        description="Place bet recommendation"
    )
    exacta_bet: Optional[ExactaBet] = Field(
        default=None,
        description="Exacta bet recommendation"
    )
    quinella_bet: Optional[QuinellaBet] = Field(
        default=None,
        description="Quinella bet recommendation"
    )
    trifecta_bet: Optional[TrifectaBet] = Field(
        default=None,
        description="Trifecta bet recommendation"
    )
    first4_bet: Optional[First4Bet] = Field(
        default=None,
        description="First4 bet recommendation"
    )
    qps_bet: Optional[QPSBet] = Field(
        default=None,
        description="QPS bet recommendation"
    )

    # Additional metadata
    key_factors: list[str] = Field(
        default_factory=list,
        description="Key factors influencing predictions"
    )
    risk_level: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Overall risk assessment"
    )
    agent_name: str = Field(
        default="",
        description="Name of the AI agent (e.g., 'gemini', 'grok')"
    )

    def total_bet_amount(self) -> float:
        """Calculate total amount across all bets."""
        total = 0.0
        if self.win_bet:
            total += self.win_bet.amount
        if self.place_bet:
            total += self.place_bet.amount
        if self.exacta_bet:
            total += self.exacta_bet.amount
        if self.quinella_bet:
            total += self.quinella_bet.amount
        if self.trifecta_bet:
            total += self.trifecta_bet.amount
        if self.first4_bet:
            total += self.first4_bet.amount
        if self.qps_bet:
            total += self.qps_bet.amount
        return total

    def has_any_bets(self) -> bool:
        """Check if any bets are recommended."""
        return any([
            self.win_bet,
            self.place_bet,
            self.exacta_bet,
            self.quinella_bet,
            self.trifecta_bet,
            self.first4_bet,
            self.qps_bet
        ])

    def get_all_bets(self) -> dict[str, BaseModel]:
        """Get all non-None bets as a dictionary."""
        bets = {}
        if self.win_bet:
            bets["win"] = self.win_bet
        if self.place_bet:
            bets["place"] = self.place_bet
        if self.exacta_bet:
            bets["exacta"] = self.exacta_bet
        if self.quinella_bet:
            bets["quinella"] = self.quinella_bet
        if self.trifecta_bet:
            bets["trifecta"] = self.trifecta_bet
        if self.first4_bet:
            bets["first4"] = self.first4_bet
        if self.qps_bet:
            bets["qps"] = self.qps_bet
        return bets
