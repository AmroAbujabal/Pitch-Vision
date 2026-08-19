# Pitch calibration corner-picker + dashboard auth

_Design doc. Written 2026-08-16._

## Problem

`PUT /api/v1/matches/{id}/calibration` has existed since 2026-08-13 and nothing
in the dashboard calls it. Formation detection is live end to end behind that
endpoint, so today a coach can only reach it with a hand-written `PUT`. Until a
screen sets `pitch_corners` and `home_defends_end`, every formation comes back
`"unknown"` and every distance falls back to a linear pixel-to-metre stretch.

Two things block the screen, and neither was visible from the handoff:

1. **The dashboard cannot authenticate.** `dashboard/lib/api.ts` sends no
   `Authorization` header, but every match and player router is
   `APIRouter(dependencies=[Depends(get_current_academy_id)])`. Verified:
   `GET /api/v1/matches/` without a token returns 401. There is no login page,
   no token storage, and no mutating call anywhere in the dashboard.
2. **Nothing serves a still frame.** `upload_video` writes to
   `settings.raw_dir / f"{match.id}{suffix}"` and no endpoint reads it back.

## Scope

In: a login flow, a corner-picker screen, a minimal create-match form, and the
seed-script change that makes any of it testable.

Out: re-processing an already-uploaded match after calibration (the pipeline
still starts on upload); the half-time end swap; the Cloud Run 503; replacing
the academy UUID with a human username.

## Approach

### Still frames come from the browser, not the server

The coach picks the video file locally. An offscreen `<video>` fed by
`URL.createObjectURL(file)` seeks to a frame, and that frame is drawn to a
canvas with `drawImage`. No upload, no backend work, and the frame is available
_before_ the pipeline starts, which is the only ordering that works.

Two server-side alternatives were rejected:

- `GET /matches/{id}/frame` extracting with opencv. `requirements-ci.txt`
  deliberately excludes opencv to keep the API image slim, and the endpoint
  could only run after upload, which is after processing has already started.
- A pipeline-generated thumbnail. Circular: it only exists after the run that
  needed the calibration.

Clicks are converted with `getBoundingClientRect()` and scaled by
`video.videoWidth / rect.width`, so stored corners are in true video pixel
space regardless of how large the canvas renders. This is the one piece of
logic that fails silently when wrong, so it lives in a pure module with tests.

### Auth is a server-side cookie, not a client-held token

Existing pages are React Server Components that fetch directly. A token in
`localStorage` would force them all to become client components. Instead:

- `app/api/auth/login/route.ts` posts the form-encoded credentials to
  `/api/v1/auth/token` and stores the JWT in a `pv_token` cookie: `httpOnly`,
  `sameSite=lax`, `secure` outside development, `maxAge` from
  `access_token_expire_minutes`. The token never reaches client JS.
- `lib/api.ts` reads the cookie through `cookies()` from `next/headers` and
  sets the `Authorization` header. A 401 throws `UnauthorizedError` so pages
  redirect to `/login` instead of rendering "API unreachable".
- `middleware.ts` redirects to `/login` when the cookie is absent. UX only; the
  API's own 401 remains the real enforcement.

Because the cookie is `httpOnly`, the client-side picker cannot call FastAPI
directly. Mutations proxy through Next route handlers that read the cookie
server-side. The upload handler forwards `req.body` as a stream rather than
buffering a multi-gigabyte file.

`NEXT_PUBLIC_ACADEMY_ID` is deleted. The token carries the academy, and
`list_matches` ignores the query parameter it was feeding.

## Components

| File                                                  | Responsibility                                                          |
| ----------------------------------------------------- | ----------------------------------------------------------------------- |
| `dashboard/lib/corners.ts`                            | Pure: canvas point to video pixel, corner-order labels, quad validation |
| `dashboard/lib/api.ts`                                | Adds the bearer header from the cookie; `UnauthorizedError`             |
| `dashboard/lib/session.ts`                            | Cookie name, maxAge, read/write helpers                                 |
| `dashboard/middleware.ts`                             | Redirect unauthenticated page requests to `/login`                      |
| `dashboard/app/login/page.tsx`                        | Credentials form                                                        |
| `dashboard/app/api/auth/login/route.ts`               | Token exchange, sets the cookie                                         |
| `dashboard/app/api/auth/logout/route.ts`              | Clears the cookie                                                       |
| `dashboard/app/matches/new/page.tsx`                  | Create-match form                                                       |
| `dashboard/app/api/matches/route.ts`                  | Proxies `POST /matches/`                                                |
| `dashboard/app/matches/[id]/calibrate/page.tsx`       | Server shell                                                            |
| `dashboard/components/CalibratePicker.tsx`            | The picker (client)                                                     |
| `dashboard/app/api/matches/[id]/calibration/route.ts` | Proxies the `PUT`                                                       |
| `dashboard/app/api/matches/[id]/upload/route.ts`      | Streams the video through                                               |
| `scripts/seed_dev.py`                                 | Sets a password so login is testable                                    |

No API, model, migration, or pipeline changes.

## Visual design

The dashboard already has a design system in `dashboard/app/globals.css`:
`--color-primary #1E40AF`, `--card-radius 10px`, Fira Sans for text and Fira
Code for numbers, and the `.card` / `.kpi-label` / `.section-title` /
`.badge-*` component classes. New screens use those tokens and add none.

`taste-skill` was consulted and self-excludes: its Section 13 lists dashboards
and multi-step forms as out of scope. Its stack-agnostic rules still apply and
are folded in below. `ui-ux-pro-max` supplied the form and accessibility rules.

- **Icons:** `lucide-react`, already a dependency. One family, consistent
  stroke width.
- **Theme:** light only, matching the rest of the app. `globals.css` defines no
  dark tokens, and theming two new pages while the other three stay light
  would be worse than not theming at all.
- **Motion:** near-static. This is a precision input surface, not a landing
  page; the only transition is the existing 200ms card easing.
- **Numbers:** pixel coordinates render in Fira Code via the existing
  `.tabular-nums` class, matching how every other figure in the app is set.

### The picker

Three states in one card, revealed in order, with a step indicator:

1. **No file.** Empty state: a dashed drop area, an `Upload` icon, and one
   sentence saying the corners come from a still and the file is not uploaded
   yet.
2. **Frame loaded.** The still fills the card. A prompt names the corner being
   placed ("Click the **top-left** corner of the pitch"). Placed corners draw
   as numbered blue dots joined by a polygon. Numbering matters: colour alone
   cannot distinguish corner 2 from corner 3. Hit-testing uses a 22px radius so
   the target clears 44px even though the dot renders at 10px.
   Undo and Clear sit next to the prompt. A disclosure holds eight number
   inputs for keyboard-only entry, bound to the same state, because clicking a
   canvas is inherently a pointer gesture.
3. **Corners complete.** The defends-end radio pair appears, worded against the
   frame rather than the enum: "Home defends the **left** goal" maps to `low`,
   right maps to `high`. `matches.py` documents that reversing this mirrors the
   reported shape with no error, so the label carries a one-line explanation
   and the picked still stays visible beside it.

Then Save, then Upload. Upload is disabled until the save succeeds, so the
"upload enqueues the pipeline immediately" trap cannot be hit through the UI.

### Forms

Labels above inputs, never placeholder-as-label. Errors below the field they
belong to, in `role="alert"`. Login validates the UUID on blur, not on every
keystroke. The password field gets a show/hide toggle and
`autocomplete="current-password"`; the academy field gets
`autocomplete="username"`. Submit buttons disable and show a spinner while in
flight. Focus rings are visible on everything interactive.

## Error handling

| Failure                                          | Handling                                                                                                                                                                                                                              |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bad credentials                                  | 401 from the API becomes one inline error above the form. The message does not distinguish a bad UUID from a bad password.                                                                                                            |
| Expired token mid-session                        | `UnauthorizedError` redirects to `/login`; route handlers return 401 to the client, which redirects.                                                                                                                                  |
| Unreadable / non-video file                      | Caught on the `<video>` `error` event, shown inline. `ALLOWED_VIDEO_EXTENSIONS` is `.mp4 .avi .mov .mkv`; `.avi` and `.mkv` frequently will not decode in a browser even though the API accepts them, so the message names that case. |
| Fewer than 4 corners                             | Save stays disabled.                                                                                                                                                                                                                  |
| Degenerate quad (collinear or self-intersecting) | Blocked before save, with a message. A degenerate quad produces a singular homography the pipeline cannot fit.                                                                                                                        |
| Calibration PUT fails                            | Inline error, corners preserved, upload stays locked.                                                                                                                                                                                 |
| Upload fails                                     | Inline error, calibration already saved, retry offered.                                                                                                                                                                               |

## Testing

`vitest` is added to the dashboard, which has no test runner today, and wired
into the existing CI dashboard job beside `tsc --noEmit`. It covers
`lib/corners.ts` only: the scaling round-trip at several canvas sizes, the
degenerate-quad rejection, and corner ordering. That function is where a wrong
answer is invisible, which is what earns it a test.

Manual verification runs against the local API with a synthetic ffmpeg clip at
a known resolution, so the expected pixel coordinates of a click are known in
advance. The check that matters is reading the row back: clicking near the
bottom-right of a 1920x1080 video must store roughly `[1900, 1050]`, not the
canvas-space `[640, 360]`.

Backend suites must not move: 154 in CI scope, 254 wider. Any change there
means something was touched that should not have been.

## Prerequisites this exposes

- The only academy in `dev.db` has `password_hash = NULL` and
  `api/routers/academies.py` is an empty router with no create or set-password
  endpoint, so no account can log in. `seed_dev.py` gains a password.
- `data/raw/140e56e2-....mp4` is a 5-byte stub from an old upload test, not a
  video. Testing uses a generated clip.
- Redis is not installed, so `process_match.delay()` cannot reach a broker and
  the upload step returns an error rather than 202. Upload verification needs
  `brew install redis`. The pipeline itself still cannot run locally without
  torch.

## Known limitations

- Calibration only affects the next pipeline run. A coach who uploads before
  calibrating still gets `"unknown"`, and the UI cannot prevent that for
  matches created outside this flow.
- `home_defends_end` describes the whole video, so a full match with a half-time
  end swap has one half mirrored.
- Login takes an academy UUID as the username. Fixing it needs a new column on
  `Academy`.
- The dashboard still says "football_ai" and "UAE Academy Analytics", which
  contradicts CLAUDE.md's Canadian-market "soccer" rule. Pre-existing.
