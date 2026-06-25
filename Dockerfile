# ---- Stage 1: dependency builder ----
# Install Python deps into a venv so the final stage only copies what's needed.
FROM python:3.11-slim AS builder

WORKDIR /build

# System libs required at install time (some packages compile C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first so Docker caches this layer
COPY requirements.txt .

# Install CPU-only PyTorch (avoids pulling in ~5 GB CUDA wheels)
# then install the rest of the requirements.
# torch + torchvision are listed in requirements.txt with >=, so we pin
# the CPU index here; the --extra-index-url lookup handles the rest.
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
        torch==2.3.0+cpu \
        torchvision==0.18.0+cpu \
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt


# ---- Stage 2: runtime ----
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system deps (opencv headless, libgomp for torch)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1-mesa-glx libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from the builder stage
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

# Expose FastAPI port
EXPOSE 8000

# Run DB migrations then start uvicorn.
# Using shell form so we can chain commands; production deployments should
# separate the migration step (run once as an init container or job).
CMD alembic upgrade head && \
    uvicorn api.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 1 \
        --log-level info
