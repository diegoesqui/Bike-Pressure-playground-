"""
Playwright driver for the Silca Pro Tire Pressure Calculator.

Selectors confirmed via scrape/inspect.py + debug output.
The calculation is client-side JS triggered by clicking "Get calculation".

Usage:
    python3.9 -m scrape.silca_driver          # test with defaults
    python3.9 -m scrape.silca_driver --debug  # show raw result HTML
"""

from __future__ import annotations

import sys
from typing import Any

from playwright.sync_api import sync_playwright, Page, Browser, Playwright

URL = "https://silca.cc/en-eu/pages/pro-tire-pressure-calculator"

# Form input selectors (confirmed via inspect.py)
WEIGHT_INPUT     = "input[name='weight']"
SURFACE_SELECT   = "select[name='surface-condition']"
WIDTH_SELECT     = "select[name='tire-width']"
DIAMETER_SELECT  = "select[name='tire-diameter']"
TIRE_TYPE_SELECT = "select[name='tire-type']"
SPEED_SELECT     = "select[name='average-speed']"
DIST_SELECT      = "select[name='weight-dist']"

# Output element IDs (confirmed via debug_output)
REAR_PSI_ID     = "#back-val"
REAR_BAR_ID     = "#back-val-bar"
FRONT_PSI_ID    = "#front-val"
FRONT_BAR_ID    = "#front-val-bar"
RESULT_BOX_ID   = "#pressure-box1"   # becomes visible once calculated

# Silca surface-condition option values → Spanish labels
SURFACES: dict[str, str] = {
    "track-indoor-wood":  "Pista (madera interior)",
    "track-outdoor-wood": "Pista (hormigón exterior)",
    "new-pavement":       "Asfalto nuevo",
    "worn-pavement":      "Asfalto desgastado / fisuras",
    "poor-pavement":      "Asfalto deteriorado / gravilla",
    "cat1-gravel":        "Grava cat. 1 (ligera)",
    "cobblestone":        "Adoquín",
    "cat2-gravel":        "Grava cat. 2",
    "cat3-gravel":        "Grava cat. 3",
    "cat4-gravel":        "Grava cat. 4 (gruesa)",
}

# Speed option values (km/h label → Silca select value)
SPEEDS: dict[str, str] = {
    "14":   "Recreativo",
    "17.5": "Grupo moderado",
    "19.5": "Grupo rápido",
    "21.5": "Competición",
}

# Weight distribution option values
WEIGHT_DIST: dict[str, str] = {
    "road":        "Carretera (48/52)",
    "gravel":      "Gravel (47/53)",
    "mountain":    "MTB (46.5/53.5)",
    "tr-tt-track": "TT/Triatlón (50/50)",
}

# Diameter option values
DIAMETERS: dict[str, str] = {
    "622": '700C / 29"',
    "584": '650B / 27.5"',
    "559": '26"',
    "571": "650C",
}


class SilcaCalculator:
    """
    Context manager that drives the Silca calculator via Playwright.

    Example:
        with SilcaCalculator() as calc:
            result = calc.get_pressure(
                total_kg=95, surface_key="new-pavement",
                tire_width_mm=35,
            )
            print(result)
    """

    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self.page: Page | None = None

    def __enter__(self) -> "SilcaCalculator":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        ctx = self._browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )
        self.page = ctx.new_page()
        self.page.goto(URL, wait_until="domcontentloaded", timeout=30_000)
        self.page.wait_for_selector(SURFACE_SELECT, timeout=15_000)
        self.page.wait_for_timeout(800)

        # Dismiss cookie consent banner if present
        try:
            accept = self.page.locator("#shopify-pc__banner__btn-accept")
            accept.wait_for(state="visible", timeout=5_000)
            accept.click()
            self.page.wait_for_timeout(400)
        except Exception:
            pass

        return self

    def __exit__(self, *_: Any) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    @property
    def surface_options(self) -> list[str]:
        """Return list of Silca surface option keys."""
        return list(SURFACES.keys())

    # ------------------------------------------------------------------
    # Form filling
    # ------------------------------------------------------------------

    def _fill_form(
        self,
        total_kg: float,
        surface_key: str,
        tire_width_mm: int,
        diameter_key: str = "622",
        tire_type_key: str = "mid-range-butyl-tube",
        speed_key: str = "14",
        dist_key: str = "road",
    ) -> None:
        p = self.page

        # Scroll past the sticky nav so it doesn't intercept clicks
        p.evaluate("window.scrollBy(0, 300)")
        p.wait_for_timeout(300)

        # Select kg units by clicking the label (it covers the radio input)
        p.locator("label[for='weight-unit-kg']").click()
        p.wait_for_timeout(200)

        # Total weight
        p.locator(WEIGHT_INPUT).click()
        p.locator(WEIGHT_INPUT).fill(str(round(total_kg, 1)))
        p.keyboard.press("Tab")
        p.wait_for_timeout(200)

        # Dropdowns — select by option value
        for sel, val in [
            (SURFACE_SELECT,   surface_key),
            (WIDTH_SELECT,     str(tire_width_mm)),
            (DIAMETER_SELECT,  diameter_key),
            (TIRE_TYPE_SELECT, tire_type_key),
            (SPEED_SELECT,     speed_key),
            (DIST_SELECT,      dist_key),
        ]:
            p.locator(sel).select_option(value=val)
            p.wait_for_timeout(150)

        # Click "Get calculation" to trigger the JS
        p.locator("button#submit").click()

        # Wait for the result box to become visible (hide class removed)
        p.wait_for_selector(f"{RESULT_BOX_ID}:not(.hide)", timeout=10_000)
        p.wait_for_timeout(300)

    # ------------------------------------------------------------------
    # Output reading
    # ------------------------------------------------------------------

    def _read_values(self) -> dict[str, float | None]:
        """Read the four output spans after calculation."""
        def _num(sel: str) -> float | None:
            try:
                txt = self.page.locator(sel).inner_text(timeout=3_000).strip()
                return float(txt) if txt else None
            except Exception:
                return None

        return {
            "front_psi": _num(FRONT_PSI_ID),
            "rear_psi":  _num(REAR_PSI_ID),
            "front_bar": _num(FRONT_BAR_ID),
            "rear_bar":  _num(REAR_BAR_ID),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_pressure(
        self,
        total_kg: float,
        surface_key: str,
        tire_width_mm: int,
        diameter_key: str = "622",
        tire_type_key: str = "mid-range-butyl-tube",
        speed_key: str = "14",
        dist_key: str = "road",
    ) -> dict[str, Any]:
        self._fill_form(total_kg, surface_key, tire_width_mm,
                        diameter_key, tire_type_key, speed_key, dist_key)
        vals = self._read_values()
        return {
            "total_kg":      total_kg,
            "surface_key":   surface_key,
            "surface":       SURFACES.get(surface_key, surface_key),
            "tire_width_mm": tire_width_mm,
            "diameter_key":  diameter_key,
            "tire_type_key": tire_type_key,
            "speed_key":     speed_key,
            "dist_key":      dist_key,
            **vals,
        }

    def dump_select_options(self) -> None:
        """Print all <option> value+text pairs for every select on the page."""
        selects = self.page.evaluate("""
            () => Array.from(document.querySelectorAll('select')).map(s => ({
                name: s.name || s.id || '?',
                options: Array.from(s.options).map(o => ({value: o.value, text: o.text.trim()}))
            }))
        """)
        for s in selects:
            print(f"\nselect[name='{s['name']}']:")
            for o in s["options"]:
                print(f"  value={o['value']!r:40s}  label={o['text']!r}")

    def debug_output(self) -> None:
        """Dump all select options, then fill a test case and print results."""
        print("=== Select options (before filling) ===")
        self.dump_select_options()

        print("\n=== Filling test case: 90 kg, new-pavement, 35mm, 700C ===")
        self._fill_form(90, "new-pavement", 35)
        vals = self._read_values()
        print(f"\nResult: {vals}")

        html = self.page.evaluate("""
            () => {
                const el = document.querySelector('#pressure-box1');
                return el ? el.parentElement.parentElement.innerHTML : null;
            }
        """)
        print(f"\nResult section HTML:\n{html}")


if __name__ == "__main__":
    debug = "--debug" in sys.argv
    with SilcaCalculator(headless=False) as calc:
        if debug:
            calc.debug_output()
        else:
            result = calc.get_pressure(
                total_kg=90,
                surface_key="new-pavement",
                tire_width_mm=35,
            )
            print("Result:", result)
