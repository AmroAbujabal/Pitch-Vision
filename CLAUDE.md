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
- Docker (CPU-only, multi-stage build)
- GitHub Actions CI/CD

## Input Assumption
**Single fixed camera** — touchline tripod or phone on a stand. No broadcast infrastructure needed.
- Phone video (MP4, MOV) ✓
- 720p–4K ✓ (1080p recommended)
- 25fps / 30fps / 60fps ✓ — stored per match in `Match.fps`

Single-camera limitations to keep in mind:
- Pitch control stats only computed for the visible zone if full width not captured
- Players leaving the frame are re-identified when they return (up to `max_lost_frames=90` frames)
- Distance/speed accuracy requires pitch corner coordinates for homography calibration

## Module Map
- /detection        → YOLO + SAM 2 pipeline (frame-level player detection + segmentation)
- /tracking         → Re-ID, multi-object tracking, trajectory storage
- /metrics          → Physical, pitch control, pressing, development scoring, prediction, heatmap, formation
- /api              → FastAPI routers, schemas, auth
- /database         → SQLAlchemy models, Alembic migrations (4 versions)
- /dashboard        → Next.js 14 coach dashboard
- /utils            → Video I/O, coordinate transforms, visualization helpers
- /scripts          → Pipeline runner, seed script, model training, weight download
- /data             → Raw footage, processed clips, model weights (gitignored)
- /tests            → Pytest test suite (126 passing, torch-free)
- /alembic          → DB migrations (initial → password_hash → frame_dims → speed_zones)
- Dockerfile        → CPU-only multi-stage build
- .github/workflows/ci.yml → lint + test + docker-build + tsc on every push

## Key Conventions
- All coordinates are normalized [0,1] relative to pitch dimensions unless stated otherwise
- Pitch reference frame: origin bottom-left, x = width, y = length
- Player IDs are persistent across a match session; re-assigned each new match
- All metric outputs include a `confidence` float [0,1]
- Frame rate and resolution stored per match (Match.fps / .frame_width / .frame_height)
- "soccer" in all user-facing copy (Canadian market); "football" only in internal/academic references

## Environment
- Python: `/usr/local/bin/python3.11` (no conda on this machine)
- Run tests: `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q`
- Start API: `/usr/local/bin/python3.11 -m uvicorn api.main:app --reload`
- GPU: configure in config/settings.py (CUDA device index); default is CPU for single-camera uploads
- Model weights stored in data/model_weights/ (gitignored)
- GitHub repo: https://github.com/AmroAbujabal/Pitch-Vision

## Completed

### Core pipeline
- Detection pipeline (YOLO + SAM 2)
- Jersey OCR + team color classification
- Physical metrics: distance, speed, sprints, hi-intensity runs, **speed zones** (walk/jog/run/sprint %)
- Pitch control (Voronoi-based; partial-pitch limitation documented)
- Pressing analysis (press count, success rate, trigger accuracy)
- **Heatmap grid accumulation** (metrics/heatmap.py → PlayerMatchStats.heatmap_data JSON)
- **Formation detection stub** (metrics/formation.py — returns "unknown", full TODO)
- DevelopmentScore auto-computed per player per week after each match
- Prediction model pipeline: Ridge regression per position group (GK/DEF/MID/FWD)
  - metrics/features.py + scripts/train_model.py
  - GET /api/v1/players/{id}/prediction: predicted_score, trend, confidence, week
  - Dashboard PredictionCard component on player profile page

### Infrastructure
- Database schema + 4 Alembic migrations (SQLite dev, PostgreSQL prod)
- FastAPI REST API with JWT auth
- Video upload endpoint → Celery async pipeline
- Next.js 14 dashboard (match list, match detail, player profile + prediction card)
- **Dockerfile** — CPU-only multi-stage build; `alembic upgrade head` on startup
- **.dockerignore** — excludes model weights, raw footage, node_modules, .env
- **GitHub Actions CI** (.github/workflows/ci.yml) — all 3 jobs passing:
  - backend: ruff lint + pytest (126 tests) using requirements-ci.txt
  - docker-build: builds API image (requirements-ci.txt, ~30s) on every push
  - dashboard: npm ci + tsc --noEmit
- **requirements-ci.txt**: slim install for CI/API image (no torch/opencv/paddlepaddle)

### Single-camera adjustments (Phase 2)
- `yolo_conf_threshold` lowered 0.5 → 0.35 (phone footage)
- `max_lost_frames` raised 30 → 90 (~3.6s at 25fps)
- `Match` stores `fps`, `frame_width`, `frame_height` per upload
- `run_pipeline.run()` accepts `--fps / --frame-width / --frame-height` CLI args
- Celery task forwards per-match camera params to pipeline

## Next Session — Pick Up Here
**Phases 1–5 complete. 126 tests passing.**

**CI is fully green (backend ✓, docker-build ✓, dashboard ✓).**

**Phase 6 — Terraform / Google Cloud Run** (confirmed target: Cloud Run, scales to zero):
- Artifact Registry Docker repo
- Cloud Run service (1 vCPU, 2Gi, CPU inference)
- Environment vars via Cloud Run env (DATABASE_URL must point to PostgreSQL — SQLite won't work on ephemeral Cloud Run FS)
- `terraform/main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`

**Remaining backlog (any order after Phase 6):**
- PostgreSQL + pgvector — required for production / Cloud Run
- Real pitch homography — `PitchHomography.fit_from_points()` needs manual corner annotations per match
- Re-ID across occlusions (TransReID/OSNet — needs torch)
- Arabic UI (`name_ar` fields in schema already)
- Formation detection — implement once team colour classification is stable

## Do Not
- Commit model weights or raw footage to git
- Use absolute paths — always use pathlib relative to PROJECT_ROOT
- Skip type hints — all functions must be typed
- Use "football" in user-facing copy — use "soccer" (Canadian market)
- Create pull requests — push directly to main
