# Football Player Identification System

## Project Overview
Computer vision pipeline to detect, track, and analytically profile football players on a pitch.
Target market: UAE football academies (Al Ain, Al Jazira, Shabab Al Ahli feeders + private academies).

## Business Goal
Sell proprietary player profile data and a club dashboard to academies that can't afford Opta/StatsBomb.
Bilingual product: Arabic + English UI.

## Stack
- Python 3.11
- SAM 2 (Meta) — segmentation
- YOLOv10 — player detection
- TransReID / OSNet — player re-identification across frames
- PaddleOCR — jersey number recognition
- FastAPI — REST API backend
- PostgreSQL + pgvector — player database with vector embeddings
- Celery + Redis — async video processing queue
- Next.js — club dashboard frontend

## Module Map
- /detection        → YOLO + SAM 2 pipeline (frame-level player detection + segmentation)
- /tracking         → Re-ID, multi-object tracking, trajectory storage
- /metrics          → All advanced metric computation (pitch control, xT, press metrics, etc.)
- /api              → FastAPI routers, schemas, auth
- /database         → SQLAlchemy models, Alembic migrations
- /dashboard        → Next.js frontend (separate repo, referenced here)
- /models           → Pydantic data models
- /utils            → Video I/O, coordinate transforms, visualization helpers
- /scripts          → One-off scripts: model downloads, dataset prep, batch processing
- /data             → Raw footage, processed clips, model weights (gitignored)
- /tests            → Pytest test suite

## Key Conventions
- All coordinates are normalized [0,1] relative to pitch dimensions unless stated otherwise
- Pitch reference frame: origin bottom-left, x = width, y = length
- Player IDs are persistent across a match session; re-assigned each new match
- All metric outputs include a `confidence` float [0,1]
- Frame rate assumption: 25fps (broadcast); 50fps (tactical cam) — configure per source

## Environment
- Python: `/usr/local/bin/python3.11` (no conda on this machine)
- Run tests: `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q`
- Start API: `/usr/local/bin/python3.11 -m uvicorn api.main:app --reload`
- GPU: configure in config/settings.py (CUDA device index)
- Model weights stored in /data/model_weights/ (not committed to git)
- GitHub repo: https://github.com/AmroAbujabal/football-VLMs

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

## Next Session — Pick Up Here
**Goal: Player performance prediction model**

Step 1 — Alembic migration (Player model already has position + date_of_birth columns, but position defaults to "unknown" from pipeline; ensure it's being set properly)

Step 2 — Feature assembly (`scripts/assemble_features.py`):
- Per player, query their last N PlayerMatchStats rows ordered by match date
- Build rolling 4-week feature vectors: [distance, sprints, hi_runs, top_speed, press_success_rate, pitch_control, dev_score]
- Output: CSV or numpy array ready for sklearn

Step 3 — Train model (`scripts/train_model.py`):
- Load features, group by position
- Ridge regression or RandomForest per position group
- Target: next week's overall_score from DevelopmentScore
- Pickle model to `data/models/prediction_{position}.pkl`

Step 4 — Prediction endpoint:
- `GET /api/v1/players/{id}/prediction`
- Returns `{predicted_score, trend, confidence, week}`
- Loads pickled model, assembles last 4 weeks of features, runs inference

Step 5 — Dashboard widget on player profile page (predicted score badge + trend arrow)

**Constraint:** Need real match data flowing through the pipeline first. With synthetic data the model won't generalise. Can train on synthetic data to validate the pipeline end-to-end, but real data is the unlock.

## Backlog
- Heatmap grid written by pipeline (endpoint exists, data not yet computed)
- Re-ID across occlusions (TransReID/OSNet — needs torch)
- PostgreSQL + pgvector for production
- Arabic UI (name_ar fields in schema already)

## Do Not
- Commit model weights or raw footage to git
- Use absolute paths — always use pathlib relative to PROJECT_ROOT
- Skip type hints — all functions must be typed
