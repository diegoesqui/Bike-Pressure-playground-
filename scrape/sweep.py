"""
Parameter sweep of the Silca tire-pressure calculator.

Writes (and resumes) data/silca_sweep.csv.

Usage:
    python -m scrape.sweep [--headless] [--speed 17.5] [--diameter 622]
                           [--tire-type mid-range-tubeless-latex] [--dist road]
"""

from __future__ import annotations

import argparse
import csv
import itertools
import pathlib
import sys
import time

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
CSV_PATH = DATA_DIR / "silca_sweep.csv"

FIELDNAMES = [
    "rider_kg", "bike_kg", "luggage_kg", "total_kg",
    "tire_width_mm", "surface",
    "wheel", "bike_type", "tire_type", "speed_kmh",
    "front_psi", "rear_psi", "data_source",
]

# Grid definition
RIDER_KG    = list(range(60, 95, 5))           # 60 65 70 75 80 85 90
BIKE_KG     = [10, 15, 20, 25]
LUGGAGE_KG  = [0, 2, 4, 6, 8, 10]
TIRE_WIDTHS_MM = [23, 25, 28, 30, 32, 35, 38, 40, 42, 45, 47, 50]

# Diameter key → wheel label
DIAMETER_TO_WHEEL = {
    "622": "700C",
    "584": "650B",
    "559": '26"',
    "571": "650C",
}

THROTTLE_S = 0.25


def row_key(row: dict) -> tuple:
    return (
        float(row["rider_kg"]),
        float(row["bike_kg"]),
        float(row["luggage_kg"]),
        int(row["tire_width_mm"]),
        row["surface"],
        row["wheel"],
        row["tire_type"],
        float(row["speed_kmh"]),
    )


def load_done(path: pathlib.Path) -> set[tuple]:
    if not path.exists():
        return set()
    done: set[tuple] = set()
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            done.add(row_key(row))
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--headed", dest="headless", action="store_false")
    parser.add_argument("--speed", type=float, default=17.5,
                        help="Speed key for Silca (14, 17.5, 19.5, 21.5)")
    parser.add_argument("--diameter", default="622",
                        help="Tire diameter key: 622=700C, 584=650B, 559=26in, 571=650C")
    parser.add_argument("--tire-type", default="mid-range-tubeless-latex",
                        help="Silca tire-type option value")
    parser.add_argument("--dist", default="road",
                        help="Weight distribution key: road, gravel, mountain, tr-tt-track")
    args = parser.parse_args()

    from scrape.silca_driver import SilcaCalculator, SURFACES as SILCA_SURFACES

    wheel_label = DIAMETER_TO_WHEEL.get(args.diameter, args.diameter)

    DATA_DIR.mkdir(exist_ok=True)
    done = load_done(CSV_PATH)
    print(f"Already done: {len(done)} rows")

    file_existed = CSV_PATH.exists()
    outfile = open(CSV_PATH, "a", newline="")
    writer = csv.DictWriter(outfile, fieldnames=FIELDNAMES)
    if not file_existed:
        writer.writeheader()
        outfile.flush()

    surface_keys = list(SILCA_SURFACES.keys())
    print(f"Surfaces: {surface_keys}")

    grid = list(itertools.product(RIDER_KG, BIKE_KG, LUGGAGE_KG, TIRE_WIDTHS_MM, surface_keys))
    total_grid = len(grid)
    print(f"Total grid size: {total_grid}  |  To do: {total_grid - len(done)}")

    with SilcaCalculator(headless=args.headless) as calc:
        for idx, (rider, bike, luggage, width, surface_key) in enumerate(grid, 1):
            total = rider + bike + luggage
            surface_label = SILCA_SURFACES[surface_key]

            key = (float(rider), float(bike), float(luggage), int(width), surface_label,
                   wheel_label, args.tire_type, float(args.speed))
            if key in done:
                continue

            try:
                result = calc.get_pressure(
                    total_kg=total,
                    surface_key=surface_key,
                    tire_width_mm=width,
                    diameter_key=args.diameter,
                    tire_type_key=args.tire_type,
                    speed_key=str(args.speed),
                    dist_key=args.dist,
                )
                row = {
                    "rider_kg": rider,
                    "bike_kg": bike,
                    "luggage_kg": luggage,
                    "total_kg": total,
                    "tire_width_mm": width,
                    "surface": surface_label,
                    "wheel": wheel_label,
                    "bike_type": "Road",
                    "tire_type": args.tire_type,
                    "speed_kmh": args.speed,
                    "front_psi": result.get("front_psi"),
                    "rear_psi": result.get("rear_psi"),
                    "data_source": "silca",
                }
            except Exception as e:
                print(f"  [WARN] row {idx}/{total_grid} failed: {e}", file=sys.stderr)
                row = {
                    "rider_kg": rider, "bike_kg": bike, "luggage_kg": luggage,
                    "total_kg": total, "tire_width_mm": width,
                    "surface": surface_label, "wheel": wheel_label,
                    "bike_type": "Road", "tire_type": args.tire_type,
                    "speed_kmh": args.speed,
                    "front_psi": None, "rear_psi": None,
                    "data_source": "silca",
                }

            writer.writerow(row)
            outfile.flush()
            done.add(key)

            if idx % 50 == 0 or idx == total_grid:
                pct = 100 * idx / total_grid
                print(f"  {idx}/{total_grid} ({pct:.1f}%)  "
                      f"rider={rider} bike={bike} luggage={luggage} "
                      f"width={width} surface={surface_label!r} "
                      f"→ front={row['front_psi']} rear={row['rear_psi']}")

            time.sleep(THROTTLE_S)

    outfile.close()
    print(f"\nDone. Wrote {CSV_PATH}")


if __name__ == "__main__":
    main()
