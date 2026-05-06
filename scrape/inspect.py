"""
Reconnaissance script: load the Silca calculator, dump network calls and form
selectors so we know whether the calc is client-side or API-based.

Usage:
    python -m scrape.inspect
"""

import json
import asyncio
import pathlib
import sys
from playwright.async_api import async_playwright

URL = "https://silca.cc/pages/pro-tire-pressure-calculator"
CHROMIUM_EXECUTABLE = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_PATH = DATA_DIR / "network_log.json"

INTERESTING_MIME = {
    "application/json",
    "text/javascript",
    "application/javascript",
}


async def run(headless: bool = False) -> None:
    log: list[dict] = []
    async with async_playwright() as p:
        import os
        exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", CHROMIUM_EXECUTABLE)
        launch_kwargs: dict = {
            "headless": headless,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if exe and pathlib.Path(exe).exists():
            launch_kwargs["executable_path"] = exe
        browser = await p.chromium.launch(**launch_kwargs)
        ctx = await browser.new_context(
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = await ctx.new_page()

        def on_request(req):
            log.append({"type": "request", "method": req.method, "url": req.url})

        async def on_response(resp):
            mime = resp.headers.get("content-type", "")
            entry = {"type": "response", "status": resp.status, "url": resp.url, "mime": mime}
            if any(m in mime for m in INTERESTING_MIME):
                try:
                    entry["body"] = await resp.text()
                except Exception:
                    pass
            log.append(entry)

        page.on("request", on_request)
        page.on("response", lambda r: asyncio.ensure_future(on_response(r)))

        print(f"Opening {URL} ...")
        try:
            await page.goto(URL, wait_until="networkidle", timeout=30_000)
        except Exception as e:
            print(f"Warning during load: {e}", file=sys.stderr)

        await page.wait_for_timeout(3000)

        print("\n=== FORM ELEMENTS ===")
        for selector in ("input", "select", "textarea", "button"):
            elements = await page.query_selector_all(selector)
            for el in elements:
                tag = await el.evaluate("el => el.tagName")
                name = await el.get_attribute("name") or ""
                label = await el.get_attribute("aria-label") or ""
                el_type = await el.get_attribute("type") or ""
                placeholder = await el.get_attribute("placeholder") or ""
                options: list[str] = []
                if tag == "SELECT":
                    opts = await el.query_selector_all("option")
                    for opt in opts:
                        txt = await opt.inner_text()
                        val = await opt.get_attribute("value") or ""
                        options.append(f"{val!r}: {txt!r}")
                print(
                    f"  <{tag.lower()}> name={name!r} type={el_type!r} "
                    f"aria-label={label!r} placeholder={placeholder!r}"
                    + (f" options=[{', '.join(options)}]" if options else "")
                )

        print("\n=== SCRIPT SOURCES ===")
        scripts = await page.query_selector_all("script[src]")
        for s in scripts:
            src = await s.get_attribute("src")
            print(f"  {src}")

        print("\n=== API-LIKE REQUESTS ===")
        for entry in log:
            url = entry.get("url", "")
            if any(kw in url for kw in ["api", "calc", "pressure", "graphql"]):
                print(f"  [{entry['type']}] {entry.get('method', '')} {url}")

        LOG_PATH.write_text(json.dumps(log, indent=2))
        print(f"\nNetwork log ({len(log)} entries) -> {LOG_PATH}")
        await browser.close()


if __name__ == "__main__":
    headless_flag = "--headless" in sys.argv
    asyncio.run(run(headless=headless_flag))
