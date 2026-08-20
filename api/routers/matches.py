"""
api/routers/matches.py

Match ingestion and analytics endpoints.
"""

import shutil
from pathlib import Path
from uuid import UUID
from typing import Literal, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import get_current_academy_id
from api.deps import get_db
from api.schemas import MatchSummaryResponse, MatchPlayerResponse
from config.settings import settings, ALLOWED_VIDEO_EXTENSIONS, find_raw_video
from database.models import Match, Player, PlayerMatchStats
from tasks.pipeline import process_match
from utils.pitch_corners import corner_problem

router = APIRouter(dependencies=[Depends(get_current_academy_id)])

_MATCH_NOT_FOUND = HTTPException(status_code=404, detail="Match not found")


def get_scoped_match(
    match_id: UUID,
    db: Session = Depends(get_db),
    academy_id: UUID = Depends(get_current_academy_id),
) -> Match:
    """
    Load a match, but only if it belongs to the calling academy.

    Every per-match route depends on this rather than calling db.get() itself,
    so a match can't be read or written across academies. A match owned by
    someone else is reported as 404, not 403 — telling a caller "this exists but
    isn't yours" would leak which match ids are real.
    """
    match = db.get(Match, match_id)
    if match is None or match.academy_id != academy_id:
        raise _MATCH_NOT_FOUND
    return match


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MatchCreate(BaseModel):
    # No academy_id — ownership is taken from the caller's token, not the body.
    # Pydantic's default extra="ignore" is deliberate here: a client that still
    # sends academy_id gets it silently dropped rather than a 422, so older
    # callers keep working. The field is powerless either way (see
    # test_body_academy_id_cannot_reassign_ownership); this only decides whether
    # they're told. Switch to extra="forbid" if the API ever wants to be strict.
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


class MatchCalibration(BaseModel):
    """
    Camera calibration for one match.

    pitch_corners:    the four pitch corners in this video's pixel space,
                      ordered TL -> TR -> BR -> BL, as [[x, y], ...].
    home_defends_end: which end of the pitch length (x) axis the home team
                      defends. The corner ordering fixes what these mean:
                      the first corner (TL) maps to x=0, so **"low" is the goal
                      on the left of frame and "high" the goal on the right**.
                      Not derivable from the corners — goal positions don't say
                      who defends which one — and getting it backwards mirrors
                      the reported shape (a 4-2-3-1 comes back as "1-3-2-4").
    half_time_seconds: seconds into the video at which the teams change ends,
                      or omitted when the video is one half. Positions after it
                      are measured from the opposite goal; without it a full
                      match reports a blend of the true shape and its mirror.
                      Seconds rather than frames so a later `fps` correction
                      cannot silently move it.
    """
    pitch_corners: list[tuple[float, float]] = Field(..., min_length=4, max_length=4)
    home_defends_end: Literal["low", "high"]
    half_time_seconds: Optional[float] = Field(default=None, gt=0)

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _corners_are_usable(self) -> "MatchCalibration":
        """
        Reject a quad the pipeline can only misread.

        `home_defends_end` is validated against a `Literal`, but it only means
        anything relative to the corner order, so the geometry that gives it
        meaning is checked here too. See `utils.pitch_corners.corner_problem`
        for why a wrong order cannot be caught later.

        The dashboard picker checks the same thing before it lets a coach save,
        but it is not the only writer — `scripts/run_pipeline.py --pitch-corners`
        and any curl caller reach the column too.
        """
        problem = corner_problem(self.pitch_corners)
        if problem:
            raise ValueError(problem)
        return self


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[MatchListResponse])
def list_matches(
    db: Session = Depends(get_db),
    academy_id: UUID = Depends(get_current_academy_id),
):
    """
    List the calling academy's matches, newest first.

    The academy comes from the bearer token, never from the request — a
    client-supplied academy_id would let any caller list another academy's
    matches. An academy_id query parameter is accepted and ignored for
    backwards compatibility with existing dashboard builds.
    """
    rows = db.execute(
        select(Match)
        .where(Match.academy_id == academy_id)
        .order_by(Match.created_at.desc())
    ).scalars().all()
    return rows


@router.post("/", response_model=MatchResponse, status_code=201)
def create_match(
    match: MatchCreate,
    db: Session = Depends(get_db),
    academy_id: UUID = Depends(get_current_academy_id),
):
    """
    Register a new match. Video upload is a separate step.

    Ownership comes from the bearer token, so a match cannot be created under
    another academy.
    """
    record = Match(**match.model_dump(), academy_id=academy_id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{match_id}/calibration", response_model=MatchCalibration)
def set_calibration(
    calibration: MatchCalibration,
    match: Match = Depends(get_scoped_match),
    db: Session = Depends(get_db),
):
    """
    Set the pitch corners and defended end for a match.

    Together these let the pipeline map pixels to real metres (homography) and
    label formations. Without them, positions fall back to a linear pixel→metre
    approximation and formations stay "unknown".

    Set this before uploading the video: uploading starts processing straight
    away, so calibration saved afterwards only takes effect on the next run. The
    corners come from the camera's fixed framing, so a still from any match shot
    at that ground works.

    `half_time_seconds` is optional and only matters for a video covering both
    halves; leaving it out keeps the whole video in one direction.
    """
    match.pitch_corners = calibration.pitch_corners
    match.home_defends_end = calibration.home_defends_end
    match.half_time_seconds = calibration.half_time_seconds
    db.commit()
    db.refresh(match)
    return match


@router.get("/{match_id}/summary", response_model=MatchSummaryResponse)
def get_match_summary(
    match: Match = Depends(get_scoped_match),
    db: Session = Depends(get_db),
):
    """
    Aggregated match stats for the dashboard match card.
    Returns team-level pitch control, top speed, and press counts.
    """
    all_stats = db.execute(
        select(PlayerMatchStats).where(PlayerMatchStats.match_id == match.id)
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
        home_formation=match.home_formation,
        away_formation=match.away_formation,
    )


@router.get("/{match_id}/players", response_model=list[MatchPlayerResponse])
def get_match_players(
    match: Match = Depends(get_scoped_match),
    db: Session = Depends(get_db),
):
    """
    All players and their stats for a match.
    Used to populate the match player table on the dashboard.
    """
    rows = db.execute(
        select(PlayerMatchStats, Player)
        .join(Player, PlayerMatchStats.player_id == Player.id)
        .where(PlayerMatchStats.match_id == match.id)
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


def _enqueue_processing(match: Match, db: Session) -> None:
    """
    Mark the match processing and hand it to the worker.

    Shared by upload and re-run. The rollback matters: the status is committed
    before the task is enqueued, so a broker that is down would otherwise leave
    the match reading "processing" forever with nothing to pick it up. Mark it
    failed so it reads honestly and can be retried.
    """
    match.processing_status = "processing"
    db.commit()

    try:
        process_match.delay(
            str(match.id),
            str(match.academy_id),
            match.fps,
            match.frame_width,
            match.frame_height,
        )
    except Exception:
        match.processing_status = "failed"
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="Could not queue processing. The video is on disk; try again.",
        )


@router.post("/{match_id}/upload-video", status_code=202)
def upload_video(
    file: UploadFile = File(...),
    match: Match = Depends(get_scoped_match),
    db: Session = Depends(get_db),
):
    """Accept a video file, save it to disk, and enqueue the processing pipeline."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}",
        )

    # Name built from the match id and the suffix checked above, never from
    # file.filename — that is caller-supplied and would put its directory
    # separators straight into the path. find_raw_video reads this back.
    name = f"{match.id}{suffix}"
    dest = settings.raw_dir / name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    match.video_path = name

    _enqueue_processing(match, db)

    return {"match_id": str(match.id), "status": "processing"}


@router.post("/{match_id}/reprocess", status_code=202)
def reprocess_match(
    match: Match = Depends(get_scoped_match),
    db: Session = Depends(get_db),
):
    """
    Re-run the pipeline on the video already on disk.

    Calibration only takes effect on the next pipeline run, so a coach who
    uploaded before picking the pitch corners is stuck with "unknown"
    formations. This is the explicit way out. PUT /calibration deliberately
    does not do this itself — a save button that silently starts a long job is
    a surprising side effect.
    """
    if find_raw_video(match.id, match.video_path) is None:
        raise HTTPException(
            status_code=404,
            detail="No source video for this match. Upload it again.",
        )

    # Two pipeline runs on one match race each other to write its stats rows.
    # The button's busy flag stops a double click, but the endpoint is callable
    # directly. Note this also blocks a match wedged at "processing" by a worker
    # that died mid-run, which nothing currently rolls back.
    if match.processing_status == "processing":
        raise HTTPException(
            status_code=409,
            detail="This match is already being processed.",
        )

    _enqueue_processing(match, db)

    return {"match_id": str(match.id), "status": "processing"}


@router.get("/{match_id}/processing-status")
def get_processing_status(match: Match = Depends(get_scoped_match)):
    """Poll the processing status of an uploaded match video."""
    return {"match_id": match.id, "status": match.processing_status}
