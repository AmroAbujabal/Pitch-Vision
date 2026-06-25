"""
api/routers/players.py

Player CRUD and profile endpoints.
"""

import pickle
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import get_current_academy_id
from api.deps import get_db
from api.schemas import (
    PlayerStatsResponse,
    PlayerProfileResponse,
    DevelopmentScoreResponse,
    PlayerHeatmapResponse,
)
from config.settings import PROJECT_ROOT
from database.models import DevelopmentScore, Match, Player, PlayerMatchStats
from metrics.features import FEATURE_KEYS, assemble_player_features

router = APIRouter(dependencies=[Depends(get_current_academy_id)])

_PLAYER_NOT_FOUND = HTTPException(status_code=404, detail="Player not found")
_MIN_MATCHES = 2
_HISTORY_WINDOW = 8
_MODEL_CONFIDENCE = 0.80
_FALLBACK_CONFIDENCE = 0.30
_DEFAULT_DEV_SCORE = 5.0

_MODEL_DIR = PROJECT_ROOT / "data" / "models"


@lru_cache(maxsize=16)
def _load_model(position: str) -> Any | None:
    """Load pickled sklearn model for a position group. Returns None if not trained yet.
    Cached per process — restart worker after retraining to pick up new models."""
    path = _MODEL_DIR / f"prediction_{position.upper()}.pkl"
    if not path.exists():
        path = _MODEL_DIR / "prediction_ALL.pkl"
    if not path.exists():
        return None
    with path.open("rb") as f:
        return pickle.load(f)


def _trend(predicted: float, current: float, threshold: float = 0.5) -> str:
    delta = predicted - current
    if delta > threshold:
        return "improving"
    if delta < -threshold:
        return "declining"
    return "stable"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PlayerBase(BaseModel):
    name: str
    name_ar: Optional[str] = None
    position: str
    jersey_number: Optional[int] = None
    preferred_foot: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None


class PlayerCreate(PlayerBase):
    academy_id: UUID


class PlayerResponse(PlayerBase):
    id: UUID
    academy_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/", response_model=PlayerResponse, status_code=201)
def create_player(player: PlayerCreate, db: Session = Depends(get_db)):
    """Register a new player in an academy."""
    record = Player(**player.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{player_id}/stats", response_model=list[PlayerStatsResponse])
def get_player_stats(
    player_id: UUID,
    db: Session = Depends(get_db),
    match_id: Optional[UUID] = Query(None),
):
    """
    Return a player's match stats history, newest first.
    Optionally filter to a single match with ?match_id=<uuid>.
    """
    player = db.get(Player, player_id)
    if player is None:
        raise _PLAYER_NOT_FOUND

    query = (
        select(PlayerMatchStats, Match)
        .join(Match, PlayerMatchStats.match_id == Match.id)
        .where(PlayerMatchStats.player_id == player_id)
    )
    if match_id:
        query = query.where(PlayerMatchStats.match_id == match_id)

    rows = db.execute(query.order_by(Match.created_at.desc())).all()

    return [
        PlayerStatsResponse(
            match_id=match.id,
            home_team=match.home_team,
            away_team=match.away_team,
            team=stats.team,
            distance_covered_m=stats.distance_covered_m,
            top_speed_ms=stats.top_speed_ms,
            avg_speed_ms=stats.avg_speed_ms,
            sprint_count=stats.sprint_count,
            hi_run_count=stats.hi_run_count,
            press_count=stats.press_count,
            press_success_rate=stats.press_success_rate,
            pitch_control_contribution=stats.pitch_control_contribution,
        )
        for stats, match in rows
    ]


@router.get("/{player_id}/profile", response_model=PlayerProfileResponse)
def get_player_profile(player_id: UUID, db: Session = Depends(get_db)):
    """Full player profile with latest stats and development trend."""
    player = db.get(Player, player_id)
    if player is None:
        raise _PLAYER_NOT_FOUND

    latest_row = db.execute(
        select(PlayerMatchStats)
        .where(PlayerMatchStats.player_id == player_id)
        .join(Match, PlayerMatchStats.match_id == Match.id)
        .order_by(Match.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    latest_stats = (
        PlayerStatsResponse.model_validate(latest_row) if latest_row else None
    )

    dev_rows = db.execute(
        select(DevelopmentScore)
        .where(DevelopmentScore.player_id == player_id)
        .order_by(DevelopmentScore.week_start.desc())
        .limit(52)
    ).scalars().all()

    return PlayerProfileResponse(
        player_id=player.id,
        name=player.name,
        position=player.position,
        jersey_number=player.jersey_number,
        academy_id=player.academy_id,
        latest_stats=latest_stats,
        development_trend=[DevelopmentScoreResponse.model_validate(r) for r in dev_rows],
    )


@router.get("/{player_id}/heatmap", response_model=PlayerHeatmapResponse)
def get_player_heatmap(
    player_id: UUID,
    match_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Heatmap grid data for a player in a specific match."""
    stats = db.execute(
        select(PlayerMatchStats)
        .where(
            PlayerMatchStats.player_id == player_id,
            PlayerMatchStats.match_id == match_id,
        )
    ).scalar_one_or_none()

    if stats is None:
        raise HTTPException(status_code=404, detail="No stats found for this player and match")

    return PlayerHeatmapResponse(
        player_id=player_id,
        match_id=match_id,
        heatmap_data=stats.heatmap_data,
    )


@router.get("/{player_id}/prediction")
def get_player_prediction(player_id: UUID, db: Session = Depends(get_db)):
    """
    Predict a player's development score for the coming week.

    Uses a pickled sklearn model trained per position group.
    Falls back to a rolling-mean estimate when no model file exists yet,
    returning confidence < 0.5 to signal the fallback.
    """
    player = db.get(Player, player_id)
    if player is None:
        raise _PLAYER_NOT_FOUND

    history = assemble_player_features(player_id, db, n_matches=_HISTORY_WINDOW)
    if len(history) < _MIN_MATCHES:
        raise HTTPException(
            status_code=422,
            detail=f"Not enough match history — need at least {_MIN_MATCHES} matches to predict.",
        )

    recent_scores = db.execute(
        select(DevelopmentScore)
        .where(DevelopmentScore.player_id == player_id)
        .order_by(DevelopmentScore.week_start.desc())
        .limit(4)
    ).scalars().all()
    current_score = recent_scores[0].overall_score if recent_scores else _DEFAULT_DEV_SCORE

    model = _load_model(player.position)

    if model is not None:
        feature_vector = [
            row[key] if row[key] is not None else 0.0
            for row in history
            for key in FEATURE_KEYS
        ]
        predicted = float(model.predict([feature_vector])[0])
        predicted = max(0.0, min(10.0, predicted))
        confidence = _MODEL_CONFIDENCE
    else:
        scores = [r.overall_score for r in recent_scores]
        predicted = sum(scores) / len(scores) if scores else current_score
        predicted = max(0.0, min(10.0, predicted))
        confidence = _FALLBACK_CONFIDENCE

    now = datetime.now(timezone.utc)
    next_monday = (now + timedelta(days=(7 - now.weekday()))).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    return {
        "player_id": str(player_id),
        "predicted_score": round(predicted, 2),
        "current_score": round(current_score, 2),
        "trend": _trend(predicted, current_score),
        "confidence": confidence,
        "week": next_monday.date().isoformat(),
    }
