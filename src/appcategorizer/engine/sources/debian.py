# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import contextlib
from urllib.parse import quote
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from .base import BaseSource

class DebianSource(BaseSource):
    SUITE = "stable"

    async def fetch(self, client, app_name: str) -> list[str]:
        url = f"https://packages.debian.org/{self.SUITE}/{quote(app_name, safe='')}"

        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()

                    # Bound the load explicitly; the default is 30 s, which is
                    # far longer than this source is allowed under the resolver's
                    # per-source ceiling.
                    await page.goto(url, wait_until="networkidle", timeout=8000)

                    # Capture everything needed while the page is still open.
                    html = await page.content()
                    page_title = await page.title()

                    # Use the saved values for validation.
                    if "No such package" in html or "Error" in page_title:
                        return []

                    return self._parse_direct(html)
                finally:
                    if browser:
                        with contextlib.suppress(Exception):
                            await browser.close()
                        browser = None

        except Exception as exc:
            self.log_failure("fetch package page", exc)
            return []

    def _parse_direct(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        tokens = []

        pdesc = soup.find("div", id="pdesc")
        if not pdesc:
            return []

        # Capture paragraphs, lists, and preformatted blocks.
        for element in pdesc.find_all(["p", "ul", "pre"]):

            # Case 1: real HTML lists.
            if element.name == "ul":
                list_items = []
                for li in element.find_all("li"):
                    # Normalize each list item.
                    li_text = " ".join(li.get_text(separator=" ", strip=True).split())
                    if li_text:
                        list_items.append(f"• {li_text}")

                if list_items:
                    # Store the full list as a single block.
                    tokens.append("\n".join(list_items))
                continue

            # Case 2: paragraphs or preformatted blocks.
            # Use newlines to preserve intentional line breaks.
            lines = element.get_text(separator="\n", strip=True).split("\n")

            formatted_lines = []
            for line in lines:
                clean_line = " ".join(line.split())
                if clean_line:
                    formatted_lines.append(clean_line)

            if not formatted_lines:
                continue

            # Rebuild the paragraph.
            final_text = ""
            for i, line in enumerate(formatted_lines):
                if i == 0:
                    final_text = line
                # Preserve line breaks for pseudo-list items inside paragraphs.
                # Otherwise, join lines with a space.
                elif line.startswith("- ") or line.startswith("* "):
                    final_text += f"\n{line}"
                else:
                    final_text += f" {line}"

            text_lower = final_text.lower()

            # Ban exact phrases instead of isolated words.
            banned_phrases = [
                "/usr/share/doc",
                "transitional package",
                "dummy package",
                "metapackage"
            ]
            is_noise = any(phrase in text_lower for phrase in banned_phrases)

            # Special rule for Debian technical installation instructions.
            if text_lower.startswith("to ") and "install" in text_lower and "package" in text_lower:
                is_noise = True

            if not is_noise:
                tokens.append(final_text)

        return tokens
