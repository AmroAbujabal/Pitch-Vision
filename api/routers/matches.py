"""
api/routers/matches.py

Match ingestion and analytics endpoints.
"""

import shutil
from pathlib import Path
from uuid import UUID
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import get_current_academy_id
from api.deps import get_db
from api.schemas import MatchSummaryResponse, MatchPlayerResponse
from config.settings import settings, ALLOWED_VIDEO_EXTENSIONS
from database.models import Match, Player, PlayerMatchStats
from tasks.pipeline import process_match

router = APIRouter(dependencies=[Depends(get_current_academy_id)])

_MATCH_NOT_FOUND = HTTPException(status_code=404, detail="Match not found")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MatchCreate(BaseModel):
    academy_id: UUID
    home_team: str
    away_team: str
    match_date: Optional[datetime] = None
    venue: Optional[str] = None
    fps: float = 25.0               # set to 30.0 for phone video
    frame_width: int = 1920
    frame_height: int = 1080


class MatchResponse(BaseModel):
    id: UUID
    academy_id: UUID
    home_team: str
    away_team: str
    match_date: Optional[datetime]
    processing_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MatchListResponse(BaseModel):
    """Lightweight match record for the matches list page."""
    id: UUID
    home_team: str
    away_team: str
    match_date: Optional[datetime]
    processing_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[MatchListResponse])
def list_matches(
    academy_id: UUID = Query(..., description="Filter matches by academy"),
    db: Session = Depends(get_db),
):
    """List all matches for an academy, newest first."""
    rows = db.execute(
        select(Match)
        .where(Match.academy_id == academy_id)
        .order_by(Match.created_at.desc())
    ).scalars().all()
    return rows


@router.post("/", response_model=MatchResponse, status_code=201)
def create_match(match: MatchCreate, db: Session = Depends(get_db)):
    """Register a new match. Video upload is a separate step."""
    record = Match(**match.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{match_id}/summary", response_model=MatchSummaryResponse)
def get_match_summary(match_id: UUID, db: Session = Depends(get_db)):
    """
    Aggregated match stats for the dashboard match card.
    Returns team-level pitch control, top speed, and press counts.
    """
    match = db.get(Match, match_id)
    if match is None:
        raise _MATCH_NOT_FOUND

    all_stats = db.execute(
        select(PlayerMatchStats).where(PlayerMatchStats.match_id == match_id)
    ).scalars().all()

    home = [s for s in all_stats if s.team == "home"]
    away = [s for s in all_stats if s.team == "away"]

    def _avg(vals: list) -> float:
        clean = [v for v in vals if v is not None]
        return sum(clean) / len(clean) if clean else 0.0

    def _max(vals: list) -> float:
        clean = [v for v in vals if v is not None]
        return max(clean) if clean else 0.0

    def _sum(vals: list) -> int:
        return sum(v or 0 for v in vals)

    return MatchSummaryResponse(
        match_id=match.id,
        home_team=match.home_team,
        away_team=match.away_team,
        processing_status=match.processing_status,
        player_count=len(all_stats),
        home_pitch_control_pct=_avg([s.pitch_control_contribution for s in home]),
        away_pitch_control_pct=_avg([s.pitch_control_contribution for s in away]),
        home_top_speed_ms=_max([s.top_speed_ms for s in home]),
        away_top_speed_ms=_max([s.top_speed_ms for s in away]),
        home_press_count=_sum([s.press_count for s in home]),
        away_press_count=_sum([s.press_count for s in away]),
    )


@router.get("/{match_id}/players", response_model=list[MatchPlayerResponse])
def get_match_players(match_id: UUID, db: Session = Depends(get_db)):
    """
    All players and their stats for a match.
    Used to populate the match player table on the dashboard.
    """
    match = db.get(Match, match_id)
    if match is None:
        raise _MATCH_NOT_FOUND

    rows = db.execute(
        select(PlayerMatchStats, Player)
        .join(Player, PlayerMatchStats.player_id == Player.id)
        .where(PlayerMatchStats.match_id == match_id)
        .order_by(PlayerMatchStats.team, Player.name)
    ).all()

    return [
        MatchPlayerResponse(
            player_id=player.id,
            player_name=player.name,
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
        for stats, player in rows
    ]


@router.post("/{match_id}/upload-video", status_code=202)
def upload_video(
    match_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Accept a video file, save it to disk, and enqueue the processing pipeline."""
    match = db.get(Match, match_id)
    if match is None:
        raise _MATCH_NOT_FOUND

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}",
        )

    dest = settings.raw_dir / f"{match_id}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    match.processing_status = "processing"
    db.commit()

    process_match.delay(
        str(match_id),
        str(match.academy_id),
        match.fps,
        match.frame_width,
        match.frame_height,
    )

    return {"match_id": str(match_id), "status": "processing"}


@router.get("/{match_id}/processing-status")
def get_processing_status(match_id: UUID, db: Session = Depends(get_db)):
    """Poll the processing status of an uploaded match video."""
    match = db.get(Match, match_id)
    if match is None:
        raise _MATCH_NOT_FOUND
    return {"match_id": match_id, "status": match.processing_status}
