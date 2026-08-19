# PitchVision — Handoff

_Last updated: 2026-08-19_ — **the correctness cluster is shipped** (`cf5a67d`,
pushed). Two of the three filed bugs were real, the third was not, and working
out why turned up two more. Then `/code-review` found three defects in the fixes
themselves, all of which were confirmed and fixed before the commit.

## Goal

Items 6, 7 and 8 from the previous handoff's next-steps: the open redirect in
the login page, reverse-winding pitch corners silently mirroring the pitch, and
the match date that shifts a day. Chosen over the half-time end swap because
three small independent fixes fit one session and all three were silent wrong
answers rather than visible failures.

## Current State

- **Verified 2026-08-19, all green:**
  - What CI runs, `pytest tests/ -q --ignore=tests/test_detection` → **291 pass** (was 273)
  - API-only subset `pytest tests/test_api/ tests/test_db/ -q` → **177 pass** (was 173)
  - `ruff check .` → clean
  - `cd dashboard && ./node_modules/.bin/tsc --noEmit` → clean
  - `cd dashboard && npm test` → **41 pass** (was 16)
- **Driven in a real browser, both directions.** For the redirect and for the
  dates, the broken version was temporarily restored to confirm the bug, then
  the fix restored and re-checked:
  - `?next=/\evil.example` → old code: browser leaves the site, page title
    `evil.example`. New code: stays on `localhost:3000/`.
  - `?next=/..//evil.example` (the regression review found in the *first* fix) →
    origin-check-only version: leaves the site. Fixpoint version: stays.
  - Match cards: `created_at` of `2026-08-17T00:11:40` renders `16 Aug 2026`,
    a `match_date` of `2026-08-19` renders `19 Aug 2026`, and each `<time
    dateTime>` now agrees with the text beside it.
  - Prediction card: `"week":"2026-08-24"` renders `24 Aug 2026`. It rendered
    `23 Aug` — a Sunday, on a card headed "Next week prediction".
  - **Re-checked with the dev server restarted under `TZ=UTC`**, which is what
    the container is. This is the check that caught the third review finding.
- **Reviews:** `/simplify` (4 agents), `/code-review high`, `/security-review`,
  `/karpathy-check`. Code review found 3 real defects in the fixes (see Failed
  Attempts); security found 1, also in a fix, also real; karpathy passed with
  warnings, two of which were acted on. All fixed before committing.
- **Committed and pushed.** `origin/main` at `cf5a67d`. Working tree clean.

## Active Files

New:

- `utils/pitch_corners.py` — `corner_problem()`, the canonical explanation of
  what each wrong corner ordering does to the analytics. Free of cv2 and numpy
  on purpose: the API image installs `requirements-ci.txt`, which has no
  opencv, and `utils/homography.py` imports cv2 at module scope.
- `dashboard/lib/safe-next.ts` — the post-login redirect guard, extracted from
  the login page so it is testable without rendering a client component.
- `dashboard/lib/dates.ts` — `formatDay`/`isoDay` for calendar dates,
  `formatInstant`/`isoInstant` for timestamps.
- `dashboard/lib/{safe-next,dates}.test.ts`, `tests/test_utils/test_pitch_corners.py`.

Modified:

- `api/routers/matches.py` — `model_validator` on `MatchCalibration`.
- `utils/homography.py` — `fit_from_corners` validates via the shared predicate.
- `dashboard/lib/corners.ts` — winding **and** starting corner; one shared
  message for both, since the remedy is the same.
- `dashboard/components/MatchCard.tsx`, `dashboard/app/players/[id]/page.tsx`,
  `dashboard/app/login/page.tsx`, `dashboard/app/matches/new/page.tsx`.
- `tests/test_api/test_calibration.py` — 4 new tests.
- `CLAUDE.md` — counts, and the two new invariants.

## Changes Made

1. **Open redirect.** `safeNext` rejected `//host` but not `/\host`; the WHATWG
   parser reads a backslash as a slash for http(s), so both resolve off-origin.
   Replaced prefix-guessing with resolve-and-compare-origins.
2. **The redirect fix needed a second pass** — see Failed Attempts item 1. It now
   also requires its own output to survive the same check, which closes the
   whole family rather than the two spellings anyone thought to list.
3. **Corner winding**, then **the starting corner** — see Failed Attempts item 2.
   Exactly 1 of the 24 orderings is now accepted, asserted exhaustively with
   `itertools.permutations` rather than by listing cases.
4. **The corner check moved to the server too.** `PUT /calibration` validated
   only `min_length=4, max_length=4`, while its own docstring spent five lines
   explaining that a wrong order mirrors the reported shape. The picker is not
   the only writer (`run_pipeline --pitch-corners`, any curl caller), and cv2
   fits a mirrored quad without complaint, so nothing downstream can notice.
   Also called from `fit_from_corners`, where the pipeline's existing
   `except (ValueError, TypeError)` degrades a legacy bad row to the linear
   fallback — i.e. to "unknown formation" rather than a confident mirror.
5. **`corner_problem` checks each corner's length before indexing.** Ragged
   input raised `IndexError`, which `scripts/run_pipeline.py` does *not* catch,
   so one hand-edited row would have aborted a whole pipeline run.
6. **Dates.** One module owns the two wire shapes. `formatDay` pins a calendar
   date to UTC so the answer is the same whichever shape it arrived in;
   `formatInstant` states the UTC an unzoned timestamp already is and renders it
   in an explicit `DISPLAY_ZONE`. `<time dateTime>` gets matching machine values.
7. **The create form sends a bare `YYYY-MM-DD`.** It was correct only by
   accident — an aware UTC-midnight value that the naive column happened to
   strip. On Postgres, an aware value cast into `timestamp without time zone`
   converts via the session `TimeZone`, which nothing pins, so the stored day
   was config-dependent in production. Pydantic parses the bare date to naive
   midnight directly.
8. **A bad date degrades to `—`.** `fmtDate`'s null guard was lost in the
   refactor; `Intl` throws `RangeError` on a NaN date, and `lib/api.ts` casts
   the JSON without validating it, so one bad row would have thrown out of a
   server component and taken the whole match list with it.

## Failed Attempts

Three of the four things that went wrong this session were in the fixes, not in
the original code. All were caught by review agents and confirmed independently
before being acted on — two of them contradicted reasoning I had already written
down and been satisfied with.

1. **The first redirect fix reintroduced the bug it fixed.** Comparing origins is
   right, but returning `pathname + search + hash` is not: `/..//evil.example`
   resolves same-origin with a *pathname* of `//evil.example`, and
   `router.replace` resolves that against the real host as protocol-relative.
   Confirmed in a browser — the "fixed" version navigated to evil.example.
   The suggested patch was to also reject `//` and `/\` prefixes, which is the
   spelling-enumeration the fix existed to replace; requiring the output to be a
   fixed point of the check closes the family. Fuzzed 23 hostile forms.
2. **Requiring positive winding did not stop the pitch mirroring.** Winding
   constrains the *direction* of the walk, not *which corner is first*, and all
   three rotations are clockwise. Solving the homography for every permutation:
   the 180° rotation maps frame-left to x=103.9 and frame-right to x=1.8 — the
   length axis mirrored, i.e. precisely the "4-2-3-1 read as 1-3-2-4" case — and
   the two 90° rotations put both frame edges at the same pitch x, transposing
   the axes entirely. All three passed.
3. **The comment blamed the wrong case.** The reverse walk mirrors pitch
   *width* (the left wing's heatmap appears on the right); the length mirror is
   the 180° rotation, which was being accepted. The wrong attribution had been
   copied into six places, which is exactly how it would have survived: it reads
   as a complete account of the check.
4. **The `created_at` fix was verified in a browser and was still broken in
   production.** `MatchCard` is a server component, so "local time" is the Node
   process's zone — UTC in the container, since the Dockerfile sets no `TZ`. It
   rendered correctly on this laptop only because the dev server inherited
   `America/Vancouver`. Both ends of every conversion are now named, so nothing
   depends on the ambient zone; the suite passes identically under UTC,
   Vancouver, Sydney and Kolkata, and `npm test` no longer needs its `TZ=` pin.

Local-harness notes:

- **A `cd x && python3 - <<'PY'` heredoc silently does nothing if the `cd`
  fails** (e.g. already in `x`) — the following line still runs and its output
  looks like success. Check `pwd` first, or use absolute paths.
- `rm -rf .next` gets "Permission denied" while the dev server is still writing
  to it; kill the server first.
- The stale-`.next` symptom is a page whose CSS and chunks all 404.

## Next steps

1. **Half-time end swap** — `home_defends_end` describes the whole video, so a
   full match mirrors one half. Needs a per-half split. Unchanged from before,
   and now the largest remaining correctness gap.
2. **Frame dimensions are never sent.** `CalibratePicker` knows the real
   `frame.width/height` but `POST /matches/` takes the 1920x1080 default and
   `PUT /calibration` has no field to correct it. Only bites when the homography
   fails and the linear fallback runs, but it is a silent wrong answer then.
3. **Zoned serialisation on the API side.** Naive `DateTime` columns serialise
   with no zone, so "these are UTC" is an out-of-band convention every consumer
   has to know; the dashboard is just the only consumer so far. Pydantic
   serialisers on the 8 datetime fields (~15 lines, no migration) would make
   `isoInstant` dead and the calendar fields consistently shaped. It is a
   visible wire-format change, which is why it was not done as a drive-by.
4. **`DISPLAY_ZONE` is one global guess** (`dashboard/lib/dates.ts`).
   America/Vancouver, hardcoded, because there is nowhere to put a per-academy
   zone. Only reachable through a card whose match has no date of its own, and
   only wrong for a coach in another province uploading near midnight — but it
   is an assumption picked mid-bugfix, not a decision anyone signed off. A
   `timezone` column on `Academy` is the upgrade; an env var is the cheap stopgap.
5. **Orphaned video files.** `upload_video` never deletes a previously uploaded
   file for the same match, so uploading a `.mov` then an `.mp4` leaks the `.mov`.
6. **`tasks/pipeline.py::process_match` has no test coverage at all** — nothing
   in `tests/` executes the task body.
7. **A third copy of the fetch/busy/error pattern** across
   `CalibratePicker.save()`, `.upload()` and `ReprocessButton`. A `useApiAction`
   hook would fold all three; skipped because it means editing the picker.
8. **The UUID regex is duplicated** — `dashboard/app/login/page.tsx:8` is
   character-for-character `lib/proxy.ts`'s, which already exports `isUuid`.
   Sharing it means moving `isUuid` somewhere client-safe, since `proxy.ts`
   imports `next/server`. Pre-existing, small.
9. **`Intl.DateTimeFormat` is rebuilt per call** in `dates.ts` (~164µs measured,
   vs 1.6µs reusing one; the match list is unpaginated and the trend table goes
   to 52 rows). A cache was written, then cut at karpathy-check as an
   optimisation smuggled into a correctness fix. Re-add it if the page is ever
   actually slow — the measurement is in this handoff, so it need not be redone.
10. **Cloud Run returned 503** on `/health` (2026-08-16). Still untouched.
11. Backlog: email/slug on `Academy` so login is not a raw UUID; the empty
    `api/routers/academies.py`; Re-ID across occlusions (needs torch); pgvector;
    unify the three copies of the linear pixel→metre fallback.

## How to resume / verify

- `cd /Users/amrabujabal/Downloads/football-ai`
- What CI runs: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → 291 pass
- Lint: `/usr/local/bin/python3.11 -m ruff check .` → clean
- Dashboard: `cd dashboard && ./node_modules/.bin/tsc --noEmit && npm test` → 41 pass
- **The date tests are zone-independent on purpose.** If you find yourself
  wanting to pin `TZ` to make one pass, the code under test has an unpinned
  conversion in it. Check the code, not the runner.
- Run it: `PYTHONPATH=. python3.11 -m uvicorn api.main:app --port 8001` and
  `cd dashboard && npm run dev`. `.env.local` points at **8001**.
- **To check anything that renders a date or a time, restart the dev server with
  `TZ=UTC`** — that is what the container is, and the laptop's zone will hide
  the bug.
- Test academy `7ceca9ce-9c63-4330-8053-d658408c9fc6` / `devpassword`.
- `dev.db` stores match ids **without dashes**; a `WHERE id='<dashed>'` updates
  zero rows and reports success.
- `dev.db` gained one match this session from driving the create form
  (`72919811-…`, Kelowna United vs Vernon FC, 19 Aug) and one match_date on
  `b4f96c33…` so a card would exercise the calendar-date path. Nothing else was
  left behind; the fabricated development_scores and player_match_stats rows
  used to make the prediction card render were deleted. Pre-session copy at
  `/private/tmp/claude-501/-Users-amrabujabal/f9a2f9f2-e214-4f19-8e14-2be297ac2d9c/scratchpad/dev.db.session-bak`.
