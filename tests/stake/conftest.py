"""
Pytest fixtures for stake service tests.
"""

import pytest
from services.stake.parser.models import RunnerInfo, ParsedRace


@pytest.fixture
def sample_runners() -> list[RunnerInfo]:
    """Return a list of 5 RunnerInfo objects: 3 active, 1 scratched, 1 active."""
    return [
        RunnerInfo(
            number=1,
            name="Thunder Bolt",
            barrier=3,
            jockey="J. Smith",
            trainer="T. Jones",
            win_odds=2.5,
            win_odds_format="decimal",
            place_odds=1.4,
            place_odds_format="decimal",
            opening_odds=2.8,
            status="active",
        ),
        RunnerInfo(
            number=2,
            name="Golden Arrow",
            barrier=1,
            jockey="R. Davis",
            trainer="M. Brown",
            win_odds=4.0,
            win_odds_format="decimal",
            place_odds=1.9,
            place_odds_format="decimal",
            opening_odds=4.5,
            status="active",
        ),
        RunnerInfo(
            number=3,
            name="Silver Streak",
            barrier=5,
            jockey="P. Wilson",
            trainer="A. Clark",
            win_odds=6.0,
            win_odds_format="decimal",
            place_odds=2.2,
            place_odds_format="decimal",
            opening_odds=5.5,
            status="active",
        ),
        RunnerInfo(
            number=4,
            name="Dark Knight",
            barrier=2,
            jockey="S. Taylor",
            trainer="C. White",
            status="scratched",
        ),
        RunnerInfo(
            number=5,
            name="Morning Star",
            barrier=7,
            jockey="B. Harris",
            trainer="D. Lewis",
            win_odds=8.0,
            win_odds_format="decimal",
            place_odds=3.0,
            place_odds_format="decimal",
            opening_odds=7.5,
            status="active",
        ),
    ]


@pytest.fixture
def sample_parsed_race(sample_runners: list[RunnerInfo]) -> ParsedRace:
    """Return a ParsedRace using the sample runners fixture."""
    return ParsedRace(
        platform="Stake.com",
        sport="horse_racing",
        region="Australia",
        track="Flemington",
        race_number="5",
        race_name="Flemington Cup",
        date="2026-03-24",
        distance="1600m",
        surface="Turf",
        time_to_start="3:15",
        runner_count=5,
        bet_types_available=["win", "place", "exacta", "quinella"],
        place_terms="1-2-3",
        runners=sample_runners,
    )
