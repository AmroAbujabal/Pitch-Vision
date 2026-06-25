# PitchVision

## Project Overview
Computer vision pipeline to detect, track, and analytically profile soccer players on a pitch.
Target market: Amateur and semi-pro soccer clubs in Canada that can't afford Opta/StatsBomb.

## Business Goal
Sell a coach-facing dashboard + player profile data to clubs running single touchline cameras or phone video. Bilingual product: Arabic + English UI (Arabic planned, English first).

## Stack
- Python 3.11
- SAM 2 (Meta) — segmentation
- YOLOv10 — player detection
- TransReID / OSNet — player re-identification across frames
- PaddleOCR — jersey number recognition
- FastAPI — REST API backend
- SQLite (dev) → PostgreSQL + pgvector (prod)
- Celery + Redis — async video processing queue
- Next.js 14 — club dashboard frontend (App Router, TypeScript, Tailwind, Recharts)

## Input Assumption
**Single fixed camera** — touchline tripod or phone on a stand. No broadcast infrastructure needed.
- Phone video (MP4, MOV) ✓
- 720p–4K ✓ (1080p recommended)
- 25fps / 30fps / 60fps ✓ (configure `default_fps` in `.env`)

Single-camera limitations to keep in mind:
- Pitch control stats are only computed for the visible zone if the full width isn't captured
- Players leaving the frame are re-identified when they return (up to `max_lost_frames` frames)
- Distance/speed accuracy requires pitch corner coordinates for homography calibration

## Module Map
- /detection        → YOLO + SAM 2 pipeline (frame-level player detection + segmentation)
- /tracking         → Re-ID, multi-object tracking, trajectory storage
- /metrics          → Physical, pitch control, pressing, development scoring, prediction
- /api              → FastAPI routers, schemas, auth
- /database         → SQLAlchemy models, Alembic migrations
- /dashboard        → Next.js 14 coach dashboard
- /models           → Pydantic data models
- /utils            → Video I/O, coordinate transforms, visualization helpers
- /scripts          → One-off scripts: model downloads, seed data, pipeline runner, model training
- /data             → Raw footage, processed clips, model weights (gitignored)
- /tests            → Pytest test suite (111 passing, torch-free)

## Key Conventions
- All coordinates are normalized [0,1] relative to pitch dimensions unless stated otherwise
- Pitch reference frame: origin bottom-left, x = width, y = length
- Player IDs are persistent across a match session; re-assigned each new match
- All metric outputs include a `confidence` float [0,1]
- Frame rate assumption: 25fps default (set 30fps for phone video in `.env`)
- "soccer" in all user-facing copy (Canadian market); "football" only in internal/academic references

## Environment
- Python: `/usr/local/bin/python3.11` (no conda on this machine)
- Run tests: `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q`
- Start API: `/usr/local/bin/python3.11 -m uvicorn api.main:app --reload`
- GPU: configure in config/settings.py (CUDA device index)
- Model weights stored in /data/model_weights/ (not committed to git)
- GitHub repo: https://github.com/AmroAbujabal/football-VLMs (rename to pitchvision pending)

## Completed
- Detection pipeline (YOLO + SAM 2)
- Jersey OCR + team color classification
- Physical metrics (distance, speed, sprints, hi-intensity runs)
- Pitch control (Voronoi-based)
- Pressing analysis (press count, success rate, trigger accuracy)
- DevelopmentScore auto-computed per player per week after each match
- Database schema + Alembic migrations
- FastAPI REST API with JWT auth
- Video upload endpoint → Celery async pipeline
- Next.js dashboard (match list, match detail, player profile)
- Prediction model pipeline: Ridge regression per position group (GK/DEF/MID/FWD)
  - metrics/features.py: assemble_player_features() + build_training_dataset()
  - scripts/train_model.py: saves to data/models/prediction_{group}.pkl
  - GET /api/v1/players/{id}/prediction: predicted_score, trend, confidence, week
  - Dashboard PredictionCard component on player profile page

## Next Session — Pick Up Here
**Phase 1 (Rename + README) is complete.**

**Phase 2 — Single-camera config adjustments:**
- Make fps/resolution configurable per upload (not hardcoded 1920×1080 @ 25fps)
- Increase `max_lost_frames` from 30 → 90–150 (players leaving single-camera frame)
- Lower `yolo_conf_threshold` from 0.5 → 0.35 for blurry phone footage
- Document pitch control limitation for partial-pitch views

**Phase 3 — Output stubs:**
- Wire heatmap grid accumulation into pipeline (endpoint exists, data always null)
- Add speed zone breakdown (walk/jog/run/sprint)
- Stub formation detection

**Phase 4 — Dockerfile (CPU-only, multi-stage build)**

**Phase 5 — GitHub Actions CI/CD** (lint, test, build Docker image on push)

**Phase 6 — Terraform / Cloud Run** (check in with user before writing)

**User to do manually:** Rename GitHub repo `football-VLMs` → `pitchvision`

To retrain the prediction model once real match data exists:
```bash
python scripts/train_model.py     # saves to data/models/prediction_{group}.pkl
# restart uvicorn — lru_cache loads the new model on first request
```

## Backlog
- Heatmap grid written by pipeline
- Speed zone breakdown (walk/jog/run/sprint)
- Re-ID across occlusions (TransReID/OSNet — needs torch)
- PostgreSQL + pgvector for production
- Arabic UI (name_ar fields in schema already)
- Formation detection
- Real pitch homography (manual corner annotations per match)

## Do Not
- Commit model weights or raw footage to git
- Use absolute paths — always use pathlib relative to PROJECT_ROOT
- Skip type hints — all functions must be typed
- Use "football" in user-facing copy — use "soccer" (Canadian market)
