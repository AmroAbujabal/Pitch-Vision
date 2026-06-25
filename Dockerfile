# ---- Stage 1: dependency builder ----
FROM python:3.11-slim AS builder

WORKDIR /build

# System libs needed to compile C extensions (cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# The API service (FastAPI + SQLAlchemy + auth) does not need torch or opencv
# at runtime — those are only required by the Celery video-processing worker.
# Installing from requirements-ci.txt keeps the API image small and fast to build.
# To build a full worker image that includes torch/paddlepaddle/opencv, pass:
#   --build-arg REQUIREMENTS=requirements.txt
ARG REQUIREMENTS=requirements-ci.txt
COPY requirements-ci.txt requirements.txt* ./

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r ${REQUIREMENTS}


# ---- Stage 2: runtime ----
FROM python:3.11-slim AS runtime

WORKDIR /app

# Minimal runtime system libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY . .

# Create directories expected at runtime
RUN mkdir -p data/raw data/processed data/model_weights data/models

# Default environment (override via --env-file or Cloud Run env vars)
ENV DATABASE_URL="sqlite:///./dev.db" \
    REDIS_URL="redis://localhost:6379/0" \
    SECRET_KEY="change-me-in-production" \
    DEFAULT_FPS="25.0" \
    FRAME_WIDTH="1920" \
    FRAME_HEIGHT="1080" \
    DEVICE="cpu"

EXPOSE 8000

# Run DB migrations then start uvicorn.
CMD alembic upgrade head && \
    uvicorn api.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 1 \
        --log-level info
