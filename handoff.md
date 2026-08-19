# PitchVision — Handoff

_Last updated: 2026-08-17_ — **the corner-picker ships. Formation detection is
reachable from the dashboard for the first time, which also meant giving the
dashboard an auth flow it never had.**

## Goal

Build the corner-picker UI, the top item carried over from 2026-08-15. Two
blockers surfaced during exploration that the previous handoff did not know
about, and both had to be solved first: the dashboard could not authenticate at
all, and nothing served a still frame to click on.

## Current State

- **Verified 2026-08-17:**
  - CI scope `pytest tests/test_api/ tests/test_db/ -q` → **157 pass** (was 154)
  - `ruff check .` → clean
  - `cd dashboard && ./node_modules/.bin/tsc --noEmit` → clean
  - `cd dashboard && npm test` → **14 pass** (vitest, new)
- **Driven end to end in a real browser** against a real API on port 8001:
  `/` redirects to `/login` → sign in → matches list scoped to the token →
  create match → calibrate → pick video → click 4 corners → choose direction →
  save. Then read back from `dev.db` and fitted through the homography.
- **The corners land in video pixel space, confirmed against ground truth.** A
  synthetic ffmpeg clip with a pitch rectangle at exactly
  `(300,200)-(1620,880)` in a 1920x1080 frame, rendered on a canvas at 734x414
  (a 2.616x scale), stored `[[300,198],[1618,198],[1618,880],[300,880]]`. The
  1-2px residual is the expected quantisation, since one CSS pixel is 2.6 video
  pixels at that scale. `PitchHomography.fit_from_corners()` maps them onto
  `(0,0) (105,0) (105,68) (0,68)` with the centre at `(52.5, 34)`.
- Design doc: `docs/superpowers/specs/2026-08-16-corner-picker-design.md`.
- **Nothing is committed.** Everything below is in the working tree.

## Active Files

New, dashboard:

- `lib/corners.ts` + `lib/corners.test.ts` — click to video pixel, corner
  labels, degenerate-quad rejection. The only logic with tests, because it is
  the only part where a wrong answer is invisible.
- `lib/session.ts` — `pv_token` cookie, `UnauthorizedError`. Cookie lifetime is
  read from the JWT's own `exp` claim rather than duplicating
  `access_token_expire_minutes`.
- `lib/proxy.ts` — `forward()` attaches the bearer server-side; `isUuid()`
  guards route params before they reach the API URL.
- `lib/guard.ts` — `redirectIfUnauthorized()` for page catch blocks.
- `middleware.ts`, `app/login/page.tsx`, `app/api/auth/{login,logout}/route.ts`
- `app/matches/new/page.tsx`, `app/api/matches/route.ts`
- `app/matches/[id]/calibrate/page.tsx`, `components/CalibratePicker.tsx`,
  `app/api/matches/[id]/{calibration,upload}/route.ts`
- `components/SignOutButton.tsx`

Modified:

- `dashboard/lib/api.ts` — sends `Authorization`; 401 throws `UnauthorizedError`.
  `matches.list()` lost its `academyId` argument.
- `dashboard/app/page.tsx` — `NEXT_PUBLIC_ACADEMY_ID` gone, "New match" added.
- `dashboard/app/matches/[id]/page.tsx` — "Calibrate camera" link, plus a
  warning when a processed match came back with `"unknown"` formations.
- `dashboard/components/Nav.tsx` — sign-out, hidden when signed out.
- `api/routers/matches.py` — the one backend change, see below.
- `scripts/seed_dev.py` — sets a password (`SEED_PASSWORD`, default
  `devpassword`), since nothing else can.
- `.github/workflows/ci.yml` — dashboard job runs `npm test` too.

## Changes Made

1. **Still frames come from the browser, not the server.** The coach picks the
   file, an offscreen `<video>` seeks, and the frame goes to a canvas. Clicks
   scale by `videoWidth / rect.width`. A server-side `GET /frame` was rejected
   twice over: it needs opencv in the production image, which
   `requirements-ci.txt` deliberately excludes, and it could only run after
   upload, which is after processing already started.
2. **Auth is an httpOnly cookie plus server-side proxies.** Existing pages are
   Server Components, so a token in `localStorage` would have forced them all
   to become client components. The cookie is unreadable from page JS, which is
   exactly why the picker's mutations go through route handlers.
3. **Upload is disabled until calibration saves**, so the
   "upload-starts-the-pipeline-immediately" trap cannot be hit through the UI.
4. **`upload_video` no longer strands a match** (`api/routers/matches.py`). It
   committed `processing_status = "processing"` _before_ enqueueing, so a
   broker that is down left the match reading "processing" forever with nothing
   to pick it up. Now the failure marks it `"failed"` and returns 503 with the
   video kept on disk for a retry. Found by clicking Upload on this machine,
   which has no Redis. Three regression tests, all verified failing against the
   old code.

## Failed Attempts

- **The canvas would not draw.** `canvasRef.current` is null inside the
  `seeked` handler, because the canvas only mounts once `frame` state is set.
  Sizing moved into `draw`, which runs after the element exists.
- **Four corners clicked quickly became one.** `setCorners([...corners, point])`
  read a stale closure, so clicks landing in the same React batch overwrote
  each other. Functional updater now. Both of these passed type-checking and
  unit tests and were only caught by driving the real page.
- Not a failure, but do not re-litigate: `taste-skill` was consulted for the
  visual design and self-excludes dashboards and multi-step forms in its
  Section 13. `ui-ux-pro-max` is the right skill for this app's UI.

## Next steps

1. **Re-processing after calibration** — now the highest-value item. Calibration
   still only affects the next pipeline run, so a coach who uploads first is
   stuck. Either let a calibration save re-enqueue, or split upload from "start
   processing".
2. **Add opencv to `requirements-ci.txt`** so `tests/test_metrics/`,
   `tests/test_utils/` and `tests/test_pipeline/` run in CI. 100 tests are
   local-only. Still the cheapest item on the list.
3. **Half-time end swap** — `home_defends_end` describes the whole video, so a
   full match mirrors one half.
4. **Cloud Run is returning 503** on `/health` as of 2026-08-16. Untouched.
5. Backlog: an email or slug column on `Academy` so login is not a raw UUID;
   `api/routers/academies.py` is still an empty router; Re-ID across occlusions
   (needs torch); pgvector; unify the three copies of the linear pixel→metre
   fallback.

## How to resume / verify

- `cd /Users/amrabujabal/Downloads/football-ai`
- CI scope: `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q` → 157 pass
- Lint: `/usr/local/bin/python3.11 -m ruff check .` → clean
- Dashboard: `cd dashboard && ./node_modules/.bin/tsc --noEmit && npm test`
- Seed a login: `SEED_PASSWORD=devpassword PYTHONPATH=. python3.11 scripts/seed_dev.py`
  (prints the academy id to sign in with). `dev.db` needed
  `alembic upgrade head` first — it predated the `frame_dims` migration.
- Run it: `PYTHONPATH=. python3.11 -m uvicorn api.main:app --port 8001` and
  `cd dashboard && npm run dev`. `.env.local` points at **8001**, not 8000.
- The upload step needs a broker: `brew install redis`. The pipeline itself
  still cannot run locally without torch.
