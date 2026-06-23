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

class FedoraSource(BaseSource):
    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        tokens = await self._fetch_direct(client, app_name)
        if tokens:
            return tokens
        return await self._fetch_search(client, app_name)

    async def _fetch_direct(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            # Fetch the package source overview page.
            source_name = quote(app_name, safe="")
            url = f"https://packages.fedoraproject.org/pkgs/{source_name}/"
            response = await client.get(url, headers=self.headers)
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "html.parser")
            pkg_detail_url = None

            # Find the exact subpackage in the list.
            for li in soup.select("ul li"):
                bold = li.find("b")
                if bold:
                    pkg_name = bold.get_text().strip()
                    if self.is_relevant(app_name, pkg_name):
                        # Build the detail URL for the matched package.
                        pkg_detail_url = (
                            "https://packages.fedoraproject.org/pkgs/"
                            f"{source_name}/{quote(pkg_name, safe='')}/"
                        )
                        break
            
            # Fall back to the predictable package URL when no list is available.
            if not pkg_detail_url:
                pkg_detail_url = (
                    "https://packages.fedoraproject.org/pkgs/"
                    f"{source_name}/{source_name}/"
                )

            # Fetch the detail page containing the long description.
            detail_response = await client.get(pkg_detail_url, headers=self.headers)
            if detail_response.status_code == 200:
                return self._parse_description(detail_response.text)

            return []
        except Exception as exc:
            self.log_failure("fetch direct package", exc)
            return []

    async def _fetch_search(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            response = await client.get(
                "https://packages.fedoraproject.org/search/",
                params={"term": app_name},
                headers=self.headers,
            )
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "html.parser")
            results = soup.select("a.package-name, td a[href*='/pkgs/']")
            for result in results:
                pkg_name = result.text.strip()
                if self.is_relevant(app_name, pkg_name):
                    return await self._fetch_direct(client, pkg_name)

            return []
        except Exception as exc:
            self.log_failure("fetch package search", exc)
            return []

    def _parse_description(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        tokens = []

        # Extract the long description from paragraphs.
        for p in soup.select("p"):
            text = p.get_text(separator=" ", strip=True)
            
            # Ignore very short text and generic Fedora interface copy.
            if len(text) > 30 and "You can contact the maintainers" not in text and "File a new bug report" not in text:
                tokens.append(text)
                break # Stop after the main description block.
                
        return [t for t in tokens if t.strip()]
