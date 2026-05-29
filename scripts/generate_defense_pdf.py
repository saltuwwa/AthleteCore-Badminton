#!/usr/bin/env python3
"""Generate AthleteCore defense PDF from HTML slides (16:9 widescreen)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "athletecore_defense_presentation.html"
PDF = ROOT / "docs" / "athletecore_defense_presentation.pdf"


def main() -> int:
    if not HTML.is_file():
        print(f"Missing HTML: {HTML}", file=sys.stderr)
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install playwright: pip install playwright && playwright install chromium", file=sys.stderr)
        return 1

    PDF.parent.mkdir(parents=True, exist_ok=True)
    file_url = HTML.resolve().as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(file_url, wait_until="networkidle")
        page.wait_for_timeout(1500)  # fonts
        page.pdf(
            path=str(PDF),
            width="13.333in",
            height="7.5in",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            prefer_css_page_size=True,
        )
        browser.close()

    size_kb = PDF.stat().st_size // 1024
    print(f"Created: {PDF} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
