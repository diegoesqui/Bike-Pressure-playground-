"""
Playwright wrapper around the Silca tire-pressure calculator.

Usage (standalone test):
    python -m scrape.silca_driver

The class is a context manager:

    with SilcaCalculator() as calc:
        result = calc.get_pressure(
            rider_kg=75, bike_kg=12, luggage_kg=4,
            tire_width_mm=35, surface="Intermediate",
        )
        print(result)  # {'front_psi': ..., 'rear_psi': ..., 'total_kg': ...}

NOTE: Selectors and input strategy are updated after running scrape/inspect.py.
      Placeholders marked with TODO will be replaced once the page DOM is known.
"""

from __future__ import annotations

import pathlib
import time
import sys
from typing import Any

from playwright.sync_api import sync_playwright, Page, Browser, Playwright

URL = "https://silca.cc/pages/pro-tire-pressure-calculator"

# Path to pre-installed Chromium in this environment.
# Set to None to let Playwright use its own download.
CHROMIUM_EXECUTABLE = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# These will be refined after running inspect.py.
# Keys are semantic names; values are CSS/aria selectors.
SELECTORS: dict[str, str] = {
    # TODO: fill after inspect – examples below are placeholders
    "unit_toggle_metric": "[aria-label*='kg']",
    "rider_weight": "input[name*='rider'], input[aria-label*='rider' i]",
    "bike_weight": "input[name*='bike'], input[aria-label*='bike' i]",
    "tire_width": "input[name*='width' i], input[aria-label*='width' i]",
    "surface": "select[name*='surface' i], select[aria-label*='surface' i]",
    "speed": "input[name*='speed' i], input[aria-label*='speed' i]",
    "wheel": "select[name*='wheel' i], select[aria-label*='wheel' i]",
    "bike_type": "select[name*='bike' i]",
    "tire_type": "select[name*='tire' i], select[name*='tube' i]",
    "front_pressure": "[class*='front' i][class*='pressure' i], [data-result='front']",
    "rear_pressure": "[class*='rear' i][class*='pressure' i], [data-result='rear']",
}

TIMEOUT_MS = 10_000


class SilcaCalculator:
    """
    Synchronous Playwright context manager for the Silca calculator.

    On first run (or when selectors are unknown), call discover() to print
    the actual DOM elements so SELECTORS can be updated.
    """

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self.page: Page | None = None
        # Cached list of surface options discovered from the DOM
        self.surface_options: list[str] = []

    def __enter__(self) -> "SilcaCalculator":
        import os
        self._pw = sync_playwright().start()
        launch_kwargs: dict = {
            "headless": self._headless,
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
        }
        exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", CHROMIUM_EXECUTABLE)
        if exe and pathlib.Path(exe).exists():
            launch_kwargs["executable_path"] = exe
        self._browser = self._pw.chromium.launch(**launch_kwargs)
        ctx = self._browser.new_context(
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        self.page = ctx.new_page()
        self.page.goto(URL, wait_until="networkidle", timeout=30_000)
        self.page.wait_for_timeout(2000)
        self._setup_units()
        self._discover_surface_options()
        return self

    def __exit__(self, *_: Any) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _setup_units(self) -> None:
        """Force metric (kg / mm) and PSI units if toggles exist."""
        page = self.page
        # Try to click a metric / kg button if present
        for label in ("kg", "metric", "kph"):
            try:
                btn = page.locator(f"button:has-text('{label}')", ).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    page.wait_for_timeout(300)
            except Exception:
                pass

    def _discover_surface_options(self) -> None:
        """Read available surface options from the dropdown."""
        page = self.page
        for sel in (
            "select[name*='surface' i]",
            "select[aria-label*='surface' i]",
            "select[id*='surface' i]",
        ):
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    opts = el.locator("option").all()
                    self.surface_options = [o.inner_text() for o in opts]
                    return
            except Exception:
                pass
        # Fallback: read all selects
        selects = page.locator("select").all()
        for sel in selects:
            opts = sel.locator("option").all()
            texts = [o.inner_text() for o in opts]
            if any("smooth" in t.lower() or "gravel" in t.lower() or "chip" in t.lower() for t in texts):
                self.surface_options = texts
                return

    def _try_set_input(self, selectors: list[str], value: str) -> bool:
        page = self.page
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=500):
                    loc.triple_click()
                    loc.type(value, delay=30)
                    loc.press("Tab")
                    page.wait_for_timeout(200)
                    return True
            except Exception:
                continue
        return False

    def _try_select(self, selectors: list[str], value: str) -> bool:
        page = self.page
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=500):
                    loc.select_option(label=value)
                    page.wait_for_timeout(300)
                    return True
            except Exception:
                continue
        return False

    def _read_text(self, selectors: list[str]) -> str | None:
        page = self.page
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=500):
                    return loc.inner_text().strip()
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_all(
        self,
        rider_kg: float,
        bike_kg: float,
        luggage_kg: float,
        tire_width_mm: int,
        surface: str,
        speed_kmh: float = 30.0,
        wheel: str = "700c",
        bike_type: str = "Road",
        tire_type: str = "Tubeless",
    ) -> None:
        """Set all calculator inputs from scratch (re-applied every sweep row)."""
        total_kg = rider_kg + bike_kg + luggage_kg

        # Rider weight
        self._try_set_input(
            ["input[aria-label*='rider' i]", "input[name*='rider' i]",
             "input[placeholder*='rider' i]", "input[id*='rider' i]"],
            str(round(rider_kg, 1)),
        )
        # Bike weight
        self._try_set_input(
            ["input[aria-label*='bike' i]", "input[name*='bike' i]",
             "input[placeholder*='bike' i]", "input[id*='bike' i]"],
            str(round(bike_kg, 1)),
        )
        # Some calculators use a single total weight field
        self._try_set_input(
            ["input[aria-label*='total' i]", "input[name*='total' i]",
             "input[aria-label*='weight' i]", "input[name*='weight' i]",
             "input[id*='weight' i]"],
            str(round(total_kg, 1)),
        )
        # Tire width
        self._try_set_input(
            ["input[aria-label*='width' i]", "input[name*='width' i]",
             "input[id*='width' i]", "input[placeholder*='width' i]"],
            str(tire_width_mm),
        )
        # Surface
        self._try_select(
            ["select[aria-label*='surface' i]", "select[name*='surface' i]",
             "select[id*='surface' i]"],
            surface,
        )
        # Speed
        self._try_set_input(
            ["input[aria-label*='speed' i]", "input[name*='speed' i]",
             "input[id*='speed' i]"],
            str(round(speed_kmh, 1)),
        )
        # Wheel
        self._try_select(
            ["select[aria-label*='wheel' i]", "select[name*='wheel' i]",
             "select[id*='wheel' i]"],
            wheel,
        )
        # Bike type
        self._try_select(
            ["select[aria-label*='bike' i]", "select[name*='bike' i]",
             "select[id*='bike_type' i]"],
            bike_type,
        )
        # Tire type
        self._try_select(
            ["select[aria-label*='tire' i]", "select[name*='tire' i]",
             "select[aria-label*='tube' i]", "select[name*='tube' i]"],
            tire_type,
        )
        # Give the page time to re-compute
        self.page.wait_for_timeout(500)

    def read_pressure(self) -> dict[str, float | None]:
        """Return {front_psi, rear_psi} by reading the output text."""
        front = self._extract_psi([
            "[class*='front' i]", "[data-result='front']",
            "span:has-text('Front')", "p:has-text('Front')",
        ])
        rear = self._extract_psi([
            "[class*='rear' i]", "[data-result='rear']",
            "span:has-text('Rear')", "p:has-text('Rear')",
        ])
        return {"front_psi": front, "rear_psi": rear}

    def _extract_psi(self, selectors: list[str]) -> float | None:
        import re
        text = self._read_text(selectors)
        if text is None:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(match.group(1)) if match else None

    def get_pressure(
        self,
        rider_kg: float,
        bike_kg: float,
        luggage_kg: float,
        tire_width_mm: int,
        surface: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Convenience: set inputs + return pressures + echo inputs."""
        self.set_all(rider_kg, bike_kg, luggage_kg, tire_width_mm, surface, **kwargs)
        result = self.read_pressure()
        result["rider_kg"] = rider_kg
        result["bike_kg"] = bike_kg
        result["luggage_kg"] = luggage_kg
        result["total_kg"] = rider_kg + bike_kg + luggage_kg
        result["tire_width_mm"] = tire_width_mm
        result["surface"] = surface
        return result

    def discover(self) -> None:
        """Print all form elements and their attributes for selector calibration."""
        page = self.page
        print("=== INPUTS ===")
        for el in page.locator("input").all():
            print(
                f"  input id={el.get_attribute('id')!r} "
                f"name={el.get_attribute('name')!r} "
                f"type={el.get_attribute('type')!r} "
                f"aria-label={el.get_attribute('aria-label')!r} "
                f"placeholder={el.get_attribute('placeholder')!r}"
            )
        print("=== SELECTS ===")
        for el in page.locator("select").all():
            opts = [o.inner_text() for o in el.locator("option").all()]
            print(
                f"  select id={el.get_attribute('id')!r} "
                f"name={el.get_attribute('name')!r} "
                f"aria-label={el.get_attribute('aria-label')!r} "
                f"options={opts}"
            )
        print("=== OUTPUT TEXT ===")
        for kw in ("psi", "bar", "front", "rear", "pressure"):
            for el in page.locator(f"*:has-text('{kw}')").all()[:5]:
                try:
                    print(f"  [{kw}] <{el.evaluate('e => e.tagName')}> "
                          f"class={el.get_attribute('class')!r} "
                          f"text={el.inner_text()[:60]!r}")
                except Exception:
                    pass


if __name__ == "__main__":
    headless = "--headless" in sys.argv
    with SilcaCalculator(headless=headless) as calc:
        print("Surface options found:", calc.surface_options)
        calc.discover()
        if calc.surface_options:
            result = calc.get_pressure(
                rider_kg=75, bike_kg=12, luggage_kg=0,
                tire_width_mm=35, surface=calc.surface_options[0],
            )
            print("Test result:", result)
