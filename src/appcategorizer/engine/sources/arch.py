# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import httpx
from urllib.parse import quote
from .base import BaseSource

class ArchSource(BaseSource):
    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        tokens = await self._fetch_official(client, app_name)
        if tokens:
            return tokens
        # Fall back to the AUR when official repositories have no match.
        return await self._fetch_aur(client, app_name)

    async def _fetch_official(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            response = await client.get(
                "https://archlinux.org/packages/search/json/",
                params={"q": app_name},
                headers=self.headers,
            )
            if response.status_code != 200:
                return []

            results = response.json().get("results", [])
            if not results:
                return []

            # Prefer an exact name match, otherwise use the first result.
            exact = next((r for r in results if r.get("pkgname", "").lower() == app_name.lower()), None)
            pkg = exact or results[0]

            if not exact and not self.is_relevant(app_name, pkg.get("pkgname", "")):
                return []

            tokens = []
            tokens.append(pkg.get("pkgdesc", ""))

            # groups often contain useful hints such as "gnome", "kde-applications", or "multimedia".
            for group in pkg.get("groups", []):
                tokens.append(group)

            return [t for t in tokens if t.strip()]

        except Exception as exc:
            self.log_failure("fetch official package", exc)
            return []

    async def _fetch_aur(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            response = await client.get(
                f"https://aur.archlinux.org/rpc/v5/search/{quote(app_name, safe='')}",
                params={"by": "name"},
                headers=self.headers,
            )
            if response.status_code != 200:
                return []

            data = response.json()
            results = data.get("results", [])
            if not results:
                return []

            exact = next((r for r in results if r.get("Name", "").lower() == app_name.lower()), None)
            pkg = exact or results[0]

            if not self.is_relevant(app_name, pkg.get("Name", "")):
                return []

            tokens = []
            tokens.append(pkg.get("Description", ""))
            tokens.extend(pkg.get("Keywords", []))

            return [t for t in tokens if t.strip()]

        except Exception as exc:
            self.log_failure("fetch AUR package", exc)
            return []
