# PitchVision — Handoff

_Last updated: 2026-08-19_ — **two changes shipped.** Re-processing after
calibration (the top item carried over from 2026-08-18), then
`Match.video_path`, which had been dead schema since the initial migration.
A coach who uploaded before calibrating is no longer stuck with `"unknown"`
formations, and nothing guesses a video's file name any more.

## Goal

Build next-steps item 1 from the previous handoff: an explicit
`POST /api/v1/matches/{id}/reprocess` plus a "Re-run analysis" button, so
calibration saved after an upload can actually take effect. The design was
decided last session and was not re-litigated.

## Current State

- **Verified 2026-08-19, all green:**
  - What CI runs, `pytest tests/ -q --ignore=tests/test_detection` → **273 pass** (was 257)
  - API-only subset `pytest tests/test_api/ tests/test_db/ -q` → **173 pass** (was 157)
  - `ruff check .` → clean
  - `cd dashboard && ./node_modules/.bin/tsc --noEmit` → clean
  - `cd dashboard && npm test` → **16 pass** (vitest, unchanged)
- **Driven end to end in a real browser** against a real API on port 8001:
  the amber banner renders its new "Re-run analysis" button → click → the DB
  flips to `processing` → `router.refresh()` re-renders the server page, so the
  status badge updates and the banner disappears without a reload.
- **Both failure paths driven live too**, not just unit-tested:
  - No video on disk → 404, and the API's `detail` string surfaces in the
    button's `role="alert"` text ("No source video for this match. Upload it
    again."). The button re-enables so the coach can retry.
  - Broker down → 503 and the match reads `failed`, confirmed by DB readback.
    This machine has no Redis, so that path is the default here; the 202 happy
    path was verified by starting the API with `REDIS_URL=memory://`.
- **Reviews:** `/simplify` (4 agents), `/code-review high`, `/security-review`
  and `/karpathy-check` all run. Security found nothing. Code review found one
  HIGH that this change created (see Changes Made item 5) plus four in older
  code, now next-steps items 5-7. Karpathy passed with two warnings, both fixed.
- **The re-run work is committed AND pushed** — `46532cb`, `origin/main` is
  current with it. The `video_path` change that follows is a second commit.

## Active Files

New:

- `dashboard/components/ReprocessButton.tsx` — client button; POSTs to the
  proxy, then `router.refresh()`. Renders the server's error string.
- `dashboard/app/api/matches/[id]/reprocess/route.ts` — the proxy, same
  `isUuid` → `badId` → `forward` shape as its siblings.

Modified:

- `api/routers/matches.py` — `reprocess_match`, plus `_enqueue_processing`
  factored out of `upload_video` so both callers share the broker-failure
  rollback instead of copying it.
- `config/settings.py` — `find_raw_video()`, see below.
- `tasks/pipeline.py` — now calls `find_raw_video()` instead of its own copy.
- `dashboard/app/matches/[id]/page.tsx` — the `needsCalibration` banner is now
  a `<div>` wrapping the copy plus the button. Its text changed from "upload
  the video again" to "re-run the analysis", which is the point of the change.
- `database/repository.py` — `save_pipeline_results` clears the match's stats
  rows before writing, see Changes Made item 5.
- `tests/test_api/test_upload.py` — `TestReprocess`, 6 tests.
- `tests/test_db/test_repository.py` — `TestReRunReplacesStatsRatherThanAppending`,
  3 tests, all checked non-vacuously against the pre-fix code.
- `tests/test_api/test_tenant_isolation.py` — `test_reprocess_returns_404`.
- `tests/test_api/test_upload.py` — `TestUploadRecordsWhereTheVideoWent`, 6 tests
  covering the recorded name, the NULL-column fallback, the stale-name 404 and
  the traversal guard.
- `CLAUDE.md` — test counts 257→267 / 157→167; the re-processing and
  corner-picker backlog items are done and removed.

## Changes Made

1. **`POST /matches/{id}/reprocess`**, behind `get_scoped_match` like every
   other per-match route. 404 when no video is on disk, otherwise sets
   `processing_status = "processing"` and enqueues. Built exactly to the spec
   decided last session — `PUT /calibration` still does **not** re-enqueue on
   its own, because a save button that silently starts a long job is a
   surprising side effect.
2. **The enqueue-and-roll-back block is now shared.** `_enqueue_processing`
   holds the "commit processing, enqueue, mark failed + 503 if the broker is
   down" unit that `upload_video` grew on 2026-08-18. Copying it into the new
   endpoint was the alternative and was explicitly rejected in the spec.
3. **`find_raw_video()` moved to `config/settings.py`** — a `/simplify` finding.
   `tasks/pipeline.py` already had a byte-for-byte copy of "loop
   `ALLOWED_VIDEO_EXTENSIONS`, build `raw_dir / f"{id}{ext}"`, return the first
   that exists". Writing a second copy in the router would have made three
   independent encodings of the storage convention (the write side in
   `upload_video` is the third). It now lives once, next to the two constants
   it is built from, and the pipeline imports it.
4. **The shared 503 string was reworded** from "The video was saved" to "The
   video is on disk" — accurate for the upload caller, wrong for the re-run
   caller once the block became shared.
5. **`save_pipeline_results` now deletes a match's stats rows before writing
   them** — the HIGH finding from code review, and a bug this change created.
   That function only ever appended, which was harmless while a match was only
   ever processed once. Making a re-run the intended flow meant the first coach
   to click the button would get two `PlayerMatchStats` rows per player:
   `player_count` doubled, every team total doubled, and the player table listed
   everyone twice. Fixed in the one shared write funnel rather than in the
   endpoint, so a manual `run_pipeline.py` re-run is covered too. Latent until
   the `run(...)` TODO in `tasks/pipeline.py` is uncommented, but planted by
   this change. `DevelopmentScore` needed no equivalent — it is keyed on
   (player, week) and already upserts, and it references players, not stats rows.
6. **`find_raw_video` iterates `sorted(ALLOWED_VIDEO_EXTENSIONS)`.** A match can
   legitimately have both a `.mov` and an `.mp4` if it was uploaded twice, and
   Python randomises string hashing per process — so an unsorted frozenset scan
   let the API process and the Celery worker pick different files.
7. **`POST /reprocess` 409s when the match is already `processing`.** Two
   concurrent runs race to write the same match's stats. Note this also blocks a
   match wedged at `processing` by a worker that died mid-run; nothing rolls that
   back today, which is worth a follow-up.
8. **`test_reprocess_returns_404` added to `test_tenant_isolation.py`** — that
   file keeps one explicit test per write route and the new one was missing,
   flagged by karpathy-check.

## Second change — `Match.video_path`

`Match.video_path` existed on the model and in the initial Alembic migration but
was **never assigned anywhere**. Every reader instead reconstructed the file name
from the match id by testing each allowed extension — the convention was encoded
in three places (the write in `upload_video`, the read in `tasks/pipeline.py`,
and the read the re-run endpoint needed). Raised by the altitude review during
the first change and deliberately deferred out of it.

- `upload_video` builds `name = f"{match.id}{suffix}"`, writes `raw_dir/name`,
  and stores `name` on the match. It is a **bare file name, not a path** —
  `raw_dir` differs between this laptop and Cloud Run, so a stored absolute path
  would not survive the trip, and CLAUDE.md forbids them anyway.
- `find_raw_video(match_id, stored_name=None)` resolves the recorded name when
  there is one. **A recorded name whose file is gone returns None rather than
  falling through to guessing** — otherwise a stale entry could resurrect an
  unrelated leftover file for the same match.
- The extension scan survives only for rows uploaded before the column was
  populated, where it is NULL. Delete it once no such rows remain.
- `tasks/pipeline.py` now loads the `Match` **before** the video lookup, which it
  previously did after, so it can pass the recorded name.
- `find_raw_video` applies `Path(stored_name).name`. Only `upload_video` writes
  the column today, from a UUID and an allowlisted suffix, but that is a
  convention held in another module; `.name` closes it structurally so a future
  writer (an import, a manual DB fixup) cannot make it a traversal. Costs
  nothing, since the value is supposed to be a bare name.

**This also properly fixes what the sorted-frozenset change only papered over.**
Upload twice with different containers and both files remain on disk; the scan
would pick `.mov` over `.mp4` on sort order regardless of which was newer. The
recorded name is simply correct. (The superseded file is still left on disk —
small disk leak, worth a follow-up.)

Verified live, not just in tests: a real upload through the API stored
`b4ca2e77-...-mp4` from a file sent as `touchline.MP4` (suffix lowercased),
re-run then resolved it (202), a re-run with the file renamed out from under the
record returned 404 rather than finding the leftover, and a second call while
`processing` returned 409. All six new tests plus the traversal test were checked
non-vacuously against the pre-fix code.

## Failed Attempts

- Nothing in the feature itself misbehaved. Unusually for this repo, the
  browser drive confirmed the code rather than finding bugs in it — the risky
  parts here (canvas, media elements, sparse arrays) are all in the picker,
  not in a button.
- **Local-harness friction worth knowing, not code faults:**
  - A backgrounded `&` process dies when the Bash tool call returns. Use the
    tool's own background mode for uvicorn / `npm run dev`, or the server is
    gone by the next command.
  - `curl` against a just-started Next dev server needs a generous timeout —
    the first request compiles the route and a 3s timeout reports a false
    "down" on a server that is fine.
  - The Playwright MCP browser holds a profile lock; a stale one has to be
    killed before `browser_navigate` works.
  - **`dev.db` stores match ids without dashes.** A `WHERE id = '<uuid>'` with
    dashes silently updates zero rows and reports success.
  - The dashboard's cwd persists across Bash calls — a stray `cd dashboard`
    makes later `sqlite3 dev.db` calls open an empty database in the wrong
    directory and report "no such table".

## Next steps

1. **Half-time end swap** — `home_defends_end` describes the whole video, so a
   full match mirrors one half. Needs a per-half split.
2. **Frame dimensions are never sent.** `CalibratePicker` knows the real
   `frame.width/height` but `POST /matches/` takes the 1920x1080 default and
   `PUT /calibration` has no field to correct it. Only bites when the
   homography fails and the linear pixel-to-metre fallback runs, but it is a
   silent wrong answer when it does.
3. **Orphaned video files.** `upload_video` never deletes a previously uploaded
   file for the same match, so uploading a `.mov` and then an `.mp4` leaves the
   `.mov` on disk forever. Harmless for correctness now that `video_path` names
   the right one, but it leaks disk. Delete the superseded file on upload, or
   sweep `raw_dir` for names no `Match.video_path` references.
4. **`tasks/pipeline.py::process_match` has no test coverage at all** — nothing
   in `tests/` executes the task body; the only hits are
   `patch("api.routers.matches.process_match")`. The `video_path` change moved
   `db.get` across that function's early-return boundary, which was traced by
   hand and is sound, but is exactly the kind of edit that wants a regression
   check. One test mocking `SessionLocal`/`find_raw_video` over the
   `match is None` and stale-`video_path` cases would close it.
5. **A third copy of the fetch/busy/error pattern** now exists across
   `CalibratePicker.save()`, `CalibratePicker.upload()` and `ReprocessButton`,
   including the same "Could not reach the dashboard server." fallback string.
   A `useApiAction` hook in `dashboard/lib` would fold all three. Skipped this
   session because it means editing the picker, which is code that took a whole
   session to get right in a browser and is not broken.
6. **Open redirect in `dashboard/app/login/page.tsx:19`** — code review, MEDIUM,
   pre-existing. `safeNext` rejects `//` but not `/\`, and the WHATWG URL parser
   treats a backslash as a slash for special schemes, so
   `?next=/\evil.com` sends a signed-in coach off-site. Reject any second
   character in `[/\\]`, or compare origins via `new URL(value, location.origin)`.
7. **Reverse-winding corners are accepted** (`dashboard/lib/corners.ts:83`) —
   code review, MEDIUM, pre-existing. The guard is
   `positive !== 0 && positive !== 4`, so clicking TL→BL→BR→TR passes as a valid
   convex quad and mirrors the whole pitch, reversing every formation. Should be
   `positive !== 4`. `corners.test.ts` only covers the bowtie case.
8. **Match date can shift a day** (`dashboard/app/matches/new/page.tsx:32`) —
   code review, LOW, pre-existing. `new Date("2026-08-19")` parses as UTC
   midnight and the card renders in local time, so a Canadian coach sees 18 Aug.
9. **Cloud Run returned 503** on `/health` (2026-08-16). Still untouched.
10. Backlog: an email or slug column on `Academy` so login is not a raw UUID;
   `api/routers/academies.py` is still an empty router with no way to create an
   academy or set a password; Re-ID across occlusions (needs torch); pgvector;
   unify the three copies of the linear pixel→metre fallback
   (`run_pipeline.to_pitch`, `pressing.py:90`, `pitch_control.py:174`).

## How to resume / verify

- `cd /Users/amrabujabal/Downloads/football-ai`
- What CI runs: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → 262 pass
- Lint: `/usr/local/bin/python3.11 -m ruff check .` → clean
- Dashboard: `cd dashboard && ./node_modules/.bin/tsc --noEmit && npm test`
- Seed a login: `SEED_PASSWORD=devpassword PYTHONPATH=. python3.11 scripts/seed_dev.py`
  (prints the academy id to sign in with). Test academy
  `7ceca9ce-9c63-4330-8053-d658408c9fc6` / `devpassword` already exists in `dev.db`.
- Run it: `PYTHONPATH=. python3.11 -m uvicorn api.main:app --port 8001` and
  `cd dashboard && npm run dev`. `.env.local` points at **8001**, not 8000.
- **To exercise the 202 path without Redis**, start the API with
  `REDIS_URL="memory://"` — `delay()` then succeeds with no worker attached,
  which is enough to prove the endpoint enqueues. Without it every enqueue
  takes the 503 branch on this machine.
- To make the re-run banner appear, a match needs `processing_status='done'`
  **and** a formation of the literal string `'unknown'` (not NULL), plus a file
  at `data/raw/{match-id-with-dashes}.mp4`.
- The pipeline itself still cannot run locally without torch.
