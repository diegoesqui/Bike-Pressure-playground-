"""
Generate a synthetic demo dataset based on Silca's published methodology.

This approximates the Silca calculator using:
  PSI = C * (total_kg * axle_split) / tire_width_mm * surface_factor * tire_type_factor

Calibrated to match documented Silca outputs (~88 kg + 25mm + smooth asphalt ≈ 90 psi rear).
Replace this file with real swept data by running: python -m scrape.sweep

Usage:
    python -m scrape.generate_synthetic_data
"""

from __future__ import annotations

import csv
import itertools
import pathlib

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
CSV_PATH = DATA_DIR / "silca_sweep.csv"

PSI_TO_BAR = 0.0689476

# Calibration constant (empirically matched to published Silca outputs)
C = 49.0

# Axle load distribution for a road/city bike
FRONT_SPLIT = 0.42
REAR_SPLIT = 0.58

# Surface names match Silca's Spanish labels; factors approximate Silca's pressure adjustments
SURFACES: dict[str, float] = {
    "Pista (madera interior)":          1.10,
    "Pista (hormigón exterior)":        1.05,
    "Asfalto nuevo":                    1.00,
    "Asfalto desgastado / fisuras":     0.93,
    "Asfalto deteriorado / gravilla":   0.86,
    "Grava cat. 1 (ligera)":            0.79,
    "Adoquín":                          0.72,
    "Grava cat. 2":                     0.65,
    "Grava cat. 3":                     0.58,
    "Grava cat. 4 (gruesa)":            0.50,
}

TIRE_TYPE_FACTOR = 0.90
SPEED_FACTOR = 0.99

# Grid mirrors sweep.py — city-bike focused
TOTAL_KG       = list(range(70, 130, 5))        # 70 75 … 125 (12 values)
TIRE_WIDTHS_MM = [25, 28, 30, 32, 35, 38, 40, 42, 45, 50]  # 25-50mm only

# Exclude velodrome surfaces (not relevant for city bikes)
SURFACES = {k: v for k, v in SURFACES.items()
            if k not in ("Pista (madera interior)", "Pista (hormigón exterior)")}

WHEEL = "700c"
BIKE_TYPE = "Road"
TIRE_TYPE = "Tubeless"
SPEED_KMH = 30.0


def compute_psi(total_kg: float, axle_split: float, width_mm: int, surface_factor: float) -> float:
    raw = C * total_kg * axle_split / width_mm * surface_factor * TIRE_TYPE_FACTOR * SPEED_FACTOR
    return round(max(12.0, min(130.0, raw)), 1)


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    fieldnames = [
        "rider_kg", "bike_kg", "luggage_kg", "total_kg",
        "tire_width_mm", "surface",
        "wheel", "bike_type", "tire_type", "speed_kmh",
        "front_psi", "rear_psi", "front_bar", "rear_bar",
        "data_source",
    ]

    rows = 0
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for total, width, (surface, sfactor) in itertools.product(
            TOTAL_KG, TIRE_WIDTHS_MM, SURFACES.items()
        ):
            front = compute_psi(total, FRONT_SPLIT, width, sfactor)
            rear  = compute_psi(total, REAR_SPLIT,  width, sfactor)
            writer.writerow({
                "rider_kg":    total,
                "bike_kg":     0,
                "luggage_kg":  0,
                "total_kg":    total,
                "tire_width_mm": width,
                "surface":     surface,
                "wheel":       WHEEL,
                "bike_type":   BIKE_TYPE,
                "tire_type":   TIRE_TYPE,
                "speed_kmh":   SPEED_KMH,
                "front_psi":   front,
                "rear_psi":    rear,
                "front_bar":   round(front * PSI_TO_BAR, 2),
                "rear_bar":    round(rear  * PSI_TO_BAR, 2),
                "data_source": "synthetic",
            })
            rows += 1

    print(f"Generated {rows} rows → {CSV_PATH}")
    print("NOTE: This is a synthetic approximation. Run `python -m scrape.sweep` for real Silca data.")


if __name__ == "__main__":
    main()
