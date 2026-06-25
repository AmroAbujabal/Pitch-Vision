from pydantic_settings import BaseSettings
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    # Paths
    data_dir: Path = PROJECT_ROOT / "data"
    raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    weights_dir: Path = PROJECT_ROOT / "data" / "model_weights"

    # GPU
    cuda_device: int = 0
    device: str = "cuda"  # "cuda" | "cpu" | "mps"

    # Detection
    yolo_model: str = "yolov10x.pt"
    yolo_conf_threshold: float = 0.35   # lowered for phone/single-camera footage
    yolo_iou_threshold: float = 0.45
    sam2_model: str = "sam2_hiera_large.pt"
    sam2_config: str = "sam2_hiera_l.yaml"

    # Tracking
    max_lost_frames: int = 90        # ~3.6s at 25fps — covers players leaving single-camera frame
    reid_threshold: float = 0.6      # cosine similarity cutoff for re-ID
    min_track_length: int = 5        # min frames before a track is confirmed

    # Video
    default_fps: float = 25.0
    tactical_fps: float = 50.0
    frame_width: int = 1920
    frame_height: int = 1080

    # Pitch dimensions (metres — standard)
    pitch_length: float = 105.0
    pitch_width: float = 68.0

    # OCR
    jersey_ocr_conf: float = 0.7

    # Database (SQLite for local dev; set postgresql+asyncpg:// in .env for production)
    database_url: str = "sqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"

    # API
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Metrics
    press_window_seconds: float = 5.0    # window to measure press success
    press_distance_threshold: float = 5.0  # metres — player considered pressing
    high_intensity_speed: float = 5.5   # m/s threshold for high intensity runs
    sprint_speed: float = 7.0           # m/s threshold for sprint

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Accepted video container formats (shared by the upload endpoint and pipeline task)
ALLOWED_VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mp4", ".avi", ".mov", ".mkv"})
