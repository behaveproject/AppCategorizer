# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote
from .base import BaseSource

class UbuntuSource(BaseSource):
    BASE_URL = "https://packages.ubuntu.com"
    SUITE = "noble"  # Ubuntu 24.04 LTS

    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        tokens = await self._fetch_direct(client, app_name)
        if tokens:
            return tokens
        return await self._fetch_search(client, app_name)

    async def _fetch_direct(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            response = await client.get(
                f"{self.BASE_URL}/{self.SUITE}/{quote(app_name, safe='')}",
                headers=self.headers,
            )
            if response.status_code != 200:
                return []

            return self._parse(response.text, app_name)
        except Exception as exc:
            self.log_failure("fetch direct package", exc)
            return []

    async def _fetch_search(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            response = await client.get(
                f"{self.BASE_URL}/search/",
                params={
                    "keywords": app_name,
                    "searchon": "names",
                    "suite": self.SUITE,
                    "section": "all",
                },
                headers=self.headers,
            )
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "html.parser")
            # Search results are listed as links.
            # Prefer an exact package-name match.
            results = soup.select("h3 a")
            for result in results:
                pkg_name = result.text.strip()
                if self.is_relevant(app_name, pkg_name):
                    # Fetch the matched package page.
                    return await self._fetch_direct(client, pkg_name)

            return []
        except Exception as exc:
            self.log_failure("fetch package search", exc)
            return []

    def _parse(self, html: str, app_name: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        tokens = []

        # Extract and normalize the package name from the h1.
        h1 = soup.find("h1")
        if h1:
            pkg_name = h1.get_text().strip()
            pkg_name = pkg_name.replace("Package:", "").split("(")[0].split("[")[0].strip()
            if not self.is_relevant(app_name, pkg_name):
                return []

        pdesc = soup.find("div", id="pdesc")
        if pdesc:
            # Short description from the h2.
            h2 = pdesc.find("h2")
            if h2:
                tokens.append(h2.get_text().strip())

            # Long description from paragraph tags, often empty on Ubuntu.
            for p in pdesc.find_all("p"):
                text = p.get_text().strip()
                if text:
                    tokens.append(text)
                    break

        # Package section.
        section_link = soup.select_one("a[href*='/section/']")
        if section_link:
            tokens.append(section_link.get_text().strip())

        # Debian tags.
        for tag in soup.select("a[href*='tag=']"):
            tag_text = tag.get_text().strip()
            if "::" in tag_text:
                tokens.append(tag_text)

        return [t for t in tokens if t.strip()]
