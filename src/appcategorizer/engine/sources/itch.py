# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import httpx
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from .base import BaseSource

class ItchSource(BaseSource):
    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            response = await client.get(
                "https://itch.io/search",
                params={"q": app_name},
                headers=self.headers,
                follow_redirects=True,
            )
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "html.parser")
            product_url = None

            # Search results are rendered as game_cell entries.
            cells = soup.find_all("div", class_="game_cell")

            for cell in cells:
                title_tag = cell.find("div", class_="title") or cell.find("div", class_="game_title")
                if not title_tag:
                    continue

                a_tag = title_tag.find("a")
                if not a_tag:
                    continue

                title = a_tag.get_text(strip=True)
                href = a_tag.get("href", "")

                try:
                    url_slug = href.split("/")[-1]
                except IndexError:
                    url_slug = ""

                # Normalize the URL slug for stricter matching.
                slug_spaced = url_slug.replace("-", " ")
                slug_mashed = url_slug.replace("-", "") # Match compact slugs such as "celesteclassic".
                app_name_mashed = app_name.replace(" ", "").replace("-", "")

                # Test all useful variants, including the compact form.
                if self.is_relevant(app_name, title, url_slug, slug_spaced, slug_mashed) or \
                   self.is_relevant(app_name_mashed, slug_mashed):
                    # Only follow links that stay on itch.io (games live on
                    # *.itch.io creator subdomains). Guards against fetching an
                    # attacker-influenced host scraped out of the search HTML.
                    candidate_url = urljoin("https://itch.io", href)
                    netloc = urlparse(candidate_url).netloc
                    if netloc != "itch.io" and not netloc.endswith(".itch.io"):
                        continue
                    product_url = candidate_url
                    break

            if not product_url:
                return []

            # Fetch the creator page for the selected result.
            detail_resp = await client.get(product_url, headers=self.headers, follow_redirects=True)
            if detail_resp.status_code != 200:
                return []

            return self._parse_detail(detail_resp.text)

        except Exception as exc:
            self.log_failure("fetch game search", exc)
            return []

    def _parse_detail(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")

        genres = []
        tags = []

        # Read the server-rendered information side panel.
        info_panel = soup.find("table", class_="game_info_panel")
        if info_panel:
            for tr in info_panel.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    label = tds[0].get_text(strip=True).lower()
                    value = tds[1].get_text(separator=", ", strip=True)

                    if "genre" in label:
                        genres.append(value)
                    elif "tags" in label:
                        # Keep only a few tags so the embedding stays focused.
                        tag_list = value.split(", ")[:5]
                        tags.extend(tag_list)

        # Build the semantic hint.
        category_str = ", ".join(genres + tags)
        if category_str:
            semantic_injection = f"This software is distributed on itch.io. Categories and tags: {category_str}."
        else:
            semantic_injection = "This is a video game, indie game, or gaming entertainment software distributed on itch.io."

        tokens = [semantic_injection]

        lines_to_process = []
        
        # Prefer SEO metadata because creator CSS can hide or reshape content.
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            lines_to_process = [meta_desc["content"]]
        else:
            # Fall back to the HTML description when SEO metadata is empty.
            desc_div = soup.find("div", class_="formatted_description")
            if desc_div:
                paragraphs = desc_div.find_all("p")
                if paragraphs:
                    lines_to_process = [p.get_text(separator=" ", strip=True) for p in paragraphs]
                else:
                    raw_lines = desc_div.get_text(separator="\n", strip=True).split("\n")
                    lines_to_process = [line for line in raw_lines if line]

        for raw_text in lines_to_process:
            clean_text = " ".join(raw_text.split())
            
            # Skip text that is too short to be useful.
            if not clean_text or len(clean_text) < 20:
                continue

            tokens.append(clean_text)

            # Stop after the first useful text block following the semantic hint.
            if len(tokens) >= 2:
                break

        return tokens
