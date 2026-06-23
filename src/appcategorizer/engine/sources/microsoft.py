# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import contextlib
import json
from urllib.parse import urlencode, urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from .base import BaseSource

class MicrosoftSource(BaseSource):
    async def fetch(self, client, app_name: str) -> list[str]:
        search_url = "https://apps.microsoft.com/search?" + urlencode(
            {"query": app_name, "hl": "en-us", "gl": "US"}
        )

        browser = None
        try:
            product_url = None

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()

                    await page.goto(search_url, wait_until="domcontentloaded")
                    with contextlib.suppress(Exception):
                        await page.locator("a[href*='/detail/']").first.wait_for(timeout=3000)

                    links = await page.locator("a[href*='/detail/']").all()

                    for link in links:
                        href = await link.get_attribute("href")

                        # Ignore review links.
                        if "review" in (href or "").lower():
                            continue

                        # inner_text() returns the text visible to a human user.
                        text_content = await link.inner_text()
                        aria_label = await link.get_attribute("aria-label") or ""

                        # Split and clean lines to recover the first line as the title.
                        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                        title = lines[0] if lines else ""

                        # Fall back to the aria-label when the visible title is missing.
                        if not title and aria_label:
                            title = aria_label

                        if self.is_relevant(app_name, title) or self.is_relevant(app_name, aria_label):
                            candidate_url = urljoin("https://apps.microsoft.com", href)
                            if urlparse(candidate_url).netloc != "apps.microsoft.com":
                                continue
                            product_url = candidate_url
                            break
                finally:
                    if browser:
                        with contextlib.suppress(Exception):
                            await browser.close()
                        browser = None

            if not product_url:
                return []

            # Fetch the product page with httpx.
            if "?" not in product_url:
                product_url += "?hl=en-us&gl=US"
            else:
                product_url += "&hl=en-us&gl=US"

            detail_resp = await client.get(product_url, headers=self.headers, follow_redirects=True)
            if detail_resp.status_code != 200:
                return []

            return self._parse_detail(detail_resp.text)

        except Exception as exc:
            self.log_failure("fetch app listing", exc)
            return []

    def _parse_detail(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]

                for item in items:
                    if item.get("@type") == "SoftwareApplication" and "description" in item:
                        return self._format_description(item["description"])
            except json.JSONDecodeError:
                continue

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return self._format_description(meta_desc["content"])

        return []

    def _format_description(self, raw_text: str) -> list[str]:
        tokens = []
        lines = raw_text.replace("\r", "").split("\n")

        # Typical noisy keywords from Microsoft Store description endings.
        banned_keywords = [
            "feedback", "contact us", "http://", "https://",
            "tweet us", "@", "privacy policy", "terms of use"
        ]

        for line in lines:
            clean_line = " ".join(line.split())
            if not clean_line:
                continue

            text_lower = clean_line.lower()

            # Drop support phrases and links.
            if any(kw in text_lower for kw in banned_keywords):
                continue

            # Remove unusual bullet symbols.
            if clean_line.startswith(("■", "•", "-", "*", "✔", "●")):
                clean_line = clean_line[1:].strip()

            tokens.append(clean_line)

            # Stop after three valid text blocks.
            if len(tokens) >= 3:
                break

        return tokens
