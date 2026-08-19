# PitchVision — Handoff

_Last updated: 2026-08-18_ — **the corner-picker ships and is committed.
Formation detection is reachable from the dashboard for the first time, which
also meant giving the dashboard an auth flow it never had. CI now runs 257
tests instead of 157.**

## Goal

Build the corner-picker UI, the top item carried over from 2026-08-15. Two
blockers surfaced during exploration that the previous handoff did not know
about, and both had to be solved first: the dashboard could not authenticate at
all, and nothing served a still frame to click on.

## Current State

- **Verified 2026-08-18 (re-run at session close, all green):**
  - What CI runs, `pytest tests/ -q --ignore=tests/test_detection` → **257 pass**
  - API-only subset `pytest tests/test_api/ tests/test_db/ -q` → **157 pass** (was 154)
  - `ruff check .` → clean
  - `cd dashboard && ./node_modules/.bin/tsc --noEmit` → clean
  - `cd dashboard && npm test` → **16 pass** (vitest, new)
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
- **Committed, not pushed.** `origin/main` is 4 commits behind:
  - `a3f474f` feat(dashboard): the picker + auth flow
  - `5f6179d` ci: run the 100 metrics/utils/pipeline tests that never ran
  - `6409eed` chore: stop tracking tsconfig.tsbuildinfo
  - plus `77df4ad` from the previous session

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
- `components/SignOutButton.tsx`, `components/StepIndicator.tsx`,
  `components/SmallButton.tsx`

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
- `.github/workflows/ci.yml` — dashboard job runs `npm test`; backend job now
  installs `requirements-test.txt` and runs the full non-detection scope.
- `requirements-test.txt` — new; `-r requirements-ci.txt` + opencv-headless.

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
- **Typing a coordinate before placing any corner crashed the page.**
  `setCorner` assigned straight to an index, so a shorter array gained holes,
  and a hole is typed as a Point but reads as undefined in `draw()` and
  `quadProblem()`. Found by code review, reproduced in the browser.
  The guard for it needed an **indexed loop**: `some`/`every`/`filter` skip
  holes rather than seeing undefined, so the obvious `points.some(p => !p)`
  compiled, read correctly, and did absolutely nothing. The test caught it.
- **Swapping a video mid-decode wiped the new one.** The old element's
  listeners stayed attached, so revoking its URL fired its `error` handler,
  which cleared the file just picked and named the wrong one. Handlers now
  check `videoRef.current === video` first.
- All four of the above passed `tsc` and the unit tests. Only driving the real
  page found them. Budget time for that on any canvas or media work here.
- Not a failure, but do not re-litigate: `taste-skill` was consulted for the
  visual design and self-excludes dashboards and multi-step forms in its
  Section 13. `ui-ux-pro-max` is the right skill for this app's UI.
- Also settled: `handoff.md` used to say "add opencv to requirements-ci.txt".
  That is wrong — `Dockerfile:16` installs that file into the production image.
  Test-only deps go in `requirements-test.txt`.

## Next steps

1. **Re-processing after calibration — design decided 2026-08-18, not built.**
   Calibration still only takes effect on the next pipeline run, so a coach who
   uploads before calibrating is stuck with `"unknown"`. Build it as an
   **explicit re-run**, not an implicit one:
   - `POST /api/v1/matches/{id}/reprocess`, behind `get_scoped_match` like every
     other per-match route. 404 if the raw video is no longer on disk at
     `settings.raw_dir / f"{match.id}{suffix}"`; otherwise set
     `processing_status = "processing"` and enqueue.
   - Reuse the broker-failure guard added to `upload_video` — mark the match
     `failed` and return 503 rather than stranding it as "processing".
     Better still, factor that enqueue-and-roll-back block out of
     `upload_video` so both callers share it, rather than copying it.
   - Dashboard: a "Re-run analysis" button on the match page, shown when the
     match is `done` but a formation is `"unknown"`. The `needsCalibration`
     banner in `dashboard/app/matches/[id]/page.tsx` already computes exactly
     that condition and is the natural place to hang it.
   - Rejected: letting `PUT /calibration` re-enqueue on its own. A save button
     that silently starts a long job is a surprising side effect.
   - Also rejected for now: splitting upload from "start processing". Cleanest
     model, but it changes the existing upload contract and its tests, and the
     re-run endpoint solves the actual problem without that churn.
2. **Half-time end swap** — `home_defends_end` describes the whole video, so a
   full match mirrors one half. Needs a per-half split.
3. **Frame dimensions are never sent.** `CalibratePicker` knows the real
   `frame.width/height` but `POST /matches/` takes the 1920x1080 default, and
   `PUT /calibration` has no field to correct it. Only bites when the
   homography fails and the linear pixel-to-metre fallback runs, but it is a
   silent wrong answer when it does. Raised by code review.
4. **Cloud Run returned 503** on `/health` (2026-08-16). Untouched, uninvestigated.
5. Backlog: an email or slug column on `Academy` so login is not a raw UUID;
   `api/routers/academies.py` is still an empty router with no way to create an
   academy or set a password; Re-ID across occlusions (needs torch); pgvector;
   unify the three copies of the linear pixel→metre fallback
   (`run_pipeline.to_pitch`, `pressing.py:90`, `pitch_control.py:174`).

## How to resume / verify

- `cd /Users/amrabujabal/Downloads/football-ai`
- What CI runs: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → 257 pass
- Lint: `/usr/local/bin/python3.11 -m ruff check .` → clean
- Dashboard: `cd dashboard && ./node_modules/.bin/tsc --noEmit && npm test`
- Seed a login: `SEED_PASSWORD=devpassword PYTHONPATH=. python3.11 scripts/seed_dev.py`
  (prints the academy id to sign in with). `dev.db` needed
  `alembic upgrade head` first — it predated the `frame_dims` migration.
- Run it: `PYTHONPATH=. python3.11 -m uvicorn api.main:app --port 8001` and
  `cd dashboard && npm run dev`. `.env.local` points at **8001**, not 8000.
- The upload step needs a broker: `brew install redis`. The pipeline itself
  still cannot run locally without torch.
