"""
Generate a synthetic demo dataset based on Silca's published methodology.

Usage:
    python -m scrape.generate_synthetic_data
"""

from __future__ import annotations

import csv
import itertools
import pathlib

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
CSV_PATH = DATA_DIR / "silca_sweep.csv"

C = 49.0
FRONT_SPLIT = 0.42
REAR_SPLIT = 0.58

SURFACES: dict[str, float] = {
    "Smooth Asphalt": 1.00,
    "Mixed Asphalt": 0.90,
    "Chip Seal": 0.81,
    "Light Gravel": 0.72,
    "Gravel / Dirt": 0.63,
}

TIRE_TYPE_FACTOR = 0.90
SPEED_FACTOR = 0.99
RIDER_KG = list(range(60, 95, 5))
BIKE_KG = [10, 15, 20, 25]
LUGGAGE_KG = [0, 2, 4, 6, 8, 10]
TIRE_WIDTHS_MM = [23, 25, 28, 30, 32, 35, 38, 40, 42, 45, 47, 50]


def compute_psi(total_kg: float, axle_split: float, width_mm: int, surface_factor: float) -> float:
    raw = C * total_kg * axle_split / width_mm * surface_factor * TIRE_TYPE_FACTOR * SPEED_FACTOR
    return round(max(12.0, min(130.0, raw)), 1)


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    fieldnames = [
        "rider_kg", "bike_kg", "luggage_kg", "total_kg",
        "tire_width_mm", "surface", "wheel", "bike_type", "tire_type", "speed_kmh",
        "front_psi", "rear_psi", "data_source",
    ]
    rows = 0
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rider, bike, luggage, width, (surface, sfactor) in itertools.product(
            RIDER_KG, BIKE_KG, LUGGAGE_KG, TIRE_WIDTHS_MM, SURFACES.items()
        ):
            total = rider + bike + luggage
            writer.writerow({
                "rider_kg": rider, "bike_kg": bike, "luggage_kg": luggage,
                "total_kg": total, "tire_width_mm": width, "surface": surface,
                "wheel": "700c", "bike_type": "Road", "tire_type": "Tubeless",
                "speed_kmh": 30.0,
                "front_psi": compute_psi(total, FRONT_SPLIT, width, sfactor),
                "rear_psi": compute_psi(total, REAR_SPLIT, width, sfactor),
                "data_source": "synthetic",
            })
            rows += 1
    print(f"Generated {rows} rows -> {CSV_PATH}")


if __name__ == "__main__":
    main()
