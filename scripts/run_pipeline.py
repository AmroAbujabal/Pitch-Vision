"""
scripts/run_pipeline.py

End-to-end pipeline: video in → player profiles out.

Usage:
    python scripts/run_pipeline.py --video data/raw/match.mp4 --max-frames 500
"""

import argparse
import uuid
from pathlib import Path
from loguru import logger

from detection.detector import PlayerDetector, TeamColorClassifier
from detection.jersey_ocr import JerseyOCR
from tracking.tracker import PlayerTracker
from metrics.pitch_control import compute_pitch_control
from metrics.physical import compute_physical_metrics
from metrics.heatmap import compute_heatmap
from metrics.formation import detect_formation
from metrics.pressing import PressAnalyser
from utils.homography import PitchHomography
from database.repository import PipelineResult, save_pipeline_results
from database.session import get_session


def run(
    video_path: Path,
    match_id: uuid.UUID,
    academy_id: uuid.UUID,
    max_frames: int | None = None,
    fps: float | None = None,
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> None:
    """
    Run the full detection → tracking → metrics → persist pipeline.

    fps / frame_width / frame_height default to settings values when not
    provided. Pass them explicitly when the upload camera differs from the
    global defaults (e.g. 30fps phone video at 1280×720).
    """
    from config.settings import settings as cfg

    _fps = fps if fps is not None else cfg.default_fps
    _fw  = frame_width  if frame_width  is not None else cfg.frame_width
    _fh  = frame_height if frame_height is not None else cfg.frame_height

    logger.info(
        f"Starting pipeline for: {video_path} "
        f"(fps={_fps}, {_fw}x{_fh})"
    )

    # --- Stage 1: Detection ---
    team_classifier = TeamColorClassifier(n_clusters=3)
    detector = PlayerDetector(use_sam=True, team_classifier=team_classifier)

    all_frame_detections = detector.process_video(
        video_path, max_frames=max_frames
    )

    # Fit team color classifier on first 100 detected crops
    early_crops = []
    for fd in all_frame_detections[:100]:
        for det in fd.detections:
            if det.crop is not None:
                early_crops.append(det.crop)
    if early_crops:
        team_classifier.fit(early_crops)
        # TODO: manually assign cluster labels after visual inspection
        # team_classifier.assign_team_labels({0: "home", 1: "away", 2: "referee"})
        logger.info(
            "Team classifier fitted — assign cluster labels manually before metric computation"
        )

    # --- Stage 2: Tracking ---
    tracker = PlayerTracker()
    all_tracked_frames = tracker.process_detections(all_frame_detections)

    # --- Stage 2b: Jersey OCR ---
    # For each confirmed track, run OCR on the best crop stored by the tracker.
    logger.info("Running jersey OCR...")
    ocr = JerseyOCR()
    jersey_numbers: dict[int, int] = {}
    for tid, track in all_confirmed.items():
        if track.best_crop is not None:
            number, conf = ocr.extract(track.best_crop)
            if number is not None:
                jersey_numbers[tid] = number
                logger.debug(f"Track {tid}: jersey #{number} (conf={conf:.2f})")
    logger.info(f"Jersey OCR complete — {len(jersey_numbers)} numbers detected")

    # --- Stage 3: Pitch control (sample every 5th frame for speed) ---
    # Single-camera limitation: Voronoi pitch control assumes all outfield
    # players are visible. When the camera covers only part of the pitch,
    # away-team players outside the frame are missing, so home_control_pct
    # will be inflated. Stats are still useful for intra-team comparisons
    # within the visible zone.
    logger.info("Computing pitch control...")
    pitch_control_results = []
    for tf in all_tracked_frames[::5]:
        home_tracks = [t for t in tf.confirmed_tracks if t.team == "home"]
        away_tracks = [t for t in tf.confirmed_tracks if t.team == "away"]
        pc = compute_pitch_control(tf.frame_id, home_tracks, away_tracks)
        pitch_control_results.append(pc)

    avg_home_control = sum(p.home_control_pct for p in pitch_control_results)
    if pitch_control_results:
        avg_home_control /= len(pitch_control_results)
    logger.info(f"Avg home pitch control: {avg_home_control:.1%}")

    # --- Stage 4: Pressing analysis ---
    logger.info("Detecting press events...")
    press_analyser = PressAnalyser()
    press_analyser.detect_press_events(all_tracked_frames)
    player_press_stats = press_analyser.aggregate_player_stats()

    logger.info(f"Press stats computed for {len(player_press_stats)} players")

    # --- Stage 5: Physical metrics ---
    logger.info("Computing physical metrics...")
    homography = PitchHomography()
    # fit() will fail without a real broadcast frame; use fit_from_points in
    # production once manual pitch corner annotations are provided.
    # For now, compute pitch positions from bbox centres using the naive
    # linear fallback (homography.pixel_to_pitch via settings dimensions).

    all_confirmed = {}
    for tf in all_tracked_frames:
        for track in tf.confirmed_tracks:
            if track.track_id not in all_confirmed:
                all_confirmed[track.track_id] = track

    physical_metrics = {}
    heatmap_by_track = {}
    pitch_control_by_track = {}

    # Aggregate pitch control contribution per track across sampled frames
    for pc_frame in pitch_control_results:
        for tid, contrib in pc_frame.player_contributions.items():
            if tid not in pitch_control_by_track:
                pitch_control_by_track[tid] = []
            pitch_control_by_track[tid].append(contrib)
    pitch_control_by_track = {
        tid: sum(vals) / len(vals)
        for tid, vals in pitch_control_by_track.items()
    }

    import numpy as np

    for tid, track in all_confirmed.items():
        if len(track.bbox_history) < 2:
            continue
        # Convert bbox centres to approximate pitch positions (linear fallback).
        # Uses per-match frame dimensions so phone video (e.g. 1280×720 @ 30fps)
        # produces accurate distances without reconfiguring global settings.
        centers = np.array([
            [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]
            for b in track.bbox_history
        ], dtype=np.float64)
        pitch_pos = np.column_stack([
            centers[:, 0] / _fw * cfg.pitch_length,
            centers[:, 1] / _fh * cfg.pitch_width,
        ])
        physical_metrics[tid] = compute_physical_metrics(
            track_id=tid,
            pitch_positions=pitch_pos,
            fps=_fps,
        )
        heatmap_by_track[tid] = compute_heatmap(pitch_pos)

    # --- Stage 5b: Formation detection (stub) ---
    home_formation = detect_formation(all_tracked_frames, team="home")
    away_formation = detect_formation(all_tracked_frames, team="away")
    logger.info(f"Formation — home: {home_formation}, away: {away_formation}")

    # --- Stage 6: Persist to database ---
    logger.info("Persisting results to database...")
    track_teams = {tid: t.team for tid, t in all_confirmed.items()}

    result = PipelineResult(
        match_id=match_id,
        fps=_fps,
        physical_metrics=physical_metrics,
        pitch_control_by_track=pitch_control_by_track,
        press_stats=player_press_stats,
        track_teams=track_teams,
        jersey_numbers=jersey_numbers,
        heatmap_by_track=heatmap_by_track,
    )

    with get_session() as session:
        n = save_pipeline_results(session, academy_id, result)
        session.commit()

    logger.info(f"Pipeline complete — {n} player profiles saved to database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PitchVision pipeline — video in, player profiles out")
    parser.add_argument("--video",        required=True,  type=Path)
    parser.add_argument("--match-id",     required=True,  type=uuid.UUID)
    parser.add_argument("--academy-id",   required=True,  type=uuid.UUID)
    parser.add_argument("--max-frames",   type=int,   default=None)
    parser.add_argument("--fps",          type=float, default=None,
                        help="Frame rate of the source video (default: settings.default_fps). "
                             "Set to 30.0 for phone video.")
    parser.add_argument("--frame-width",  type=int,   default=None,
                        help="Pixel width of the source video (default: settings.frame_width).")
    parser.add_argument("--frame-height", type=int,   default=None,
                        help="Pixel height of the source video (default: settings.frame_height).")
    args = parser.parse_args()

    run(
        args.video, args.match_id, args.academy_id,
        max_frames=args.max_frames,
        fps=args.fps,
        frame_width=args.frame_width,
        frame_height=args.frame_height,
    )
