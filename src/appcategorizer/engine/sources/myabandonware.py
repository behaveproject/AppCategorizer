# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import contextlib
import urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from .base import BaseSource

class MyAbandonwareSource(BaseSource):
    async def fetch(self, client, app_name: str) -> list[str]:
        query = urllib.parse.quote(app_name.strip(), safe="")
        search_url = f"https://www.myabandonware.com/search/q/{query}/"

        browser = None
        try:
            # Use Chromium because MyAbandonware requires JavaScript execution.
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(user_agent=self.headers["User-Agent"])
                    page = await context.new_page()

                    await page.goto(search_url)

                    # Wait up to 10 seconds for Cloudflare to validate the browser.
                    for _ in range(10):
                        page_title = await page.title()
                        # Continue once the page title is no longer a loading message.
                        if "Please wait" not in page_title and "Just a moment" not in page_title and "Attention" not in page_title:
                            break
                        await page.wait_for_timeout(1000)

                    # Check whether Cloudflare redirected directly to the game page.
                    current_url = page.url
                    if "/game/" in current_url and "search" not in current_url:
                        html = await page.content()
                        return self._parse_detail(html)

                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    product_url = None

                    for a in soup.find_all("a", href=True):
                        href = a["href"]

                        if "/game/" in href and "search" not in href:
                            span_name = a.find("span", class_="name")
                            title = span_name.get_text(separator=" ", strip=True) if span_name else a.get_text(separator=" ", strip=True)

                            try:
                                # Extract the slug, for example prince-of-persia-pd.
                                url_slug = href.split("/game/")[1].split("/")[0]
                            except IndexError:
                                url_slug = ""

                            if self.is_relevant(app_name, title, url_slug):
                                candidate_url = urllib.parse.urljoin(
                                    "https://www.myabandonware.com", href
                                )
                                if (
                                    urllib.parse.urlparse(candidate_url).netloc
                                    != "www.myabandonware.com"
                                ):
                                    continue
                                product_url = candidate_url
                                break

                    if not product_url:
                        return []

                    # Keep the same Playwright session when opening the detail page.
                    # Cloudflare will remember the validated browser state.
                    await page.goto(product_url, wait_until="domcontentloaded")
                    with contextlib.suppress(Exception):
                        await page.wait_for_load_state("networkidle", timeout=1500)

                    detail_html = await page.content()

                    return self._parse_detail(detail_html)
                finally:
                    if browser:
                        with contextlib.suppress(Exception):
                            await browser.close()
                        browser = None

        except Exception as exc:
            self.log_failure("fetch game listing", exc)
            return []

    def _parse_detail(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")

        # Add a semantic hint.
        tokens = ["This is a retro video game and single-player entertainment software."]

        # Look for the long description in common content blocks first.
        desc_div = (
            soup.find("div", id="desc") or
            soup.find("div", id="description") or
            soup.find("div", class_="desc") or
            soup.find("div", class_="gameDescription")
        )

        lines_to_process = []

        if desc_div:
            paragraphs = desc_div.find_all("p")
            if not paragraphs:
                raw_lines = desc_div.get_text(separator="\n", strip=True).split("\n")
                lines_to_process = [line for line in raw_lines if line]
            else:
                lines_to_process = [p.get_text(separator=" ", strip=True) for p in paragraphs]
        else:
            # Fall back to the meta description.
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                # Use the SEO description content.
                lines_to_process = [meta_desc["content"]]
            else:
                return tokens

        banned_keywords = [
            "how to play", "download", "emulator", "dosbox",
            "abandonware", "zip file", "archive", "click here"
        ]

        # Filter noisy support and download text.
        for raw_text in lines_to_process:
            clean_text = " ".join(raw_text.split())

            if not clean_text:
                continue

            text_lower = clean_text.lower()

            is_noise = any(kw in text_lower for kw in banned_keywords)
            if is_noise and len(clean_text) < 150:
                continue

            tokens.append(clean_text)

            if len(tokens) >= 3:
                break

        return tokens
