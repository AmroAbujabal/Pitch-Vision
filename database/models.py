"""
database/models.py

SQLAlchemy ORM models.
Schema: Academy → Player → Match → PlayerMatchStats → MetricSnapshot
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer,
    String, Text, JSON, Uuid, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Academy
# ---------------------------------------------------------------------------

class Academy(Base):
    __tablename__ = "academies"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[Optional[str]] = mapped_column(String(200))   # Arabic name
    city: Mapped[str] = mapped_column(String(100), default="Dubai")
    country: Mapped[str] = mapped_column(String(100), default="UAE")
    tier: Mapped[str] = mapped_column(String(50))  # "starter" | "pro" | "club"
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    players: Mapped[list[Player]] = relationship("Player", back_populates="academy")
    matches: Mapped[list[Match]] = relationship("Match", back_populates="academy")


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

class Player(Base):
    __tablename__ = "players"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    academy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academies.id"))
    name: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[Optional[str]] = mapped_column(String(200))
    date_of_birth: Mapped[Optional[datetime]] = mapped_column(DateTime)
    nationality: Mapped[Optional[str]] = mapped_column(String(100))
    position: Mapped[str] = mapped_column(String(50))  # GK | CB | FB | DM | CM | AM | W | ST
    jersey_number: Mapped[Optional[int]] = mapped_column(Integer)
    preferred_foot: Mapped[Optional[str]] = mapped_column(String(10))  # left | right | both
    height_cm: Mapped[Optional[float]] = mapped_column(Float)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    academy: Mapped[Academy] = relationship("Academy", back_populates="players")
    match_stats: Mapped[list[PlayerMatchStats]] = relationship(
        "PlayerMatchStats", back_populates="player"
    )
    development_scores: Mapped[list[DevelopmentScore]] = relationship(
        "DevelopmentScore", back_populates="player"
    )


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------

class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    academy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academies.id"))
    home_team: Mapped[str] = mapped_column(String(200))
    away_team: Mapped[str] = mapped_column(String(200))
    match_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    venue: Mapped[Optional[str]] = mapped_column(String(200))
    video_path: Mapped[Optional[str]] = mapped_column(String(500))
    processing_status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # pending | processing | done | failed
    fps: Mapped[float] = mapped_column(Float, default=25.0)
    frame_width: Mapped[int] = mapped_column(Integer, default=1920)
    frame_height: Mapped[int] = mapped_column(Integer, default=1080)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    academy: Mapped[Academy] = relationship("Academy", back_populates="matches")
    player_stats: Mapped[list[PlayerMatchStats]] = relationship(
        "PlayerMatchStats", back_populates="match"
    )


# ---------------------------------------------------------------------------
# Player match statistics
# ---------------------------------------------------------------------------

class PlayerMatchStats(Base):
    """
    All computed metrics for one player in one match.
    Stored as JSON columns for flexibility — new metrics don't require migrations.
    """
    __tablename__ = "player_match_stats"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"))
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"))
    team: Mapped[str] = mapped_column(String(10))  # "home" | "away"
    minutes_played: Mapped[Optional[float]] = mapped_column(Float)

    # --- Physical ---
    top_speed_ms: Mapped[Optional[float]] = mapped_column(Float)
    avg_speed_ms: Mapped[Optional[float]] = mapped_column(Float)
    distance_covered_m: Mapped[Optional[float]] = mapped_column(Float)
    hi_run_count: Mapped[Optional[int]] = mapped_column(Integer)       # high intensity runs
    sprint_count: Mapped[Optional[int]] = mapped_column(Integer)
    acceleration_profile: Mapped[Optional[dict]] = mapped_column(JSON) # {mean, peak, count}
    fatigue_index: Mapped[Optional[float]] = mapped_column(Float)       # 70-90 vs 0-20 min ratio

    # --- Pressing ---
    press_count: Mapped[Optional[int]] = mapped_column(Integer)
    press_success_rate: Mapped[Optional[float]] = mapped_column(Float)
    press_trigger_accuracy: Mapped[Optional[float]] = mapped_column(Float)
    recovery_shadow_score: Mapped[Optional[float]] = mapped_column(Float)
    ppda_contribution: Mapped[Optional[float]] = mapped_column(Float)

    # --- Spatial ---
    pitch_control_contribution: Mapped[Optional[float]] = mapped_column(Float)
    dangerous_zone_occupancy: Mapped[Optional[float]] = mapped_column(Float)
    heatmap_data: Mapped[Optional[dict]] = mapped_column(JSON)          # grid array

    # --- Off-ball ---
    space_creation_index: Mapped[Optional[float]] = mapped_column(Float)
    run_threat_score: Mapped[Optional[float]] = mapped_column(Float)
    shadow_escape_rate: Mapped[Optional[float]] = mapped_column(Float)
    third_man_availability: Mapped[Optional[float]] = mapped_column(Float)

    # --- Decision quality ---
    decision_score: Mapped[Optional[float]] = mapped_column(Float)
    xt_added: Mapped[Optional[float]] = mapped_column(Float)            # expected threat added
    under_pressure_pass_quality: Mapped[Optional[float]] = mapped_column(Float)
    turnover_location_value: Mapped[Optional[float]] = mapped_column(Float)

    # --- Weak foot ---
    weak_foot_action_pct: Mapped[Optional[float]] = mapped_column(Float)
    weak_foot_success_rate: Mapped[Optional[float]] = mapped_column(Float)

    # --- Duel analysis ---
    duel_typology: Mapped[Optional[dict]] = mapped_column(JSON)         # {type: {count, win_rate}}

    # --- Composite scores ---
    positional_iq_score: Mapped[Optional[float]] = mapped_column(Float)
    overall_rating: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    player: Mapped[Player] = relationship("Player", back_populates="match_stats")
    match: Mapped[Match] = relationship("Match", back_populates="player_stats")


# ---------------------------------------------------------------------------
# Development tracking (week-on-week progression)
# ---------------------------------------------------------------------------

class DevelopmentScore(Base):
    """Weekly player development score — used for academy progression tracking."""
    __tablename__ = "development_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"))
    week_start: Mapped[datetime] = mapped_column(DateTime)
    overall_score: Mapped[float] = mapped_column(Float)
    physical_score: Mapped[Optional[float]] = mapped_column(Float)
    tactical_score: Mapped[Optional[float]] = mapped_column(Float)
    technical_score: Mapped[Optional[float]] = mapped_column(Float)
    weak_foot_progress: Mapped[Optional[float]] = mapped_column(Float)  # delta from prev week
    flags: Mapped[Optional[dict]] = mapped_column(JSON)   # coach flags, e.g. {"weak_foot": true}
    coach_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    player: Mapped[Player] = relationship("Player", back_populates="development_scores")
