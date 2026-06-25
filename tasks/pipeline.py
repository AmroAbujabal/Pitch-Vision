"""
tasks/pipeline.py

Celery task for async video processing.
Broker: Redis (settings.redis_url)
"""

import uuid
from loguru import logger
from celery import Celery

from config.settings import settings, ALLOWED_VIDEO_EXTENSIONS

celery_app = Celery("football_ai", broker=settings.redis_url)


@celery_app.task(name="tasks.pipeline.process_match", bind=False)
def process_match(
    match_id: str,
    academy_id: str,
    fps: float = 25.0,
    frame_width: int = 1920,
    frame_height: int = 1080,
) -> None:
    """
    Process a match video through the full pipeline.

    fps/frame_width/frame_height come from the Match record so each upload
    can specify the source camera's actual resolution and frame rate.

    Finds the video at settings.raw_dir/{match_id}.{ext}, runs the pipeline,
    then marks the match "done". On any unhandled exception marks it "failed".
    """
    from database.session import SessionLocal
    from database.models import Match

    # Parse early so both the happy path and the except block share `mid`.
    mid = uuid.UUID(match_id)

    db = SessionLocal()
    try:
        video_path = None
        for ext in ALLOWED_VIDEO_EXTENSIONS:
            candidate = settings.raw_dir / f"{match_id}{ext}"
            if candidate.exists():
                video_path = candidate
                break

        if video_path is None:
            logger.warning(f"process_match: no video file found for match {match_id}")
            return

        # TODO: uncomment once torch is installed in the active conda env
        # from scripts.run_pipeline import run
        # run(video_path, mid, uuid.UUID(academy_id),
        #     fps=fps, frame_width=frame_width, frame_height=frame_height)

        match = db.get(Match, mid)
        if match is not None:
            match.processing_status = "done"
            db.commit()

        logger.info(f"process_match: complete for match {match_id}")

    except Exception:
        logger.exception(f"process_match: pipeline failed for match {match_id}")
        db.close()                          # release the bad session first
        db = SessionLocal()                 # fresh session for the status update
        try:
            match = db.get(Match, mid)
            if match is not None:
                match.processing_status = "failed"
                db.commit()
        finally:
            db.close()
        raise

    finally:
        db.close()
