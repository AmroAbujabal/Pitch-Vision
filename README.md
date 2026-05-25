# football-ai

Computer vision pipeline for detecting, tracking, and analytically profiling football players — built for UAE football academies.

## What it does

Ingests broadcast video of a match, detects and tracks every player frame-by-frame, computes advanced physical and tactical metrics, and serves them through a REST API to a Next.js dashboard.

**Target customer:** UAE football academies (Al Ain FC, Al Jazira, Shabab Al Ahli feeders, private academies) that can't afford Opta/StatsBomb.

---

## Stack

| Layer | Technology |
|---|---|
| Detection | YOLOv10x + SAM 2 Hiera Large |
| Re-ID | OSNet / TransReID (HOG stub, upgrade pending) |
| OCR | PaddleOCR — jersey number extraction |
| Tracking | SORT (Kalman + Hungarian) |
| Metrics | Custom Python — pitch control, pressing, physical |
| Backend | FastAPI + SQLAlchemy 2.0 |
| Database | SQLite (dev) → PostgreSQL + pgvector (prod) |
| Queue | Celery + Redis |
| Frontend | Next.js 14 — App Router, TypeScript, Tailwind, Recharts |
| Migrations | Alembic |
| Auth | JWT (python-jose + passlib/bcrypt) |

---

## Quick start

### 1. Python backend

```bash
git clone https://github.com/AmroAbujabal/football-ai.git
cd football-ai

# Install dependencies (base anaconda env)
/opt/anaconda3/bin/pip install -r requirements.txt

# Create database tables
/opt/anaconda3/bin/python -c "
from database.session import engine
from database.models import Base
Base.metadata.create_all(engine)
print('Tables created.')
"

# Seed a test academy + match
PYTHONPATH=. /opt/anaconda3/bin/python scripts/seed_dev.py

# Start the API
/opt/anaconda3/bin/python -m uvicorn api.main:app --reload
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
# All torch-free tests (134 total)
/opt/anaconda3/bin/python -m pytest tests/ --ignore=tests/test_detection -q
```

---

## API endpoints

Base URL: `http://localhost:8000` · Docs: `/docs`

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/auth/token` | Exchange academy_id + password for JWT |

### Matches
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/matches/?academy_id=` | List all matches, newest first |
| `POST` | `/api/v1/matches/` | Register a new match |
| `POST` | `/api/v1/matches/{id}/upload-video` | Upload video → enqueue Celery job |
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

---

## Project structure

```
football-ai/
├── api/                  FastAPI routers, schemas, auth, deps
├── config/               Pydantic settings (all tunables in settings.py)
├── dashboard/            Next.js 14 frontend
├── database/             SQLAlchemy models, session, repository
├── alembic/              Database migrations
├── detection/            YOLOv10 + SAM 2 + jersey OCR
├── tracking/             SORT tracker + re-ID
├── metrics/              Pitch control, pressing, physical metrics
├── utils/                Homography (pixel ↔ pitch coords), visualisation
├── tasks/                Celery task (video processing pipeline)
├── scripts/              run_pipeline.py CLI + seed_dev.py
└── tests/                134 passing tests (torch-free)
```

---

## Running the video pipeline

```bash
# Requires torch + model weights (see scripts/download_weights.sh)
PYTHONPATH=. /opt/anaconda3/bin/python scripts/run_pipeline.py \
  --video data/raw/match.mp4 \
  --match-id <uuid> \
  --academy-id <uuid>
```

### With Celery (async, triggered by upload-video endpoint)

```bash
redis-server &
/opt/anaconda3/bin/celery -A tasks.pipeline.celery_app worker --loglevel=info
```

---

## Environment variables

Copy `.env.local.example` → `.env` for the backend, `.env.local.example` → `dashboard/.env.local` for the frontend.

Key variables:

| Variable | Default | Description |
|---|---|---|
| `database_url` | `sqlite:///./dev.db` | Override with `postgresql+asyncpg://...` for prod |
| `redis_url` | `redis://localhost:6379/0` | Celery broker |
| `secret_key` | `change-me-in-production` | JWT signing key — **change this** |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL for the dashboard |
| `NEXT_PUBLIC_ACADEMY_ID` | — | Academy UUID to display in the dashboard |

---

## What's left to build

| Priority | Item | Status |
|---|---|---|
| D | Replace HOG re-ID with OSNet/TransReID | Pending (needs torch) |
| — | PostgreSQL + pgvector for production | Pending |
| — | Rate limiting on auth endpoints | Pending |
| — | Arabic UI (name_ar fields wired) | Pending |

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Write tests first (TDD — see `tests/`)
4. Open a pull request

All tests must pass before merging:
```bash
/opt/anaconda3/bin/python -m pytest tests/ --ignore=tests/test_detection -q
```
