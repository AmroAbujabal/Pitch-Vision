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

- /detection → YOLO + SAM 2 pipeline (frame-level player detection + segmentation)
- /tracking → Re-ID, multi-object tracking, trajectory storage
- /metrics → Physical, pitch control, pressing, development scoring, prediction, heatmap, formation
- /api → FastAPI routers, schemas, auth
- /database → SQLAlchemy models, Alembic migrations (5 versions)
- /dashboard → Next.js 14 coach dashboard
- /utils → Video I/O, coordinate transforms, visualization helpers
- /scripts → Pipeline runner, seed script, model training, weight download
- /data → Raw footage, processed clips, model weights (gitignored)
- /tests → Pytest test suite (257 passing in CI, torch-free)
- /alembic → DB migrations (initial → password_hash → frame_dims → speed_zones → pitch_calibration)
- Dockerfile → CPU-only multi-stage build
- .github/workflows/ci.yml → lint + test + docker-build + tsc on every push

## Key Conventions

- All coordinates are normalized [0,1] relative to pitch dimensions unless stated otherwise
- Pitch reference frame: origin bottom-left, **x = length (goal-to-goal, 0–105 m), y = width (0–68 m)**. Depth/attacking direction is the x axis — this is what `utils/homography.py`, `metrics/pitch_control.py` and `metrics/pressing.py` all assume.
- Player IDs are persistent across a match session; re-assigned each new match
- All metric outputs include a `confidence` float [0,1]
- Frame rate and resolution stored per match (Match.fps / .frame_width / .frame_height)
- "soccer" in all user-facing copy (Canadian market); "football" only in internal/academic references

## Environment

- Python: `/usr/local/bin/python3.11` (no conda on this machine)
- Run tests (what CI runs): `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → 257 pass
- API-only subset: `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q` → 157 pass
- `tests/test_detection/` still needs torch + ultralytics and runs nowhere
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
- **Formation detection** (metrics/formation.py) — **LIVE end to end.** Direction-aware `detect_formation(frames, team, *, own_goal_end, min_players)`. Correct-or-silent: labels the shape only when `own_goal_end` ("low"/"high") is supplied, else returns "unknown" (no guessing — a [4 clustered]+[1 isolated] shape is mirror-identical for GK vs lone striker, so direction is required). Orients depth → drops the deepest player only if isolated by a keeper-like gap (GK_ISOLATION_M=12) → gap-clusters outfield (LINE_TOLERANCE_M=12) → "4-3-3". Reads `track.pitch_history` (true match average), falling back to `track.pitch_pos`. 19 unit tests. Persisted to `Match.home_formation` / `away_formation` → match summary API → dashboard KPI card.
- **Pitch calibration** — `Match.pitch_corners` (four corners in the video's pixel space, TL→TR→BR→BL) + `Match.home_defends_end`, set via `PUT /api/v1/matches/{id}/calibration`. The pipeline fits `PitchHomography.fit_from_corners()` from them, passes it to pitch control + pressing, and populates `track.pitch_history` / `pitch_pos` for every confirmed track; without corners everything falls back to a linear pixel→metre stretch. `home_defends_end` cannot be derived from the corners (goal positions don't say who defends which one), so it is coach-supplied — **"low" is the goal on the left of frame, "high" the goal on the right**, fixed by the corner ordering (first corner → x=0). Getting it backwards mirrors the shape. It is ignored without a working homography, and the away team gets the opposite end. Projected positions are clamped to the pitch ±`PITCH_MARGIN_M` so a point past the horizon can't become a 46 m/s sprint.
- DevelopmentScore auto-computed per player per week after each match
- Prediction model pipeline: Ridge regression per position group (GK/DEF/MID/FWD)
  - metrics/features.py + scripts/train_model.py
  - GET /api/v1/players/{id}/prediction: predicted_score, trend, confidence, week
  - Dashboard PredictionCard component on player profile page

### Infrastructure

- Database schema + 5 Alembic migrations (SQLite dev, PostgreSQL prod)
- FastAPI REST API with JWT auth
- **Match and player routes are tenant-scoped** — every per-match route depends on `get_scoped_match` and every per-player route on `get_scoped_player`, which 404 (not 403, so a caller can't confirm which ids exist) when the record belongs to another academy. `list_matches`, `create_match` and `create_player` take the academy from the bearer token, never from the query string or request body. `tests/test_api/test_tenant_isolation.py` holds that line.
  - **Two visible contract changes** from that fix (2026-08-14): `GET /matches/` no longer requires `academy_id` — a missing one now returns 200 scoped to the token instead of 422, and a supplied one is ignored. `POST /matches/` dropped `academy_id` from the body; it is silently ignored (pydantic `extra="ignore"`), not rejected.
  - **One more from the players fix (2026-08-15):** `POST /players/` likewise dropped `academy_id` from the body. A client that still sends another academy's id now gets a 201 with the player under **its own** academy rather than a 422 — silently ignored, the same trade-off as matches.
- Video upload endpoint → Celery async pipeline
- Next.js 14 dashboard (match list, match detail, player profile + prediction card)
- **Dockerfile** — CPU-only multi-stage build; `alembic upgrade head` on startup
- **.dockerignore** — excludes model weights, raw footage, node_modules, .env
- **GitHub Actions CI** (.github/workflows/ci.yml) — all 3 jobs passing:
  - backend: ruff lint + pytest (257 tests) using requirements-test.txt
  - docker-build: builds API image (requirements-ci.txt, ~30s) on every push
  - dashboard: npm ci + tsc --noEmit
- **requirements-ci.txt**: slim install for the API image (no torch/opencv/paddlepaddle)
- **requirements-test.txt**: `-r requirements-ci.txt` + `opencv-python-headless`, used by CI only. Separate because the Dockerfile defaults to `REQUIREMENTS=requirements-ci.txt`, and the API serves JSON and does no computer vision — but `utils/homography.py` imports cv2 at module scope, which used to keep `tests/test_metrics/`, `tests/test_utils/` and `tests/test_pipeline/` (100 tests) out of CI

### Single-camera adjustments (Phase 2)

- `yolo_conf_threshold` lowered 0.5 → 0.35 (phone footage)
- `max_lost_frames` raised 30 → 90 (~3.6s at 25fps)
- `Match` stores `fps`, `frame_width`, `frame_height` per upload
- `run_pipeline.run()` accepts `--fps / --frame-width / --frame-height` CLI args
- Celery task forwards per-match camera params to pipeline

## Next Session — Pick Up Here

**Phases 1–6 complete. 257 tests passing in CI. API live on Cloud Run.**

**Formation detection is live end to end** — calibration API → homography →
`pitch_history` → formation → DB → summary API → dashboard card.

**CI note:** the backend lint job was red from `a5f88be` until 2026-08-13 (an
unused `pytest` import tripped `ruff check .`). Fixed; `ruff check .` is clean.

**Phase 6 — Terraform / Google Cloud Run ✓ COMPLETE**

- Artifact Registry Docker repo: `us-central1-docker.pkg.dev/pitchvision-prod/pitchvision/pitchvision-api`
- Cloud Run service: `https://pitchvision-api-4hxfthgkna-uc.a.run.app`
  - 1 vCPU, 2Gi, cpu_idle=true, scales 0–3
  - Startup probe: GET /health:8000, `container_port = 8000` (critical — Cloud Run defaults to 8080)
  - DATABASE_URL → `postgresql://` (psycopg2, sync), not `postgresql+asyncpg://`
  - `requirements-ci.txt` includes `psycopg2-binary` for Alembic + API
- `terraform/main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, `terraform.tfvars` (gitignored)

**Remaining backlog (any order after Phase 6):**

- **Corner-picker UI** — the calibration API exists but nothing in the dashboard sets it. A coach currently needs a raw `PUT /calibration` call. Needs a click-four-corners-on-a-still screen.
- **Re-processing after calibration** — uploading a video starts processing immediately, so calibration saved afterwards only applies to the next run. Either let calibration re-enqueue the pipeline, or split upload from "start processing".
- **Half-time end swap** — `home_defends_end` describes the whole video. A full-match upload has the teams swapping ends at the break, so one half's formation will be mirrored. Fine for single-half clips; needs a per-half split for full matches.
- Re-ID across occlusions (TransReID/OSNet — needs torch)
- pgvector — embedding-based player search (schema placeholder exists)
- Three copies of the linear pixel→metre fallback now exist (`scripts/run_pipeline.py` `to_pitch`, `metrics/pressing.py:90`, `metrics/pitch_control.py:174`); the latter two use global settings rather than per-match dimensions. Worth unifying once homography is the normal path.

## Do Not

- Commit model weights or raw footage to git
- Use absolute paths — always use pathlib relative to PROJECT_ROOT
- Skip type hints — all functions must be typed
- Use "football" in user-facing copy — use "soccer" (Canadian market)
- Create pull requests — push directly to main
