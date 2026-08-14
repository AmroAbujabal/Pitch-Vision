"""
api/schemas/__init__.py

Shared Pydantic response schemas used across multiple routers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MatchSummaryResponse(BaseModel):
    """Aggregated match-level stats for the dashboard match card."""
    model_config = ConfigDict(from_attributes=True)

    match_id: UUID
    home_team: str
    away_team: str
    processing_status: str
    player_count: int
    home_pitch_control_pct: float
    away_pitch_control_pct: float
    home_top_speed_ms: float
    away_top_speed_ms: float
    home_press_count: int
    away_press_count: int
    # None until the match has been processed; "unknown" when the shape could
    # not be labelled (no calibration, or too few tracked players).
    home_formation: Optional[str] = None
    away_formation: Optional[str] = None


class MatchPlayerResponse(BaseModel):
    """One player's stats within a match — used in the match player list."""
    model_config = ConfigDict(from_attributes=True)

    player_id: UUID
    player_name: str
    team: str
    distance_covered_m: Optional[float] = None
    top_speed_ms: Optional[float] = None
    avg_speed_ms: Optional[float] = None
    sprint_count: Optional[int] = None
    hi_run_count: Optional[int] = None
    press_count: Optional[int] = None
    press_success_rate: Optional[float] = None
    pitch_control_contribution: Optional[float] = None


class PlayerStatsResponse(BaseModel):
    """One match entry in a player's stats history."""
    model_config = ConfigDict(from_attributes=True)

    match_id: UUID
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    team: str
    distance_covered_m: Optional[float] = None
    top_speed_ms: Optional[float] = None
    avg_speed_ms: Optional[float] = None
    sprint_count: Optional[int] = None
    hi_run_count: Optional[int] = None
    press_count: Optional[int] = None
    press_success_rate: Optional[float] = None
    pitch_control_contribution: Optional[float] = None



class DevelopmentScoreResponse(BaseModel):
    """One week's development score entry for a player."""
    model_config = ConfigDict(from_attributes=True)

    week_start: datetime
    overall_score: float
    physical_score: Optional[float] = None
    tactical_score: Optional[float] = None
    technical_score: Optional[float] = None


class PlayerProfileResponse(BaseModel):
    """Full player profile: bio + latest match stats + development trend."""
    model_config = ConfigDict(from_attributes=True)

    player_id: UUID
    name: str
    position: str
    jersey_number: Optional[int] = None
    academy_id: UUID
    latest_stats: Optional[PlayerStatsResponse] = None
    development_trend: list[DevelopmentScoreResponse] = []


class PlayerHeatmapResponse(BaseModel):
    """Heatmap grid data for a player in a specific match."""
    model_config = ConfigDict(from_attributes=True)

    player_id: UUID
    match_id: UUID
    heatmap_data: Optional[dict[str, Any]] = None
