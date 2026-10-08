"""Materialize the 2025 XGBoost feature store for low-resource web hosting."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.cutoff_forecast_service import (
    FORECAST_FEATURES_PATH,
    cutoff_forecast_service,
)


def main() -> None:
    forecast = cutoff_forecast_service._forecast_features()
    FORECAST_FEATURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    forecast.to_csv(FORECAST_FEATURES_PATH, index=False)
    print(f"Wrote {len(forecast):,} forecast feature rows to {FORECAST_FEATURES_PATH}")


if __name__ == "__main__":
    main()
