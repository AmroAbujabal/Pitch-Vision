# PitchVision

Computer vision pipeline for detecting, tracking, and analytically profiling soccer players — built for amateur and semi-pro clubs in Canada.

## What it does

Upload a match clip from a single fixed touchline camera or phone. PitchVision detects and tracks every player frame-by-frame, computes per-player physical and tactical metrics, and serves them through a REST API to a coach-facing dashboard.

**Target user:** Amateur and semi-pro soccer clubs that want data-driven player analysis without expensive multi-camera setups or broadcast infrastructure.

---

## Stack

| Layer | Technology |
|---|---|
| Detection | YOLOv10 + SAM 2 |
| Re-ID | OSNet / TransReID (HOG stub, upgrade pending) |
| OCR | PaddleOCR — jersey number extraction |
| Tracking | SORT (Kalman + Hungarian) |
| Metrics | Custom Python — pitch control, pressing, physical, development scoring |
| Backend | FastAPI + SQLAlchemy 2.0 |
| Database | SQLite (dev) → PostgreSQL + pgvector (prod) |
| Queue | Celery + Redis |
| Frontend | Next.js 14 — App Router, TypeScript, Tailwind, Recharts |
| Migrations | Alembic |
| Auth | JWT (python-jose + passlib/bcrypt) |

---

## Camera requirements

PitchVision is designed around **a single fixed camera** — a touchline tripod or phone on a stand. You do not need broadcast infrastructure.

| Input | Supported |
|---|---|
| Phone video (MP4, MOV) | ✓ |
| Touchline fixed camera | ✓ |
| 720p – 4K | ✓ (1080p recommended) |
| 25fps / 30fps / 60fps | ✓ (configure `default_fps` in `.env`) |
| Multi-camera broadcast | Works, but not required |

**Limitations with single-camera footage:**
- If the camera doesn't capture the full pitch width, pitch control stats are only computed for the visible zone
- Players who leave the frame are re-identified when they return (up to `max_lost_frames` frames, default 90)
- Distance and speed accuracy depends on providing accurate pitch corner coordinates for homography calibration

---

## Quick start

### 1. Python backend

```bash
git clone https://github.com/AmroAbujabal/football-VLMs.git pitchvision
cd pitchvision

pip install -r requirements.txt

# Create database tables
python -c "
from database.session import engine
from database.models import Base
Base.metadata.create_all(engine)
print('Tables created.')
"

# Seed a test club + match
PYTHONPATH=. python scripts/seed_dev.py

# Start the API
python -m uvicorn api.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

### 2. Dashboard

```bash
cd dashboard
npm install
cp .env.local.example .env.local
# Edit .env.local:
#   NEXT_PUBLIC_API_URL=http://localhost:8000
#   NEXT_PUBLIC_ACADEMY_ID=<paste UUID from seed output>

npm run dev
# → http://localhost:3000
```

### 3. Run tests

```bash
python -m pytest tests/test_api/ tests/test_db/ -q
```

---

## API endpoints

Base URL: `http://localhost:8000` · Docs: `/docs`

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/auth/token` | Exchange club_id + password for JWT |

### Matches
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/matches/?academy_id=` | List all matches, newest first |
| `POST` | `/api/v1/matches/` | Register a new match |
| `POST` | `/api/v1/matches/{id}/upload-video` | Upload video → enqueue processing job |
| `GET` | `/api/v1/matches/{id}/summary` | Aggregated team stats |
| `GET` | `/api/v1/matches/{id}/players` | All player stats for a match |
| `GET` | `/api/v1/matches/{id}/processing-status` | Poll pipeline status |

### Players
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/players/` | Register a player |
| `GET` | `/api/v1/players/{id}/stats` | Match stats history |
| `GET` | `/api/v1/players/{id}/profile` | Bio + latest stats + development trend |
| `GET` | `/api/v1/players/{id}/heatmap?match_id=` | Heatmap grid for one match |
| `GET` | `/api/v1/players/{id}/prediction` | Predicted development score for coming week |

---

## Outputs

### Per-player (per match)
| Metric | Status |
|---|---|
| Distance covered (m) | ✓ |
| Top speed / avg speed (m/s) | ✓ |
| Sprint count | ✓ |
| High-intensity run count | ✓ |
| Press count + success rate | ✓ |
| Pitch control contribution | ✓ |
| Heatmap grid | ⚠ Endpoint ready, pipeline wiring pending |
| Speed zone breakdown (walk/jog/run/sprint) | Planned |

### Team-level (per match)
| Metric | Status |
|---|---|
| Pitch control % (home vs away) | ✓ |
| Top speed per team | ✓ |
| Total press count per team | ✓ |
| Formation detection | Planned |
| Possession zones | Planned |

### Development tracking (weekly)
| Metric | Status |
|---|---|
| Overall / physical / tactical / technical score | ✓ |
| Week-on-week trend | ✓ |
| Predicted next-week score | ✓ |

---

## Project structure

```
pitchvision/
├── api/                  FastAPI routers, schemas, auth, deps
├── config/               Pydantic settings (all tunables in settings.py)
├── dashboard/            Next.js 14 coach dashboard
├── database/             SQLAlchemy models, session, repository
├── alembic/              Database migrations
├── detection/            YOLOv10 + SAM 2 + jersey OCR
├── tracking/             SORT tracker + re-ID
├── metrics/              Physical, pitch control, pressing, development scoring
├── utils/                Homography (pixel ↔ pitch coords)
├── tasks/                Celery task (async video processing)
├── scripts/              run_pipeline.py CLI, seed_dev.py, train_model.py
└── tests/                111 passing tests (torch-free)
```

---

## Running the video pipeline

```bash
# Requires torch + model weights (see scripts/download_weights.sh)
PYTHONPATH=. python scripts/run_pipeline.py \
  --video data/raw/match.mp4 \
  --match-id <uuid> \
  --academy-id <uuid>
```

### With Celery (async, triggered by upload endpoint)

```bash
redis-server &
celery -A tasks.pipeline.celery_app worker --loglevel=info
```

---

## Environment variables

Copy `.env.example` → `.env`.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./dev.db` | Override with `postgresql+asyncpg://...` for prod |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker |
| `SECRET_KEY` | `change-me-in-production` | JWT signing key — **change this** |
| `DEFAULT_FPS` | `25.0` | Set to `30.0` for phone video |
| `FRAME_WIDTH` | `1920` | Set to match your camera resolution |
| `FRAME_HEIGHT` | `1080` | Set to match your camera resolution |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL for the dashboard |
| `NEXT_PUBLIC_ACADEMY_ID` | — | Club UUID to display in the dashboard |

---

## Deployment

PitchVision is designed to run as a containerised cloud service. See the [deployment roadmap](#roadmap) below.

**GPU vs CPU:** Processing a 90-minute match at 25fps requires GPU for real-time throughput. With CPU and frame sampling (every 10th frame), a match takes ~45 minutes. For amateur clubs uploading a match and checking results the next morning, CPU is viable.

---

## Roadmap

| Item | Status |
|---|---|
| Heatmap grid written by pipeline | Next |
| Speed zone breakdown | Next |
| Dockerfile (CPU inference) | Next |
| GitHub Actions CI/CD | Next |
| Cloud deployment (Google Cloud Run) | Next |
| Pitch homography calibration UI | Planned |
| Re-ID across occlusions (TransReID/OSNet) | Planned (needs torch) |
| PostgreSQL + pgvector for production | Planned |
| Formation detection | Planned |

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Write tests first (TDD — see `tests/`)
4. Push and open a pull request

All tests must pass before merging:
```bash
python -m pytest tests/test_api/ tests/test_db/ -q
```
