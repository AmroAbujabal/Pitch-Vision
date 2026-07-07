# PitchVision — Handoff

_Last updated: 2026-07-05_

## Goal

Ship a computer-vision pipeline that detects, tracks, and analytically profiles soccer players from a single fixed touchline camera, and serve the metrics through a REST API + Next.js coach dashboard. Target market: Canadian amateur/semi-pro clubs that can't afford Opta/StatsBomb.

## Current State

- **All 6 phases complete.** 126 tests passing, CI green (backend ✓ / docker-build ✓ / dashboard ✓).
- **API is live** on Google Cloud Run: `https://pitchvision-api-4hxfthgkna-uc.a.run.app` (GET /health → 200). Scales 0–3, 1 vCPU / 2Gi.
- Working tree is **clean**; latest commit `9c0f9ef fix(phase-6): commit working Cloud Run deploy fixes`.
- Commit is **local only — not yet pushed** to `origin/main` (awaiting user confirmation to push).
- Core pipeline live: YOLOv10 + SAM 2 detection, SORT tracking, PaddleOCR jersey numbers, physical/speed-zone/heatmap/pitch-control/pressing metrics, DevelopmentScore, Ridge-regression prediction per position group.

## Active Files

- `CLAUDE.md` — project overview + "Next Session" pointer (source of truth for status).
- `terraform/main.tf` — Cloud Run service def; `container_port = 8000` is load-bearing.
- `requirements-ci.txt` — CI/prod deps; includes `psycopg2-binary` (sync Postgres for Alembic + API).
- `metrics/formation.py` — stub returning "unknown" (next feature candidate).
- `metrics/` — physical.py, heatmap.py, pitch control, pressing, features.py, development scoring.
- `terraform/terraform.tfvars` — gitignored, holds Supabase creds.

## Changes Made

- **2026-07-05** — Committed the uncommitted Phase-6 deploy fixes (`9c0f9ef`): `container_port = 8000` (Cloud Run defaults to 8080), `psycopg2-binary` in requirements-ci.txt, CLAUDE.md marked Phase 6 complete. Ran karpathy-check (clean; diff_surgeon "noise" was doc-update false positive). Created this handoff.md.

## Failed Attempts

- _(none recorded yet this session)_
- Historical deploy gotchas already solved & documented in CLAUDE.md: Cloud Run defaulting to port 8080; `postgresql+asyncpg://` breaking sync SQLAlchemy/Alembic (must use `postgresql://`); missing `psycopg2-binary`.

## Next Steps

1. **Push** `9c0f9ef` to `origin/main` (pending user confirmation).
2. Backlog (any order):
   - Formation detection — implement `metrics/formation.py` (team-colour classification now stable).
   - Real pitch homography — `PitchHomography.fit_from_points()` needs manual corner annotations per match.
   - Re-ID across occlusions — TransReID/OSNet (needs torch).
   - pgvector — embedding-based player search (schema placeholder exists).
