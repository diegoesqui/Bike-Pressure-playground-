"""
Playwright driver for the Silca Pro Tire Pressure Calculator.

Selectors confirmed via scrape/inspect.py output.
The calculation is client-side JS — no API endpoint exists.

Usage:
    python3.9 -m scrape.silca_driver          # test with defaults
    python3.9 -m scrape.silca_driver --debug  # show discovered output elements
"""

from __future__ import annotations

import pathlib
import sys
import time
from typing import Any

from playwright.sync_api import sync_playwright, Page, Browser, Playwright

URL = "https://silca.cc/en-eu/pages/pro-tire-pressure-calculator"

# Confirmed selectors from inspect.py
WEIGHT_INPUT    = "input[name='weight']"
WEIGHT_UNIT_KG  = "input[name='weight-unit'][value='kg']"
SURFACE_SELECT  = "select[name='surface-condition']"
WIDTH_SELECT    = "select[name='tire-width']"
DIAMETER_SELECT = "select[name='tire-diameter']"
TIRE_TYPE_SELECT = "select[name='tire-type']"
SPEED_SELECT    = "select[name='average-speed']"
DIST_SELECT     = "select[name='weight-dist']"

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

# Speed option values
SPEEDS: dict[str, str] = {
    "14":   "Recreativo",
    "17.5": "Grupo moderado",
    "19.5": "Grupo rápido",
    "21.5": "Competición",
}

# Weight distribution option values
WEIGHT_DIST: dict[str, str] = {
    "road":       "Carretera (48/52)",
    "gravel":     "Gravel (47/53)",
    "mountain":   "MTB (46.5/53.5)",
    "tr-tt-track":"TT/Triatlón (50/50)",
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
                tire_width_mm=35, diameter_key="622",
                tire_type_key="mid-range-tubeless-latex",
                speed_key="17.5", dist_key="road",
            )
            print(result)
    """

    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self.page: Page | None = None
        # Set once the output selector is confirmed
        self._front_sel: str | None = None
        self._rear_sel: str | None = None

    def __enter__(self) -> "SilcaCalculator":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        ctx = self._browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )
        self.page = ctx.new_page()
        # Don't wait for networkidle — too slow. Wait for the form instead.
        self.page.goto(URL, wait_until="domcontentloaded", timeout=30_000)
        self.page.wait_for_selector(SURFACE_SELECT, timeout=15_000)
        self.page.wait_for_timeout(1000)
        return self

    def __exit__(self, *_: Any) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    # ------------------------------------------------------------------
    # Form filling
    # ------------------------------------------------------------------

    def _fill_form(
        self,
        total_kg: float,
        surface_key: str,
        tire_width_mm: int,
        diameter_key: str = "622",
        tire_type_key: str = "mid-range-tubeless-latex",
        speed_key: str = "17.5",
        dist_key: str = "road",
    ) -> None:
        p = self.page

        # Scroll past the sticky nav so it doesn't intercept clicks
        p.evaluate("window.scrollBy(0, 300)")
        p.wait_for_timeout(300)

        # Select kg units — click the <label> because it covers the radio input
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

        # Give JS time to compute the result
        p.wait_for_timeout(1000)

    # ------------------------------------------------------------------
    # Output reading
    # ------------------------------------------------------------------

    def _find_psi_candidates(self) -> list[dict]:
        """Return all visible text nodes that look like PSI values (15–150)."""
        return self.page.evaluate("""
            () => {
                const results = [];
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT, null
                );
                let node;
                while ((node = walker.nextNode())) {
                    const t = node.textContent.trim();
                    const n = parseFloat(t);
                    if (/^\\d{2,3}(\\.\\d)?$/.test(t) && n >= 15 && n <= 150) {
                        const el = node.parentElement;
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            results.push({
                                value: n,
                                text: t,
                                tag: el.tagName,
                                id: el.id || '',
                                cls: el.className || '',
                                outerHTML: el.outerHTML.slice(0, 120),
                            });
                        }
                    }
                }
                return results;
            }
        """)

    def _read_front_rear(self) -> tuple[float | None, float | None]:
        """
        Read front and rear PSI from the result section.
        Uses stored selectors if available, otherwise auto-detects.
        """
        import re

        def extract_number(text: str) -> float | None:
            m = re.search(r"(\d+(?:\.\d+)?)", text)
            return float(m.group(1)) if m else None

        # Try known selectors first
        if self._front_sel and self._rear_sel:
            try:
                ft = self.page.locator(self._front_sel).first.inner_text(timeout=2000)
                rt = self.page.locator(self._rear_sel).first.inner_text(timeout=2000)
                return extract_number(ft), extract_number(rt)
            except Exception:
                pass

        # Auto-detect: look for PSI-like numbers, expect exactly 2
        candidates = self._find_psi_candidates()
        values = [c["value"] for c in candidates]
        if len(values) >= 2:
            # Typically front < rear — take lowest as front
            values_sorted = sorted(set(values))
            if len(values_sorted) >= 2:
                return values_sorted[0], values_sorted[1]
            if len(values_sorted) == 1:
                return values_sorted[0], values_sorted[0]
        if len(values) == 1:
            return values[0], None
        return None, None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_pressure(
        self,
        total_kg: float,
        surface_key: str,
        tire_width_mm: int,
        diameter_key: str = "622",
        tire_type_key: str = "mid-range-tubeless-latex",
        speed_key: str = "17.5",
        dist_key: str = "road",
    ) -> dict[str, Any]:
        self._fill_form(total_kg, surface_key, tire_width_mm,
                        diameter_key, tire_type_key, speed_key, dist_key)
        front, rear = self._read_front_rear()
        return {
            "total_kg": total_kg,
            "surface_key": surface_key,
            "surface": SURFACES.get(surface_key, surface_key),
            "tire_width_mm": tire_width_mm,
            "diameter_key": diameter_key,
            "tire_type_key": tire_type_key,
            "speed_key": speed_key,
            "dist_key": dist_key,
            "front_psi": front,
            "rear_psi": rear,
        }

    @property
    def surface_options(self) -> list[str]:
        """Return list of Silca surface option keys."""
        return list(SURFACES.keys())

    def debug_output(self) -> None:
        """Fill a test case and show all PSI candidate elements."""
        print("Filling test case: 90 kg, new-pavement, 35mm, 700C…")
        self._fill_form(90, "new-pavement", 35)
        candidates = self._find_psi_candidates()
        print(f"\nFound {len(candidates)} PSI-candidate elements:")
        for c in candidates:
            print(f"  {c['value']:6.1f} psi  <{c['tag']}> id={c['id']!r} "
                  f"class={c['cls']!r}")
            print(f"           {c['outerHTML']}")


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
