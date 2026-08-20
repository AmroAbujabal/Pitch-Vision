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
- /utils → Video I/O, coordinate transforms, visualization helpers, pitch-corner validation (`pitch_corners.py`, cv2-free so the API can import it)
- /scripts → Pipeline runner, seed script, model training, weight download
- /data → Raw footage, processed clips, model weights (gitignored)
- /tests → Pytest test suite (309 passing in CI, torch-free)
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
- Run tests (what CI runs): `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → 309 pass
- API-only subset: `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q` → 185 pass
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
- **Half-time end swap** (2026-08-19) — teams change ends at half-time, so a full-match upload used to have one half's positions mirrored along the pitch length axis before averaging into the formation, producing a confidently wrong shape. `Match.half_time_seconds` is a coach-supplied mark in seconds, nullable, and **never inferred** — a wrong split re-creates the exact mirror it was added to remove, so there is no auto-detection fallback. `metrics/formation.py` now orients each observation to the goal its team was actually defending at that moment rather than to one fixed end for the whole video. The frame is derived once, in `run_pipeline` where `fps` is resolved (`half_time_frame(half_time_seconds, fps)`), so a later `fps` correction on the match can't silently move the mark out from under an already-derived frame number. Set via the same `PUT /api/v1/matches/{id}/calibration` picker flow, with a mirrored `le=86_400` (24h) ceiling in both `api/routers/matches.py` and `dashboard/lib/half-time.ts` so an out-of-range value is refused before it can overflow `round(half_time_seconds * fps)`. Two halves only — extra time and multi-break formats are out of scope. `metrics/pressing.compute_dangerous_zone_occupancy` and `compute_recovery_shadow_score` are still direction-dependent and uncalled; they'd need the same per-observation treatment if ever wired up.
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
- Video upload endpoint → Celery async pipeline, plus `POST /matches/{id}/reprocess` to re-run
  the pipeline on the video already on disk (404 if it is gone). Both go through the same
  `_enqueue_processing` helper, so a broker that is down marks the match `failed` and returns
  503 rather than stranding it as "processing". The on-disk path convention lives in one place,
  `config.settings.find_raw_video()`, shared with `tasks/pipeline.py`.
- **`Match.video_path` records where the upload went** (2026-08-19). It was dead
  schema from the initial migration until then, so every reader guessed the file
  name back from the match id by testing each allowed extension. Upload now
  stores the **bare file name** — not a full path, because `raw_dir` differs
  between a laptop and Cloud Run — and `find_raw_video(match_id, stored_name)`
  reads it. A recorded name that no longer exists returns None rather than
  falling through to guessing, so a stale entry can't resurrect an unrelated
  leftover file for the same match. The extension scan survives only as the
  fallback for rows uploaded before the column was populated (it is NULL there);
  delete it once no such rows remain. `find_raw_video` applies `Path(name).name`
  so a future writer of that column cannot turn it into a path traversal.
- **Pitch corners are validated where they arrive, not just in the picker**
  (2026-08-19). `utils/pitch_corners.corner_problem()` accepts **exactly one of
  the 24 orderings** of four corners — cv2 fits all the others happily, so a
  mirrored or transposed pitch is not detectable downstream. Winding alone is
  not enough; the starting corner has to be pinned too. That module's docstring
  is the canonical explanation of what each wrong ordering does. It is called
  from a `model_validator` on `MatchCalibration` (a curl caller gets a 422) and
  from `PitchHomography.fit_from_corners` (covering `run_pipeline
--pitch-corners` and pre-API rows), and is free of cv2/numpy because the API
  image has no opencv. `dashboard/lib/corners.ts` is its twin for the picker —
  two languages either side of the wire, keep them in step.
- **Dates on the wire have two shapes, and the dashboard normalises both**
  (2026-08-19, `dashboard/lib/dates.ts`). Naive `DateTime` columns serialise
  with no zone, so `created_at` — written by the database's UTC `now()` — was
  read as local and dated an evening upload to tomorrow. Calendar dates arrive
  either bare (`"2026-08-24"` from the prediction route) or as
  `"2026-08-24T00:00:00"`, and `new Date` reads the first as UTC midnight and
  the second as _local_ midnight. `formatDay`/`isoDay` pin a calendar date to
  the day it names; `formatInstant`/`isoInstant` state the UTC a timestamp
  already is and render it in an explicit `DISPLAY_ZONE`. **Both ends of both
  conversions are named on purpose** — the cards render in a server component,
  so "local" would mean whatever zone the Node process is in, which is UTC in
  the container and reintroduced the whole bug in production while looking fixed
  in dev. Nothing here depends on the ambient `TZ`, so the tests hold in any.
- Next.js 14 dashboard (match list, match detail, player profile + prediction card)
- **Dockerfile** — CPU-only multi-stage build; `alembic upgrade head` on startup
- **.dockerignore** — excludes model weights, raw footage, node_modules, .env
- **GitHub Actions CI** (.github/workflows/ci.yml) — all 3 jobs passing:
  - backend: ruff lint + pytest (309 tests) using requirements-test.txt
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

**Phases 1–6 complete. 309 tests passing in CI. API live on Cloud Run.**

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

- Re-ID across occlusions (TransReID/OSNet — needs torch)
- pgvector — embedding-based player search (schema placeholder exists)
- Three copies of the linear pixel→metre fallback now exist (`scripts/run_pipeline.py` `to_pitch`, `metrics/pressing.py:90`, `metrics/pitch_control.py:174`); the latter two use global settings rather than per-match dimensions. Worth unifying once homography is the normal path.

## Do Not

- Commit model weights or raw footage to git
- Use absolute paths — always use pathlib relative to PROJECT_ROOT
- Skip type hints — all functions must be typed
- Use "football" in user-facing copy — use "soccer" (Canadian market)
- Create pull requests — push directly to main
