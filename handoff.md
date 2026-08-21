# PitchVision — Handoff

_Last updated: 2026-08-20 (second session that day)._ The six sections below
describe **this** session; the four detailed write-ups after them are the
technical record, and the half-time end swap from earlier the same day is
summarised at the bottom.

## Goal

No single feature. The session started as "pick up PitchVision" and was
redirected twice by the user:

1. **Rename all folders and branding to PitchVision.** Most of the repo already
   said PitchVision; the dashboard, the Celery app and the folder itself did not.
2. **Remove every UAE reference — keep it universal, leaning Canada, with no
   cultural or language preferences.** This reached the schema, not just copy.
3. **"Keep going"** — work the filed backlog. Closed the three items that were
   real bugs or real duplication, and left the ones that are deliberate notes.

The GitHub repo name was explicitly left as `AmroAbujabal/Pitch-Vision`.

## Current State

- **Six commits on `main`, pushed. Working tree clean.**
  - `3b55d21` chore: finish the PitchVision rename on the last football_ai surfaces
  - `3cf478c` docs(handoff): record the rename and the new repo path
  - `9bd809f` refactor: drop the UAE-era locale assumptions from the schema and fixtures
  - `bd67f2a` fix(upload): record the video's real dimensions, and stop orphaning the old file
  - `ca59ba9` refactor(dashboard): share one isUuid instead of two copies of the regex
  - `2da207e` docs(handoff): record the upload fixes and the isUuid dedup
- **The repo moved to `/Users/amrabujabal/Downloads/pitchvision`** (was
  `Downloads/football-ai`). Nothing inside it pinned the old path.
- **Verified at session close, all green:** **319 pytest** (was 309) / ruff clean /
  single alembic head **`b1d5f27ac903`** / `tsc --noEmit` clean / **65 vitest**
  (was 56).
- **Driven in a real browser**, API on 8001 with `REDIS_URL="memory://"`,
  dashboard under `TZ=UTC`: login → corner entry → save → upload with a 1280x720
  ffmpeg clip. `dev.db` ended at `1280|720` where it read `1920|1080` at
  creation. The rendered `/login` showed the new title, description and wordmark
  with zero occurrences of "football".
- **`dev.db` was left as found**, apart from the intended reseed: the test match
  and its uploaded file were deleted, the compat-test player row removed, and the
  two academy rows renamed to the new Canadian seed values. Backups at
  `$CLAUDE_JOB_DIR/tmp/dev.db.bak` and `dev.db.preframe`.
- **Gates run:** `/karpathy-check` twice (rename, upload fixes) and `/code-review`
  once (UAE removal). All findings fixed — see Failed Attempts.

## Active Files

New:

- `alembic/versions/b1d5f27ac903_drop_name_ar.py` — drops `name_ar` from both tables.
- `dashboard/lib/uuid.ts` + `uuid.test.ts` — the shared `isUuid`, kept pure for
  the same reason `lib/corners.ts` and `lib/half-time.ts` are.

Modified:

- `api/routers/matches.py` — `MAX_FRAME_DIM`, the two upload form fields, the
  previous-file cleanup, the loguru import.
- `dashboard/components/CalibratePicker.tsx` — sends the decoded frame size.
- `dashboard/components/Nav.tsx`, `dashboard/app/layout.tsx` — the wordmark and
  page titles.
- `dashboard/lib/proxy.ts`, `dashboard/app/login/page.tsx` — both now use the
  shared `isUuid`.
- `database/models.py`, `api/routers/players.py` — `name_ar` gone, `city`/`country`
  defaults changed.
- `tasks/pipeline.py` (Celery app name), `.env.example`, `CLAUDE.md`, `README.md`,
  `scripts/seed_dev.py`, and ten test files (fixture place names).

## Changes Made

Four pieces, each written up in full in its own section below:

1. **Rename to PitchVision** — the folder, the dashboard wordmark, page titles,
   the Celery app name, the example DB name. `CLAUDE.md:63` reserves "football"
   for internal references, so the copy says "soccer".
2. **UAE-era locale assumptions dropped** — `name_ar` off both tables and off
   `PlayerBase`, `city` default removed, `country` defaults to Canada, fixtures
   made Canadian.
3. **Upload records the real frame dimensions, and no longer orphans the previous
   file** — two corrections to `upload_video`, both about the file it was handed.
4. **One `isUuid` instead of two copies of the regex.**

## Failed Attempts

Kept because each was caught by something, and the something is the lesson.

1. **I asserted a performance claim I had not checked.** A comment said appending
   the small form fields before the file lets them "be parsed without waiting on
   a multi-gigabyte stream". Starlette's `MultiPartParser` consumes the whole body
   before the handler runs, so field order is functionally inert. The
   `/karpathy-check` review caught it. Removed from the code and from the write-up
   below.
2. **The filed fix for the duplicated UUID regex would not have worked.** The
   previous handoff said `login/page.tsx` was character-for-character
   `lib/proxy.ts`'s `isUuid` and implied importing it. `proxy.ts` pulls in
   `next/server` and `lib/session.ts`, and session.ts calls `cookies()` — the
   login page is a client component. The duplication was load-bearing. A filed
   item is a report of a symptom, not a design.
3. **I traced the frame-dims bug to the wrong place first.** The assumption was
   that wrong dims corrupt calibrated matches. They do not: `_fw`/`_fh` are read
   only in `to_pitch`'s `homography is None` branch. That is what moved the fix
   from `PUT /calibration` to `POST /upload-video`.
4. **An unrequested wording trim.** Fixing "UAE football academies" I also dropped
   "Advanced" from the description — not implied by a rename. Caught by
   `/karpathy-check`, restored.
5. **My own test comment confused two languages.** It claimed JavaScript's `$`
   matches before a trailing newline. That is Python's `re`; JavaScript's `$` is
   end-of-string. Checked in `node` rather than left as prose.
6. **`sqlite3` from the wrong working directory silently created an empty
   `dev.db`** in the scratch dir and reported success on a table that did not
   exist. The shell cwd persists between calls; `cd` to the repo root before
   touching `dev.db`.

## Rename to PitchVision — SHIPPED 2026-08-20 (`3b55d21`)

**The repo now lives at `/Users/amrabujabal/Downloads/pitchvision`** (was
`Downloads/football-ai`). Nothing inside the repo pinned the old path —
`config/settings.py` derives `PROJECT_ROOT` from `__file__` and `dev.db` is
relative to cwd — so the move was a plain `mv`. Two absolute paths in the
archived half-time plan doc were updated; `dashboard/.next` was deleted because
it bakes absolute paths.

The API, README, terraform and `package.json` already said PitchVision. The
holdouts were the dashboard wordmark (`Nav.tsx`, now `pitch` + blue `vision`),
the page title/template and description (`layout.tsx`), the Celery app name
(`tasks/pipeline.py:14`) and the example database name (`.env.example`). This
closes the gap filed at `docs/superpowers/specs/2026-08-16-corner-picker-design.md:202`.

- **Renaming the Celery app name is safe** because the task name is pinned
  explicitly on the next line (`name="tasks.pipeline.process_match"`). Celery
  only derives task names from the app's `main` string for tasks defined in
  `__main__`, and nothing reads `celery_app.main` for queue routing — grepped,
  not assumed. Queued tasks are not orphaned by the rename.
- **The description was wrong on two counts, not one.** It said "UAE football
  academies": the market is Canada (README), and CLAUDE.md:63 reserves
  "football" for internal/academic references — user-facing copy says "soccer".
- **Verified in the rendered page, not just `tsc`.** The dev server was started
  from the new path and `/login` fetched: `<title>`, the description meta and
  the wordmark all correct, and zero occurrences of "football" in the HTML. A
  folder move is exactly the kind of thing that survives type-checking and
  breaks the build, and this repo has a three-session history of that.

**The UAE era is gone too** (same session, second commit). `name_ar` is dropped
from both `academies` and `players` by migration `b1d5f27ac903` — the product is
English-only, and a column reserved for one script is a preference the schema
should not carry. `Academy.city` lost its `"Dubai"` default entirely (there is no
sensible universal one, and a wrong guess is worse than being asked) and
`country` now defaults to `"Canada"`, the home market. Seed and test fixtures use
Canadian placeholders.

- **No migration was needed for the defaults.** The initial migration declares
  `city`/`country` `nullable=False` with **no `server_default`** — the defaults
  were Python-side only, so removing them is a model change. `alembic check`
  confirms models and migrations stay in sync.
- **Dropping `name_ar` broke nothing, and that was the test.** All 309 tests
  passed unedited afterwards, which is the evidence that nothing read the column —
  it was written through `PlayerBase` and returned again, never used for search,
  display or matching.
- **The upgrade and the downgrade were both run against `dev.db`**, not just
  written. Round-trips cleanly; `name_ar` comes back nullable because the dropped
  values are unrecoverable.
- **`PlayerBase` losing `name_ar` is a wire-contract change**, verified live: a
  client that still sends it gets **201 with the field ignored**, not a 422 —
  pydantic's default `extra="ignore"`, the same trade-off already made for
  `academy_id`. Checked against a running API, not inferred.

## Frame dimensions are sent from the picker — SHIPPED 2026-08-20

Next-steps item 2 from the previous handoff, closed. `POST /matches/` runs before
a video exists, so it could only default to 1920x1080 and a coach could not be
expected to know better. `CalibratePicker` decodes the chosen file in the browser
to show a still for corner-picking — it has displayed "1280 x 720 source pixels"
on screen the whole time — and never sent it.

`POST /{match_id}/upload-video` now takes optional `frame_width` /
`frame_height` form fields, and the picker appends them.

- **Upload, not calibration, is the right place.** The dimensions describe _this
  file_, and upload is the only moment the server sees it. The API's upload
  endpoint has no calibration gate (only the dashboard UI does), so a curl caller
  can upload uncalibrated — and that is precisely the path where wrong dims do
  damage.
- **Wrong dims corrupt the _uncalibrated_ path, not the calibrated one.** Worth
  knowing before someone "fixes" this again: `_fw`/`_fh` are read in exactly one
  place, `run_pipeline.to_pitch`'s `homography is None` branch
  (`pixel / _fw * pitch_length`). With corners set, `to_pitch` uses the
  homography, which carries true pixel space and needs no dims at all. So a
  1280-wide video recorded as 1920 puts every player at two thirds of their true
  distance from the goal line — silently — but only without a homography.
- **The write must happen before `_enqueue_processing`**, which commits and then
  passes the dimensions to the worker _by value_. Writing after would leave the
  run using the guess while the row claimed otherwise.
- **`gt=0` is load-bearing, the ceiling is defensive.** `frame_width=0` reaches
  `pixel / 0` in `to_pitch` and `metrics/pressing.py` and raises deep in the
  worker, long after the request returned 202. `MAX_FRAME_DIM = 16_384` is past
  8K so no real camera reaches it.
- **Optional on purpose** — omitting the fields leaves whatever `POST /matches/`
  recorded, so `run_pipeline` and existing callers keep working rather than
  starting to get 422s.
- **The Next proxy needed no change**: it streams the multipart body straight
  through, so extra fields pass with the boundary intact. (An earlier comment
  claimed appending the fields before the file lets them be parsed without
  waiting on the stream — that is wrong and the review caught it. Starlette's
  `MultiPartParser` consumes the whole body before the handler runs, so field
  order is functionally inert. The order is kept only as convention.)
- **The tests were mutation-checked, not just run.** Deleting the two assignment
  lines makes exactly the two discriminating tests fail with `assert 1920 == 1280`
  — the wrong-scale symptom itself. A test that reads the dims back off the
  fixture would have passed either way, which is why they use literals.
- **Driven in a real browser end to end**: a 1280x720 clip generated with ffmpeg,
  through login → corner entry → save → upload, ending with `dev.db` reading
  `1280|720` where it read `1920|1080` at creation. The stored corners (max
  1200x650) now sit inside the recorded frame — the mismatch that forced last
  session's `dev.db` cleanup cannot happen from the dashboard any more.

**Not closed:** nothing validates stored `pitch_corners` against the frame dims,
so a curl caller can still pair corners from one resolution with dims from
another. Cross-request validation was judged speculative — the dashboard can no
longer produce that state. Filed as next-steps item 2.

## Re-upload no longer orphans the old video — SHIPPED 2026-08-20

Previous next-steps item 5. The stored name is `{match_id}{suffix}`, so uploading
a `.mov` and then an `.mp4` for the same match wrote a second file and left the
first on disk for good — only the newest is ever read back.

`upload_video` now resolves the previous file before writing and unlinks it
after, when the name changed.

- **The order is load-bearing in both directions.** Resolved _before_ the write,
  because the write is what makes it stale. Unlinked _after_, because deleting
  first and then failing the write would leave the match with no video at all
  rather than the previous one.
- **The same-suffix case is the dangerous one.** Re-uploading `.mp4` over `.mp4`
  overwrites in place, so "the previous file" and "the file just written" are the
  same path — an unguarded unlink deletes the upload that just succeeded.
  `previous != dest` is what prevents it, and
  `test_reuploading_the_same_container_keeps_the_new_file` fails without it.
- **Resolved through `find_raw_video`, not built here**, so the existing `.name`
  sanitising applies to a stored value this module did not necessarily write.
- **A failed unlink logs and continues.** Leaking a file is exactly the behaviour
  being replaced, so it is not worth failing an upload that already succeeded and
  is queued.
- **Mutation-checked:** disabling the delete fails
  `test_the_previous_container_is_removed`; dropping the `!= dest` guard fails
  `test_reuploading_the_same_container_keeps_the_new_file`. Two distinct
  mutations, two distinct tests.

## The duplicated UUID regex is deduped — SHIPPED 2026-08-20

Previous next-steps item 8, but **not** the way it was filed. The note said
`login/page.tsx` was character-for-character `lib/proxy.ts`'s exported `isUuid`
and implied importing it. That does not work: `proxy.ts` imports `next/server`
and `lib/session.ts`, and `session.ts` calls `cookies()` from `next/headers`.
The login page is a client component, so the import would pull server-only code
into the browser bundle. The duplication was load-bearing, not laziness.

New `dashboard/lib/uuid.ts` holds the regex and `isUuid`, with no imports at all
— the same reason `lib/corners.ts` and `lib/half-time.ts` are pure. `proxy.ts`
re-exports it so the three route handlers importing from there are untouched.
9 vitest cases.

- **JavaScript's `$` is genuinely end-of-string.** Checked rather than assumed,
  because Python's `re` `$` matches _before_ a trailing newline and would need
  `\Z` — a port of this check to the API side would be subtly weaker. Both the
  trailing-newline and embedded-traversal cases are pinned.

## Next steps

1. **`run()`'s stage-5b wiring has no test.** `half_time_frame()` is extracted and
   covered, but the composition inside `scripts/run_pipeline.py::run` — computing
   `split`, the two warning branches, and threading `half_time_frame=split` into
   _both_ `detect_formation` calls — is verified by reading, not by anything that
   runs. Nothing in `tests/` imports `run` at all; only its pure helpers. Deliberate:
   `run()` lazily imports `detection.detector`, `jersey_ocr` and `tracking.tracker`
   inside its body so the module stays importable without torch, so a test reaching
   the wiring would have to mock the detector, tracker, OCR, video decode and DB
   session to assert two kwargs — it would mostly assert its own mocks. Named here so
   it is not mistaken for verified. Same family as item 6 below.

2. **Corners are never checked against the frame dimensions.** The dashboard can
   no longer pair them wrongly (the picker sends both from the same decoded
   file), but `PUT /calibration` and `POST /upload-video` are separate requests,
   so a curl caller can still store corners measured at one resolution against
   dims recorded at another — the exact state that forced last session's `dev.db`
   cleanup. `corner_problem()` cannot catch it; it never sees the dims. Left open
   deliberately: cross-request validation for a state the UI cannot produce.
3. **Zoned serialisation on the API side.** Naive `DateTime` columns serialise with no
   zone. ~15 lines of pydantic serialisers, no migration, would make `isoInstant`
   dead. Visible wire-format change, which is why it is not a drive-by.
4. **`DISPLAY_ZONE` is one global guess** (`dashboard/lib/dates.ts`). A `timezone`
   column on `Academy` is the upgrade; an env var is the cheap stopgap.
5. **`tasks/pipeline.py::process_match` has no test coverage at all.**
6. **A third copy of the fetch/busy/error pattern** across `CalibratePicker.save()`,
   `.upload()` and `ReprocessButton`. A `useApiAction` hook would fold all three.
7. **`Intl.DateTimeFormat` is rebuilt per call** in `dates.ts` (~164µs vs 1.6µs
   reusing one). Measurement already done; re-add the cache only if a page is slow.
8. **Cloud Run returned 503** on `/health` (2026-08-16). Still untouched.
9. Backlog: half-time per-half formation output if a coach ever asks; email/slug on
   `Academy` so login is not a raw UUID; the empty `api/routers/academies.py`; Re-ID
   across occlusions (needs torch); pgvector.
## Earlier on 2026-08-20 — half-time end swap (`dd0f1d3`)

Summarised; the full write-up is in git history and in the design doc and plan
under `docs/superpowers/`.

`home_defends_end` described the whole video, so a full match had one half's
positions mirrored along the pitch length axis before averaging into the
formation. `Match.half_time_seconds` is a coach-supplied mark, **never inferred**
— a wrong split re-creates the exact mirror it removes. 13 commits, gated by a
task review each, two scoped re-reviews, a whole-branch review and
`/karpathy-check`.

- **Orientation had to become absolute, not a flip about the deepest observed
  player.** `s.max() - s` is fine for one direction because every downstream read
  is a difference, but two halves flipped about two different anchors are not on a
  common scale. `L - s` differs by a constant, which is why all 19 pre-existing
  formation tests passed unedited — that was the check on the reasoning.
- **`frame_history` is index-aligned with `pitch_history`**, so attributing an
  observation to a half is a filter, not tracker surgery.
- **A `mm:ss` field must accept minutes > 59.** Half-time in a full-match video is
  normally past minute 59. `tsc` and unit tests both passed; only driving the real
  page found it.
- **Client and server must share a bound.** `le=86_400` sits in both
  `api/routers/matches.py` and `dashboard/lib/half-time.ts`.
- **Known gap, deliberate:** `scripts/run_pipeline.py::run`'s stage-5b wiring has
  no test — see next-steps item 1.

## How to resume / verify

- The repo is at `/Users/amrabujabal/Downloads/pitchvision`; work is on `main`.
- What CI runs: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → 319
- Lint: `/usr/local/bin/python3.11 -m ruff check .` → clean
- Migrations: `/usr/local/bin/python3.11 -m alembic heads` → single, `b1d5f27ac903`
- Dashboard: `cd dashboard && ./node_modules/.bin/tsc --noEmit && npm test` → 65
- The SDD workspace for this plan has been deleted; every finding it tracked was
  fixed and merged, so the git history is the record now. The design doc and plan
  remain under `docs/superpowers/`.
- To drive the picker: API `PYTHONPATH=. REDIS_URL="memory://" python3.11 -m uvicorn
api.main:app --port 8001`, dashboard `cd dashboard && TZ=UTC npm run dev`.
  Test academy `7ceca9ce-9c63-4330-8053-d658408c9fc6` / `devpassword`.
- **The picker needs a decodable video** to extract a frame. `data/raw/`'s only file
  is a 5-byte stub. Make one: `ffmpeg -f lavfi -i testsrc=size=1280x720:rate=25 -t 3
-pix_fmt yuv420p out.mp4`. Playwright MCP can only read files under
  `/Users/amrabujabal` — put it there, not in the scratchpad.
- Clicking canvas corners through Playwright is unreliable; the picker's
  "Enter coordinates instead" panel has `#corner-N-x` / `#corner-N-y` inputs. Use those.
- **Those inputs are inside a collapsed `<details>`**, so `fill()` times out with
  "element is not visible" even though the locator resolves. Open it first:
  `page.evaluate(() => document.querySelectorAll('details').forEach(d => d.open = true))`.
- **The file input is `sr-only` behind its label**, so clicking it fails with
  "span intercepts pointer events". Set the file directly instead:
  `page.setInputFiles('#video-file', '/Users/amrabujabal/<clip>.mp4')`.
- Playwright MCP's `browser_run_code_unsafe` takes an `async (page) => {...}`
  arrow function, not bare statements — bare `await page...` is a SyntaxError.
- `dev.db` stores match ids **without dashes**; a `WHERE id='<dashed>'` updates zero
  rows and reports success.
