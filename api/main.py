"""
api/main.py

FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import players, matches, academies, metrics, auth
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="PitchVision — Player Analytics API",
    description="Computer vision player profiling for amateur and semi-pro soccer clubs",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],   # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(academies.router, prefix="/api/v1/academies", tags=["Academies"])
app.include_router(players.router, prefix="/api/v1/players", tags=["Players"])
app.include_router(matches.router, prefix="/api/v1/matches", tags=["Matches"])
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["Metrics"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
