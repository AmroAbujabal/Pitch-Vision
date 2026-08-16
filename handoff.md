# PitchVision — Handoff

_Last updated: 2026-08-15_ — **player routes are now tenant-scoped, closing the
last known cross-academy hole. Formation detection still live but still has no
dashboard screen.**

## Goal

Close the open item carried over from the previous session: `api/routers/players.py`
loaded records by id with no academy check, the same bug class fixed on the match
routes on 2026-08-14. Give players the equivalent `get_scoped_player` dependency.

## Current State

- **Verified 2026-08-15:**
  - CI scope `pytest tests/test_api/ tests/test_db/ -q` → **154 pass** (was 145)
  - Wider `pytest tests/ -q --ignore=tests/test_detection` → **254 pass** (was 245)
  - `ruff check .` → clean; `cd dashboard && ./node_modules/.bin/tsc --noEmit` → clean
- Every new test was checked against the code it guards, not just run green: the
  seven tenant-isolation tests against the _old_ router (`git stash` on
  `api/routers/players.py` alone — all seven fail, the ten pre-existing ones still
  pass), and the traversal test with the `isalpha` guard deleted. None are vacuous.
- `db.get(Player, ...)` and `db.get(Match, ...)` now each appear exactly once in
  `api/`, both inside a scoping dependency.
- **Still true from last session:** nobody can use formation detection yet — the
  calibration endpoint has no dashboard screen, so it needs a hand-written `PUT`.
- **Local env unchanged:** `alembic` + `opencv-python-headless` are installed for
  python3.11 but absent from `requirements-ci.txt`, so `tests/test_metrics/`,
  `tests/test_utils/` and `tests/test_pipeline/` — 100 of the 254 — still don't
  run in CI.

## Active Files

- `api/routers/players.py` — new `get_scoped_player`; all four read routes take
  `player: Player = Depends(get_scoped_player)` instead of a raw `player_id: UUID`;
  `PlayerCreate` lost its `academy_id`; `create_player` takes it from the token.
- `tests/test_api/test_tenant_isolation.py` — new `foreign_player` fixture,
  `TestForeignPlayerIsInvisible`, `TestCreatePlayerIsOwnedByTheCaller`.
- `tests/test_api/test_prediction.py`, `tests/test_api/test_player_profile.py` —
  fixtures point the fake token at the academy they create.
- `api/routers/players.py` `_load_model` — free-text `position` no longer shapes
  the pickle path.
- `tests/test_api/conftest.py` — `auth_academy` docstring warns that only one
  academy-creating fixture may be used per test.
- `CLAUDE.md` / `README.md` — scoping now covers players, the `POST /players/`
  contract change is documented, test counts 145→154 and 245→254.

## Changes Made

1. **`get_scoped_player`** mirrors `get_scoped_match` exactly: load, compare
   `academy_id` against the token, 404 (not 403) on mismatch so player ids can't
   be enumerated. `/stats`, `/profile`, `/heatmap` and `/prediction` all depend on
   it. `/heatmap` previously loaded no player at all — it queried
   `PlayerMatchStats` by `player_id` + `match_id` directly.
2. **`create_player` no longer takes `academy_id` from the body.** Ownership comes
   from the bearer token. Pydantic's default `extra="ignore"` is kept deliberately,
   matching `MatchCreate`: an old client that still sends the field gets it dropped
   rather than a 422. No in-repo caller sends it — the dashboard never calls
   `POST /players/`.
3. **Four test fixtures were never making an authorised request.** They each
   created their own `Academy` without pointing `auth_academy` at it, exactly the
   misalignment that let the match-route bug survive its own test suite. Twenty
   tests went red the moment scoping landed, which is the suite working as
   intended. Fixed by setting `auth_academy["id"]` after the flush, the pattern
   `seeded` already used.

4. **`_load_model` no longer lets `position` shape the pickle path** — two lines,
   out of the session's stated scope, taken because both reviews flagged it and
   the sink is one function every caller routes through. `position` is free text
   from player creation and the file it names is `pickle.load`ed; non-alphabetic
   positions now take the shared model.

   Worth recording precisely, because the first description of this was too
   generous to the attacker. `position="../.."` does **not** escape: the filename
   is `f"prediction_{position.upper()}.pkl"`, so `..` becomes the literal
   component `prediction_..`. The escaping form needs a leading slash —
   `"/../../x"` yields components `prediction_`, `..`, `..`, `X.pkl` — and POSIX
   only walks `..` through directories that exist, so it also needs a real
   `prediction_` directory under `data/models/`, which a caller can't create.
   It was hardening, not a live hole. `tests/test_api/test_prediction.py::
TestLoadModelPathIsNotCallerControlled` builds that directory so the test
   actually catches an escape; verified failing with the guard removed.

   Both reviews proposed a `Literal[...]` on `PlayerBase.position` instead. That
   would be wrong: `database/repository.py:219` writes `position="unknown"` and
   real positions are free-form codes (`CM`, `ST`, `LW`), so a `Literal` of
   GK/DEF/MID/FWD would reject what the pipeline itself produces.

## Failed Attempts

- Nothing failed. One thing not to re-litigate: `/heatmap` and `/stats` still take
  a caller-supplied `match_id` and don't scope it. That's fine — every row they
  return is already filtered to an academy-scoped player, so a foreign `match_id`
  simply matches nothing. Adding a second scoping dependency would be redundant.

## Next steps

1. **Corner-picker UI** — now the highest-value item by a distance. Click four
   corners on a still, plus an explicit "which goal does the home team defend?"
   toggle ("low" = goal on the left of frame). Without it nothing from the
   formation session is reachable. Pairs with **re-processing**: upload starts the
   pipeline immediately, so calibration saved afterwards only applies next run.
2. **Add opencv to `requirements-ci.txt`** so `tests/test_metrics/`,
   `tests/test_utils/` and `tests/test_pipeline/` run in CI — 100 tests are
   currently local-only. Cheapest item on the list.
3. **Half-time end swap** — `home_defends_end` describes the whole video, so a
   full-match upload mirrors one half's formation. Needs a per-half split.
4. Backlog: Re-ID across occlusions (TransReID/OSNet, needs torch); pgvector
   player search; unify the three copies of the linear pixel→metre fallback
   (`run_pipeline.to_pitch`, `pressing.py:90`, `pitch_control.py:174`).

## How to resume / verify

- `cd /Users/amrabujabal/Downloads/football-ai`
- CI scope: `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q` → 154 pass
- Wider: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → 254 pass
- Lint: `/usr/local/bin/python3.11 -m ruff check .` → clean
- Dashboard: `cd dashboard && ./node_modules/.bin/tsc --noEmit` → clean
- `tests/test_detection/` needs torch/ultralytics — not installed here.
- API live: `https://pitchvision-api-4hxfthgkna-uc.a.run.app/health`
