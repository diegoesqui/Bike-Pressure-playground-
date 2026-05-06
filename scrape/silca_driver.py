"""
Playwright wrapper around the Silca tire-pressure calculator.

Usage:
    python -m scrape.silca_driver
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

from playwright.sync_api import sync_playwright, Page, Browser, Playwright

URL = "https://silca.cc/pages/pro-tire-pressure-calculator"
CHROMIUM_EXECUTABLE = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


class SilcaCalculator:
    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self.page: Page | None = None
        self.surface_options: list[str] = []

    def __enter__(self) -> "SilcaCalculator":
        import os
        self._pw = sync_playwright().start()
        exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", CHROMIUM_EXECUTABLE)
        launch_kwargs: dict = {
            "headless": self._headless,
            "args": ["--disable-blink-features=AutomationControlled",
                     "--no-sandbox", "--disable-dev-shm-usage"],
        }
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

    def _setup_units(self) -> None:
        page = self.page
        for label in ("kg", "metric", "kph"):
            try:
                btn = page.locator(f"button:has-text('{label}')").first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    page.wait_for_timeout(300)
            except Exception:
                pass

    def _discover_surface_options(self) -> None:
        page = self.page
        for sel in ("select[name*='surface' i]", "select[aria-label*='surface' i]",
                    "select[id*='surface' i]"):
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    self.surface_options = [o.inner_text() for o in el.locator("option").all()]
                    return
            except Exception:
                pass
        for sel_el in page.locator("select").all():
            texts = [o.inner_text() for o in sel_el.locator("option").all()]
            if any("smooth" in t.lower() or "gravel" in t.lower() for t in texts):
                self.surface_options = texts
                return

    def _try_set_input(self, selectors: list[str], value: str) -> bool:
        for sel in selectors:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=500):
                    loc.triple_click()
                    loc.type(value, delay=30)
                    loc.press("Tab")
                    self.page.wait_for_timeout(200)
                    return True
            except Exception:
                continue
        return False

    def _try_select(self, selectors: list[str], value: str) -> bool:
        for sel in selectors:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=500):
                    loc.select_option(label=value)
                    self.page.wait_for_timeout(300)
                    return True
            except Exception:
                continue
        return False

    def _read_text(self, selectors: list[str]) -> str | None:
        for sel in selectors:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=500):
                    return loc.inner_text().strip()
            except Exception:
                continue
        return None

    def set_all(self, rider_kg: float, bike_kg: float, luggage_kg: float,
                tire_width_mm: int, surface: str, speed_kmh: float = 30.0,
                wheel: str = "700c", bike_type: str = "Road",
                tire_type: str = "Tubeless") -> None:
        total_kg = rider_kg + bike_kg + luggage_kg
        self._try_set_input(
            ["input[aria-label*='rider' i]", "input[name*='rider' i]"],
            str(round(rider_kg, 1)))
        self._try_set_input(
            ["input[aria-label*='bike' i]", "input[name*='bike' i]"],
            str(round(bike_kg, 1)))
        self._try_set_input(
            ["input[aria-label*='weight' i]", "input[name*='weight' i]",
             "input[id*='weight' i]"],
            str(round(total_kg, 1)))
        self._try_set_input(
            ["input[aria-label*='width' i]", "input[name*='width' i]"],
            str(tire_width_mm))
        self._try_select(
            ["select[aria-label*='surface' i]", "select[name*='surface' i]"],
            surface)
        self._try_set_input(
            ["input[aria-label*='speed' i]", "input[name*='speed' i]"],
            str(round(speed_kmh, 1)))
        self._try_select(
            ["select[aria-label*='wheel' i]", "select[name*='wheel' i]"], wheel)
        self._try_select(
            ["select[aria-label*='bike' i]", "select[id*='bike_type' i]"], bike_type)
        self._try_select(
            ["select[aria-label*='tire' i]", "select[name*='tire' i]"], tire_type)
        self.page.wait_for_timeout(500)

    def _extract_psi(self, selectors: list[str]) -> float | None:
        import re
        text = self._read_text(selectors)
        if text is None:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(match.group(1)) if match else None

    def read_pressure(self) -> dict[str, float | None]:
        return {
            "front_psi": self._extract_psi(
                ["[class*='front' i]", "[data-result='front']",
                 "span:has-text('Front')", "p:has-text('Front')"]),
            "rear_psi": self._extract_psi(
                ["[class*='rear' i]", "[data-result='rear']",
                 "span:has-text('Rear')", "p:has-text('Rear')"]),
        }

    def get_pressure(self, rider_kg: float, bike_kg: float, luggage_kg: float,
                     tire_width_mm: int, surface: str, **kwargs: Any) -> dict[str, Any]:
        self.set_all(rider_kg, bike_kg, luggage_kg, tire_width_mm, surface, **kwargs)
        result = self.read_pressure()
        result.update({"rider_kg": rider_kg, "bike_kg": bike_kg, "luggage_kg": luggage_kg,
                       "total_kg": rider_kg + bike_kg + luggage_kg,
                       "tire_width_mm": tire_width_mm, "surface": surface})
        return result

    def discover(self) -> None:
        page = self.page
        for el in page.locator("input").all():
            print(f"  input id={el.get_attribute('id')!r} name={el.get_attribute('name')!r} "
                  f"aria-label={el.get_attribute('aria-label')!r}")
        for el in page.locator("select").all():
            opts = [o.inner_text() for o in el.locator("option").all()]
            print(f"  select id={el.get_attribute('id')!r} "
                  f"aria-label={el.get_attribute('aria-label')!r} options={opts}")


if __name__ == "__main__":
    headless = "--headless" in sys.argv
    with SilcaCalculator(headless=headless) as calc:
        print("Surface options:", calc.surface_options)
        calc.discover()
