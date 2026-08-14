"""
scripts/run_pipeline.py

End-to-end pipeline: video in → player profiles out.

Usage:
    python scripts/run_pipeline.py --video data/raw/match.mp4 --max-frames 500
"""

import argparse
import json
import uuid
from pathlib import Path

import numpy as np
from loguru import logger

from metrics.pitch_control import compute_pitch_control
from metrics.physical import compute_physical_metrics
from metrics.heatmap import compute_heatmap
from metrics.formation import detect_formation
from metrics.pressing import PressAnalyser
from database.repository import PipelineResult, save_pipeline_results
from database.session import get_session

# Which end each team defends, given the other. Home's end comes from the match
# record; away necessarily defends the opposite.
_OPPOSITE_END = {"low": "high", "high": "low"}

# How far outside the pitch a projected position may land before it is clamped.
# Generous enough for throw-ins, keepers behind the line and corner takers.
PITCH_MARGIN_M = 5.0


def clamp_to_pitch(
    pitch: np.ndarray,
    pitch_length: float,
    pitch_width: float,
) -> np.ndarray:
    """
    Keep projected positions inside a padded pitch rectangle.

    A projective map compresses hard near the horizon, and a point at or beyond
    the vanishing line divides by ~0 and comes back inf/nan. Unclamped, one such
    frame becomes a player's top_speed_ms, and the dashboard KPI shows the team
    maximum — so a single bad detection would be the headline number.

    Non-finite rows hold the previous good position rather than being dropped:
    physical metrics assume one position per observed frame.
    """
    pitch = np.array(pitch, dtype=np.float64, copy=True)

    bad = ~np.isfinite(pitch).all(axis=1)
    if bad.any():
        logger.warning(
            f"{int(bad.sum())}/{len(pitch)} points projected past the horizon "
            "— holding last known position"
        )
        for i in np.flatnonzero(bad):
            pitch[i] = pitch[i - 1] if i else [0.0, 0.0]

    pitch[:, 0] = np.clip(pitch[:, 0], -PITCH_MARGIN_M, pitch_length + PITCH_MARGIN_M)
    pitch[:, 1] = np.clip(pitch[:, 1], -PITCH_MARGIN_M, pitch_width + PITCH_MARGIN_M)
    return pitch


def feet_pixels(bbox_history: list) -> np.ndarray:
    """
    Ground-contact point of each [x1, y1, x2, y2] box: bottom edge, mid-width.

    Players are mapped from the bottom of the box rather than its centre — that
    is where they touch the ground, and the ground plane is what the pitch
    homography is fitted to. Using the centre projects a player's torso onto the
    pitch and pushes positions away from the camera.

    Tradeoff: the centre averaged two independently-noisy box edges, while the
    bottom edge carries one edge's full noise. Correct under a homography, and
    slightly jitterier on uncalibrated matches, which take the linear fallback.
    """
    boxes = np.asarray(bbox_history, dtype=np.float64)
    return np.column_stack([(boxes[:, 0] + boxes[:, 2]) / 2, boxes[:, 3]])


def run(
    video_path: Path,
    match_id: uuid.UUID,
    academy_id: uuid.UUID,
    max_frames: int | None = None,
    fps: float | None = None,
    frame_width: int | None = None,
    frame_height: int | None = None,
    pitch_corners: list | None = None,
    home_defends_end: str | None = None,
) -> None:
    """
    Run the full detection → tracking → metrics → persist pipeline.

    fps / frame_width / frame_height default to settings values when not
    provided. Pass them explicitly when the upload camera differs from the
    global defaults (e.g. 30fps phone video at 1280×720).

    pitch_corners:    the four pitch corners in pixel space, TL → TR → BR → BL.
                      Solves a real homography; without them player positions
                      fall back to a linear scaling of the frame.
    home_defends_end: "low" or "high" — which end of the pitch length axis the
                      home team defends. Required for formation detection;
                      without it both formations are reported "unknown".
    """
    # Imported here, not at module scope, so the pipeline's pure helpers stay
    # importable (and testable) without torch installed.
    from detection.detector import PlayerDetector, TeamColorClassifier
    from detection.jersey_ocr import JerseyOCR
    from tracking.tracker import PlayerTracker
    from config.settings import settings as cfg

    _fps = fps if fps is not None else cfg.default_fps
    _fw  = frame_width  if frame_width  is not None else cfg.frame_width
    _fh  = frame_height if frame_height is not None else cfg.frame_height

    logger.info(
        f"Starting pipeline for: {video_path} "
        f"(fps={_fps}, {_fw}x{_fh})"
    )

    # Pixel → pitch metres. Annotated corners give a real homography; otherwise
    # positions are a linear stretch of the frame onto the pitch, which ignores
    # perspective entirely and is only a rough approximation.
    homography = None
    if pitch_corners:
        from utils.homography import PitchHomography

        homography = PitchHomography()
        try:
            fitted = homography.fit_from_corners(np.float32(pitch_corners))
        except (ValueError, TypeError) as exc:
            # Match.pitch_corners is a free-form JSON column, so a hand-edited
            # or pre-API row can be ragged or the wrong length. Degrade to the
            # linear approximation rather than failing the whole match.
            logger.warning(f"Unusable pitch_corners ({exc}) — ignoring calibration")
            fitted = False
        if fitted:
            logger.info("Pitch homography fitted from annotated corners")
        else:
            logger.warning(
                "Homography fit failed (degenerate corners?) — "
                "falling back to linear pixel scaling"
            )
            homography = None

    # Labelling a formation off the crude linear stretch is exactly the
    # confidently-wrong answer metrics/formation.py declines to give, so a
    # direction without a working homography is not enough to label one.
    if home_defends_end and homography is None:
        logger.warning(
            "home_defends_end given without a usable homography — "
            "formations stay 'unknown' rather than be read off approximate positions"
        )
        home_defends_end = None

    def to_pitch(pixels: np.ndarray) -> np.ndarray:
        """
        (N, 2) pixel points → (N, 2) pitch metres (x = length, y = width).

        A projective map compresses hard near the horizon: a few pixels of
        detector noise on the far touchline can be many metres, and a point at
        or above the vanishing line divides by ~0 and comes back inf/nan. Those
        would flow straight into top_speed_ms and the dashboard KPI, which takes
        the team maximum — one bad frame becomes the headline number. So results
        are clamped into a padded pitch rectangle and non-finite points are
        pinned to the previous good position.
        """
        if homography is None:
            return np.column_stack([
                pixels[:, 0] / _fw * cfg.pitch_length,
                pixels[:, 1] / _fh * cfg.pitch_width,
            ])

        return clamp_to_pitch(
            homography.batch_pixel_to_pitch(pixels),
            cfg.pitch_length,
            cfg.pitch_width,
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

    # Build track lookup once — used by OCR below and physical metrics later
    all_confirmed: dict[int, object] = {}
    for tf in all_tracked_frames:
        for track in tf.confirmed_tracks:
            if track.track_id not in all_confirmed:
                all_confirmed[track.track_id] = track

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
        pc = compute_pitch_control(
            tf.frame_id, home_tracks, away_tracks, homography=homography
        )
        pitch_control_results.append(pc)

    avg_home_control = sum(p.home_control_pct for p in pitch_control_results)
    if pitch_control_results:
        avg_home_control /= len(pitch_control_results)
    logger.info(f"Avg home pitch control: {avg_home_control:.1%}")

    # --- Stage 4: Pressing analysis ---
    logger.info("Detecting press events...")
    press_analyser = PressAnalyser(homography=homography)
    press_analyser.detect_press_events(all_tracked_frames)
    player_press_stats = press_analyser.aggregate_player_stats()

    logger.info(f"Press stats computed for {len(player_press_stats)} players")

    # --- Stage 5: Physical metrics ---
    logger.info("Computing physical metrics...")
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

    for tid, track in all_confirmed.items():
        if len(track.bbox_history) < 2:
            continue
        pitch_pos = to_pitch(feet_pixels(track.bbox_history))

        # Publish positions on the track: pitch_history is the per-frame record
        # (formation averages it; metrics/pitch_control.compute_player_pitch_
        # control_summary and metrics/pressing.compute_recovery_shadow_score
        # read it too, though neither is called from this pipeline yet),
        # pitch_pos the latest position. Stages 3 and 4 run before this point,
        # so they take the homography directly rather than reading these.
        track.pitch_history = list(pitch_pos)
        track.pitch_pos = pitch_pos[-1]

        physical_metrics[tid] = compute_physical_metrics(
            track_id=tid,
            pitch_positions=pitch_pos,
            fps=_fps,
        )
        heatmap_by_track[tid] = compute_heatmap(pitch_pos)

    # --- Stage 5b: Formation detection ---
    # The away team defends the opposite end. When the match has no annotated
    # direction both stay "unknown" by design — a confidently wrong formation is
    # worse than none for a coach.
    away_defends_end = _OPPOSITE_END.get(home_defends_end or "")
    home_formation = detect_formation(
        all_tracked_frames, team="home", own_goal_end=home_defends_end
    )
    away_formation = detect_formation(
        all_tracked_frames, team="away", own_goal_end=away_defends_end
    )
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
        home_formation=home_formation,
        away_formation=away_formation,
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
    parser.add_argument("--pitch-corners", type=str, default=None,
                        help='Four pitch corners in pixel space, TL->TR->BR->BL, as JSON: '
                             '"[[x,y],[x,y],[x,y],[x,y]]". Without them positions are a '
                             "linear approximation instead of a real homography.")
    parser.add_argument("--home-defends-end", choices=("low", "high"), default=None,
                        help="Which end the home team defends: 'low' is the goal on the "
                             "left of frame, 'high' the goal on the right (the first "
                             "pitch corner maps to x=0). Required to label formations, "
                             "and only honoured alongside --pitch-corners; otherwise "
                             "formations are reported 'unknown'.")
    args = parser.parse_args()

    run(
        args.video, args.match_id, args.academy_id,
        max_frames=args.max_frames,
        fps=args.fps,
        frame_width=args.frame_width,
        frame_height=args.frame_height,
        pitch_corners=json.loads(args.pitch_corners) if args.pitch_corners else None,
        home_defends_end=args.home_defends_end,
    )
