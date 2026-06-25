"""
scripts/train_model.py

Train a player performance prediction model from the database.

Usage:
    python scripts/train_model.py
    python scripts/train_model.py --position MID --n-matches 4

Trains one Ridge regression model per position group (GK, DEF, MID, FWD)
plus an ALL fallback. Models are saved to data/models/.

Requires scikit-learn:
    pip install scikit-learn
"""

import argparse
import pickle

from loguru import logger

from config.settings import PROJECT_ROOT
from database.session import get_session
from metrics.features import FEATURE_KEYS, build_training_dataset

MODEL_DIR = PROJECT_ROOT / "data" / "models"

POSITION_GROUPS = {
    "GK":  {"GK"},
    "DEF": {"CB", "FB", "DEF"},
    "MID": {"DM", "CM", "AM", "MID"},
    "FWD": {"W", "ST", "FWD"},
}


def _train(X, y, label: str) -> None:
    from sklearn.linear_model import Ridge
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if len(X) < 5:
        logger.warning(f"{label}: only {len(X)} samples — skipping (need ≥5)")
        return

    model = Pipeline([
        ("impute",  SimpleImputer(strategy="mean")),
        ("scale",   StandardScaler()),
        ("regress", Ridge(alpha=1.0)),
    ])
    model.fit(X, y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / f"prediction_{label}.pkl"
    with path.open("wb") as f:
        pickle.dump(model, f)
    logger.info(f"Saved {label} model → {path}  (n={len(X)})")


def main(n_matches: int = 4) -> None:
    logger.info("Loading features from database...")
    with get_session() as session:
        X_all, y_all = build_training_dataset(session, n_matches=n_matches)

        if not X_all:
            logger.warning("No training data found — process some matches first.")
            return

        logger.info(f"Total samples: {len(X_all)}")

        # Train per-position models
        from sqlalchemy import select
        from database.models import Player

        # Re-query to get position labels per sample
        # build_training_dataset doesn't return labels, so we rebuild with positions

        all_players = session.execute(select(Player)).scalars().all()
        position_map = {p.id: p.position.upper() for p in all_players}

        # Rebuild per-position
        from metrics.features import assemble_player_features
        from database.models import DevelopmentScore
        from datetime import timezone, timedelta

        pos_X: dict[str, list] = {g: [] for g in POSITION_GROUPS}
        pos_y: dict[str, list] = {g: [] for g in POSITION_GROUPS}

        for player in all_players:
            rows = assemble_player_features(player.id, session, n_matches=n_matches)
            if len(rows) < 2:
                continue
            feature_rows = rows[:-1]
            last_date = rows[-1]["match_date"]
            if last_date is None:
                continue
            last_dt = last_date if last_date.tzinfo else last_date.replace(tzinfo=timezone.utc)
            week_start = (last_dt - timedelta(days=last_dt.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            dev = session.execute(
                select(DevelopmentScore)
                .where(
                    DevelopmentScore.player_id == player.id,
                    DevelopmentScore.week_start >= week_start,
                )
                .order_by(DevelopmentScore.week_start.asc())
                .limit(1)
            ).scalar_one_or_none()
            if dev is None:
                continue

            flat = [r[k] if r[k] is not None else 0.0 for r in feature_rows for k in FEATURE_KEYS]
            pos = position_map.get(player.id, "").upper()
            for group, positions in POSITION_GROUPS.items():
                if pos in positions:
                    pos_X[group].append(flat)
                    pos_y[group].append(dev.overall_score)
                    break

        for group in POSITION_GROUPS:
            _train(pos_X[group], pos_y[group], group)

        # Fallback: all positions combined
        _train(X_all, y_all, "ALL")

    logger.info("Training complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train player performance prediction model")
    parser.add_argument("--n-matches", type=int, default=4,
                        help="Number of recent matches to use as features")
    args = parser.parse_args()
    main(n_matches=args.n_matches)
