"""
Parameter sweep of the Silca tire-pressure calculator.
Writes (and resumes) data/silca_sweep.csv.

Usage:
    python -m scrape.sweep [--headed] [--speed 30] [--wheel 700c]
                           [--bike-type Road] [--tire-type Tubeless]
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
    "tire_width_mm", "surface", "wheel", "bike_type", "tire_type", "speed_kmh",
    "front_psi", "rear_psi",
]

RIDER_KG = list(range(60, 95, 5))
BIKE_KG = [10, 15, 20, 25]
LUGGAGE_KG = [0, 2, 4, 6, 8, 10]
TIRE_WIDTHS_MM = [23, 25, 28, 30, 32, 35, 38, 40, 42, 45, 47, 50]
THROTTLE_S = 0.25


def row_key(row: dict) -> tuple:
    return (float(row["rider_kg"]), float(row["bike_kg"]), float(row["luggage_kg"]),
            int(row["tire_width_mm"]), row["surface"], row["wheel"],
            row["bike_type"], row["tire_type"], float(row["speed_kmh"]))


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
    parser.add_argument("--speed", type=float, default=30.0)
    parser.add_argument("--wheel", default="700c")
    parser.add_argument("--bike-type", default="Road")
    parser.add_argument("--tire-type", default="Tubeless")
    args = parser.parse_args()

    from scrape.silca_driver import SilcaCalculator

    DATA_DIR.mkdir(exist_ok=True)
    done = load_done(CSV_PATH)
    print(f"Already done: {len(done)} rows")

    file_existed = CSV_PATH.exists()
    outfile = open(CSV_PATH, "a", newline="")
    writer = csv.DictWriter(outfile, fieldnames=FIELDNAMES)
    if not file_existed:
        writer.writeheader()
        outfile.flush()

    with SilcaCalculator(headless=args.headless) as calc:
        surfaces = calc.surface_options
        if not surfaces:
            print("ERROR: No surface options found.", file=sys.stderr)
            sys.exit(1)
        print(f"Surfaces: {surfaces}")
        grid = list(itertools.product(RIDER_KG, BIKE_KG, LUGGAGE_KG, TIRE_WIDTHS_MM, surfaces))
        total = len(grid)
        print(f"Grid: {total} | To do: {total - len(done)}")

        for idx, (rider, bike, luggage, width, surface) in enumerate(grid, 1):
            key = (float(rider), float(bike), float(luggage), int(width), surface,
                   args.wheel, args.bike_type, args.tire_type, float(args.speed))
            if key in done:
                continue
            try:
                result = calc.get_pressure(
                    rider_kg=rider, bike_kg=bike, luggage_kg=luggage,
                    tire_width_mm=width, surface=surface,
                    speed_kmh=args.speed, wheel=args.wheel,
                    bike_type=args.bike_type, tire_type=args.tire_type,
                )
                row = {"rider_kg": rider, "bike_kg": bike, "luggage_kg": luggage,
                       "total_kg": rider + bike + luggage, "tire_width_mm": width,
                       "surface": surface, "wheel": args.wheel, "bike_type": args.bike_type,
                       "tire_type": args.tire_type, "speed_kmh": args.speed,
                       "front_psi": result.get("front_psi"),
                       "rear_psi": result.get("rear_psi")}
            except Exception as e:
                print(f"  [WARN] {idx}: {e}", file=sys.stderr)
                row = {"rider_kg": rider, "bike_kg": bike, "luggage_kg": luggage,
                       "total_kg": rider + bike + luggage, "tire_width_mm": width,
                       "surface": surface, "wheel": args.wheel, "bike_type": args.bike_type,
                       "tire_type": args.tire_type, "speed_kmh": args.speed,
                       "front_psi": None, "rear_psi": None}
            writer.writerow(row)
            outfile.flush()
            done.add(key)
            if idx % 100 == 0 or idx == total:
                print(f"  {idx}/{total} ({100*idx/total:.0f}%) "
                      f"front={row['front_psi']} rear={row['rear_psi']}")
            time.sleep(THROTTLE_S)

    outfile.close()
    print(f"Done -> {CSV_PATH}")


if __name__ == "__main__":
    main()
