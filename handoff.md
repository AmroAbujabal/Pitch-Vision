# PitchVision — Handoff

_Last updated: 2026-07-10_ — **paused, safe to pick up. Working tree clean, all pushed to origin/main.**

## Goal

Ship a computer-vision pipeline that detects, tracks, and analytically profiles soccer players from a single fixed touchline camera, and serve the metrics through a REST API + Next.js coach dashboard. Target market: Canadian amateur/semi-pro clubs that can't afford Opta/StatsBomb.

## Current State

- **All 6 phases complete.** 126 tests passing, CI green (backend ✓ / docker-build ✓ / dashboard ✓).
- **API is live** on Google Cloud Run: `https://pitchvision-api-4hxfthgkna-uc.a.run.app` (GET /health → 200). Scales 0–3, 1 vCPU / 2Gi.
- Latest commit `a5f88be feat(metrics): direction-aware formation detection` — **pushed to `origin/main`**. Working tree clean, git fully synced, no loose ends.
- Core pipeline live: YOLOv10 + SAM 2 detection, SORT tracking, PaddleOCR jersey numbers, physical/speed-zone/heatmap/pitch-control/pressing metrics, DevelopmentScore, Ridge-regression prediction per position group.
- **Formation detection implemented & committed** (`metrics/formation.py`, 18 tests) — direction-aware, correct-or-silent design. Blocked for production on homography (attack direction) + `track.pitch_pos` population in the pipeline.
- Local test note: `test_metrics/` needs `cv2` (not installed here / not in CI). Made `conftest.py` cv2-import lazy → `test_formation` + `test_physical` now run locally; `test_pressing`/`test_pitch_control*` still need opencv. CI runs only `test_api/` + `test_db/` (126 passing).

## Active Files

- `CLAUDE.md` — project overview + "Next Session" pointer (source of truth for status).
- `terraform/main.tf` — Cloud Run service def; `container_port = 8000` is load-bearing.
- `requirements-ci.txt` — CI/prod deps; includes `psycopg2-binary` (sync Postgres for Alembic + API).
- `metrics/formation.py` — direction-aware `detect_formation(..., own_goal_end=...)`; orient → conditional GK drop → depth-gap line clustering.
- `tests/test_metrics/test_formation.py` — 18 unit tests (incl. regressions: lone striker, GK off-camera, winger stagger, direction-unknown, crash guard).
- `tests/test_metrics/conftest.py` — homography/cv2 import made lazy so cv2-free metric tests collect.
- `metrics/` — physical.py, heatmap.py, pitch control, pressing, features.py, development scoring.
- `terraform/terraform.tfvars` — gitignored, holds Supabase creds.

## Changes Made

- **2026-07-05** — Committed the uncommitted Phase-6 deploy fixes (`9c0f9ef`): `container_port = 8000` (Cloud Run defaults to 8080), `psycopg2-binary` in requirements-ci.txt, CLAUDE.md marked Phase 6 complete. Ran karpathy-check (clean; diff_surgeon "noise" was doc-update false positive). Created this handoff.md.
- **2026-07-06** — Pushed `9c0f9ef` + `e098bba` (handoff.md) to `origin/main`.
- **2026-07-07** — Implemented `detect_formation()` (TDD). Made `test_metrics/conftest.py` cv2-import lazy (unblocks `test_formation` + `test_physical` locally).
- **2026-07-08** — High-effort code-review flagged the position-only heuristic as direction-ambiguous (GK vs lone striker) and dead-on-arrival (pipeline never sets `pitch_pos`). Verified findings, then **redesigned to direction-aware** (`own_goal_end` param, correct-or-silent) + fixed tolerance/guard/min_players. 18 tests green; CI 126 + physical 13 green, no regression.
- **2026-07-10** — Committed + pushed formation (`a5f88be`, karpathy-check passed 100/100). Session paused here.

## Failed Attempts

- **Position-only GK-isolation orientation (rejected 2026-07-08)** — first formation impl guessed the own-goal end from which depth-extreme was more isolated. Fails on mirror-symmetric shapes: a lone striker is indistinguishable from a goalkeeper, so 4-5-1 reversed to "5-4-1" and an off-camera GK dropped a real defender. Lesson: attack direction cannot be inferred from positions alone — it must be supplied (homography goal ends). Replaced with the direction-aware design.
- Historical deploy gotchas already solved & documented in CLAUDE.md: Cloud Run defaulting to port 8080; `postgresql+asyncpg://` breaking sync SQLAlchemy/Alembic (must use `postgresql://`); missing `psycopg2-binary`.

## Next Steps

**Recommended first: pitch homography** — it's the shared blocker that unblocks formation AND improves distance/speed accuracy.

1. **Pitch homography** — `PitchHomography.fit_from_points()` with manual corner annotations per match. Deliverables: a way to enter/store the 4 pitch corners per match, then use the homography to (a) populate `track.pitch_pos` in `run_pipeline.py` (currently never set — see note below), and (b) derive each team's `own_goal_end` from the goal coordinates.
2. **Go-live formation** (needs step 1) — in `run_pipeline.py`: populate `track.pitch_pos`, pass `own_goal_end` into `detect_formation()`, store the result on the match (schema + Alembic migration) → expose via API → surface on the dashboard. Until step 1, `detect_formation()` is a correct-but-no-op function.
   - Quick independent win available: populating `track.pitch_pos` (the linear bbox-centre fallback already computed at `run_pipeline.py` ~line 165) can be wired back now even before full homography — but direction still needs step 1 for a real label.
3. Remaining backlog (any order):
   - Re-ID across occlusions — TransReID/OSNet (needs torch).
   - pgvector — embedding-based player search (schema placeholder exists).

## How to resume / verify
- `cd /Users/amrabujabal/Downloads/football-ai`
- Tests (CI scope): `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q` → 126 pass
- cv2-free metrics: `/usr/local/bin/python3.11 -m pytest tests/test_metrics/test_formation.py tests/test_metrics/test_physical.py -q` → 31 pass
- `test_pressing` / `test_pitch_control*` need `cv2` (opencv) installed locally; they run in neither CI nor this env.
- API live: `https://pitchvision-api-4hxfthgkna-uc.a.run.app/health`
