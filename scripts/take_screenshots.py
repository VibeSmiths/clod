"""
Generate Rich terminal screenshots of key clod UI elements.

Usage:
    python scripts/take_screenshots.py
    python scripts/take_screenshots.py --install-playwright
"""

import sys
import pathlib
import subprocess
import argparse

# Make clod importable from the project root
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import io

import clod
from clod import TokenBudget
from rich.console import Console

SCREENSHOTS_DIR = pathlib.Path(__file__).parent.parent / "assets"


def capture(name: str, fn):
    """
    Create a recording Rich Console, call fn(console), export to HTML,
    screenshot via Playwright, then clean up the temp HTML file.
    """
    from playwright.sync_api import sync_playwright

    # 1. Create recording console (file=StringIO avoids Windows charmap errors)
    recording_console = Console(
        record=True,
        width=100,
        force_terminal=True,
        force_jupyter=False,
        file=io.StringIO(),
    )

    # 2. Save original clod.console, replace with recording one
    original_console = clod.console
    clod.console = recording_console

    try:
        # 3. Call the capture function
        fn(recording_console)
    finally:
        # 4. Restore original console
        clod.console = original_console

    # 5. Export HTML
    html_content = recording_console.export_html(inline_styles=True)

    # 6. Save HTML to screenshots/{name}.html
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    html_path = SCREENSHOTS_DIR / f"{name}.html"
    html_path.write_text(html_content, encoding="utf-8")

    # 7. Screenshot via Playwright
    png_path = SCREENSHOTS_DIR / f"{name}.png"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file:///{html_path.as_posix()}")
        page.screenshot(path=str(png_path), full_page=True)
        browser.close()

    # 8. Remove temp HTML file
    html_path.unlink()

    # 9. Print confirmation
    print(f"  [ok] {name}.png")


def main():
    parser = argparse.ArgumentParser(description="Generate clod UI screenshots")
    parser.add_argument(
        "--install-playwright",
        action="store_true",
        help="Install Playwright Chromium before generating screenshots",
    )
    args = parser.parse_args()

    if args.install_playwright:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )

    print("Generating screenshots...")

    # 1. help
    capture("help", lambda c: clod.print_help())

    # 2. header_default
    capture(
        "header_default",
        lambda c: clod.print_header("qwen2.5-coder:14b", None, False),
    )

    # 3. header_pipeline
    capture(
        "header_pipeline",
        lambda c: clod.print_header("qwen2.5-coder:14b", "code_review", True),
    )

    # 4. header_tokens
    def _header_tokens(c):
        budget = TokenBudget(100_000)
        budget.used = 45_000
        clod.print_header("qwen2.5-coder:14b", None, False, budget=budget)

    capture("header_tokens", _header_tokens)

    # 5. header_offline
    def _header_offline(c):
        budget = TokenBudget(100_000)
        budget.used = 86_000
        clod.print_header("qwen2.5-coder:14b", None, False, budget=budget, offline=True)

    capture("header_offline", _header_offline)

    print(f"\nAll screenshots saved to: {SCREENSHOTS_DIR}")


if __name__ == "__main__":
    main()
